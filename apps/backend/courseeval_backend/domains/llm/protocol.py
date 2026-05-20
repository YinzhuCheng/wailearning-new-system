from __future__ import annotations

import json
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from apps.backend.courseeval_backend.db.models import Homework
from apps.backend.courseeval_backend.domains.llm.errors import RetryableLLMError

RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
NON_RETRYABLE_STATUS_CODES = {401, 403}


def build_chat_completion_url(base_url: str) -> str:
    normalized = base_url.rstrip("/") + "/"
    if normalized.endswith("/chat/completions/"):
        return normalized[:-1]
    return urljoin(normalized, "chat/completions")


def redact_endpoint_host(url: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}/.../chat/completions"
    except Exception:
        pass
    return "(endpoint URL redacted)"


def extract_message_content(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text") or "")
        return "\n".join(part for part in parts if part)
    return ""


def strip_markdown_fence(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            body = "\n".join(lines[1:-1]).strip()
            return body
    return stripped


def extract_first_json_object(text: str) -> Optional[str]:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def parse_scoring_json(raw_text: str, homework: Homework) -> dict[str, Any]:
    text = strip_markdown_fence(raw_text)
    payload_text = text
    try:
        payload = json.loads(payload_text)
    except ValueError:
        payload_text = extract_first_json_object(text or "") or ""
        if not payload_text:
            raise RetryableLLMError("Model did not return a JSON object.")
        try:
            payload = json.loads(payload_text)
        except ValueError as exc:
            raise RetryableLLMError("Model JSON output could not be parsed.") from exc
    if not isinstance(payload, dict):
        raise RetryableLLMError("Model JSON root is not an object.")
    if "score" not in payload or "comment" not in payload:
        raise RetryableLLMError("Model JSON is missing score/comment fields.")
    try:
        score = float(payload["score"])
    except (TypeError, ValueError) as exc:
        raise RetryableLLMError("Model score is not a valid number.") from exc
    if score < 0 or score > float(homework.max_score or 100):
        raise RetryableLLMError("Model score is outside the allowed range.")
    comment = payload.get("comment")
    if comment is None:
        comment = ""
    if not isinstance(comment, str):
        comment = str(comment)
    return {"score": score, "comment": comment}

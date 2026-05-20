"""Normalize optional Markdown vs plain-text flags for API + ORM."""

from __future__ import annotations

from typing import Literal, Optional

ContentFormat = Literal["markdown", "plain"]


def normalize_content_format(value: Optional[str], *, default: ContentFormat = "markdown") -> ContentFormat:
    """Maps legacy / unknown values to markdown or plain."""
    v = (value or "").strip().lower()
    if v == "plain":
        return "plain"
    return default


def body_text_for_grading_llm(*, content: Optional[str], content_format: Optional[str]) -> str:
    """When student chose plain text, fence for the model so # / * etc. are not parsed as Markdown."""
    raw = (content or "").strip()
    if not raw:
        return ""
    if normalize_content_format(content_format) != "plain":
        return raw
    inner = raw.replace("```", "``\u200b`")
    return f"```text\n{inner}\n```"

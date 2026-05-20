"""Expand Markdown image references to data URLs for LLM multimodal prompts."""

from __future__ import annotations

import ipaddress
import re
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from apps.backend.courseeval_backend.attachments import get_attachment_file_path

_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(\s*([^)]+?)\s*\)")
_DATA_URL_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\((data:image/[^;]+;base64,[A-Za-z0-9+/=]+)\)")


def _strip_url_and_title(inner: str) -> str:
    s = (inner or "").strip()
    if not s:
        return ""
    if s[0] in "\"'":
        return ""
    for i, ch in enumerate(s):
        if ch.isspace():
            return s[:i].strip()
    return s


def _host_is_blocked(hostname: str) -> bool:
    h = (hostname or "").strip().lower()
    if not h:
        return True
    if h in ("localhost", "metadata.google.internal"):
        return True
    if h.endswith(".local") or h.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(h)
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)
    except ValueError:
        pass
    # Block obvious private IPv4 literal prefixes in hostname position (unusual)
    blocked_prefixes = (
        "10.",
        "192.168.",
        "172.16.",
        "172.17.",
        "172.18.",
        "172.19.",
        "172.20.",
        "172.21.",
        "172.22.",
        "172.23.",
        "172.24.",
        "172.25.",
        "172.26.",
        "172.27.",
        "172.28.",
        "172.29.",
        "172.30.",
        "172.31.",
        "127.",
        "0.",
        "169.254.",
    )
    return any(h.startswith(p) for p in blocked_prefixes)


def _load_local_attachment_as_data_url(raw_url: str) -> Optional[str]:
    path = (urlparse(raw_url).path or raw_url).replace("\\", "/")
    if "/api/files/download/" not in path and "/files/download/" not in path:
        return None
    stored = get_attachment_file_path(raw_url)
    if not stored or not stored.is_file():
        return None
    data = stored.read_bytes()
    if not data or len(data) > 20 * 1024 * 1024:
        return None
    from apps.backend.courseeval_backend.llm_grading import build_png_data_url_from_image_bytes

    return build_png_data_url_from_image_bytes(data)


def _fetch_http_image_as_data_url(url: str, *, timeout: float) -> Optional[str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    if _host_is_blocked(parsed.hostname or ""):
        return None
    headers = {"User-Agent": "ClassroomLLMImageFetcher/1.0"}
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        r = client.get(url, headers=headers)
        r.raise_for_status()
        data = r.content
    if not data or len(data) > 20 * 1024 * 1024:
        return None
    from apps.backend.courseeval_backend.llm_grading import build_png_data_url_from_image_bytes

    return build_png_data_url_from_image_bytes(data)


def expand_markdown_images_for_llm(
    markdown_text: Optional[str],
    *,
    timeout: float = 25.0,
    max_images: int = 32,
) -> str:
    """
    Replace http(s) and same-origin attachment image URLs in Markdown with
    data:image/png;base64,... for vision models. Leaves data: URLs unchanged.
    On failure, keeps the original image markdown.
    """
    if not markdown_text:
        return markdown_text or ""

    out: list[str] = []
    pos = 0
    replaced = 0
    for m in _MD_IMAGE_RE.finditer(markdown_text):
        out.append(markdown_text[pos : m.start()])
        pos = m.end()
        alt = m.group(1) or ""
        url = _strip_url_and_title(m.group(2))
        full = m.group(0)
        if not url or replaced >= max_images:
            out.append(full)
            continue
        if url.startswith("data:image/") and "base64," in url:
            out.append(full)
            continue
        new_url: Optional[str] = None
        try:
            if url.startswith("http://") or url.startswith("https://"):
                new_url = _fetch_http_image_as_data_url(url, timeout=timeout)
            else:
                new_url = _load_local_attachment_as_data_url(url)
        except Exception:
            new_url = None
        if new_url:
            replaced += 1
            out.append(f"![{alt}]({new_url})")
        else:
            out.append(full)
    out.append(markdown_text[pos:])
    return "".join(out)


def append_markdown_with_dataurl_images_to_parts(
    user_parts: list[dict[str, Any]],
    markdown_text: str,
) -> None:
    """
    Split markdown that may contain ![alt](data:image/...;base64,...) into
    alternating text and image_url parts for multimodal chat APIs.
    """
    text = markdown_text or ""
    if not text:
        return
    pos = 0
    found = False
    for m in _DATA_URL_MD_IMAGE_RE.finditer(text):
        found = True
        pre = text[pos : m.start()]
        if pre:
            user_parts.append({"type": "text", "text": pre})
        cap = f"[INSTRUCTOR_MD_IMAGE alt={m.group(1)!r}]"
        user_parts.append({"type": "text", "text": cap})
        user_parts.append({"type": "image_url", "image_url": {"url": m.group(2)}})
        pos = m.end()
    tail = text[pos:]
    if tail:
        user_parts.append({"type": "text", "text": tail})
    elif not found and text.strip():
        user_parts.append({"type": "text", "text": text})

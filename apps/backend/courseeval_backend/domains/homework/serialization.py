"""Pure serialization helpers shared by homework HTTP serializers."""

from __future__ import annotations

from typing import Any, Optional


def task_call_log(task: Any) -> Optional[list]:
    if not task or not isinstance(getattr(task, "artifact_manifest", None), dict):
        return None
    log = task.artifact_manifest.get("llm_call_log")
    return log if isinstance(log, list) else None


def preview_text(value: Optional[str], limit: int = 180) -> Optional[str]:
    if not value or not str(value).strip():
        return None
    text = str(value).strip().replace("\r\n", "\n").replace("\r", "\n")
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"

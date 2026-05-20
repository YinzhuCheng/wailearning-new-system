from __future__ import annotations

import re

_LLM_FIRST_LINE = re.compile(r"^\s*@LLM\s*\n?", re.IGNORECASE)


def strip_llm_ui_prefix(body: str) -> str:
    """Remove the leading @LLM line inserted by the UI."""
    return _LLM_FIRST_LINE.sub("", body or "", count=1).strip()

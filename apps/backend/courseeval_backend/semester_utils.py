from __future__ import annotations

import re

DEFAULT_SEMESTERS = (
    {"name": "2024-\u6625\u5b63", "year": 2024},
    {"name": "2024-\u79cb\u5b63", "year": 2024},
    {"name": "2025-\u6625\u5b63", "year": 2025},
    {"name": "2025-\u79cb\u5b63", "year": 2025},
    {"name": "2026-\u6625\u5b63", "year": 2026},
    {"name": "2026-\u79cb\u5b63", "year": 2026},
)


def normalize_semester_name(name: str | None) -> str | None:
    if not name:
        return name

    normalized = name.strip()
    match = re.fullmatch(r"(\d{4})-(1|2)", normalized)
    if not match:
        return normalized

    year, term = match.groups()
    return f"{year}-\u6625\u5b63" if term == "1" else f"{year}-\u79cb\u5b63"

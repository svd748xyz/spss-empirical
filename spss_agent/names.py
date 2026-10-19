"""SPSS variable-name checks and light sanitizing."""

from __future__ import annotations

import re

_INVALID = re.compile(r"[^\w@#$.]", re.UNICODE)


def is_spss_name(name: str) -> bool:
    if not name or name[0].isdigit():
        return False
    if len(name.encode("utf-8")) > 64:
        return False
    return _INVALID.search(name) is None


def sanitize(name: str, used: set[str], index: int) -> str:
    cleaned = _INVALID.sub("_", name.strip()) or f"v{index}"
    if cleaned[0].isdigit():
        cleaned = f"v_{cleaned}"
    raw = cleaned.encode("utf-8")
    if len(raw) > 64:
        cleaned = raw[:64].decode("utf-8", errors="ignore") or f"v{index}"
    base = cleaned
    n = 2
    while cleaned in used:
        suffix = f"_{n}"
        cleaned = (base[: 64 - len(suffix)] + suffix)
        n += 1
    used.add(cleaned)
    return cleaned

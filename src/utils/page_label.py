from __future__ import annotations

import re


PAGE_PATTERNS = (
    re.compile(r"^(?:page|p\.?)\s*[-:]?\s*(\d{1,4})$", re.IGNORECASE),
    re.compile(r"^페이지\s*(\d{1,4})$"),
    re.compile(r"^[-–—]\s*(\d{1,4})\s*[-–—]$"),
    re.compile(r"^(\d{1,4})\s*/\s*\d{1,4}$"),
    re.compile(r"^([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[IVXLCDM]+)\s*[-–—]\s*(\d{1,4})$", re.IGNORECASE),
    re.compile(r"^(\d{1,4})$"),
)


def extract_display_page_label(text: str, fallback: int | str = "") -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    candidates = lines[-12:] + lines[:4]
    for line in reversed(candidates):
        normalized = _normalize_line(line)
        if not normalized or len(normalized) > 30:
            continue
        label = _match_label(normalized)
        if label:
            return label
    return str(fallback) if fallback else ""


def _normalize_line(line: str) -> str:
    line = line.replace("\u0001", " ")
    line = re.sub(r"\s+", " ", line).strip()
    return line


def _match_label(line: str) -> str:
    for pattern in PAGE_PATTERNS:
        match = pattern.match(line)
        if not match:
            continue
        if len(match.groups()) == 2:
            return f"{match.group(1)}-{match.group(2)}"
        value = match.group(1)
        if value.isdigit() and int(value) == 0:
            return ""
        return value
    return ""

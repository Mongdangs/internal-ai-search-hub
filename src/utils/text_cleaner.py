from __future__ import annotations

import re


SPACE_RE = re.compile(r"[ \t]+")
LINE_RE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line)
    return LINE_RE.sub("\n\n", text).strip()


def trim_snippet(text: str, limit: int = 500) -> str:
    text = clean_text(text).replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."

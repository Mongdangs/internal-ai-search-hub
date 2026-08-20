from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

from src.utils.korean_tokenizer import tokenize


VERSION_RE = re.compile(
    r"(?i)(?:rev\.?\s*\d+(?:[._-]\d+)*|v(?:er(?:sion)?)?\.?\s*\d+(?:[._-]\d+)*|최종|완료|수정|사본|copy|final)"
)
DATE_RE = re.compile(r"(?:20\d{2}[._ -]?\d{2}[._ -]?\d{2}|20\d{6}|\d{6,8})")
NUMBER_RE = re.compile(r"\b\d+(?:[._-]\d+)*\b")
PUNCT_RE = re.compile(r"[\s._\-()[\]{}]+")


@dataclass(frozen=True)
class DocumentProfile:
    document_id: str
    project_id: str
    canonical_key: str
    content_signature: str
    file_mtime: float


def canonical_document_key(path: str | Path, root: str | Path | None = None) -> str:
    file_path = Path(path)
    project_key = ""
    if root:
        try:
            relative = file_path.resolve().relative_to(Path(root).resolve())
            project_key = _normalize_part(relative.parts[0]) if relative.parts else ""
        except ValueError:
            project_key = ""
    stem = _normalize_part(file_path.stem)
    stem = VERSION_RE.sub(" ", stem)
    stem = DATE_RE.sub(" ", stem)
    stem = NUMBER_RE.sub(" ", stem)
    stem = PUNCT_RE.sub(" ", stem)
    tokens = [token for token in tokenize(stem) if token not in {"보고서", "제안서", "최종", "수정", "사본"}]
    normalized_stem = " ".join(tokens) or _normalize_part(file_path.stem)
    return f"{project_key}:{normalized_stem}".strip(":")


def select_latest_versions(files: list[Path], root: str | Path) -> list[Path]:
    latest: dict[str, Path] = {}
    for path in files:
        key = canonical_document_key(path, root)
        current = latest.get(key)
        if current is None or file_mtime(path) > file_mtime(current):
            latest[key] = path
    return sorted(latest.values(), key=lambda item: (-file_mtime(item), str(item).lower()))


def newest_first(files: list[Path]) -> list[Path]:
    return sorted(files, key=lambda item: (-file_mtime(item), str(item).lower()))


def document_signature(text: str, max_items: int = 2000) -> str:
    tokens = tokenize(text)
    if len(tokens) < 5:
        values = {_hash(token) for token in tokens}
    else:
        values = {_hash(" ".join(tokens[index : index + 5])) for index in range(0, len(tokens) - 4)}
    return " ".join(sorted(values)[:max_items])


def content_similarity(left: str, right: str) -> float:
    left_set = set(left.split())
    right_set = set(right.split())
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def file_mtime(path: str | Path) -> float:
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0.0


def _normalize_part(text: str) -> str:
    return PUNCT_RE.sub(" ", text.lower()).strip()


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]

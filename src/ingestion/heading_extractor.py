from __future__ import annotations

from dataclasses import dataclass, replace
import re

from src.models import ParsedUnit
from src.utils.text_cleaner import clean_text


CHAPTER_SYNONYMS: dict[str, tuple[str, ...]] = {
    "현황분석": ("현황분석", "현황 분석", "As-Is", "ASIS", "업무현황", "시스템 현황", "환경분석", "환경 분석"),
    "기술동향분석": ("기술동향분석", "기술 동향", "기술동향", "동향분석", "Technology Trend", "최신기술동향"),
    "목표모델": (
        "목표모델",
        "목표 모델",
        "To-Be",
        "TOBE",
        "미래모델",
        "개선모델",
        "목표 아키텍처",
        "목표아키텍처",
        "목표 아키텍쳐",
        "목표아키텍쳐",
    ),
    "요구사항분석": ("요구사항분석", "요구사항 분석", "요구사항", "Requirement", "Requirements"),
    "이행계획": ("이행계획", "이행 계획", "추진계획", "로드맵", "Roadmap", "실행계획", "전환계획"),
}

DEFAULT_CHAPTER_TITLE = "기타"
STATIC_CHAPTERS = (*tuple(CHAPTER_SYNONYMS), DEFAULT_CHAPTER_TITLE)
ROMAN_CHARS = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫIVXLCDM"
HEADING_PREFIX_RE = re.compile(
    rf"^\s*(?P<prefix>(?:[제第]\s*\d+\s*장|chapter\s*\d+|[{ROMAN_CHARS}]+|\d+(?:\.\d+)*))\s*[.)．:]?\s*(?P<title>.+)$",
    re.IGNORECASE,
)
SECTION_NUMBER_RE = re.compile(r"^\s*\d+(?:\.\d+)+\s*[.)．:]?\s*")
ROMAN_PREFIX_RE = re.compile(rf"^\s*(?:[{ROMAN_CHARS}]+)\s*[.)．:]?\s*", re.IGNORECASE)
CHAPTER_PREFIX_RE = re.compile(r"^\s*(?:[제第]\s*\d+\s*장|chapter\s*\d+)\s*[.)．:]?\s*", re.IGNORECASE)
NUMBER_PREFIX_RE = re.compile(r"^\s*\d+(?:\.\d+)*\s*[.)．:]?\s*")
PUNCT_RE = re.compile(r"[^0-9a-zA-Z가-힣]+")
SENTENCE_MARKERS = ("한다", "한다.", "하여", "하고", "위해", "통해", "확보", "도출", "제시", "정의")


@dataclass(frozen=True)
class HeadingCandidate:
    title: str
    level: int
    canonical: str = ""


def enrich_units_with_headings(units: list[ParsedUnit]) -> list[ParsedUnit]:
    enriched: list[ParsedUnit] = []
    current_chapter = DEFAULT_CHAPTER_TITLE
    current_section = ""

    for unit in units:
        for heading in _heading_candidates(unit):
            if heading.canonical:
                if current_chapter == heading.canonical and not _same_as_canonical(heading.title, heading.canonical):
                    current_section = heading.title
                else:
                    current_chapter = heading.canonical
                    current_section = "" if _same_as_canonical(heading.title, heading.canonical) else heading.title
            elif _is_document_level_unknown(heading.title):
                current_chapter = DEFAULT_CHAPTER_TITLE
                current_section = heading.title
            elif heading.level >= 1:
                current_section = heading.title

        section_title = unit.section_title
        if not section_title or section_title == current_chapter:
            section_title = current_section
        heading_path = build_heading_path(current_chapter, section_title)
        enriched.append(
            replace(
                unit,
                chapter_title=current_chapter,
                section_title=section_title,
                heading_path=heading_path,
            )
        )
    return enriched


def build_heading_path(chapter_title: str, section_title: str = "") -> str:
    parts = [part.strip() for part in (chapter_title, section_title) if part and part.strip()]
    return " > ".join(dict.fromkeys(parts))


def heading_search_norm(chapter_title: str, section_title: str = "", heading_path: str = "") -> str:
    values = [chapter_title, section_title, heading_path]
    norms: list[str] = []
    for value in values:
        if not value:
            continue
        normalized = normalize_chapter_name(value)
        if normalized:
            norms.append(normalized)
        canonical = canonical_chapter(value)
        if canonical:
            norms.extend(chapter_filter_norms(canonical))
    return " ".join(_unique(norms))


def normalize_chapter_name(text: str) -> str:
    text = (text or "").strip().lower()
    text = CHAPTER_PREFIX_RE.sub("", text)
    text = ROMAN_PREFIX_RE.sub("", text)
    text = NUMBER_PREFIX_RE.sub("", text)
    text = re.sub(r"\bchapter\b", "", text, flags=re.IGNORECASE)
    for suffix in ("챕터", "chapter", "장", "절"):
        text = text.replace(suffix, "")
    return PUNCT_RE.sub("", text)


def normalize_heading(text: str) -> str:
    return normalize_chapter_name(text)


def canonical_chapter(text: str) -> str:
    if (text or "").strip() == DEFAULT_CHAPTER_TITLE:
        return DEFAULT_CHAPTER_TITLE
    normalized = normalize_chapter_name(text)
    compact_original = _compact_for_alias(text)
    for canonical, aliases in CHAPTER_SYNONYMS.items():
        alias_norms = {normalize_chapter_name(alias) for alias in aliases}
        alias_compacts = {_compact_for_alias(alias) for alias in aliases}
        if normalized in alias_norms or any(alias and alias in normalized for alias in alias_norms):
            return canonical
        if compact_original in alias_compacts or any(alias and alias in compact_original for alias in alias_compacts):
            return canonical
    return ""


def chapter_filter_norms(chapter_filter: str) -> list[str]:
    canonical = canonical_chapter(chapter_filter) or chapter_filter
    aliases = CHAPTER_SYNONYMS.get(canonical, (canonical,))
    norms = [normalize_chapter_name(canonical), *[normalize_chapter_name(alias) for alias in aliases]]
    return [norm for norm in _unique(norms) if norm]


def _heading_candidates(unit: ParsedUnit) -> list[HeadingCandidate]:
    texts = []
    if unit.section_title:
        texts.append(unit.section_title)
    texts.extend((unit.text or "").splitlines()[:16])

    candidates: list[HeadingCandidate] = []
    for line in texts:
        heading = detect_heading(line)
        if heading:
            candidates.append(heading)
    return candidates


def detect_heading(line: str) -> HeadingCandidate | None:
    text = clean_text(line).replace("\n", " ").strip()
    if not text:
        return None
    match = HEADING_PREFIX_RE.match(text)
    canonical = canonical_chapter(text)
    if match:
        prefix = match.group("prefix") or ""
        title = _clean_heading_title(text)
        level = _heading_level(prefix)
        if _looks_like_heading(title, has_prefix=True, canonical=canonical):
            return HeadingCandidate(title=title, level=level, canonical=canonical)
    if canonical and _looks_like_heading(text, has_prefix=False, canonical=canonical):
        return HeadingCandidate(title=_clean_heading_title(text), level=1, canonical=canonical)
    return None


def _is_chapter_heading(heading: HeadingCandidate) -> bool:
    return bool(heading.canonical) or heading.level <= 1


def _same_as_canonical(title: str, canonical: str) -> bool:
    title_norm = normalize_chapter_name(title)
    canonical_norm = normalize_chapter_name(canonical)
    if not title_norm or not canonical_norm:
        return False
    return title_norm == canonical_norm or title_norm in {f"{canonical_norm}수립", f"{canonical_norm}설계"}


def _is_document_level_unknown(title: str) -> bool:
    return bool(CHAPTER_PREFIX_RE.match(title) or ROMAN_PREFIX_RE.match(title))


def _heading_level(prefix: str) -> int:
    prefix = (prefix or "").strip().lower()
    if SECTION_NUMBER_RE.match(prefix):
        return prefix.count(".") + 1
    if re.match(r"^\d", prefix):
        return 1
    return 1


def _clean_heading_title(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" .\t")


def _looks_like_heading(title: str, has_prefix: bool, canonical: str = "") -> bool:
    compact = title.replace(" ", "")
    if len(compact) < 3:
        return False
    if len(title) > 90 and not canonical:
        return False
    if canonical:
        return True
    if not has_prefix:
        return False
    if len(title) <= 45:
        return True
    return not any(marker in title for marker in SENTENCE_MARKERS)


def _compact_for_alias(text: str) -> str:
    return PUNCT_RE.sub("", (text or "").lower())


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen

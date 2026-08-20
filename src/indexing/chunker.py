from __future__ import annotations

import re

from src.domain.domain_dictionary import domain_keywords_for_text
from src.domain.heading_taxonomy import classify_heading_hierarchy
from src.ingestion.metadata_extractor import stable_id
from src.ingestion.heading_extractor import (
    DEFAULT_CHAPTER_TITLE,
    build_heading_path,
    canonical_chapter,
    heading_search_norm,
    normalize_heading,
)
from src.indexing.design_keywords import target_model_design_keywords
from src.indexing.index_metadata import INDEX_VERSION
from src.models import Chunk, DocumentMetadata, ParsedUnit, ProjectMetadata
from src.utils.korean_tokenizer import tokenize
from src.utils.text_cleaner import clean_text


class Chunker:
    def __init__(self, chunk_size: int = 1000, overlap: int = 150) -> None:
        self.chunk_size = chunk_size
        self.overlap = max(0, min(overlap, chunk_size // 2))

    def build_chunks(self, document: DocumentMetadata, units: list[ParsedUnit], project: ProjectMetadata | None = None) -> list[Chunk]:
        chunks: list[Chunk] = []
        keyword_context = " ".join([document.document_title, document.file_name, document.file_path])
        full_text = "\n".join(unit.text for unit in units)
        document_keywords = ", ".join(target_model_design_keywords(full_text, context=keyword_context))
        parent_context_by_path = _parent_contexts(units)
        for unit in units:
            raw_chapter_title = unit.chapter_title or DEFAULT_CHAPTER_TITLE
            raw_section_title = unit.section_title or ""
            raw_heading_path = unit.heading_path or build_heading_path(raw_chapter_title, raw_section_title) or raw_chapter_title
            chapter_title = _major_chapter(raw_chapter_title, unit.section_title, unit.heading_path)
            section_title = _section_title(unit.section_title, chapter_title)
            heading_path = build_heading_path(chapter_title, section_title) or raw_heading_path or chapter_title
            classification = classify_heading_hierarchy(raw_chapter_title, section_title or raw_section_title, raw_heading_path)
            canonical = classification["canonical_chapter_title"] or chapter_title
            canonical_section = classification["canonical_section_title"]
            canonical_subsection = classification["canonical_subsection_title"]
            canonical_heading_path = classification["canonical_heading_path"] or build_heading_path(canonical, canonical_section) or canonical
            normalized_fallback = normalize_heading(DEFAULT_CHAPTER_TITLE)
            normalized_chapter = normalize_heading(chapter_title) or normalized_fallback
            normalized_section = normalize_heading(section_title)
            normalized_heading = normalize_heading(heading_path) or normalized_chapter or normalized_fallback
            heading_norm = heading_search_norm(canonical, section_title, " ".join([heading_path, canonical_heading_path])) or normalized_heading
            parent_context = parent_context_by_path.get(raw_heading_path) or clean_text(unit.text[:1600])
            parent_chunk_id = stable_id(f"{document.document_id}:{raw_heading_path or heading_path}", "parent")
            table_metadata = _table_metadata(unit.text, canonical_heading_path, section_title)
            domain_keywords = ", ".join(
                domain_keywords_for_text(
                    unit.text,
                    document.document_title,
                    document.file_name,
                    canonical_heading_path,
                    section_title,
                )
            )
            for part_index, (text, char_start, char_end) in enumerate(self._split_text(unit.text), start=1):
                chunk_id = stable_id(f"{document.document_id}:{document.file_name}:{unit.page_no}:{part_index}:{text[:50]}", "chk")
                embedding_text = _embedding_text(
                    document=document,
                    project=project,
                    page_no=unit.page_no,
                    display_page=unit.display_page,
                    canonical_heading_path=canonical_heading_path,
                    raw_heading_path=raw_heading_path,
                    domain_keywords=domain_keywords,
                    parent_context=parent_context,
                    chunk_text=text,
                )
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        document_id=document.document_id,
                        project_id=document.project_id,
                        page_no=unit.page_no,
                        section_title=section_title,
                        chunk_text=text,
                        keywords=document_keywords,
                        token_count=len(tokenize(text)),
                        display_page=unit.display_page,
                        source_file=document.file_name,
                        file_type=document.file_type,
                        chunk_index=part_index,
                        index_version=INDEX_VERSION,
                        chapter_title=chapter_title,
                        canonical_chapter_title=canonical,
                        normalized_chapter_title=normalized_chapter,
                        normalized_section_title=normalized_section,
                        heading_path=heading_path,
                        normalized_heading_path=normalized_heading,
                        heading_norm=heading_norm,
                        page_range=str(unit.page_no),
                        char_start=char_start,
                        char_end=char_end,
                        raw_chapter_title=classification["raw_chapter_title"],
                        raw_section_title=classification["raw_section_title"],
                        raw_heading_path=classification["raw_heading_path"],
                        canonical_section_title=canonical_section,
                        canonical_subsection_title=canonical_subsection,
                        canonical_heading_path=canonical_heading_path,
                        heading_classification_confidence=float(classification["heading_classification_confidence"] or 0.0),
                        heading_classification_reason=classification["heading_classification_reason"],
                        table_type=table_metadata["table_type"],
                        table_title=table_metadata["table_title"],
                        table_headers=table_metadata["table_headers"],
                        table_row_text=table_metadata["table_row_text"],
                        domain_keywords=domain_keywords,
                        parent_chunk_id=parent_chunk_id,
                        parent_context=parent_context,
                        embedding_text=embedding_text,
                    )
                )
        return chunks

    def _split_text(self, text: str) -> list[tuple[str, int, int]]:
        text = clean_text(text)
        if not text:
            return []
        if _looks_like_table(text):
            return [(text, 0, len(text))]
        if len(text) <= self.chunk_size:
            return [(text, 0, len(text))]

        parts: list[tuple[str, int, int]] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + self.chunk_size)
            window = text[start:end]
            split_at = max(window.rfind("\n"), window.rfind(". "), window.rfind("다."))
            if split_at > self.chunk_size * 0.55:
                end = start + split_at + 1
            end = _avoid_regulation_split(text, start, end)
            part = clean_text(text[start:end])
            if part:
                parts.append((part, start, end))
            if end >= len(text):
                break
            start = max(0, end - self.overlap)
        return parts


REGULATION_RE = re.compile(r"[가-힣A-Za-z0-9·ㆍ\s]{2,80}(?:법률|시행령|시행규칙|고시|지침|규정|훈령|예규|조례|법)")


def _avoid_regulation_split(text: str, start: int, end: int) -> int:
    if end >= len(text):
        return end
    for match in REGULATION_RE.finditer(text, max(0, end - 90), min(len(text), end + 90)):
        if match.start() < end < match.end():
            return min(len(text), match.end())
    return end


def _section_title(section_title: str, chapter_title: str) -> str:
    section_title = clean_text(section_title or "")
    if not section_title:
        return ""
    if normalize_heading(section_title) == normalize_heading(chapter_title):
        return ""
    return section_title


def _major_chapter(chapter_title: str, section_title: str, heading_path: str) -> str:
    for value in (chapter_title, section_title, heading_path):
        canonical = canonical_chapter(value)
        if canonical and canonical != DEFAULT_CHAPTER_TITLE:
            return canonical
    return DEFAULT_CHAPTER_TITLE


def _parent_contexts(units: list[ParsedUnit]) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for unit in units:
        key = unit.heading_path or build_heading_path(unit.chapter_title, unit.section_title) or DEFAULT_CHAPTER_TITLE
        grouped.setdefault(key, []).append(unit.text)
    return {key: clean_text("\n".join(values))[:1800] for key, values in grouped.items()}


def _table_metadata(text: str, heading_path: str, section_title: str) -> dict[str, str]:
    cleaned = clean_text(text)
    if not _looks_like_table(cleaned):
        return {"table_type": "", "table_title": "", "table_headers": "", "table_row_text": ""}
    haystack = " ".join([heading_path, section_title, cleaned])
    table_type = _table_type(haystack)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    headers = lines[0] if lines else ""
    title = _table_title(lines, heading_path, section_title)
    return {
        "table_type": table_type,
        "table_title": title,
        "table_headers": headers[:400],
        "table_row_text": cleaned[:1800],
    }


def _looks_like_table(text: str) -> bool:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    tableish_lines = sum(1 for line in lines if "|" in line or "\t" in line or re.search(r"\S\s{2,}\S", line))
    header_hits = sum(1 for term in ("성명", "등급", "역할", "단가", "수량", "금액", "요구사항", "일정", "기간") if term in text)
    return tableish_lines >= 2 or header_hits >= 2


def _table_type(text: str) -> str:
    if any(term in text for term in ("성명", "등급", "역할", "참여율", "주요경력", "투입인력", "참여인력")):
        return "staff"
    if any(term in text for term in ("단가", "수량", "금액", "비용", "견적", "소요예산", "TCO")):
        return "cost"
    if any(term in text for term in ("요구사항", "요구ID", "요구 ID", "기능요건", "비기능")):
        return "requirement"
    if any(term in text for term in ("일정", "기간", "착수", "완료", "단계", "로드맵")):
        return "schedule"
    return "general"


def _table_title(lines: list[str], heading_path: str, section_title: str) -> str:
    for line in lines[:4]:
        if any(term in line for term in ("표", "Table", "목록", "내역", "현황")):
            return line[:160]
    return (section_title or heading_path).strip()[:160]


def _embedding_text(
    document: DocumentMetadata,
    project: ProjectMetadata | None,
    page_no: int,
    display_page: str,
    canonical_heading_path: str,
    raw_heading_path: str,
    domain_keywords: str,
    parent_context: str,
    chunk_text: str,
) -> str:
    values = [
        f"문서명: {document.document_title}",
        f"프로젝트명: {project.project_name if project else ''}",
        f"고객기관: {project.client_name if project else ''}",
        f"문서영역: {canonical_heading_path}",
        f"원본경로: {raw_heading_path}",
        f"페이지: {display_page or page_no}",
        f"키워드: {domain_keywords}",
        f"상위문맥: {parent_context[:700]}",
        f"본문: {chunk_text}",
    ]
    return "\n".join(value for value in values if value.split(":", 1)[-1].strip())

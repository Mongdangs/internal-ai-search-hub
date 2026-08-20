from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProjectMetadata:
    project_id: str
    project_name: str
    client_name: str = ""
    year: str = ""
    business_type: str = ""
    domain: str = ""
    folder_path: str = ""
    security_level: str = ""


@dataclass(frozen=True)
class DocumentMetadata:
    document_id: str
    project_id: str
    document_title: str
    document_type: str
    file_path: str
    file_type: str
    file_name: str
    version: str = ""
    is_final: int = 0
    access_acl: str = ""
    canonical_key: str = ""
    content_signature: str = ""
    file_mtime: float = 0.0


@dataclass(frozen=True)
class ParsedUnit:
    page_no: int
    text: str
    section_title: str = ""
    display_page: str = ""
    chapter_title: str = ""
    heading_path: str = ""


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    project_id: str
    page_no: int
    section_title: str
    chunk_text: str
    keywords: str
    token_count: int
    embedding_id: str = ""
    display_page: str = ""
    source_file: str = ""
    file_type: str = ""
    chunk_index: int = 0
    index_version: str = ""
    chapter_title: str = ""
    heading_path: str = ""
    heading_norm: str = ""
    canonical_chapter_title: str = ""
    normalized_chapter_title: str = ""
    normalized_section_title: str = ""
    normalized_heading_path: str = ""
    page_range: str = ""
    char_start: int = 0
    char_end: int = 0
    raw_chapter_title: str = ""
    raw_section_title: str = ""
    raw_heading_path: str = ""
    canonical_section_title: str = ""
    canonical_subsection_title: str = ""
    canonical_heading_path: str = ""
    heading_classification_confidence: float = 0.0
    heading_classification_reason: str = ""
    table_type: str = ""
    table_title: str = ""
    table_headers: str = ""
    table_row_text: str = ""
    domain_keywords: str = ""
    parent_chunk_id: str = ""
    parent_context: str = ""
    embedding_text: str = ""


@dataclass
class SearchResult:
    chunk_id: str
    document_id: str
    project_id: str
    project_name: str
    client_name: str
    document_title: str
    document_type: str
    file_path: str
    page_no: int
    display_page: str
    matched_text: str
    score: float
    keyword_score: float = 0.0
    vector_score: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    keyword_coverage: float = 0.0
    document_keywords: list[str] = field(default_factory=list)
    source_file: str = ""
    chapter_title: str = ""
    section_title: str = ""
    heading_path: str = ""
    canonical_chapter_title: str = ""
    canonical_section_title: str = ""
    canonical_subsection_title: str = ""
    canonical_heading_path: str = ""
    raw_heading_path: str = ""
    normalized_chapter_title: str = ""
    normalized_section_title: str = ""
    normalized_heading_path: str = ""
    table_type: str = ""
    domain_keywords: str = ""
    parent_context: str = ""
    heading_classification_confidence: float = 0.0
    page_range: str = ""
    chunk_index: int = 0
    index_version: str = ""

    def to_dict(self, rank: int | None = None) -> dict:
        data = {
            "project_name": self.project_name,
            "client_name": self.client_name,
            "document_title": self.document_title,
            "document_type": self.document_type,
            "file_path": self.file_path,
            "page_no": self.page_no,
            "display_page": self.display_page,
            "matched_text": self.matched_text,
            "score": self.score,
            "keyword_score": self.keyword_score,
            "vector_score": self.vector_score,
            "matched_keywords": self.matched_keywords,
            "missing_keywords": self.missing_keywords,
            "keyword_coverage": self.keyword_coverage,
            "document_keywords": self.document_keywords,
            "source_file": self.source_file,
            "chapter_title": self.chapter_title,
            "section_title": self.section_title,
            "heading_path": self.heading_path,
            "canonical_chapter_title": self.canonical_chapter_title,
            "canonical_section_title": self.canonical_section_title,
            "canonical_subsection_title": self.canonical_subsection_title,
            "canonical_heading_path": self.canonical_heading_path,
            "raw_heading_path": self.raw_heading_path,
            "normalized_chapter_title": self.normalized_chapter_title,
            "normalized_section_title": self.normalized_section_title,
            "normalized_heading_path": self.normalized_heading_path,
            "table_type": self.table_type,
            "domain_keywords": self.domain_keywords,
            "parent_context": self.parent_context,
            "heading_classification_confidence": self.heading_classification_confidence,
            "page_range": self.page_range,
            "chunk_index": self.chunk_index,
            "index_version": self.index_version,
        }
        if rank is not None:
            data["rank"] = rank
        return data


@dataclass(frozen=True)
class IndexSummary:
    project_count: int
    document_count: int
    chunk_count: int
    unsupported_files: list[str]
    backup_path: str = ""
    report_path: str = ""
    index_version: str = ""
    chapters: list[dict] = field(default_factory=list)
    validation: dict = field(default_factory=dict)
    failed_documents: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class RfpSearchResponse:
    summary: dict
    similar_projects: list[dict]
    results: list[SearchResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rfp_summary": self.summary,
            "similar_projects": self.similar_projects,
            "results": [result.to_dict() for result in self.results],
        }

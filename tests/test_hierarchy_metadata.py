from pathlib import Path

from src.db.database import Database
from src.db.repositories import SearchRepository
from src.domain.heading_taxonomy import canonicalize_heading, classify_heading_hierarchy, normalize_heading_text
from src.indexing.chunker import Chunker
from src.models import DocumentMetadata, ParsedUnit, ProjectMetadata


def test_heading_taxonomy_classifies_nested_aliases():
    assert normalize_heading_text("Ⅲ. 목표 아키텍처 수립") == "목표아키텍처수립"

    match = canonicalize_heading("To-Be 인프라 구성", {"목표모델": ["To-Be", "목표 아키텍처"]})

    assert match["canonical"] == "목표모델"
    assert match["confidence"] >= 0.72

    classified = classify_heading_hierarchy(
        "Ⅲ. 목표 아키텍처 수립",
        "3.1 인프라 구성 방안",
        "Ⅲ. 목표 아키텍처 수립 > 3.1 인프라 구성 방안 > 3.1.2 원격지 재해복구센터 구축",
    )

    assert classified["canonical_chapter_title"] == "목표모델"
    assert classified["canonical_section_title"] == "인프라 아키텍처"
    assert classified["canonical_subsection_title"] == "DR/백업/이중화"


def test_chunker_persists_hierarchy_embedding_and_repository_roundtrip(tmp_path):
    db = Database(tmp_path / "db" / "search.sqlite3")
    db.initialize()
    repository = SearchRepository(db)
    project = ProjectMetadata("prj", "한국공항공사 ISP", "한국공항공사")
    document = DocumentMetadata("doc", "prj", "목표모델 보고서", "보고서", "H:/report.pdf", "pdf", "report.pdf")
    units = [
        ParsedUnit(
            page_no=42,
            text="성명  등급  역할\n홍길동  특급  PM\n재해복구 RTO RPO 이중화 방안을 제시한다.",
            section_title="3.1 인프라 구성 방안",
            display_page="42",
            chapter_title="Ⅲ. 목표 아키텍처",
            heading_path="Ⅲ. 목표 아키텍처 > 3.1 인프라 구성 방안 > DR센터 구축",
        )
    ]

    chunks = Chunker().build_chunks(document, units, project)
    repository.upsert_project(project)
    repository.upsert_document(document)
    repository.replace_chunks(document, project, chunks)
    rows = repository.get_chunks_by_ids([chunks[0].chunk_id])
    result = repository.make_search_result(rows[chunks[0].chunk_id], 1.0, 1.0, 0.0, "DR PM")

    assert chunks[0].canonical_heading_path
    assert chunks[0].embedding_text.startswith("문서명:")
    assert chunks[0].table_type == "staff"
    assert result.canonical_heading_path == chunks[0].canonical_heading_path
    assert result.domain_keywords

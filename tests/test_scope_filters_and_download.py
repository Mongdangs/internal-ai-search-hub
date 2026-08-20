from pathlib import Path

import pytest

from src.config import AppConfig, EmbeddingConfig, IndexingConfig, SearchConfig, SecurityConfig, UiConfig
from src.db.database import Database
from src.db.repositories import SearchRepository
from src.models import Chunk, DocumentMetadata, ProjectMetadata
from src.search.search_service import SearchService
from src.services.download_service import DownloadAuditLogger, DownloadRegistry, RootFolderDownloadAuthorizer


def test_source_scope_prefixes_filter_repository_queries(tmp_path):
    config = AppConfig(
        root_folders=("H:/01.제안서", "H:/02.사업수행"),
        data_dir=tmp_path,
        indexing=IndexingConfig(),
        search=SearchConfig(top_k=10),
        embedding=EmbeddingConfig(provider="hashing", dimensions=64),
        security=SecurityConfig(),
        ui=UiConfig(),
    )
    db = Database(config.database_path)
    db.initialize()
    repo = SearchRepository(db)
    service = SearchService(config, repo)

    project = ProjectMetadata(project_id="prj", project_name="검색 테스트")
    docs = [
        DocumentMetadata("proposal", "prj", "제안서", "제안서", "H:/01.제안서/a/proposal.pdf", "pdf", "proposal.pdf"),
        DocumentMetadata("report", "prj", "보고서", "보고서", "H:/02.사업수행/b/report.pdf", "pdf", "report.pdf"),
        DocumentMetadata("outside", "prj", "외부", "기타", "H:/99.외부/outside.pdf", "pdf", "outside.pdf"),
    ]
    chunks = [
        Chunk("proposal_chunk", "proposal", "prj", 1, "", "데이터 이관 계획", "데이터 이관", 3),
        Chunk("report_chunk", "report", "prj", 1, "", "데이터 이관 계획", "데이터 이관", 3),
        Chunk("outside_chunk", "outside", "prj", 1, "", "데이터 이관 계획", "데이터 이관", 3),
    ]

    repo.upsert_project(project)
    for doc, chunk in zip(docs, chunks):
        repo.upsert_document(doc)
        repo.replace_chunks(doc, project, [chunk])
    service.vector_index.upsert_chunks(chunks)

    all_scoped = service.search(
        "데이터 이관",
        filters={"source_scope": "all", "proposal_prefixes": ["H:/01.제안서"], "report_prefixes": ["H:/02.사업수행"]},
    )
    proposal_scoped = service.search(
        "데이터 이관",
        filters={"source_scope": "proposal", "proposal_prefixes": ["H:/01.제안서"]},
    )
    report_scoped = service.search(
        "데이터 이관",
        filters={"source_scope": "report", "report_prefixes": ["H:/02.사업수행"]},
    )

    assert {result.document_id for result in all_scoped} == {"proposal", "report"}
    assert {result.document_id for result in proposal_scoped} == {"proposal"}
    assert {result.document_id for result in report_scoped} == {"report"}


def test_download_registry_validates_root_expires_token_and_audits(tmp_path):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    inside = allowed_root / "inside.pdf"
    outside = tmp_path / "outside.pdf"
    inside.write_text("inside", encoding="utf-8")
    outside.write_text("outside", encoding="utf-8")
    audit_logger = DownloadAuditLogger(tmp_path / "download_audit.log")
    registry = DownloadRegistry(
        RootFolderDownloadAuthorizer((str(allowed_root),)),
        audit_logger,
        token_ttl_seconds=-1,
    )

    token = registry.register(str(inside), user_id="user-1")

    assert registry.resolve(token, client_ip="127.0.0.1") is None
    with pytest.raises(PermissionError):
        registry.register(str(outside), user_id="user-1")

    audit_text = audit_logger.log_path.read_text(encoding="utf-8")
    assert "expired_token" in audit_text
    assert "unauthorized_path_or_acl" in audit_text

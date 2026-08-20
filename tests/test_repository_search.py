from pathlib import Path

from src.config import AppConfig, EmbeddingConfig, IndexingConfig, SearchConfig, SecurityConfig, UiConfig
from src.db.database import Database
from src.db.repositories import SearchRepository
from src.models import Chunk, DocumentMetadata, ProjectMetadata
from src.search.search_service import SearchService


def test_search_returns_page_and_file_path(tmp_path):
    config = AppConfig(
        root_folders=("H:/01.제안서", "H:/02.사업수행"),
        data_dir=tmp_path,
        indexing=IndexingConfig(),
        search=SearchConfig(top_k=5),
        embedding=EmbeddingConfig(provider="hashing", dimensions=64),
        security=SecurityConfig(),
        ui=UiConfig(),
    )
    db = Database(config.database_path)
    db.initialize()
    repo = SearchRepository(db)
    service = SearchService(config, repo)

    project = ProjectMetadata(
        project_id="prj_test",
        project_name="N2SF 보안컨설팅",
        client_name="예시기관",
        year="2025",
        folder_path="H:/01.제안서/N2SF",
    )
    document = DocumentMetadata(
        document_id="doc_test",
        project_id=project.project_id,
        document_title="N2SF 분석 보고서",
        document_type="보고서",
        file_path=str(Path("H:/01.제안서/N2SF/report.pdf")),
        file_type="pdf",
        file_name="report.pdf",
    )
    chunk = Chunk(
        chunk_id="chk_test",
        document_id=document.document_id,
        project_id=project.project_id,
        page_no=42,
        section_title="복구 전략",
        chunk_text="랜섬웨어 감염 시 클린룸 복구 환경에서 백업망 확산을 차단한다.",
        keywords="랜섬웨어, 클린룸, 복구",
        token_count=8,
    )

    repo.upsert_project(project)
    repo.upsert_document(document)
    repo.replace_chunks(document, project, [chunk])
    service.vector_index.upsert_chunks([chunk])

    results = service.search("클린룸 복구", top_k=3)

    assert results
    assert results[0].page_no == 42
    assert results[0].file_path.endswith("report.pdf")
    assert "클린룸" in results[0].matched_text


def test_search_scope_filters_by_source_folder(tmp_path):
    config = AppConfig(
        root_folders=("H:/01.제안서", "H:/02.사업수행"),
        data_dir=tmp_path,
        indexing=IndexingConfig(),
        search=SearchConfig(top_k=5),
        embedding=EmbeddingConfig(provider="hashing", dimensions=64),
        security=SecurityConfig(),
        ui=UiConfig(),
    )
    db = Database(config.database_path)
    db.initialize()
    repo = SearchRepository(db)
    service = SearchService(config, repo)

    proposal_project = ProjectMetadata(
        project_id="prj_proposal",
        project_name="제안 프로젝트",
        client_name="제안고객",
        folder_path="H:/01.제안서/제안 프로젝트",
    )
    report_project = ProjectMetadata(
        project_id="prj_report",
        project_name="수행 프로젝트",
        client_name="수행고객",
        folder_path="H:/02.사업수행/수행 프로젝트",
    )
    proposal_doc = DocumentMetadata(
        document_id="doc_proposal",
        project_id=proposal_project.project_id,
        document_title="제안서",
        document_type="제안서",
        file_path="H:/01.제안서/제안 프로젝트/proposal.pdf",
        file_type="pdf",
        file_name="proposal.pdf",
    )
    report_doc = DocumentMetadata(
        document_id="doc_report",
        project_id=report_project.project_id,
        document_title="보고서",
        document_type="보고서",
        file_path="H:/02.사업수행/수행 프로젝트/report.pdf",
        file_type="pdf",
        file_name="report.pdf",
    )
    proposal_chunk = Chunk(
        chunk_id="chk_proposal",
        document_id=proposal_doc.document_id,
        project_id=proposal_project.project_id,
        page_no=1,
        section_title="",
        chunk_text="데이터 이관 계획 제안 내용",
        keywords="데이터, 이관",
        token_count=4,
    )
    report_chunk = Chunk(
        chunk_id="chk_report",
        document_id=report_doc.document_id,
        project_id=report_project.project_id,
        page_no=2,
        section_title="",
        chunk_text="데이터 이관 계획 수행 보고 내용",
        keywords="데이터, 이관",
        token_count=5,
    )

    repo.upsert_project(proposal_project)
    repo.upsert_document(proposal_doc)
    repo.replace_chunks(proposal_doc, proposal_project, [proposal_chunk])
    repo.upsert_project(report_project)
    repo.upsert_document(report_doc)
    repo.replace_chunks(report_doc, report_project, [report_chunk])
    service.vector_index.upsert_chunks([proposal_chunk, report_chunk])

    proposal_results = service.search("데이터 이관", filters={"file_path_prefixes": ["H:/01.제안서"]})
    report_results = service.search("데이터 이관", filters={"file_path_prefixes": ["H:/02.사업수행"]})
    all_results = service.search("데이터 이관")

    assert proposal_results
    assert all(result.file_path.startswith("H:/01.제안서") for result in proposal_results)
    assert report_results
    assert all(result.file_path.startswith("H:/02.사업수행") for result in report_results)
    assert {result.document_id for result in all_results} == {"doc_proposal", "doc_report"}


def test_report_scope_boost_prefers_goal_model(tmp_path):
    config = AppConfig(
        root_folders=("H:/01.제안서", "H:/02.사업수행"),
        data_dir=tmp_path,
        indexing=IndexingConfig(),
        search=SearchConfig(top_k=5),
        embedding=EmbeddingConfig(provider="hashing", dimensions=64),
        security=SecurityConfig(),
        ui=UiConfig(),
    )
    db = Database(config.database_path)
    db.initialize()
    repo = SearchRepository(db)
    service = SearchService(config, repo)
    project = ProjectMetadata(project_id="prj", project_name="수행", folder_path="H:/02.사업수행/수행")
    base_doc = DocumentMetadata(
        document_id="base",
        project_id="prj",
        document_title="현황분석 보고서",
        document_type="보고서",
        file_path="H:/02.사업수행/수행/03.현황분석/base.pdf",
        file_type="pdf",
        file_name="base.pdf",
    )
    boosted_doc = DocumentMetadata(
        document_id="boosted",
        project_id="prj",
        document_title="목표모델 보고서",
        document_type="보고서",
        file_path="H:/02.사업수행/수행/04.목표모델/boosted.pdf",
        file_type="pdf",
        file_name="boosted.pdf",
    )
    chunks = [
        Chunk("base_chunk", "base", "prj", 1, "", "데이터 이관 계획", "데이터, 이관", 3),
        Chunk("boosted_chunk", "boosted", "prj", 2, "", "데이터 이관 계획", "데이터, 이관", 3),
    ]
    repo.upsert_project(project)
    repo.upsert_document(base_doc)
    repo.replace_chunks(base_doc, project, [chunks[0]])
    repo.upsert_document(boosted_doc)
    repo.replace_chunks(boosted_doc, project, [chunks[1]])
    service.vector_index.upsert_chunks(chunks)

    results = service.search("데이터 이관", filters={"file_path_prefixes": ["H:/02.사업수행"], "source_scope": "report"})

    assert results[0].document_id == "boosted"


def test_proposal_scope_boost_prefers_tech_function(tmp_path):
    config = AppConfig(
        root_folders=("H:/01.제안서", "H:/02.사업수행"),
        data_dir=tmp_path,
        indexing=IndexingConfig(),
        search=SearchConfig(top_k=5),
        embedding=EmbeddingConfig(provider="hashing", dimensions=64),
        security=SecurityConfig(),
        ui=UiConfig(),
    )
    db = Database(config.database_path)
    db.initialize()
    repo = SearchRepository(db)
    service = SearchService(config, repo)
    project = ProjectMetadata(project_id="prj", project_name="제안", folder_path="H:/01.제안서/제안")
    base_doc = DocumentMetadata(
        document_id="base",
        project_id="prj",
        document_title="프로젝트 관리 제안서",
        document_type="제안서",
        file_path="H:/01.제안서/제안/Ⅴ.프로젝트관리/base.pptx",
        file_type="pptx",
        file_name="base.pptx",
    )
    boosted_doc = DocumentMetadata(
        document_id="boosted",
        project_id="prj",
        document_title="Ⅲ. 기술 및 기능 제안서",
        document_type="제안서",
        file_path="H:/01.제안서/제안/Ⅲ.기술 및 기능/boosted.pptx",
        file_type="pptx",
        file_name="boosted.pptx",
    )
    chunks = [
        Chunk("base_chunk", "base", "prj", 1, "", "데이터 이관 계획", "데이터, 이관", 3),
        Chunk("boosted_chunk", "boosted", "prj", 2, "", "데이터 이관 계획", "데이터, 이관", 3),
    ]
    repo.upsert_project(project)
    repo.upsert_document(base_doc)
    repo.replace_chunks(base_doc, project, [chunks[0]])
    repo.upsert_document(boosted_doc)
    repo.replace_chunks(boosted_doc, project, [chunks[1]])
    service.vector_index.upsert_chunks(chunks)

    results = service.search("데이터 이관", filters={"file_path_prefixes": ["H:/01.제안서"], "source_scope": "proposal"})

    assert results[0].document_id == "boosted"


def test_rnd_query_matches_expanded_project_title(tmp_path):
    config = AppConfig(
        root_folders=("H:/01.제안서", "H:/02.사업수행"),
        data_dir=tmp_path,
        indexing=IndexingConfig(),
        search=SearchConfig(top_k=5),
        embedding=EmbeddingConfig(provider="hashing", dimensions=64),
        security=SecurityConfig(),
        ui=UiConfig(),
    )
    db = Database(config.database_path)
    db.initialize()
    repo = SearchRepository(db)
    service = SearchService(config, repo)

    project = ProjectMetadata(
        project_id="prj_kistep",
        project_name="KISTEP 데이터 중심 범부처 R&D 통합 플랫폼",
        client_name="한국과학기술기획평가원",
        folder_path="H:/01.제안서/KISTEP 데이터 중심 범부처 R&D 통합 플랫폼",
    )
    document = DocumentMetadata(
        document_id="doc_kistep",
        project_id=project.project_id,
        document_title="KISTEP 기술 및 기능",
        document_type="제안서",
        file_path="H:/01.제안서/KISTEP/기술및기능.pptx",
        file_type="pptx",
        file_name="기술및기능.pptx",
    )
    chunk = Chunk(
        chunk_id="chk_kistep",
        document_id=document.document_id,
        project_id=project.project_id,
        page_no=3,
        section_title="",
        chunk_text="AI 데이터 분석 플랫폼 기능과 IRIS 연계를 정의한다.",
        keywords="AI, 데이터, IRIS",
        token_count=8,
    )

    repo.upsert_project(project)
    repo.upsert_document(document)
    repo.replace_chunks(document, project, [chunk])
    service.vector_index.upsert_chunks([chunk])

    rnd_results = service.search("R&D", top_k=3)
    ai_research_results = service.search("AI 기반 연구", top_k=3)

    assert rnd_results
    assert rnd_results[0].document_id == "doc_kistep"
    assert ai_research_results
    assert ai_research_results[0].document_id == "doc_kistep"

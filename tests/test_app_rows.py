from src.models import SearchResult

from app import _result_rows


def test_result_rows_do_not_include_open_file_link():
    result = SearchResult(
        chunk_id="chk",
        document_id="doc",
        project_id="prj",
        project_name="프로젝트",
        client_name="고객",
        document_title="문서",
        document_type="보고서",
        file_path="H:/02.사업수행/report.pdf",
        page_no=1,
        display_page="1",
        matched_text="클라우드 MSA",
        score=1.0,
        document_keywords=["클라우드", "MSA"],
    )

    rows = _result_rows([result])

    assert "원문 열기" not in rows[0]
    assert "문서유형" not in rows[0]

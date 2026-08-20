import pytest

from src.extraction.cost_extractor import extract_cost_rows
from src.extraction.evidence_extractor import extract_evidence_rows
from src.extraction.staff_extractor import extract_staff_rows
from src.extraction.technology_trend_extractor import extract_technology_trend_rows
from src.models import SearchResult
from src.search.nlu_query_parser import parse_natural_query
from src.search.query_expander import expand_query
from src.search.reranker import rerank_results
from src.domain.domain_dictionary import domain_keywords_for_text
from src.utils.korean_tokenizer import matched_keywords, tokenize


QUERY_CASES = [
    ("목표모델에서 DR 관련 산출물 찾아줘", "architecture_evidence", "목표모델", "DR", {}),
    ("클라우드 비용 산정 관련 산출물 찾아줘", "cost_estimation", "비용산정", "클라우드", {}),
    ("정보기술동향에서 MSA 관련 내용 찾아줘", "technology_trend", "정보기술동향", "MSA", {}),
    ("투입인력에서 공항업무경력이 있는 인력 명단 찾아줘", "staff_experience", "투입인력", "공항업무", {"business_domain": "공항업무"}),
    ("한국공항공사 사업 경험 있는 PM 찾아줘", "staff_experience", "", "한국공항공사 PM", {"client": "한국공항공사", "role": "PM"}),
    ("클라우드 전환 사업 경험 있는 TA 찾아줘", "staff_experience", "", "클라우드 전환 TA", {"business_domain": "클라우드", "project_type": "전환", "role": "TA"}),
    ("ISP 수행 경험 있는 특급 PM 찾아줘", "staff_experience", "", "ISP PM 특급", {"project_type": "ISP", "role": "PM", "grade": "특급"}),
    ("데이터 표준화 사업 경험 있는 인력 찾아줘", "staff_experience", "", "데이터 표준화", {"business_domain": "데이터", "project_type": "표준화"}),
    ("공공기관 AI 서비스 구축 경험 있는 PL 찾아줘", "staff_experience", "", "공공기관 AI 서비스 구축 PL", {"business_domain": "공공기관 AI", "project_type": "구축", "role": "PL"}),
]


@pytest.mark.parametrize("query,domain,chapter,topic,conditions", QUERY_CASES)
def test_parse_and_expand_required_queries(query, domain, chapter, topic, conditions):
    parsed = expand_query(parse_natural_query(query))

    assert parsed.search_domain == domain
    assert parsed.target_chapter == chapter
    assert topic in parsed.topic
    assert parsed.output_type
    assert parsed.semantic_query
    assert parsed.expanded_keywords
    assert parsed.confidence > 0
    for key, value in conditions.items():
        assert parsed.conditions[key] == value


@pytest.mark.parametrize("query,domain,chapter,topic,conditions", QUERY_CASES)
def test_required_queries_produce_top_10_and_structured_rows(query, domain, chapter, topic, conditions):
    parsed = expand_query(parse_natural_query(query))
    results = _sample_results_for(parsed, 12)

    top_results = rerank_results(parsed, results, top_k=10)
    rows = _structured_rows(parsed, top_results)

    assert len(top_results) == 10
    assert len(rows) == 10
    for row in rows:
        assert row["문서명"]
        assert row["페이지"]
        assert row["챕터"]
        assert row["근거 문장"]
        assert row["chunk_id"]


def test_staff_extractor_does_not_create_uncertain_person_name():
    parsed = expand_query(parse_natural_query("한국공항공사 사업 경험 있는 PM 찾아줘"))
    result = _result(
        1,
        "한국공항공사 차세대 시스템 구축 사업 수행경험과 PM 역할 근거가 있다.",
        "투입인력",
    )

    row = extract_staff_rows([result], parsed.conditions)[0]

    assert row["성명"] == "확인 필요"
    assert row["근거 문장"] in result.matched_text


def test_query_expander_removes_search_utility_words_from_keywords():
    parsed = expand_query(parse_natural_query("클라우드 전환 관련 산출물 근거 문서 페이지 찾아줘"))

    forbidden = {"근거", "사례", "산출물", "문서", "페이지", "관련"}

    assert forbidden.isdisjoint(set(parsed.expanded_keywords))
    assert "클라우드" in parsed.expanded_keywords


def test_search_utility_words_are_not_matched_keywords():
    forbidden = {"근거", "사례", "산출물", "문서", "페이지", "검색"}

    assert forbidden.isdisjoint(set(tokenize("클라우드 전환 근거 사례 산출물 문서 페이지 검색")))
    assert matched_keywords("클라우드 전환 근거 페이지 검색", "클라우드 전환 근거 페이지 검색 문서") == [
        "클라우드",
        "전환",
    ]


def test_domain_keywords_include_technical_domain_terms():
    keywords = domain_keywords_for_text("Kubernetes 기반 클라우드 전환 아키텍처와 API Gateway, RAG 검색을 설계한다.")

    assert "CLOUD" in keywords
    assert "Kubernetes" in keywords
    assert "INTEGRATION" in keywords
    assert "API Gateway" in keywords
    assert "AI" in keywords


def _structured_rows(parsed, results):
    if parsed.output_type == "staff_table":
        return extract_staff_rows(results, parsed.conditions)
    if parsed.output_type == "cost_table":
        return extract_cost_rows(results, parsed)
    if parsed.output_type == "technology_trend_table":
        return extract_technology_trend_rows(results, parsed)
    return extract_evidence_rows(results, parsed)


def _sample_results_for(parsed, count):
    text_by_domain = {
        "staff_experience": "홍길동 특급 PM 투입인력 주요경력 한국공항공사 ISP 클라우드 전환 데이터 표준화 공공기관 AI 서비스 구축 수행경험",
        "architecture_evidence": "목표모델 To-Be 아키텍처에서 DR 재해복구 RTO RPO 이중화 구성도를 제시한다.",
        "technology_trend": "정보기술동향 MSA 마이크로서비스 최신기술 적용사례와 시사점을 정리한다.",
        "cost_estimation": "클라우드 비용산정 TCO 단가 1,000원 수량 10개 금액 10,000원 사용량 기준을 제시한다.",
        "general": "관련 산출물 근거 문장이다.",
    }
    chapter_by_domain = {
        "staff_experience": "투입인력",
        "architecture_evidence": "목표모델",
        "technology_trend": "정보기술동향",
        "cost_estimation": "비용산정",
        "general": "기타",
    }
    return [
        _result(index, text_by_domain[parsed.search_domain], chapter_by_domain[parsed.search_domain])
        for index in range(count)
    ]


def _result(index, text, chapter):
    return SearchResult(
        chunk_id=f"chunk_{index}",
        document_id=f"doc_{index}",
        project_id="project",
        project_name="예시 사업",
        client_name="예시기관",
        document_title=f"예시 문서 {index}",
        document_type="제안서",
        file_path=f"H:/01.제안서/example_{index}.pdf",
        page_no=index + 1,
        display_page=str(index + 1),
        matched_text=text,
        score=1.0 - index * 0.01,
        keyword_score=0.8,
        vector_score=0.7,
        matched_keywords=[],
        document_keywords=[],
        chapter_title=chapter,
        section_title="섹션",
        heading_path=f"{chapter} > 섹션",
    )

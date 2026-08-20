from src.rfp.rfp_analyzer import RfpAnalyzer
from src.rfp.requirement_extractor import extract_keywords, extract_requirement_sections


def test_rfp_analyzer_extracts_summary():
    text = """
    사업명: AI 검색 플랫폼 구축
    발주기관: 예시기관
    사업목적: 데이터 기반 검색 서비스를 구축한다.
    주요 요구사항: 클라우드, 보안, 데이터 이관, 평가항목을 포함한다.
    """
    summary = RfpAnalyzer().summarize(text)
    assert summary["business_name"] == "AI 검색 플랫폼 구축"
    assert summary["client_name"] == "예시기관"
    assert "데이터" in summary["main_keywords"]


def test_rfp_keywords_prioritize_consulting_requirements():
    text = """
    사업명: 차세대 통합 플랫폼 구축 컨설팅
    사업기간: 계약일로부터 6개월
    사업예산: 1,200,000,000원
    제안서 제출기한: 2026.06.30

    Ⅲ. 컨설팅 요구사항
    현황분석을 통해 업무 프로세스와 데이터 흐름을 진단하고 개선과제를 도출한다.
    목표모델 수립 시 클라우드네이티브, MSA, API 연계, 데이터아키텍처, 보안아키텍처를 설계한다.
    이행계획은 전환 전략, 마이그레이션 방안, 단계별 추진 로드맵을 포함한다.

    Ⅳ. 평가항목
    기술평가 배점 및 가격평가 기준을 따른다.
    """

    sections = extract_requirement_sections(text)
    keywords = extract_keywords(text, requirement_sections=sections)
    compact_keywords = {keyword.lower().replace(" ", "") for keyword in keywords}

    assert any("현황분석" in section or "목표모델" in section for section in sections)
    assert "클라우드네이티브" in keywords
    assert "MSA" in keywords
    assert "API" in keywords
    assert "데이터아키텍처" in keywords
    assert "사업기간" not in compact_keywords
    assert "사업예산" not in compact_keywords
    assert "평가항목" not in compact_keywords


def test_rfp_queries_do_not_use_title_budget_or_period():
    text = """
    사업명: AI 기반 업무혁신 컨설팅
    용역기간: 착수일로부터 180일
    추정가격: 500,000,000원

    상세요구사항
    데이터 표준화 체계와 메타데이터 관리체계를 수립한다.
    클라우드 전환 대상 시스템을 분석하고 API 연계 구조를 설계한다.
    """

    analyzer = RfpAnalyzer()
    summary = analyzer.summarize(text)
    queries = [query for query, _ in analyzer.build_weighted_queries(summary)]
    joined = " ".join(queries)

    assert "AI 기반 업무혁신 컨설팅" not in joined
    assert "500,000,000" not in joined
    assert "180일" not in joined
    assert "데이터" in joined
    assert "클라우드" in joined
    assert "API" in joined

from src.ingestion.heading_extractor import (
    canonical_chapter,
    chapter_filter_norms,
    enrich_units_with_headings,
    heading_search_norm,
    normalize_chapter_name,
)
from src.models import ParsedUnit
from src.search.query_parser import parse_search_query


def test_query_parser_splits_chapter_and_semantic_query():
    cases = [
        ("목표모델에서 클라우드 관련 설계 내용을 찾아줘", "목표모델", "클라우드 관련 설계 내용"),
        ("현황분석에서 데이터 용량 분석 관련 내용을 찾아줘", "현황분석", "데이터 용량 분석 관련 내용"),
        ("기술동향분석에서 MSA에 관한 내용을 찾아줘", "기술동향분석", "MSA에 관한 내용"),
        ("요구사항 분석에서 SSO 관련 내용을 찾아줘", "요구사항분석", "SSO 관련 내용"),
        ("이행계획에서 단계별 전환 로드맵을 찾아줘", "이행계획", "단계별 전환 로드맵"),
    ]

    for query, expected_chapter, expected_semantic in cases:
        parsed = parse_search_query(query)
        assert parsed.chapter_filter == expected_chapter
        assert parsed.semantic_query == expected_semantic


def test_query_parser_keeps_whole_search_without_chapter():
    parsed = parse_search_query("클라우드 관련 내용을 찾아줘")

    assert parsed.chapter_filter == ""
    assert parsed.semantic_query == "클라우드 관련 내용"


def test_chapter_normalization_and_synonyms():
    assert normalize_chapter_name("Ⅲ. 목표모델 수립") == "목표모델수립"
    assert canonical_chapter("TO-BE 아키텍처") == "목표모델"
    assert canonical_chapter("Requirements") == "요구사항분석"
    assert "요구사항분석" in chapter_filter_norms("요구사항 분석")


def test_heading_extractor_inherits_previous_heading():
    units = [
        ParsedUnit(page_no=1, text="Ⅲ. 목표모델\n1. 클라우드 전환 목표모델\n클라우드 설계 방향"),
        ParsedUnit(page_no=2, text="API Gateway와 MSA 기반 연계 구조를 설계한다."),
        ParsedUnit(page_no=3, text="1.1 인프라 설계\n컨테이너 기반 운영 방안을 정의한다."),
    ]

    enriched = enrich_units_with_headings(units)

    assert enriched[0].chapter_title == "목표모델"
    assert enriched[1].chapter_title == "목표모델"
    assert "클라우드 전환 목표모델" in enriched[1].section_title
    assert "목표모델" in enriched[1].heading_path
    assert enriched[2].section_title == "1.1 인프라 설계"


def test_heading_extractor_collapses_unknown_headings_to_other():
    units = [
        ParsedUnit(page_no=1, text="Ⅰ. 사업 개요\n프로젝트 추진 배경"),
        ParsedUnit(page_no=2, text="1. 수행 조직\nPMO 운영 체계"),
    ]

    enriched = enrich_units_with_headings(units)

    assert {unit.chapter_title for unit in enriched} == {"기타"}
    assert enriched[0].section_title == "Ⅰ. 사업 개요"


def test_heading_search_norm_supports_partial_alias_matching():
    norm = heading_search_norm("Ⅲ. 목표모델 수립", "1. 클라우드 전환 목표모델", "Ⅲ. 목표모델 수립 > 1. 클라우드 전환 목표모델")

    assert "목표모델" in norm
    assert "tobe" in norm

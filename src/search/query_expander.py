from __future__ import annotations

from dataclasses import replace

from src.domain.domain_dictionary import (
    CLOUD_COST_KEYWORDS,
    COMMON_STAFF_TERMS,
    DR_KEYWORDS,
    MSA_KEYWORDS,
)
from src.search.nlu_query_parser import ParsedNaturalQuery


ARCHITECTURE_BASE_KEYWORDS = ("목표모델", "목표 아키텍처", "To-Be", "설계", "구성도", "아키텍처")
COST_BASE_KEYWORDS = ("비용산정", "TCO", "단가", "수량", "금액", "구축비", "운영비", "라이선스", "사용량")
TECHNOLOGY_TREND_BASE_KEYWORDS = ("기술동향", "최신기술", "트렌드", "적용사례", "시사점")
SEARCH_UTILITY_STOPWORDS = {
    "근거",
    "사례",
    "산출물",
    "문서",
    "페이지",
    "관련",
    "내용",
    "찾아줘",
    "찾아",
    "검색",
    "보여줘",
    "알려줘",
}


def expand_query(parsed: ParsedNaturalQuery) -> ParsedNaturalQuery:
    keywords = expanded_keywords_for(parsed)
    semantic_query = build_semantic_query(parsed, keywords)
    return replace(parsed, expanded_keywords=keywords, semantic_query=semantic_query)


def expanded_keywords_for(parsed: ParsedNaturalQuery) -> list[str]:
    keywords: list[str] = []
    topic = parsed.topic or parsed.original_query
    keywords.extend(_topic_terms(topic))

    if parsed.search_domain == "staff_experience":
        keywords.extend(COMMON_STAFF_TERMS)
        for key in ("client", "business_domain", "business_content", "project_type", "role", "grade", "participation_type"):
            value = parsed.conditions.get(key, "")
            if value:
                keywords.append(value)
        if parsed.conditions.get("experience_years"):
            keywords.append(parsed.conditions["experience_years"])
    elif parsed.search_domain == "architecture_evidence":
        keywords.extend(ARCHITECTURE_BASE_KEYWORDS)
        keywords.extend(_subject_keywords(topic))
    elif parsed.search_domain == "cost_estimation":
        keywords.extend(COST_BASE_KEYWORDS)
        keywords.extend(CLOUD_COST_KEYWORDS)
    elif parsed.search_domain == "technology_trend":
        keywords.extend(TECHNOLOGY_TREND_BASE_KEYWORDS)
        keywords.extend(_subject_keywords(topic))
    else:
        keywords.extend(_subject_keywords(topic))

    return _unique([keyword.strip() for keyword in keywords if _is_search_keyword(keyword)])


def build_semantic_query(parsed: ParsedNaturalQuery, keywords: list[str]) -> str:
    values = [
        parsed.topic or parsed.original_query,
        parsed.target_chapter,
        parsed.target_section,
        parsed.target_subsection,
        *keywords,
    ]
    return " ".join(_unique([value for value in values if value]))


def _subject_keywords(topic: str) -> list[str]:
    lower = topic.lower()
    keywords: list[str] = []
    if "dr" in lower or "재해" in topic or "복구" in topic:
        keywords.extend(DR_KEYWORDS)
    if "msa" in lower or "마이크로" in topic:
        keywords.extend(MSA_KEYWORDS)
    if "클라우드" in topic:
        keywords.extend(("클라우드", "Cloud", "전환", "마이그레이션", "인프라"))
    if "보안" in topic:
        keywords.extend(("보안", "인증", "권한", "암호화", "접근통제"))
    if "데이터" in topic:
        keywords.extend(("데이터", "표준화", "품질", "거버넌스", "이관"))
    if "ai" in lower or "인공지능" in topic:
        keywords.extend(("AI", "인공지능", "모델", "서비스", "학습"))
    return keywords


def _topic_terms(topic: str) -> list[str]:
    separators = " ,/|()[]{}"
    values = [topic]
    for separator in separators:
        split_values = []
        for value in values:
            split_values.extend(value.split(separator))
        values = split_values
    return [value.strip() for value in values if _is_search_keyword(value)]


def _is_search_keyword(value: str) -> bool:
    keyword = (value or "").strip()
    if len(keyword) < 2:
        return False
    return keyword.lower() not in {item.lower() for item in SEARCH_UTILITY_STOPWORDS}


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen

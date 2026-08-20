from __future__ import annotations

from dataclasses import dataclass, field
import re

from src.domain.domain_dictionary import (
    CHAPTER_ALIASES,
    GRADE_ALIASES,
    ORGANIZATION_SUFFIXES,
    PARTICIPATION_ALIASES,
    PROJECT_TYPE_ALIASES,
    ROLE_ALIASES,
    STAFF_QUERY_TRIGGERS,
)
from src.domain.heading_taxonomy import (
    CANONICAL_CHAPTER_ALIASES,
    CANONICAL_SECTION_ALIASES,
    CANONICAL_SUBSECTION_ALIASES,
    canonicalize_heading,
)


SEARCH_DOMAINS = {
    "staff_experience",
    "architecture_evidence",
    "technology_trend",
    "cost_estimation",
    "general",
}


@dataclass(frozen=True)
class ParsedNaturalQuery:
    original_query: str
    search_domain: str = "general"
    target_chapter: str = ""
    target_section: str = ""
    target_subsection: str = ""
    topic: str = ""
    output_type: str = "evidence_table"
    semantic_query: str = ""
    expanded_keywords: list[str] = field(default_factory=list)
    conditions: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0


def parse_natural_query(query: str) -> ParsedNaturalQuery:
    original_query = _normalize_spaces(query)
    if not original_query:
        return ParsedNaturalQuery(original_query="")

    target_chapter = _detect_chapter(original_query)
    target_section = _detect_canonical(original_query, CANONICAL_SECTION_ALIASES)
    target_subsection = _detect_canonical(original_query, CANONICAL_SUBSECTION_ALIASES)
    domain_scores = _domain_scores(original_query, target_chapter)
    search_domain = _choose_domain(domain_scores)
    conditions = _extract_conditions(original_query, search_domain)
    topic = _extract_topic(original_query, search_domain, target_chapter, conditions)
    output_type = _output_type(search_domain)
    confidence = _confidence(domain_scores, search_domain, target_chapter, conditions)

    return ParsedNaturalQuery(
        original_query=original_query,
        search_domain=search_domain,
        target_chapter=target_chapter,
        target_section=target_section,
        target_subsection=target_subsection,
        topic=topic,
        output_type=output_type,
        semantic_query=topic or original_query,
        expanded_keywords=[],
        conditions=conditions,
        confidence=confidence,
    )


def _domain_scores(query: str, target_chapter: str) -> dict[str, int]:
    text = query.lower()
    scores = {
        "staff_experience": _count_alias_hits(query, {"staff": STAFF_QUERY_TRIGGERS}),
        "architecture_evidence": _count_terms(text, ("목표모델", "목표 모델", "목표 아키텍처", "to-be", "tobe", "설계", "구성도")),
        "technology_trend": _count_terms(text, ("정보기술동향", "기술동향", "최신기술", "최신 기술", "트렌드", "technology trend")),
        "cost_estimation": _count_terms(text, ("비용", "비용산정", "비용 산정", "tco", "견적", "단가", "수량", "소요예산", "예산")),
        "general": 1,
    }
    if target_chapter in {"투입인력"}:
        scores["staff_experience"] += 3
    elif target_chapter in {"목표모델"}:
        scores["architecture_evidence"] += 3
    elif target_chapter in {"정보기술동향"}:
        scores["technology_trend"] += 3
    elif target_chapter in {"비용산정"}:
        scores["cost_estimation"] += 3
    return scores


def _choose_domain(scores: dict[str, int]) -> str:
    candidates = sorted(
        ((domain, score) for domain, score in scores.items() if domain != "general"),
        key=lambda item: item[1],
        reverse=True,
    )
    if not candidates or candidates[0][1] <= 0:
        return "general"
    top_domain, top_score = candidates[0]
    if len(candidates) > 1 and top_score == candidates[1][1]:
        if top_domain == "staff_experience":
            return top_domain
    return top_domain


def _extract_conditions(query: str, search_domain: str) -> dict[str, str]:
    if search_domain != "staff_experience":
        return {}
    conditions: dict[str, str] = {}
    client = _extract_client(query)
    if client:
        conditions["client"] = client
    role = _find_alias(query, ROLE_ALIASES)
    if role:
        conditions["role"] = role
    grade = _find_alias(query, GRADE_ALIASES)
    if grade:
        conditions["grade"] = grade
    project_type = _find_alias(query, PROJECT_TYPE_ALIASES)
    if project_type:
        conditions["project_type"] = project_type
    participation = _find_alias(query, PARTICIPATION_ALIASES)
    if participation:
        conditions["participation_type"] = participation
    years = _extract_experience_years(query)
    if years:
        conditions["experience_years"] = years

    business_phrase = _extract_business_phrase(query, conditions)
    if business_phrase:
        conditions["business_content"] = business_phrase
        business_domain = _infer_business_domain(business_phrase)
        if business_domain:
            conditions["business_domain"] = business_domain
    return conditions


def _extract_topic(query: str, search_domain: str, target_chapter: str, conditions: dict[str, str]) -> str:
    if search_domain == "staff_experience":
        parts: list[str] = []
        for value in (
            conditions.get("client", ""),
            conditions.get("business_content", ""),
            conditions.get("business_domain", ""),
            conditions.get("project_type", ""),
            conditions.get("role", ""),
            conditions.get("grade", ""),
        ):
            _append_topic_part(parts, value)
        topic = " ".join(parts)
        return topic or _clean_topic(query, target_chapter)
    return _clean_topic(query, target_chapter)


def _output_type(search_domain: str) -> str:
    return {
        "staff_experience": "staff_table",
        "architecture_evidence": "evidence_table",
        "technology_trend": "technology_table",
        "cost_estimation": "cost_table",
    }.get(search_domain, "evidence_table")


def _confidence(scores: dict[str, int], search_domain: str, target_chapter: str, conditions: dict[str, str]) -> float:
    if search_domain == "general":
        return 0.45 if target_chapter else 0.35
    domain_score = scores.get(search_domain, 0)
    other_scores = [score for domain, score in scores.items() if domain not in {search_domain, "general"}]
    margin = domain_score - max(other_scores or [0])
    value = 0.45
    value += min(domain_score, 4) * 0.08
    if target_chapter:
        value += 0.12
    value += min(len([value for value in conditions.values() if value]), 5) * 0.04
    if margin <= 0:
        value -= 0.12
    elif margin == 1:
        value -= 0.04
    return round(max(0.0, min(value, 0.95)), 2)


def _detect_chapter(query: str) -> str:
    lower = query.lower()
    best: tuple[str, int] = ("", 0)
    alias_groups = {**CHAPTER_ALIASES, **{key: tuple(value) for key, value in CANONICAL_CHAPTER_ALIASES.items()}}
    for chapter, aliases in alias_groups.items():
        for alias in aliases:
            alias_lower = alias.lower()
            if alias_lower and alias_lower in lower and len(alias_lower) > best[1]:
                best = (chapter, len(alias_lower))
    return best[0]


def _detect_canonical(query: str, aliases: dict[str, list[str]]) -> str:
    match = canonicalize_heading(query, aliases, threshold=0.70)
    return str(match["canonical"] or "")


def _find_alias(query: str, aliases_by_value: dict[str, tuple[str, ...]]) -> str:
    lower = query.lower()
    best: tuple[str, int] = ("", 0)
    for value, aliases in aliases_by_value.items():
        for alias in aliases:
            alias_lower = alias.lower()
            if not alias_lower:
                continue
            if _contains_alias(lower, alias_lower) and len(alias_lower) > best[1]:
                best = (value, len(alias_lower))
    return best[0]


def _contains_alias(text: str, alias: str) -> bool:
    if re.fullmatch(r"[a-z0-9]+", alias, flags=re.IGNORECASE):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text, flags=re.IGNORECASE))
    return alias in text


def _extract_client(query: str) -> str:
    suffix_pattern = "|".join(re.escape(suffix) for suffix in sorted(ORGANIZATION_SUFFIXES, key=len, reverse=True))
    matches = re.findall(rf"[가-힣A-Za-z0-9·&()._-]{{2,}}(?:{suffix_pattern})", query)
    if not matches:
        return ""
    cleaned = [_strip_common_prefix(match) for match in matches]
    cleaned = [match for match in cleaned if match and not match.endswith("업무")]
    return max(cleaned, key=len) if cleaned else ""


def _extract_experience_years(query: str) -> str:
    match = re.search(r"\d+\s*년\s*(?:이상|초과|이내|미만|경력)?", query)
    return _normalize_spaces(match.group(0)) if match else ""


def _extract_business_phrase(query: str, conditions: dict[str, str]) -> str:
    patterns = (
        r"([가-힣A-Za-z0-9·&()._\-\s]+?업무)\s*경력",
        r"([가-힣A-Za-z0-9·&()._\-\s]+?)\s*(?:사업|서비스|시스템|플랫폼)?\s*(?:수행\s*)?경험",
        r"([가-힣A-Za-z0-9·&()._\-\s]+?)\s*(?:관련|기반)?\s*인력",
    )
    for pattern in patterns:
        match = re.search(pattern, query)
        if not match:
            continue
        phrase = _clean_business_phrase(match.group(1), conditions)
        if phrase:
            return phrase
    return ""


def _clean_business_phrase(phrase: str, conditions: dict[str, str]) -> str:
    value = _normalize_spaces(phrase)
    removals = {
        "투입인력",
        "투입 인력",
        "투입",
        "참여인력",
        "참여 인력",
        "에서",
        "있는",
        "인력",
        "명단",
        "찾아줘",
        "찾아",
        "관련",
        "기반",
        "사업",
        "경험",
        "경력",
        "수행",
    }
    for key in ("client", "role", "grade", "participation_type", "experience_years"):
        condition = conditions.get(key, "")
        if condition:
            value = value.replace(condition, " ")
    for removal in removals:
        value = value.replace(removal, " ")
    return _normalize_spaces(value).strip(" ,")


def _infer_business_domain(phrase: str) -> str:
    if not phrase:
        return ""
    if phrase.endswith("업무"):
        return phrase
    domain_terms = []
    for term in ("공공기관", "클라우드", "데이터", "AI", "인공지능", "보안", "재해복구", "DR", "금융", "의료"):
        if term.lower() in phrase.lower():
            domain_terms.append(term)
    return " ".join(_unique(domain_terms)) if domain_terms else phrase


def _clean_topic(query: str, target_chapter: str) -> str:
    topic = _normalize_spaces(query)
    if target_chapter:
        for alias in CHAPTER_ALIASES.get(target_chapter, (target_chapter,)):
            topic = re.sub(re.escape(alias), " ", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\b(?:에서|의|관련|내용|산출물|찾아줘|찾아|검색|보여줘|알려줘)\b", " ", topic)
    topic = topic.replace("에서", " ").replace("관련", " ").replace("찾아줘", " ")
    return _normalize_spaces(topic)


def _count_alias_hits(query: str, alias_groups: dict[str, tuple[str, ...]]) -> int:
    lower = query.lower()
    count = 0
    for aliases in alias_groups.values():
        for alias in aliases:
            if _contains_alias(lower, alias.lower()):
                count += 1
    return count


def _count_terms(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term.lower() in text)


def _strip_common_prefix(value: str) -> str:
    return re.sub(r"^(?:발주기관|고객기관|고객|기관)\s*", "", value).strip()


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def _append_topic_part(parts: list[str], value: str) -> None:
    value = (value or "").strip()
    if not value:
        return
    if any(value == part or value in part for part in parts):
        return
    parts.append(value)

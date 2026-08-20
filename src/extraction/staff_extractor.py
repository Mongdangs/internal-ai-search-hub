from __future__ import annotations

import re

from src.models import SearchResult


UNKNOWN = "확인 필요"
ROLE_TERMS = ("PM", "PL", "TA", "AA", "DA", "DBA", "개발", "컨설턴트")
GRADE_TERMS = ("특급", "고급", "중급", "초급")
PROJECT_TERMS = ("ISP", "ISMP", "BPR", "구축", "운영", "감리", "컨설팅", "전환", "표준화")


def extract_staff_rows(results: list[SearchResult], conditions: dict[str, str]) -> list[dict]:
    return [_row_for(result, conditions) for result in results]


def _row_for(result: SearchResult, conditions: dict[str, str]) -> dict:
    evidence = _evidence_sentence(result.matched_text)
    haystack = _haystack(result)
    matched_conditions = [value for value in conditions.values() if value and value.lower() in haystack.lower()]
    role = _term_in_text(ROLE_TERMS, evidence) or _condition_if_present("role", conditions, evidence)
    grade = _term_in_text(GRADE_TERMS, evidence) or _condition_if_present("grade", conditions, evidence)
    project_type = _term_in_text(PROJECT_TERMS, evidence) or _condition_if_present("project_type", conditions, evidence)
    related_work = _matched_condition_value(("business_domain", "business_content"), conditions, haystack)

    return {
        "성명": _extract_name(evidence),
        "등급": grade or UNKNOWN,
        "역할": role or UNKNOWN,
        "조건 매칭 근거": ", ".join(matched_conditions) if matched_conditions else UNKNOWN,
        "발주기관/사업명": _client_project(result),
        "사업성격": project_type or UNKNOWN,
        "관련 업무": related_work or UNKNOWN,
        "문서명": result.document_title or UNKNOWN,
        "페이지": result.display_page or str(result.page_no or "") or UNKNOWN,
        "챕터": result.chapter_title or UNKNOWN,
        "근거 문장": evidence or UNKNOWN,
        "신뢰도": _confidence(evidence, matched_conditions, role, grade),
        "chunk_id": result.chunk_id,
    }


def _extract_name(text: str) -> str:
    explicit = re.search(r"(?:성명|이름)\s*[:：]?\s*([가-힣]{2,4})", text)
    if explicit:
        return explicit.group(1)
    near_role = re.search(r"\b([가-힣]{2,4})\s+(?:특급|고급|중급|초급)?\s*(?:PM|PL|TA|AA|DA|DBA|개발|컨설턴트)\b", text)
    if near_role:
        return near_role.group(1)
    return UNKNOWN


def _condition_if_present(key: str, conditions: dict[str, str], text: str) -> str:
    value = conditions.get(key, "")
    if value and value.lower() in text.lower():
        return value
    return ""


def _matched_condition_value(keys: tuple[str, ...], conditions: dict[str, str], haystack: str) -> str:
    for key in keys:
        value = conditions.get(key, "")
        if value and value.lower() in haystack.lower():
            return value
    return ""


def _term_in_text(terms: tuple[str, ...], text: str) -> str:
    lower = text.lower()
    for term in terms:
        if term.lower() in lower:
            return term
    return ""


def _client_project(result: SearchResult) -> str:
    values = [value for value in (result.client_name, result.project_name) if value]
    return " / ".join(values) if values else UNKNOWN


def _evidence_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ""
    sentences = re.split(r"(?:[.!?。]\s+|다\.\s+)", text, maxsplit=1)
    return sentences[0].strip() if sentences else text


def _confidence(evidence: str, matched_conditions: list[str], role: str, grade: str) -> str:
    score = 0.35
    if evidence:
        score += 0.2
    if matched_conditions:
        score += min(len(matched_conditions), 3) * 0.1
    if role:
        score += 0.1
    if grade:
        score += 0.05
    return f"{min(score, 0.95):.2f}"


def _haystack(result: SearchResult) -> str:
    return " ".join(
        str(value or "")
        for value in (
            result.project_name,
            result.client_name,
            result.document_title,
            result.chapter_title,
            result.section_title,
            result.heading_path,
            result.matched_text,
        )
    )

from __future__ import annotations

import re

from src.models import SearchResult
from src.search.nlu_query_parser import ParsedNaturalQuery


UNKNOWN = "확인 필요"


def extract_cost_rows(results: list[SearchResult], parsed: ParsedNaturalQuery) -> list[dict]:
    return [_row_for(result, parsed) for result in results]


def _row_for(result: SearchResult, parsed: ParsedNaturalQuery) -> dict:
    evidence = _evidence_sentence(result.matched_text)
    return {
        "비용 항목": _first_keyword(parsed.expanded_keywords, evidence) or UNKNOWN,
        "수량": _extract_quantity(evidence) or UNKNOWN,
        "단가": _extract_unit_price(evidence) or UNKNOWN,
        "금액": _extract_amount(evidence) or UNKNOWN,
        "문서명": result.document_title or UNKNOWN,
        "페이지": result.display_page or str(result.page_no or "") or UNKNOWN,
        "챕터": result.chapter_title or UNKNOWN,
        "근거 문장": evidence or UNKNOWN,
        "신뢰도": _confidence(evidence),
        "chunk_id": result.chunk_id,
    }


def _extract_quantity(text: str) -> str:
    match = re.search(r"\d[\d,]*(?:\.\d+)?\s*(?:식|명|개|대|식|건|월|년|core|Core|GB|TB|EA)", text)
    return match.group(0) if match else ""


def _extract_unit_price(text: str) -> str:
    match = re.search(r"단가\s*[:：]?\s*[\d,]+(?:\.\d+)?\s*(?:원|천원|백만원|억원)?", text)
    return match.group(0) if match else ""


def _extract_amount(text: str) -> str:
    match = re.search(r"[\d,]+(?:\.\d+)?\s*(?:원|천원|백만원|억원)", text)
    return match.group(0) if match else ""


def _first_keyword(keywords: list[str], text: str) -> str:
    lower = text.lower()
    for keyword in keywords:
        if keyword.lower() in lower:
            return keyword
    return ""


def _evidence_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ""
    sentences = re.split(r"(?:[.!?。]\s+|다\.\s+)", text, maxsplit=1)
    return sentences[0].strip() if sentences else text


def _confidence(evidence: str) -> str:
    score = 0.4 if evidence else 0.2
    if _extract_amount(evidence):
        score += 0.25
    if _extract_quantity(evidence):
        score += 0.15
    if _extract_unit_price(evidence):
        score += 0.15
    return f"{min(score, 0.95):.2f}"

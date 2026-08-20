from __future__ import annotations

import re

from src.models import SearchResult
from src.search.nlu_query_parser import ParsedNaturalQuery


UNKNOWN = "확인 필요"


def extract_technology_trend_rows(results: list[SearchResult], parsed: ParsedNaturalQuery) -> list[dict]:
    return [_row_for(result, parsed) for result in results]


def _row_for(result: SearchResult, parsed: ParsedNaturalQuery) -> dict:
    evidence = _evidence_sentence(result.matched_text)
    matched_keywords = [keyword for keyword in parsed.expanded_keywords if keyword.lower() in evidence.lower()]
    return {
        "기술/키워드": ", ".join(matched_keywords[:5]) if matched_keywords else parsed.topic or UNKNOWN,
        "동향/시사점": evidence if _looks_like_trend(evidence) else UNKNOWN,
        "문서명": result.document_title or UNKNOWN,
        "페이지": result.display_page or str(result.page_no or "") or UNKNOWN,
        "챕터": result.chapter_title or UNKNOWN,
        "근거 문장": evidence or UNKNOWN,
        "신뢰도": _confidence(evidence, matched_keywords),
        "chunk_id": result.chunk_id,
    }


def _looks_like_trend(text: str) -> bool:
    return any(term in text for term in ("동향", "트렌드", "최신", "적용", "사례", "시사점", "기술"))


def _evidence_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ""
    sentences = re.split(r"(?:[.!?。]\s+|다\.\s+)", text, maxsplit=1)
    return sentences[0].strip() if sentences else text


def _confidence(evidence: str, matched_keywords: list[str]) -> str:
    score = 0.35 + (0.25 if evidence else 0.0) + min(len(matched_keywords), 4) * 0.08
    if _looks_like_trend(evidence):
        score += 0.1
    return f"{min(score, 0.95):.2f}"

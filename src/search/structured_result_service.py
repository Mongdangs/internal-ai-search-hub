from __future__ import annotations

from src.extraction.cost_extractor import extract_cost_rows
from src.extraction.evidence_extractor import extract_evidence_rows
from src.extraction.staff_extractor import extract_staff_rows
from src.extraction.technology_trend_extractor import extract_technology_trend_rows
from src.models import SearchResult
from src.search.nlu_query_parser import ParsedNaturalQuery


UNKNOWN = "확인 필요"


def build_structured_rows(results: list[SearchResult], parsed: ParsedNaturalQuery) -> list[dict]:
    if parsed.output_type == "staff_table":
        rows = extract_staff_rows(results, parsed.conditions)
    elif parsed.output_type == "cost_table":
        rows = extract_cost_rows(results, parsed)
    elif parsed.output_type in {"technology_table", "technology_trend_table"}:
        rows = extract_technology_trend_rows(results, parsed)
    else:
        rows = extract_evidence_rows(results, parsed)
    return [_with_common_fields(row, result, parsed) for row, result in zip(rows, results)]


def build_evidence_rows(results: list[SearchResult], parsed: ParsedNaturalQuery) -> list[dict]:
    rows = extract_evidence_rows(results, parsed)
    return [_with_common_fields(row, result, parsed) for row, result in zip(rows, results)]


def document_area(result: SearchResult) -> str:
    return (
        result.canonical_heading_path
        or result.heading_path
        or " > ".join(part for part in (result.canonical_chapter_title or result.chapter_title, result.section_title) if part)
        or UNKNOWN
    )


def _with_common_fields(row: dict, result: SearchResult, parsed: ParsedNaturalQuery) -> dict:
    enriched = dict(row)
    enriched.setdefault("프로젝트명", result.project_name or UNKNOWN)
    enriched.setdefault("고객기관", result.client_name or UNKNOWN)
    enriched.setdefault("문서명", result.document_title or UNKNOWN)
    enriched.setdefault("페이지", result.display_page or str(result.page_no or "") or UNKNOWN)
    enriched["문서영역"] = document_area(result)
    enriched["원본경로"] = result.raw_heading_path or result.heading_path or ""
    enriched["매칭 키워드"] = ", ".join(result.matched_keywords or _matched_expanded_keywords(result, parsed)) or UNKNOWN
    enriched["점수"] = round(float(result.score or 0.0), 4)
    enriched["chunk_id"] = result.chunk_id
    return enriched


def _matched_expanded_keywords(result: SearchResult, parsed: ParsedNaturalQuery) -> list[str]:
    haystack = " ".join(
        [
            result.document_title,
            result.project_name,
            result.client_name,
            result.canonical_heading_path,
            result.heading_path,
            result.domain_keywords,
            result.matched_text,
            result.parent_context,
        ]
    ).lower()
    return [keyword for keyword in parsed.expanded_keywords if keyword.lower() in haystack]

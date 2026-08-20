from __future__ import annotations

import json
from pathlib import Path

from src.models import SearchResult
from src.search.nlu_query_parser import parse_natural_query
from src.search.query_expander import expand_query
from src.search.reranker import rerank_results
from src.search.search_service import SearchService
from src.search.structured_result_service import document_area


QUALITY_TEST_QUERIES: tuple[str, ...] = (
    "목표모델에서 DR 관련 산출물 찾아줘",
    "목표 아키텍처에서 재해복구 관련 내용 찾아줘",
    "To-Be 인프라에서 RTO RPO 관련 내용 찾아줘",
    "목표시스템에서 이중화 방안 찾아줘",
    "정보기술동향에서 MSA 관련 내용 찾아줘",
    "기술 트렌드에서 마이크로서비스 관련 내용 찾아줘",
    "비용산정에서 클라우드 TCO 근거 찾아줘",
    "소요예산에서 클라우드 사용량 기반 비용 찾아줘",
    "투입인력에서 ISP 경험 있는 PM 찾아줘",
    "참여인력 주요경력에서 ISMP 경험자 찾아줘",
)


def run_search_quality_diagnostics(search_service: SearchService, data_dir: Path, top_k: int = 10) -> Path:
    report = {
        "queries": [],
    }
    for query in QUALITY_TEST_QUERIES:
        parsed = expand_query(parse_natural_query(query))
        candidate_top_k = max(top_k * 3, 30)
        candidates = search_service.search(parsed.semantic_query or query, top_k=candidate_top_k)
        results = rerank_results(parsed, candidates, top_k=top_k)
        report["queries"].append(
            {
                "query": query,
                "parsed_query": {
                    "search_domain": parsed.search_domain,
                    "target_chapter": parsed.target_chapter,
                    "target_section": parsed.target_section,
                    "target_subsection": parsed.target_subsection,
                    "expanded_keywords": parsed.expanded_keywords,
                    "confidence": parsed.confidence,
                },
                "results": [_result_row(rank, result, parsed.expanded_keywords) for rank, result in enumerate(results, start=1)],
            }
        )
    output_path = Path(data_dir) / "indexes" / "search_quality_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _result_row(rank: int, result: SearchResult, keywords: list[str]) -> dict:
    haystack = " ".join(
        [
            result.document_title,
            result.project_name,
            result.client_name,
            result.canonical_heading_path,
            result.heading_path,
            result.domain_keywords,
            result.matched_text,
        ]
    ).lower()
    matched = [keyword for keyword in keywords if keyword.lower() in haystack]
    missing = [keyword for keyword in keywords if keyword.lower() not in haystack]
    return {
        "rank": rank,
        "score": round(float(result.score or 0.0), 6),
        "keyword_score": round(float(result.keyword_score or 0.0), 6),
        "vector_score": round(float(result.vector_score or 0.0), 6),
        "project_name": result.project_name,
        "client_name": result.client_name,
        "document_title": result.document_title,
        "page": result.display_page or str(result.page_no),
        "canonical_heading_path": document_area(result),
        "matched_keywords": matched,
        "missing_keywords": missing[:20],
        "matched_text": result.matched_text,
    }

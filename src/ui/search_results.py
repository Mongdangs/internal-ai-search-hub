from __future__ import annotations


def result_rows(results) -> list[dict]:
    rows = []
    for rank, result in enumerate(results, start=1):
        keyword_coverage = getattr(result, "keyword_coverage", 0.0)
        missing_keywords = getattr(result, "missing_keywords", [])
        rows.append(
            {
                "순위": rank,
                "프로젝트명": result.project_name,
                "고객기관": result.client_name,
                "문서명": result.document_title,
                "표시 페이지": result.display_page or str(result.page_no),
                "물리 페이지": result.page_no,
                "챕터": getattr(result, "chapter_title", ""),
                "섹션": getattr(result, "section_title", ""),
                "경로": getattr(result, "heading_path", ""),
                "문서영역": getattr(result, "canonical_heading_path", "") or getattr(result, "heading_path", ""),
                "표 유형": getattr(result, "table_type", ""),
                "도메인 키워드": getattr(result, "domain_keywords", ""),
                "관련 문단": result.matched_text,
                "점수": round(result.score, 4),
                "문서 키워드": ", ".join(getattr(result, "document_keywords", [])),
                "키워드 일치율": round(keyword_coverage, 2),
                "매칭 키워드": ", ".join(result.matched_keywords),
                "누락 키워드": ", ".join(missing_keywords),
                "파일경로": result.file_path,
            }
        )
    return rows


def document_groups(results) -> list[dict]:
    groups = {}
    for result in results:
        key = result.document_id
        group = groups.setdefault(
            key,
            {
                "project_name": result.project_name,
                "client_name": result.client_name,
                "document_title": result.document_title,
                "document_id": result.document_id,
                "file_path": result.file_path,
                "score": result.score,
                "results": [],
            },
        )
        group["score"] = max(group["score"], result.score)
        group["results"].append(result)
    return sorted(groups.values(), key=lambda group: group["score"], reverse=True)


def preview_request(result) -> dict:
    return {
        "chunk_id": result.chunk_id,
        "file_path": result.file_path,
        "page_no": result.page_no,
        "display_page": result.display_page,
        "document_title": result.document_title,
        "project_name": result.project_name,
        "client_name": result.client_name,
        "matched_text": result.matched_text,
        "canonical_heading_path": getattr(result, "canonical_heading_path", ""),
        "raw_heading_path": getattr(result, "raw_heading_path", ""),
        "matched_keywords": ", ".join(getattr(result, "matched_keywords", [])),
    }

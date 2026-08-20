from __future__ import annotations

from collections import defaultdict

from src.models import SearchResult


def aggregate_by_project(results: list[SearchResult], top_k: int = 10) -> list[dict]:
    grouped: dict[str, list[SearchResult]] = defaultdict(list)
    for result in results:
        grouped[result.project_id].append(result)

    projects = []
    for project_results in grouped.values():
        project_results.sort(key=lambda item: item.score, reverse=True)
        best = project_results[0]
        pages = sorted({item.page_no for item in project_results if item.page_no})
        documents = []
        seen_docs = set()
        for item in project_results:
            if item.document_id in seen_docs:
                continue
            seen_docs.add(item.document_id)
            documents.append(item.document_title)
        projects.append(
            {
                "project_id": best.project_id,
                "project_name": best.project_name,
                "similarity_score": sum(item.score for item in project_results[:5]) / min(5, len(project_results)),
                "related_documents": ", ".join(documents[:5]),
                "pages": pages[:10],
                "matching_reasons": _matching_reasons(project_results[:3]),
                "usage_points": _usage_points(project_results[:3]),
            }
        )

    projects.sort(key=lambda item: item["similarity_score"], reverse=True)
    for rank, project in enumerate(projects[:top_k], start=1):
        project["rank"] = rank
    return projects[:top_k]


def _matching_reasons(results: list[SearchResult]) -> list[str]:
    reasons = []
    for result in results:
        keyword_text = ", ".join(result.matched_keywords[:5]) if result.matched_keywords else "핵심 키워드"
        reasons.append(f"{result.document_title} p.{result.page_no}에서 {keyword_text} 관련 내용이 매칭됨")
    return reasons


def _usage_points(results: list[SearchResult]) -> list[str]:
    points = []
    for result in results:
        points.append(f"p.{result.page_no} 문단을 제안 구조와 근거 문구 참고용으로 활용 가능")
    return points

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.db.database import Database
from src.db.repositories import SearchRepository
from src.search.chapter_filter import ChapterFilterNotFound
from src.search.query_parser import parse_search_query
from src.search.search_service import SearchService


TEST_QUERIES = (
    "목표모델에서 클라우드 관련 설계 내용을 찾아줘",
    "현황분석에서 데이터 용량 분석 관련 내용을 찾아줘",
    "기술동향분석에서 MSA에 관한 내용을 찾아줘",
    "요구사항 분석에서 SSO 관련 내용을 찾아줘",
    "이행계획에서 단계별 전환 로드맵을 찾아줘",
    "클라우드 관련 내용을 찾아줘",
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    config = load_config()
    db = Database(config.database_path)
    db.initialize()
    repository = SearchRepository(db)
    search_service = SearchService(config, repository)

    for query in TEST_QUERIES:
        parsed = parse_search_query(query)
        filters = {"source_scope": "all"}
        if parsed.chapter_filter:
            filters["chapter_filter"] = parsed.chapter_filter

        print("=" * 80)
        print(f"원본 질의: {query}")
        print(f"추출된 chapter_filter: {parsed.chapter_filter or '전체'}")
        print(f"추출된 semantic_query: {parsed.effective_query}")
        print(f"적용된 검색 범위: {parsed.chapter_filter or '전체'}")

        try:
            results = search_service.search(parsed.effective_query, top_k=3, filters=filters)
        except ChapterFilterNotFound as exc:
            print(f"검색 결과: {exc}")
            print(f"추천 챕터: {', '.join(exc.suggestions) if exc.suggestions else '-'}")
            continue

        if not results:
            print("검색 결과: 상위 결과가 없습니다.")
            continue

        for index, result in enumerate(results[:3], start=1):
            location = result.display_page or str(result.page_no)
            print(
                f"{index}. {result.document_title} p.{location} | "
                f"챕터={result.chapter_title or '-'} | 섹션={result.section_title or '-'} | "
                f"점수={result.score:.4f}"
            )
            print(f"   경로: {result.heading_path or '-'}")
            print(f"   발췌: {result.matched_text[:180]}")


if __name__ == "__main__":
    main()

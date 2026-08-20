from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.config import AppConfig
from src.db.repositories import SearchRepository
from src.models import RfpSearchResponse
from src.rfp.rfp_analyzer import RfpAnalyzer
from src.rfp.rfp_parser import RfpParser
from src.search.result_aggregator import aggregate_by_project
from src.search.search_service import SearchService


class RfpSearchService:
    def __init__(self, config: AppConfig, repository: SearchRepository, search_service: SearchService | None = None) -> None:
        self.config = config
        self.repository = repository
        self.search_service = search_service or SearchService(config, repository)
        self.parser = RfpParser()
        self.analyzer = RfpAnalyzer()

    def search_similar(self, rfp_path: str | Path, top_k: int = 20) -> RfpSearchResponse:
        text = self.parser.parse_text(rfp_path)
        summary = self.analyzer.summarize(text)
        queries = self.analyzer.build_weighted_queries(summary)
        best_results = {}
        for query, weight in queries:
            for result in self.search_service.search(query, top_k=top_k):
                weighted_result = replace(result, score=result.score * weight)
                previous = best_results.get(result.chunk_id)
                if previous is None or weighted_result.score > previous.score:
                    best_results[result.chunk_id] = weighted_result
        all_results = list(best_results.values())
        all_results.sort(key=lambda result: result.score, reverse=True)
        projects = aggregate_by_project(all_results, top_k=10)
        self.repository.log_search(str(rfp_path), "rfp", len(projects))
        return RfpSearchResponse(summary=summary, similar_projects=projects, results=all_results[: max(top_k, 20)])

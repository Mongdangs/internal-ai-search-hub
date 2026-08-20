from __future__ import annotations

from pathlib import Path

from src.config import AppConfig
from src.db.repositories import SearchRepository
from src.models import IndexSummary
from src.search.search_service import SearchService


class IndexManagementService:
    def __init__(self, config: AppConfig, repository: SearchRepository, search_service: SearchService | None = None) -> None:
        self.config = config
        self.repository = repository
        self.search_service = search_service or SearchService(config, repository)

    def rebuild(self, root_folders: list[str] | tuple[str, ...]) -> IndexSummary:
        return self.search_service.index_folder(root_folders, rebuild=True)

    def refresh(self, root_folders: list[str] | tuple[str, ...]) -> IndexSummary:
        return self.search_service.index_folder(root_folders, rebuild=False)

    def reindex_document(self, file_path: str | Path) -> IndexSummary:
        return self.search_service.reindex_document(file_path)

    def validate(self) -> dict:
        return self.search_service.validate_index()

    def stats(self) -> dict:
        return self.repository.stats()

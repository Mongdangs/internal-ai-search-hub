from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from src.config import load_config
from src.db.database import Database
from src.db.repositories import SearchRepository
from src.search.search_service import SearchService


def _service() -> SearchService:
    config = load_config()
    db = Database(config.database_path)
    db.initialize()
    repository = SearchRepository(db)
    return SearchService(config, repository)


def _summary_dict(summary) -> dict:
    return {
        "index_version": summary.index_version,
        "projects": summary.project_count,
        "documents": summary.document_count,
        "chunks": summary.chunk_count,
        "backup_path": summary.backup_path,
        "report_path": summary.report_path,
        "unsupported_files": summary.unsupported_files,
        "failed_documents": summary.failed_documents,
        "validation": summary.validation,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Safe chapter-aware reindexing")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Back up and rebuild every configured root folder")
    group.add_argument("--file", help="Back up and reindex one document")
    group.add_argument("--validate", action="store_true", help="Validate chapter/section metadata in the current index")
    args = parser.parse_args()

    service = _service()
    if args.validate:
        payload = service.validate_index()
    elif args.all:
        payload = _summary_dict(service.index_folder(service.config.root_folders, rebuild=True))
    else:
        payload = _summary_dict(service.reindex_document(Path(args.file)))

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

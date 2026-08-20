from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .config import load_config
from .db.database import Database
from .db.repositories import SearchRepository
from .search.rfp_search_service import RfpSearchService
from .search.search_service import SearchService


def _services():
    config = load_config()
    db = Database(config.database_path)
    db.initialize()
    repo = SearchRepository(db)
    search_service = SearchService(config, repo)
    return config, repo, search_service, RfpSearchService(config, repo, search_service)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Evidence search PoC")
    sub = parser.add_subparsers(dest="command", required=True)

    index_parser = sub.add_parser("index", help="Index a local folder")
    index_parser.add_argument("--root", required=True, nargs="+")
    index_parser.add_argument("--rebuild", action="store_true")

    search_parser = sub.add_parser("search", help="Search indexed chunks")
    search_parser.add_argument("query")
    search_parser.add_argument("--top-k", type=int, default=None)

    rfp_parser = sub.add_parser("rfp", help="Search similar deliverables for an RFP")
    rfp_parser.add_argument("path")
    rfp_parser.add_argument("--top-k", type=int, default=None)

    args = parser.parse_args()
    config, repo, search_service, rfp_service = _services()

    if args.command == "index":
        summary = search_service.index_folder(args.root, rebuild=args.rebuild)
        print(
            json.dumps(
                {
                    "projects": summary.project_count,
                    "documents": summary.document_count,
                    "chunks": summary.chunk_count,
                    "index_version": summary.index_version,
                    "backup_path": summary.backup_path,
                    "report_path": summary.report_path,
                    "unsupported_files": summary.unsupported_files,
                    "failed_documents": summary.failed_documents,
                    "validation": summary.validation,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "search":
        results = search_service.search(args.query, top_k=args.top_k or config.search.top_k)
        repo.log_search(args.query, "topic", len(results))
        print(json.dumps([result.to_dict(rank=i + 1) for i, result in enumerate(results)], ensure_ascii=False, indent=2))
    elif args.command == "rfp":
        response = rfp_service.search_similar(Path(args.path), top_k=args.top_k or config.search.top_k)
        print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

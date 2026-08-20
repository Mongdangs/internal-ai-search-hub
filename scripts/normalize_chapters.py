from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.db.database import Database
from src.db.repositories import SearchRepository
from src.ingestion.heading_extractor import (
    DEFAULT_CHAPTER_TITLE,
    build_heading_path,
    canonical_chapter,
    heading_search_norm,
    normalize_heading,
)
from src.indexing.index_metadata import utc_now
from src.search.search_service import SearchService
from src.utils.text_cleaner import clean_text


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    config = load_config()
    db = Database(config.database_path)
    db.initialize()
    repo = SearchRepository(db)

    changed = 0
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT chunk_id, chapter_title, section_title, heading_path
            FROM chunks
            """
        ).fetchall()
        for row in rows:
            chapter_title = _major_chapter(row["chapter_title"], row["section_title"], row["heading_path"])
            section_title = _section_title(row["section_title"], chapter_title)
            heading_path = build_heading_path(chapter_title, section_title) or chapter_title
            normalized_chapter = normalize_heading(chapter_title) or normalize_heading(DEFAULT_CHAPTER_TITLE)
            normalized_section = normalize_heading(section_title)
            normalized_heading = normalize_heading(heading_path) or normalized_chapter
            heading_norm = heading_search_norm(chapter_title, section_title, heading_path) or normalized_heading
            values = (
                chapter_title,
                chapter_title,
                normalized_chapter,
                section_title,
                normalized_section,
                heading_path,
                normalized_heading,
                heading_norm,
                row["chunk_id"],
            )
            conn.execute(
                """
                UPDATE chunks
                SET chapter_title = ?,
                    canonical_chapter_title = ?,
                    normalized_chapter_title = ?,
                    section_title = ?,
                    normalized_section_title = ?,
                    heading_path = ?,
                    normalized_heading_path = ?,
                    heading_norm = ?
                WHERE chunk_id = ?
                """,
                values,
            )
            changed += 1

    service = SearchService(config, repo)
    validation = service.validate_index()
    chapters = repo.chapter_report(limit=500)
    report_path = config.data_dir / "indexes" / "reindex_report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    else:
        report = {}
    report["chapter_normalized_at"] = utc_now()
    report["validation"] = validation
    report["chapters"] = chapters
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "updated_chunks": changed,
                "validation": validation,
                "chapters": chapters[:20],
                "report_path": str(report_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _major_chapter(chapter_title: str, section_title: str, heading_path: str) -> str:
    current = canonical_chapter(chapter_title)
    if current and current != DEFAULT_CHAPTER_TITLE:
        return current
    for value in (section_title, heading_path):
        canonical = canonical_chapter(value)
        if canonical and canonical != DEFAULT_CHAPTER_TITLE:
            return canonical
    return DEFAULT_CHAPTER_TITLE


def _section_title(section_title: str, chapter_title: str) -> str:
    section_title = clean_text(section_title or "")
    if not section_title:
        return ""
    if normalize_heading(section_title) == normalize_heading(chapter_title):
        return ""
    return section_title


if __name__ == "__main__":
    main()

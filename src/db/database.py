from __future__ import annotations

import sqlite3
from pathlib import Path

from src.utils.file_utils import ensure_parent


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        ensure_parent(self.path)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        with self.connect() as conn:
            conn.executescript(schema_path.read_text(encoding="utf-8"))
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()}
            for column, column_type in {
                "display_page": "TEXT",
                "source_file": "TEXT",
                "file_type": "TEXT",
                "page_range": "TEXT",
                "chunk_index": "INTEGER",
                "index_version": "TEXT",
                "chapter_title": "TEXT",
                "canonical_chapter_title": "TEXT",
                "normalized_chapter_title": "TEXT",
                "normalized_section_title": "TEXT",
                "heading_path": "TEXT",
                "normalized_heading_path": "TEXT",
                "heading_norm": "TEXT",
                "char_start": "INTEGER",
                "char_end": "INTEGER",
                "raw_chapter_title": "TEXT",
                "raw_section_title": "TEXT",
                "raw_heading_path": "TEXT",
                "canonical_section_title": "TEXT",
                "canonical_subsection_title": "TEXT",
                "canonical_heading_path": "TEXT",
                "heading_classification_confidence": "REAL",
                "heading_classification_reason": "TEXT",
                "table_type": "TEXT",
                "table_title": "TEXT",
                "table_headers": "TEXT",
                "table_row_text": "TEXT",
                "domain_keywords": "TEXT",
                "parent_chunk_id": "TEXT",
                "parent_context": "TEXT",
                "embedding_text": "TEXT",
            }.items():
                if column not in columns:
                    conn.execute(f"ALTER TABLE chunks ADD COLUMN {column} {column_type}")
            document_columns = {row["name"] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
            for column, column_type in {
                "canonical_key": "TEXT",
                "content_signature": "TEXT",
                "file_mtime": "REAL",
            }.items():
                if column not in document_columns:
                    conn.execute(f"ALTER TABLE documents ADD COLUMN {column} {column_type}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_canonical ON documents(project_id, canonical_key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_heading_norm ON chunks(heading_norm)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_index_version ON chunks(index_version)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_canonical_chapter ON chunks(canonical_chapter_title)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_canonical_section ON chunks(canonical_section_title)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_canonical_subsection ON chunks(canonical_subsection_title)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_canonical_heading_path ON chunks(canonical_heading_path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_table_type ON chunks(table_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_domain_keywords ON chunks(domain_keywords)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_normalized_heading ON chunks(normalized_heading_path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_saved_evidence_search ON saved_evidence(saved_search_id)")

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from difflib import SequenceMatcher

from src.ingestion.metadata_extractor import stable_id
from src.ingestion.heading_extractor import chapter_filter_norms, normalize_chapter_name
from src.indexing.document_dedup import DocumentProfile
from src.search.filters import active_file_path_prefixes, sql_like_patterns_for_prefix
from src.models import Chunk, DocumentMetadata, ProjectMetadata, SearchResult
from src.utils.korean_tokenizer import expand_domain_synonyms, matched_keywords, missing_keywords, tokenize, unique_tokens
from src.utils.page_label import extract_display_page_label
from src.utils.text_cleaner import trim_snippet

from .database import Database


class SearchRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def clear(self) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM chunk_fts")
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM documents")
            conn.execute("DELETE FROM projects")

    def upsert_project(self, project: ProjectMetadata) -> None:
        now = utc_now()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    project_id, project_name, client_name, year, business_type, domain,
                    folder_path, security_level, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    project_name = excluded.project_name,
                    client_name = excluded.client_name,
                    year = excluded.year,
                    business_type = excluded.business_type,
                    domain = excluded.domain,
                    folder_path = excluded.folder_path,
                    security_level = excluded.security_level
                """,
                (
                    project.project_id,
                    project.project_name,
                    project.client_name,
                    project.year,
                    project.business_type,
                    project.domain,
                    project.folder_path,
                    project.security_level,
                    now,
                ),
            )

    def upsert_document(self, document: DocumentMetadata) -> None:
        now = utc_now()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (
                    document_id, project_id, document_title, document_type, file_path,
                    file_type, file_name, version, is_final, indexed_at, access_acl,
                    canonical_key, content_signature, file_mtime
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    document_title = excluded.document_title,
                    document_type = excluded.document_type,
                    file_path = excluded.file_path,
                    file_type = excluded.file_type,
                    file_name = excluded.file_name,
                    version = excluded.version,
                    is_final = excluded.is_final,
                    indexed_at = excluded.indexed_at,
                    access_acl = excluded.access_acl,
                    canonical_key = excluded.canonical_key,
                    content_signature = excluded.content_signature,
                    file_mtime = excluded.file_mtime
                """,
                (
                    document.document_id,
                    document.project_id,
                    document.document_title,
                    document.document_type,
                    document.file_path,
                    document.file_type,
                    document.file_name,
                    document.version,
                    document.is_final,
                    now,
                    document.access_acl,
                    document.canonical_key,
                    document.content_signature,
                    document.file_mtime,
                ),
            )

    def document_exists(self, document_id: str) -> bool:
        with self.db.connect() as conn:
            row = conn.execute("SELECT 1 FROM documents WHERE document_id = ? LIMIT 1", (document_id,)).fetchone()
        return row is not None

    def document_ids(self) -> set[str]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT document_id FROM documents").fetchall()
        return {row["document_id"] for row in rows}

    def iter_document_profiles(self) -> list[DocumentProfile]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT document_id, project_id, canonical_key, content_signature, file_mtime
                FROM documents
                WHERE content_signature IS NOT NULL AND content_signature != ''
                """
            ).fetchall()
        return [
            DocumentProfile(
                document_id=row["document_id"],
                project_id=row["project_id"],
                canonical_key=row["canonical_key"] or "",
                content_signature=row["content_signature"] or "",
                file_mtime=float(row["file_mtime"] or 0.0),
            )
            for row in rows
        ]

    def delete_documents(self, document_ids: list[str]) -> list[str]:
        if not document_ids:
            return []
        with self.db.connect() as conn:
            chunk_ids: list[str] = []
            for batch in _batches(document_ids, 400):
                placeholders = ", ".join("?" for _ in batch)
                chunk_rows = conn.execute(
                    f"SELECT chunk_id FROM chunks WHERE document_id IN ({placeholders})",
                    batch,
                ).fetchall()
                chunk_ids.extend(row["chunk_id"] for row in chunk_rows)
            for batch in _batches(chunk_ids, 400):
                placeholders = ", ".join("?" for _ in batch)
                conn.execute(f"DELETE FROM chunk_fts WHERE chunk_id IN ({placeholders})", batch)
            for batch in _batches(document_ids, 400):
                placeholders = ", ".join("?" for _ in batch)
                conn.execute(f"DELETE FROM chunks WHERE document_id IN ({placeholders})", batch)
                conn.execute(f"DELETE FROM documents WHERE document_id IN ({placeholders})", batch)
        return chunk_ids

    def replace_chunks(self, document: DocumentMetadata, project: ProjectMetadata, chunks: list[Chunk]) -> None:
        now = utc_now()
        with self.db.connect() as conn:
            existing = conn.execute("SELECT chunk_id FROM chunks WHERE document_id = ?", (document.document_id,)).fetchall()
            for row in existing:
                conn.execute("DELETE FROM chunk_fts WHERE chunk_id = ?", (row["chunk_id"],))
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document.document_id,))
            for chunk in chunks:
                conn.execute(
                    """
                    INSERT INTO chunks (
                        chunk_id, document_id, project_id, source_file, file_type, page_no, display_page,
                        page_range, chunk_index, index_version, chapter_title, canonical_chapter_title,
                        normalized_chapter_title, section_title, normalized_section_title, heading_path,
                        normalized_heading_path, heading_norm, chunk_text, keywords, embedding_id,
                        token_count, char_start, char_end, raw_chapter_title, raw_section_title,
                        raw_heading_path, canonical_section_title, canonical_subsection_title,
                        canonical_heading_path, heading_classification_confidence,
                        heading_classification_reason, table_type, table_title, table_headers,
                        table_row_text, domain_keywords, parent_chunk_id, parent_context,
                        embedding_text, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.project_id,
                        chunk.source_file or document.file_name,
                        chunk.file_type or document.file_type,
                        chunk.page_no,
                        chunk.display_page,
                        chunk.page_range,
                        chunk.chunk_index,
                        chunk.index_version,
                        chunk.chapter_title,
                        chunk.canonical_chapter_title,
                        chunk.normalized_chapter_title,
                        chunk.section_title,
                        chunk.normalized_section_title,
                        chunk.heading_path,
                        chunk.normalized_heading_path,
                        chunk.heading_norm,
                        chunk.chunk_text,
                        chunk.keywords,
                        chunk.embedding_id or chunk.chunk_id,
                        chunk.token_count,
                        chunk.char_start,
                        chunk.char_end,
                        chunk.raw_chapter_title,
                        chunk.raw_section_title,
                        chunk.raw_heading_path,
                        chunk.canonical_section_title,
                        chunk.canonical_subsection_title,
                        chunk.canonical_heading_path,
                        chunk.heading_classification_confidence,
                        chunk.heading_classification_reason,
                        chunk.table_type,
                        chunk.table_title,
                        chunk.table_headers,
                        chunk.table_row_text,
                        chunk.domain_keywords,
                        chunk.parent_chunk_id,
                        chunk.parent_context,
                        chunk.embedding_text,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO chunk_fts (chunk_id, chunk_text, keywords, project_name, document_title)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        _fts_text(_chunk_fts_text(chunk, document, project)),
                        _fts_text(" ".join([chunk.keywords, chunk.domain_keywords])),
                        _fts_text(project.project_name),
                        _fts_text(document.document_title),
                    ),
                )

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> dict[str, sqlite3.Row]:
        if not chunk_ids:
            return {}
        placeholders = ", ".join("?" for _ in chunk_ids)
        query = f"""
            SELECT c.*, d.document_title, d.document_type, d.file_path, d.file_mtime, p.project_name, p.client_name
            FROM chunks c
            JOIN documents d ON c.document_id = d.document_id
            JOIN projects p ON c.project_id = p.project_id
            WHERE c.chunk_id IN ({placeholders})
        """
        with self.db.connect() as conn:
            rows = conn.execute(query, chunk_ids).fetchall()
        return {row["chunk_id"]: row for row in rows}

    def keyword_search(self, query: str, top_k: int = 20, filters: dict | None = None) -> dict[str, float]:
        try:
            return self._keyword_search_fts(query, top_k, filters)
        except sqlite3.OperationalError:
            return self._keyword_search_like(query, top_k, filters)

    def _keyword_search_fts(self, query: str, top_k: int, filters: dict | None) -> dict[str, float]:
        fts_query = build_fts_query(query)
        if not fts_query:
            return {}
        params: list[object] = [fts_query]
        where = "chunk_fts MATCH ?"
        where = _append_filters(where, params, filters)
        sql = f"""
            SELECT c.*,
                   d.document_title, p.project_name, bm25(chunk_fts) AS bm25_rank
            FROM chunk_fts
            JOIN chunks c ON chunk_fts.chunk_id = c.chunk_id
            JOIN documents d ON c.document_id = d.document_id
            JOIN projects p ON c.project_id = p.project_id
            WHERE {where}
            ORDER BY score
            LIMIT ?
        """
        params.append(top_k)
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        if not rows:
            return {}
        query_tokens = set(tokenize(query))
        raw_scores = []
        for rank, row in enumerate(rows, start=1):
            haystack = _coverage_haystack(row)
            coverage = _token_coverage(query_tokens, haystack)
            if coverage <= 0:
                continue
            raw_scores.append((row["chunk_id"], 1.0 / rank, coverage))
        if not raw_scores:
            return {}
        scored = [(chunk_id, rank_score * coverage) for chunk_id, rank_score, coverage in raw_scores]
        scored.sort(key=lambda item: item[1], reverse=True)
        return dict(scored[:top_k])

    def _keyword_search_like(self, query: str, top_k: int, filters: dict | None) -> dict[str, float]:
        tokens = _like_tokens(query)
        if not tokens:
            return {}
        params: list[object] = []
        clauses = []
        for token in tokens:
            clauses.append(
                "(c.chunk_text LIKE ? OR c.keywords LIKE ? OR c.chapter_title LIKE ? OR "
                "c.section_title LIKE ? OR c.heading_path LIKE ? OR d.document_title LIKE ? OR p.project_name LIKE ?)"
            )
            like = f"%{token}%"
            params.extend([like, like, like, like, like, like, like])
        where = " OR ".join(clauses)
        where = _append_filters(where, params, filters)
        sql = f"""
            SELECT c.*,
                   d.document_title, p.project_name
            FROM chunks c
            JOIN documents d ON c.document_id = d.document_id
            JOIN projects p ON c.project_id = p.project_id
            WHERE {where}
        """
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        scores = []
        for row in rows:
            scores.append((row["chunk_id"], _token_coverage(set(tokens), _coverage_haystack(row))))
        scores.sort(key=lambda item: item[1], reverse=True)
        return dict(scores[:top_k])

    def all_chunk_texts(self) -> list[tuple[str, str]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT chunk_id, chunk_text FROM chunks").fetchall()
        return [(row["chunk_id"], row["chunk_text"]) for row in rows]

    def make_search_result(self, row, score: float, keyword_score: float, vector_score: float, query: str) -> SearchResult:
        haystack = _coverage_haystack(row)
        matched = matched_keywords(query, haystack)
        missing = missing_keywords(query, haystack)
        token_count = len(unique_tokens(query))
        display_page = row["display_page"] if "display_page" in row.keys() else ""
        display_page = display_page or extract_display_page_label(row["chunk_text"], row["page_no"])
        return SearchResult(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            project_id=row["project_id"],
            project_name=row["project_name"],
            client_name=row["client_name"] or "",
            document_title=row["document_title"],
            document_type=row["document_type"],
            file_path=row["file_path"],
            page_no=int(row["page_no"] or 0),
            display_page=str(display_page),
            matched_text=trim_snippet(row["chunk_text"]),
            score=score,
            keyword_score=keyword_score,
            vector_score=vector_score,
            matched_keywords=matched,
            missing_keywords=missing,
            keyword_coverage=(len(matched) / token_count) if token_count else 0.0,
            document_keywords=_split_keywords(row["keywords"]),
            source_file=(row["source_file"] if "source_file" in row.keys() else "") or row["file_path"].split("\\")[-1],
            chapter_title=(row["chapter_title"] if "chapter_title" in row.keys() else "") or "",
            section_title=(row["section_title"] if "section_title" in row.keys() else "") or "",
            heading_path=(row["heading_path"] if "heading_path" in row.keys() else "") or "",
            canonical_chapter_title=(row["canonical_chapter_title"] if "canonical_chapter_title" in row.keys() else "") or "",
            canonical_section_title=(row["canonical_section_title"] if "canonical_section_title" in row.keys() else "") or "",
            canonical_subsection_title=(row["canonical_subsection_title"] if "canonical_subsection_title" in row.keys() else "") or "",
            canonical_heading_path=(row["canonical_heading_path"] if "canonical_heading_path" in row.keys() else "") or "",
            raw_heading_path=(row["raw_heading_path"] if "raw_heading_path" in row.keys() else "") or "",
            normalized_chapter_title=(row["normalized_chapter_title"] if "normalized_chapter_title" in row.keys() else "") or "",
            normalized_section_title=(row["normalized_section_title"] if "normalized_section_title" in row.keys() else "") or "",
            normalized_heading_path=(row["normalized_heading_path"] if "normalized_heading_path" in row.keys() else "") or "",
            table_type=(row["table_type"] if "table_type" in row.keys() else "") or "",
            domain_keywords=(row["domain_keywords"] if "domain_keywords" in row.keys() else "") or "",
            parent_context=(row["parent_context"] if "parent_context" in row.keys() else "") or "",
            heading_classification_confidence=float(row["heading_classification_confidence"] or 0.0)
            if "heading_classification_confidence" in row.keys()
            else 0.0,
            page_range=(row["page_range"] if "page_range" in row.keys() else "") or "",
            chunk_index=int(row["chunk_index"] or 0) if "chunk_index" in row.keys() else 0,
            index_version=(row["index_version"] if "index_version" in row.keys() else "") or "",
        )

    def log_search(self, query_text: str, query_type: str, result_count: int) -> None:
        log_id = stable_id(f"{query_type}:{query_text}:{utc_now()}", "log")
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO search_logs (log_id, query_text, query_type, result_count, created_at) VALUES (?, ?, ?, ?, ?)",
                (log_id, query_text, query_type, result_count, utc_now()),
            )

    def save_search(self, query_text: str, parsed_query_json: str, result_count: int) -> str:
        saved_search_id = stable_id(f"saved:{query_text}:{utc_now()}", "ss")
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO saved_searches (saved_search_id, query_text, parsed_query_json, result_count, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (saved_search_id, query_text, parsed_query_json, result_count, utc_now()),
            )
        return saved_search_id

    def save_evidence(self, saved_search_id: str, result: SearchResult, note: str = "") -> str:
        evidence_id = stable_id(f"evidence:{saved_search_id}:{result.chunk_id}:{utc_now()}", "ev")
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO saved_evidence (evidence_id, saved_search_id, chunk_id, document_id, page_no, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (evidence_id, saved_search_id, result.chunk_id, result.document_id, result.page_no, note, utc_now()),
            )
        return evidence_id

    def stats(self) -> dict:
        with self.db.connect() as conn:
            projects = conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]
            documents = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
            chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
            logs = conn.execute("SELECT COUNT(*) AS n FROM search_logs").fetchone()["n"]
        return {"projects": projects, "documents": documents, "chunks": chunks, "search_logs": logs}

    def has_heading_metadata(self, filters: dict | None = None) -> bool:
        params: list[object] = []
        where = (
            "(c.chapter_title IS NOT NULL AND c.chapter_title != '' "
            "AND c.heading_path IS NOT NULL AND c.heading_path != '' "
            "AND c.heading_norm IS NOT NULL AND c.heading_norm != '')"
        )
        where = _append_filters(where, params, _filters_without_chapter(filters))
        sql = f"""
            SELECT 1
            FROM chunks c
            JOIN documents d ON c.document_id = d.document_id
            JOIN projects p ON c.project_id = p.project_id
            WHERE {where}
            LIMIT 1
        """
        with self.db.connect() as conn:
            return conn.execute(sql, params).fetchone() is not None

    def has_chapter_matches(self, chapter_norms: list[str], filters: dict | None = None) -> bool:
        if not chapter_norms:
            return False
        params: list[object] = []
        where = _chapter_where(chapter_norms, params)
        where = _append_filters(where, params, _filters_without_chapter(filters))
        sql = f"""
            SELECT 1
            FROM chunks c
            JOIN documents d ON c.document_id = d.document_id
            JOIN projects p ON c.project_id = p.project_id
            WHERE {where}
            LIMIT 1
        """
        with self.db.connect() as conn:
            return conn.execute(sql, params).fetchone() is not None

    def chapter_names(self, filters: dict | None = None, limit: int = 300) -> list[str]:
        params: list[object] = []
        where = "(COALESCE(NULLIF(c.canonical_chapter_title, ''), NULLIF(c.chapter_title, ''), '기타') != '')"
        where = _append_filters(where, params, _filters_without_chapter(filters))
        sql = f"""
            SELECT COALESCE(NULLIF(c.canonical_chapter_title, ''), NULLIF(c.chapter_title, ''), '기타') AS chapter_title,
                   COUNT(*) AS n
            FROM chunks c
            JOIN documents d ON c.document_id = d.document_id
            JOIN projects p ON c.project_id = p.project_id
            WHERE {where}
            GROUP BY chapter_title
            ORDER BY n DESC, chapter_title
            LIMIT ?
        """
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [row["chapter_title"] for row in rows if row["chapter_title"]]

    def suggest_chapters(self, chapter_filter: str, filters: dict | None = None, limit: int = 5) -> list[str]:
        target_norms = chapter_filter_norms(chapter_filter) or [normalize_chapter_name(chapter_filter)]
        suggestions: list[tuple[str, float]] = []
        for chapter in self.chapter_names(filters, limit=500):
            chapter_norm = normalize_chapter_name(chapter)
            score = max((SequenceMatcher(None, target, chapter_norm).ratio() for target in target_norms), default=0.0)
            if any(target and (target in chapter_norm or chapter_norm in target) for target in target_norms):
                score = max(score, 0.92)
            suggestions.append((chapter, score))
        suggestions.sort(key=lambda item: item[1], reverse=True)
        return [chapter for chapter, score in suggestions[:limit] if score >= 0.2]

    def chapter_report(self, filters: dict | None = None, limit: int = 500) -> list[dict]:
        params: list[object] = []
        where = "1 = 1"
        where = _append_filters(where, params, _filters_without_chapter(filters))
        sql = f"""
            SELECT
                COALESCE(NULLIF(c.canonical_chapter_title, ''), NULLIF(c.chapter_title, ''), '기타') AS chapter,
                COUNT(*) AS chunk_count,
                COUNT(DISTINCT c.document_id) AS document_count,
                MIN(c.page_no) AS first_page,
                MAX(c.page_no) AS last_page
            FROM chunks c
            JOIN documents d ON c.document_id = d.document_id
            JOIN projects p ON c.project_id = p.project_id
            WHERE {where}
            GROUP BY chapter
            ORDER BY chunk_count DESC, chapter
            LIMIT ?
        """
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "chapter": row["chapter"],
                "document_count": int(row["document_count"] or 0),
                "chunk_count": int(row["chunk_count"] or 0),
                "page_range": f"{row['first_page'] or ''}-{row['last_page'] or ''}",
            }
            for row in rows
        ]

    def heading_tree(self, filters: dict | None = None) -> list[dict]:
        levels = [
            (1, "COALESCE(NULLIF(c.canonical_chapter_title, ''), NULLIF(c.chapter_title, ''), '기타')"),
            (2, "COALESCE(NULLIF(c.canonical_section_title, ''), NULLIF(c.section_title, ''), '')"),
            (3, "COALESCE(NULLIF(c.canonical_subsection_title, ''), '')"),
        ]
        tree: list[dict] = []
        with self.db.connect() as conn:
            for level, expression in levels:
                params: list[object] = []
                where = f"{expression} != ''"
                where = _append_filters(where, params, _filters_without_chapter(filters))
                sql = f"""
                    SELECT
                        {expression} AS label,
                        COUNT(*) AS chunk_count,
                        COUNT(DISTINCT c.document_id) AS document_count,
                        COUNT(DISTINCT c.document_id || ':' || c.page_no) AS page_count,
                        GROUP_CONCAT(c.domain_keywords, ',') AS keyword_blob
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.document_id
                    JOIN projects p ON c.project_id = p.project_id
                    WHERE {where}
                    GROUP BY label
                    ORDER BY chunk_count DESC, label
                    LIMIT 200
                """
                rows = conn.execute(sql, params).fetchall()
                for row in rows:
                    label = row["label"] or ""
                    if not label:
                        continue
                    tree.append(
                        {
                            "label": label,
                            "level": level,
                            "document_count": int(row["document_count"] or 0),
                            "chunk_count": int(row["chunk_count"] or 0),
                            "page_count": int(row["page_count"] or 0),
                            "top_keywords": _top_keywords(row["keyword_blob"] or ""),
                        }
                    )
        return tree

    def validate_index_metadata(self, expected_index_version: str) -> dict:
        with self.db.connect() as conn:
            total_chunks = _scalar(conn, "SELECT COUNT(*) FROM chunks")
            total_documents = _scalar(conn, "SELECT COUNT(*) FROM documents")
            heading_chunks = _scalar(
                conn,
                """
                SELECT COUNT(*) FROM chunks
                WHERE COALESCE(chapter_title, '') != ''
                  AND COALESCE(heading_path, '') != ''
                  AND COALESCE(heading_norm, '') != ''
                """,
            )
            missing_chapter = _scalar(conn, "SELECT COUNT(*) FROM chunks WHERE COALESCE(chapter_title, '') = ''")
            missing_heading_path = _scalar(conn, "SELECT COUNT(*) FROM chunks WHERE COALESCE(heading_path, '') = ''")
            canonical_chapter_missing = _scalar(
                conn,
                "SELECT COUNT(*) FROM chunks WHERE COALESCE(canonical_chapter_title, '') = ''",
            )
            canonical_section_missing = _scalar(
                conn,
                "SELECT COUNT(*) FROM chunks WHERE COALESCE(canonical_section_title, '') = ''",
            )
            canonical_heading_path_missing = _scalar(
                conn,
                "SELECT COUNT(*) FROM chunks WHERE COALESCE(canonical_heading_path, '') = ''",
            )
            low_confidence_heading = _scalar(
                conn,
                """
                SELECT COUNT(*) FROM chunks
                WHERE COALESCE(heading_classification_confidence, 0) > 0
                  AND COALESCE(heading_classification_confidence, 0) < 0.72
                """,
            )
            table_chunk_count = _scalar(conn, "SELECT COUNT(*) FROM chunks WHERE COALESCE(table_type, '') != ''")
            staff_chunk_count = _scalar(conn, "SELECT COUNT(*) FROM chunks WHERE table_type = 'staff' OR domain_keywords LIKE '%STAFF%'")
            cost_chunk_count = _scalar(conn, "SELECT COUNT(*) FROM chunks WHERE table_type = 'cost' OR domain_keywords LIKE '%CLOUD_COST%'")
            vector_missing_chunk_count = _scalar(conn, "SELECT COUNT(*) FROM chunks WHERE COALESCE(embedding_id, '') = ''")
            missing_normalized_heading = _scalar(
                conn,
                "SELECT COUNT(*) FROM chunks WHERE COALESCE(normalized_heading_path, '') = ''",
            )
            missing_heading_norm = _scalar(conn, "SELECT COUNT(*) FROM chunks WHERE COALESCE(heading_norm, '') = ''")
            other_chunks = _scalar(conn, "SELECT COUNT(*) FROM chunks WHERE chapter_title = '기타'")
            version_mismatch = _scalar(
                conn,
                "SELECT COUNT(*) FROM chunks WHERE COALESCE(index_version, '') != ?",
                (expected_index_version,),
            )
            distinct_chapters = _scalar(
                conn,
                """
                SELECT COUNT(DISTINCT COALESCE(NULLIF(canonical_chapter_title, ''), NULLIF(chapter_title, ''), '기타'))
                FROM chunks
                """,
            )
            chapter_distribution = _distribution(conn, "COALESCE(NULLIF(canonical_chapter_title, ''), NULLIF(chapter_title, ''), '기타')")
            section_distribution = _distribution(conn, "COALESCE(NULLIF(canonical_section_title, ''), NULLIF(section_title, ''), '기타')")
            subsection_distribution = _distribution(conn, "COALESCE(NULLIF(canonical_subsection_title, ''), '기타')")
            low_confidence_examples = conn.execute(
                """
                SELECT document_id, page_no, raw_heading_path, canonical_heading_path,
                       heading_classification_confidence, heading_classification_reason
                FROM chunks
                WHERE COALESCE(heading_classification_confidence, 0) > 0
                  AND COALESCE(heading_classification_confidence, 0) < 0.72
                LIMIT 10
                """
            ).fetchall()
        metadata_ready = (
            total_chunks > 0
            and heading_chunks == total_chunks
            and missing_chapter == 0
            and missing_heading_path == 0
            and missing_normalized_heading == 0
            and missing_heading_norm == 0
            and version_mismatch == 0
        )
        return {
            "expected_index_version": expected_index_version,
            "metadata_ready": metadata_ready,
            "documents": total_documents,
            "chunks": total_chunks,
            "chunks_with_heading_metadata": heading_chunks,
            "missing_chapter_title": missing_chapter,
            "missing_heading_path": missing_heading_path,
            "canonical_chapter_missing_count": canonical_chapter_missing,
            "canonical_section_missing_count": canonical_section_missing,
            "canonical_heading_path_missing_count": canonical_heading_path_missing,
            "heading_classification_low_confidence_count": low_confidence_heading,
            "table_chunk_count": table_chunk_count,
            "staff_chunk_count": staff_chunk_count,
            "cost_chunk_count": cost_chunk_count,
            "vector_missing_chunk_count": vector_missing_chunk_count,
            "missing_heading_norm": missing_heading_norm,
            "missing_normalized_heading_path": missing_normalized_heading,
            "other_chunks": other_chunks,
            "index_version_mismatch_chunks": version_mismatch,
            "distinct_chapters": distinct_chapters,
            "chapter_distribution": chapter_distribution,
            "section_distribution": section_distribution,
            "subsection_distribution": subsection_distribution,
            "low_confidence_heading_examples": [dict(row) for row in low_confidence_examples],
            "reindex_required": not metadata_ready,
        }


def build_fts_query(query: str) -> str:
    tokens = tokenize(query)
    safe_tokens = []
    if _has_rnd_expression(query):
        safe_tokens.append("r d")
    for token in tokens:
        normalized = re.sub(r'["]', "", token)
        normalized = re.sub(r"[^\w가-힣+#.-]+", " ", normalized).strip()
        if normalized:
            safe_tokens.append(normalized)
    return " OR ".join(f'"{token}"' for token in _unique(safe_tokens))


def _like_tokens(query: str) -> list[str]:
    tokens = unique_tokens(query)
    if _has_rnd_expression(query):
        tokens.append("r&d")
    return _unique(tokens)


def _has_rnd_expression(query: str) -> bool:
    return bool(re.search(r"(?i)\b(?:r\s*&\s*d|r\s*[-_/]\s*d|rnd)\b", query or ""))


def _coverage_haystack(row) -> str:
    parts = [
        _row_value(row, "chunk_text"),
        _row_value(row, "keywords"),
        _row_value(row, "domain_keywords"),
        _row_value(row, "chapter_title"),
        _row_value(row, "canonical_chapter_title"),
        _row_value(row, "canonical_section_title"),
        _row_value(row, "canonical_subsection_title"),
        _row_value(row, "canonical_heading_path"),
        _row_value(row, "raw_heading_path"),
        _row_value(row, "normalized_chapter_title"),
        _row_value(row, "section_title"),
        _row_value(row, "normalized_section_title"),
        _row_value(row, "heading_path"),
        _row_value(row, "normalized_heading_path"),
        _row_value(row, "table_headers"),
        _row_value(row, "table_row_text"),
        _row_value(row, "parent_context"),
        _row_value(row, "document_title"),
        _row_value(row, "project_name"),
    ]
    return expand_domain_synonyms(" ".join(parts)).lower()


def _chunk_fts_text(chunk: Chunk, document: DocumentMetadata, project: ProjectMetadata) -> str:
    return "\n".join(
        value
        for value in (
            chunk.chunk_text,
            chunk.keywords,
            chunk.domain_keywords,
            project.project_name,
            project.client_name,
            document.document_title,
            document.file_name,
            chunk.chapter_title,
            chunk.section_title,
            chunk.heading_path,
            chunk.canonical_chapter_title,
            chunk.canonical_section_title,
            chunk.canonical_subsection_title,
            chunk.canonical_heading_path,
            chunk.raw_heading_path,
            chunk.table_headers,
            chunk.table_row_text,
            chunk.parent_context,
        )
        if value
    )


def _fts_text(text: str) -> str:
    return expand_domain_synonyms(text or "")


def _token_coverage(query_tokens: set[str], haystack: str) -> float:
    if not query_tokens:
        return 0.0
    hit_count = sum(1 for token in query_tokens if token in haystack)
    return hit_count / len(query_tokens)


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def _append_filters(where: str, params: list[object], filters: dict | None) -> str:
    if not filters:
        return where
    clauses = [where]
    if filters.get("document_type"):
        clauses.append("d.document_type = ?")
        params.append(filters["document_type"])
    chapter_norms = filters.get("chapter_norms") or []
    if chapter_norms:
        clauses.append(_chapter_where(chapter_norms, params))
    prefixes = active_file_path_prefixes(filters)
    if prefixes:
        path_clauses = []
        for prefix in prefixes:
            for pattern in sql_like_patterns_for_prefix(str(prefix)):
                path_clauses.append("d.file_path LIKE ?")
                params.append(pattern)
        clauses.append("(" + " OR ".join(path_clauses) + ")")
    return " AND ".join(f"({clause})" if " OR " in clause and not clause.startswith("(") else clause for clause in clauses)


def _chapter_where(chapter_norms: list[str], params: list[object]) -> str:
    clauses = []
    for norm in chapter_norms:
        if not norm:
            continue
        clauses.append(
            "("
            "c.normalized_chapter_title LIKE ? OR "
            "c.canonical_chapter_title LIKE ? OR "
            "REPLACE(c.canonical_section_title, ' ', '') LIKE ? OR "
            "REPLACE(c.canonical_subsection_title, ' ', '') LIKE ? OR "
            "REPLACE(c.canonical_heading_path, ' ', '') LIKE ? OR "
            "REPLACE(c.raw_heading_path, ' ', '') LIKE ? OR "
            "c.normalized_heading_path LIKE ?"
            ")"
        )
        like = f"%{norm}%"
        params.extend([like, like, like, like, like, like, like])
    if not clauses:
        return "1 = 0"
    return "(" + " OR ".join(clauses) + ")"


def _filters_without_chapter(filters: dict | None) -> dict | None:
    if not filters:
        return None
    copied = dict(filters)
    copied.pop("chapter_filter", None)
    copied.pop("chapter_norms", None)
    return copied


def _row_value(row, key: str) -> str:
    try:
        if key not in row.keys():
            return ""
        return str(row[key] or "")
    except Exception:
        return ""


def _batches(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return 0
    return int(row[0] or 0)


def _distribution(conn: sqlite3.Connection, expression: str, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        f"""
        SELECT {expression} AS label, COUNT(*) AS chunk_count, COUNT(DISTINCT document_id) AS document_count
        FROM chunks
        GROUP BY label
        ORDER BY chunk_count DESC, label
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "label": row["label"],
            "chunk_count": int(row["chunk_count"] or 0),
            "document_count": int(row["document_count"] or 0),
        }
        for row in rows
    ]


def _top_keywords(blob: str, limit: int = 5) -> list[str]:
    counts: dict[str, int] = {}
    for value in re.split(r"[,;\s]+", blob or ""):
        keyword = value.strip()
        if not keyword:
            continue
        counts[keyword] = counts.get(keyword, 0) + 1
    return [keyword for keyword, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]]


def _split_keywords(text: str) -> list[str]:
    return [keyword.strip() for keyword in (text or "").split(",") if keyword.strip()]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

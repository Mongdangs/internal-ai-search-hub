from __future__ import annotations

from pathlib import Path
import sys
from collections import Counter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.db.database import Database
from src.indexing.design_keywords import target_model_design_keywords
from src.utils.korean_tokenizer import expand_domain_synonyms


BATCH_SIZE = 1000
COMMON_DOC_RATIO = 0.7


def main() -> None:
    config = load_config()
    db = Database(config.database_path)
    db.initialize()
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT c.chunk_id, c.section_title, c.chunk_text,
                   d.document_id, d.document_title, d.file_name, d.file_path, p.project_name, p.client_name
            FROM chunks c
            JOIN documents d ON c.document_id = d.document_id
            JOIN projects p ON c.project_id = p.project_id
            """
        ).fetchall()
        documents: dict[str, dict] = {}
        for row in rows:
            item = documents.setdefault(
                row["document_id"],
                {
                    "chunk_ids": [],
                    "texts": [],
                    "context": " ".join(
                        [
                            row["project_name"] or "",
                            row["client_name"] or "",
                            row["document_title"] or "",
                            row["file_name"] or "",
                            row["file_path"] or "",
                        ]
                    ),
                },
            )
            item["chunk_ids"].append(row["chunk_id"])
            item["texts"].append(row["chunk_text"] or "")

        raw_keywords: dict[str, list[str]] = {}
        frequencies: Counter[str] = Counter()
        for document_id, item in documents.items():
            keywords = target_model_design_keywords("\n".join(item["texts"]), context=item["context"])
            raw_keywords[document_id] = keywords
            frequencies.update(set(keywords))

        common_cutoff = max(5, int(len(documents) * COMMON_DOC_RATIO))
        common_keywords = {keyword for keyword, count in frequencies.items() if count >= common_cutoff}

        batch: list[tuple[str, str]] = []
        updated = 0
        for document_id, item in documents.items():
            keywords = ", ".join(keyword for keyword in raw_keywords[document_id] if keyword not in common_keywords)
            for chunk_id in item["chunk_ids"]:
                batch.append((keywords, chunk_id))
                updated += 1
            if len(batch) >= BATCH_SIZE:
                conn.executemany("UPDATE chunks SET keywords = ? WHERE chunk_id = ?", batch)
                conn.commit()
                print(f"updated_chunks: {updated}/{len(rows)}", flush=True)
                batch.clear()
        if batch:
            conn.executemany("UPDATE chunks SET keywords = ? WHERE chunk_id = ?", batch)
            conn.commit()
        conn.execute("DELETE FROM chunk_fts")
        fts_rows = conn.execute(
            """
            SELECT c.chunk_id, c.chunk_text, c.keywords, p.project_name, d.document_title
            FROM chunks c
            JOIN documents d ON c.document_id = d.document_id
            JOIN projects p ON c.project_id = p.project_id
            """
        ).fetchall()
        conn.executemany(
            """
            INSERT INTO chunk_fts (chunk_id, chunk_text, keywords, project_name, document_title)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    row["chunk_id"],
                    expand_domain_synonyms(row["chunk_text"] or ""),
                    expand_domain_synonyms(row["keywords"] or ""),
                    expand_domain_synonyms(row["project_name"] or ""),
                    expand_domain_synonyms(row["document_title"] or ""),
                )
                for row in fts_rows
            ],
        )
        conn.commit()
    print(f"updated_chunks: {len(rows)}")
    print(f"common_keywords_removed: {', '.join(sorted(common_keywords))}")


if __name__ == "__main__":
    main()

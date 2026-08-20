from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.db.database import Database
from src.db.repositories import SearchRepository
from src.utils.file_utils import is_old_path, is_reference_path


def main() -> None:
    config = load_config()
    db = Database(config.database_path)
    db.initialize()
    repo = SearchRepository(db)

    with db.connect() as conn:
        rows = conn.execute("SELECT document_id, file_path FROM documents").fetchall()
    supported = tuple(config.indexing.supported_extensions)
    document_ids = [
        row["document_id"]
        for row in rows
        if is_old_path(Path(row["file_path"]))
        or is_reference_path(Path(row["file_path"]))
        or Path(row["file_path"]).suffix.lower() not in supported
    ]
    chunk_ids = repo.delete_documents(document_ids)
    print(f"removed_documents: {len(document_ids)}")
    print(f"removed_chunks: {len(chunk_ids)}")
    print("note: orphan vectors are ignored at search time and will be removed on the next full vector rebuild.")


if __name__ == "__main__":
    main()

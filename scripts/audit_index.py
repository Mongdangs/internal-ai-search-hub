from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.db.database import Database
from src.utils.file_utils import has_exclude_pattern, is_old_path, is_reference_path, is_temp_or_hidden


def main() -> None:
    config = load_config()
    db = Database(config.database_path)
    db.initialize()
    supported = tuple(config.indexing.supported_extensions)
    with db.connect() as conn:
        for root in config.root_folders:
            root_path = Path(root)
            indexed_paths = {
                row["file_path"]
                for row in conn.execute(
                    "SELECT file_path FROM documents WHERE file_path LIKE ?",
                    (str(root_path).rstrip("\\/") + "%",),
                )
            }
            files = []
            excluded = 0
            for path in root_path.rglob("*"):
                if not path.is_file() or is_temp_or_hidden(path):
                    continue
                if is_old_path(path) or is_reference_path(path):
                    excluded += 1
                    continue
                if path.suffix.lower() not in supported:
                    continue
                if has_exclude_pattern(path, config.security.exclude_patterns):
                    excluded += 1
                    continue
                files.append(path.resolve())
            candidate_paths = [str(path) for path in files]
            missing = [path for path in candidate_paths if path not in indexed_paths]
            print(f"root: {root}")
            print(f"supported_files_after_exclusions: {len(files)}")
            print(f"excluded_by_policy: {excluded}")
            print("content_duplicates_skipped: checked_during_learning")
            print(f"learning_candidates: {len(candidate_paths)}")
            print(f"indexed_documents: {len(indexed_paths)}")
            print(f"missing_documents: {len(missing)}")
            for path in missing[:20]:
                print(f"missing: {path}")
            print()


if __name__ == "__main__":
    main()

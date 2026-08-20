from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.db.database import Database
from src.db.repositories import utc_now
from src.ingestion.metadata_extractor import MetadataExtractor


def main() -> None:
    config = load_config()
    db = Database(config.database_path)
    db.initialize()
    updated = 0
    with db.connect() as conn:
        rows = conn.execute("SELECT project_id, folder_path FROM projects").fetchall()
        for row in rows:
            folder_path = Path(row["folder_path"])
            if not folder_path:
                continue
            root = folder_path.parent
            project = MetadataExtractor(root).project_for(folder_path / "__metadata_probe__.pdf")
            conn.execute(
                """
                UPDATE projects
                SET project_name = ?, client_name = ?, year = ?, business_type = ?, folder_path = ?, created_at = ?
                WHERE project_id = ?
                """,
                (
                    project.project_name,
                    project.client_name,
                    project.year,
                    project.business_type,
                    project.folder_path,
                    utc_now(),
                    row["project_id"],
                ),
            )
            updated += 1
    print(f"updated projects: {updated}")


if __name__ == "__main__":
    main()

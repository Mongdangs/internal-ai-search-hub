from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INDEX_VERSION = "hierarchy-embedding-v2"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_existing_index(data_dir: Path) -> Path:
    """Back up the SQLite database and vector index before destructive rebuilds."""
    data_dir = Path(data_dir)
    backup_base = data_dir / "backups" / f"index_backup_{timestamp()}"
    backup_root = backup_base
    suffix = 1
    while backup_root.exists():
        suffix += 1
        backup_root = backup_base.with_name(f"{backup_base.name}_{suffix}")
    backup_root.mkdir(parents=True, exist_ok=False)

    copied: list[dict[str, str]] = []
    for name in ("db", "indexes"):
        source = data_dir / name
        if not source.exists():
            continue
        target = backup_root / name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        copied.append({"source": str(source), "target": str(target)})

    manifest = {
        "created_at": utc_now(),
        "index_version": INDEX_VERSION,
        "data_dir": str(data_dir),
        "copied": copied,
    }
    (backup_root / "backup_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return backup_root


def write_reindex_report(data_dir: Path, report: dict[str, Any]) -> Path:
    report_path = Path(data_dir) / "indexes" / "reindex_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path

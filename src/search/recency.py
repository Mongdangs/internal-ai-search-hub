from __future__ import annotations

from pathlib import Path


def file_mtime(path: str) -> float:
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0.0


def recency_boost(mtime: float, candidate_mtimes: list[float], max_boost: float = 1.15) -> float:
    available = [value for value in candidate_mtimes if value > 0]
    if not mtime or len(available) < 2:
        return 1.0
    oldest = min(available)
    newest = max(available)
    if newest <= oldest:
        return 1.0
    normalized = (mtime - oldest) / (newest - oldest)
    normalized = max(0.0, min(1.0, normalized))
    return 1.0 + (max_boost - 1.0) * normalized

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


ALL_SCOPE = "all"
PROPOSAL_SCOPE = "proposal"
REPORT_SCOPE = "report"


def filters_for_scope(scope: str, root_folders: tuple[str, ...]) -> dict:
    normalized = _normalize_scope_label(scope)
    if normalized == PROPOSAL_SCOPE and len(root_folders) >= 1:
        return {
            "source_scope": PROPOSAL_SCOPE,
            "file_path_prefixes": [root_folders[0]],
            "proposal_prefixes": [root_folders[0]],
        }
    if normalized == REPORT_SCOPE and len(root_folders) >= 2:
        return {
            "source_scope": REPORT_SCOPE,
            "file_path_prefixes": [root_folders[1]],
            "report_prefixes": [root_folders[1]],
        }
    filters: dict[str, object] = {"source_scope": ALL_SCOPE}
    if len(root_folders) >= 1:
        filters["proposal_prefixes"] = [root_folders[0]]
    if len(root_folders) >= 2:
        filters["report_prefixes"] = [root_folders[1]]
    prefixes = active_file_path_prefixes(filters)
    if prefixes:
        filters["file_path_prefixes"] = prefixes
    return filters


def active_file_path_prefixes(filters: dict | None) -> list[str]:
    if not filters:
        return []
    prefixes: list[str] = []
    prefixes.extend(_as_list(filters.get("file_path_prefixes")))
    scope = filters.get("source_scope")
    if scope == PROPOSAL_SCOPE:
        prefixes.extend(_as_list(filters.get("proposal_prefixes")))
    elif scope == REPORT_SCOPE:
        prefixes.extend(_as_list(filters.get("report_prefixes")))
    elif scope == ALL_SCOPE:
        prefixes.extend(_as_list(filters.get("proposal_prefixes")))
        prefixes.extend(_as_list(filters.get("report_prefixes")))
    return _unique([str(prefix).rstrip("\\/") for prefix in prefixes if str(prefix).strip()])


def file_path_matches_filters(file_path: str, filters: dict | None) -> bool:
    prefixes = active_file_path_prefixes(filters)
    if not prefixes:
        return True
    return any(path_startswith(file_path, prefix) for prefix in prefixes)


def sql_like_patterns_for_prefix(prefix: str) -> list[str]:
    variants = _path_variants(prefix.rstrip("\\/"))
    return [f"{variant}%" for variant in variants]


def path_startswith(file_path: str, prefix: str) -> bool:
    path_variants = _path_variants(file_path)
    prefix_variants = [variant.rstrip("\\/") for variant in _path_variants(prefix)]
    for path in path_variants:
        for prefix_value in prefix_variants:
            if path.startswith(prefix_value):
                return True
    return False


def _normalize_scope_label(scope: str) -> str:
    cleaned = (scope or "").strip().lower()
    if cleaned in {PROPOSAL_SCOPE, "proposal", "제안서"}:
        return PROPOSAL_SCOPE
    if cleaned in {REPORT_SCOPE, "report", "보고서"}:
        return REPORT_SCOPE
    return ALL_SCOPE


def _path_variants(value: str | Path) -> list[str]:
    raw = str(value)
    values = {
        raw,
        raw.replace("\\", "/"),
        raw.replace("/", "\\"),
        os.path.normcase(os.path.normpath(raw)),
        os.path.normcase(os.path.normpath(raw.replace("\\", "/"))),
        os.path.normcase(os.path.normpath(raw.replace("/", "\\"))),
    }
    return _unique([item.rstrip("\\/") for item in values if item])


def _as_list(value: object) -> list[str]:
    if not value:
        return []
    if isinstance(value, (str, Path)):
        return [str(value)]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return [str(value)]


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen

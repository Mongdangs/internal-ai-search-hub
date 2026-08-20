from __future__ import annotations


REPORT_BOOSTS = (
    (("목표모델", "목표 모델", "tomodel"), 1.45),
    (("현황분석", "현황 분석", "asis", "as-is"), 1.35),
    (("환경분석", "환경 분석"), 1.25),
    (("이행계획", "이행 계획", "로드맵", "roadmap"), 1.15),
)

PROPOSAL_BOOSTS = (
    (("기술 및 기능", "기술및 기능", "기술및기능", "기술 기능", "기술부문", "기능부문"), 1.5),
    (("목표모델", "목표 모델", "tomodel"), 1.35),
    (("현황분석", "현황 분석", "asis", "as-is"), 1.25),
)


def scoped_boost(row, filters: dict | None) -> float:
    if not filters:
        return 1.0
    scope = filters.get("source_scope")
    if scope == "all":
        return _all_scope_boost(row, filters)
    if scope == "report":
        return _boost_for(row, REPORT_BOOSTS)
    if scope == "proposal":
        return _boost_for(row, PROPOSAL_BOOSTS)
    return 1.0


def _all_scope_boost(row, filters: dict) -> float:
    file_path = str(row["file_path"])
    report_prefixes = [str(prefix).rstrip("\\/") for prefix in filters.get("report_prefixes", [])]
    proposal_prefixes = [str(prefix).rstrip("\\/") for prefix in filters.get("proposal_prefixes", [])]
    if any(file_path.startswith(prefix) for prefix in report_prefixes):
        return 1.2 * _boost_for(row, REPORT_BOOSTS)
    if any(file_path.startswith(prefix) for prefix in proposal_prefixes):
        return _boost_for(row, PROPOSAL_BOOSTS)
    return 1.0


def _boost_for(row, rules: tuple[tuple[tuple[str, ...], float], ...]) -> float:
    haystack = _haystack(row)
    boost = 1.0
    for terms, weight in rules:
        if any(term.lower() in haystack for term in terms):
            boost = max(boost, weight)
    return boost


def _haystack(row) -> str:
    values = [
        row["file_path"],
        row["document_title"],
        row["document_type"],
        row["section_title"],
        row["chapter_title"] if "chapter_title" in row.keys() else "",
        row["heading_path"] if "heading_path" in row.keys() else "",
        row["chunk_text"],
    ]
    return " ".join(str(value or "") for value in values).lower()

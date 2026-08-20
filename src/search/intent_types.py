from __future__ import annotations

from typing import Literal


SearchDomain = Literal[
    "architecture_evidence",
    "technology_trend",
    "cost_estimation",
    "staff_experience",
    "general",
]

OutputType = Literal[
    "evidence_table",
    "technology_table",
    "cost_table",
    "staff_table",
    "general_table",
]


SEARCH_DOMAINS: tuple[str, ...] = (
    "architecture_evidence",
    "technology_trend",
    "cost_estimation",
    "staff_experience",
    "general",
)

OUTPUT_TYPES: tuple[str, ...] = (
    "evidence_table",
    "technology_table",
    "cost_table",
    "staff_table",
    "general_table",
)

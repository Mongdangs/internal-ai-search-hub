from __future__ import annotations


def combine_scores(keyword_score: float, vector_score: float, keyword_weight: float, vector_weight: float) -> float:
    total = keyword_weight + vector_weight
    if total <= 0:
        return 0.0
    return (keyword_score * keyword_weight + vector_score * vector_weight) / total

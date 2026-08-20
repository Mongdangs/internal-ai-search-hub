from __future__ import annotations

from src.indexing.hybrid_index import combine_scores


def rank_chunk_ids(
    keyword_scores: dict[str, float],
    vector_scores: dict[str, float],
    keyword_weight: float,
    vector_weight: float,
    top_k: int,
    allow_vector_only: bool = True,
) -> list[tuple[str, float, float, float]]:
    chunk_ids = set(keyword_scores) | set(vector_scores)
    ranked = []
    for chunk_id in chunk_ids:
        keyword_score = keyword_scores.get(chunk_id, 0.0)
        vector_score = vector_scores.get(chunk_id, 0.0)
        if keyword_score <= 0 and not allow_vector_only:
            continue
        score = combine_scores(keyword_score, vector_score, keyword_weight, vector_weight)
        ranked.append((chunk_id, score, keyword_score, vector_score))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked[:top_k]

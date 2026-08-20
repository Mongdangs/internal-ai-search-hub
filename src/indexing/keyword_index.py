from __future__ import annotations

from src.utils.korean_tokenizer import tokenize


def keyword_overlap_score(query: str, text: str) -> float:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    text_lower = (text or "").lower()
    hits = sum(1 for token in query_tokens if token in text_lower)
    return hits / len(query_tokens)

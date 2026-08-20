from __future__ import annotations

from dataclasses import dataclass
import re

from src.ingestion.heading_extractor import CHAPTER_SYNONYMS, canonical_chapter


COMMAND_SUFFIX_RE = re.compile(r"\s*(?:을|를)?\s*(?:찾아줘|찾아|검색해줘|검색|알려줘|보여줘)\s*$")
TOPIC_PREFIX_RE = re.compile(r"^\s*(?:관련\s*)?(?:내용|문서|산출물)\s*(?:중|에서|에\s*관한)?\s*")


@dataclass(frozen=True)
class ParsedSearchQuery:
    original_query: str
    chapter_filter: str = ""
    semantic_query: str = ""

    @property
    def effective_query(self) -> str:
        return self.semantic_query or self.original_query


def parse_search_query(query: str) -> ParsedSearchQuery:
    query = re.sub(r"\s+", " ", (query or "").strip())
    if not query:
        return ParsedSearchQuery(original_query="")

    chapter_pattern = _chapter_pattern()
    patterns = (
        rf"^(?P<chapter>{chapter_pattern})\s*(?:챕터|장|절)?\s*(?:에서|내에서|부분에서|중)\s*(?P<topic>.+)$",
        rf"^(?P<chapter>{chapter_pattern})\s*(?:챕터|장|절)\s*에서\s*(?P<topic>.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if not match:
            continue
        chapter = canonical_chapter(match.group("chapter")) or match.group("chapter").strip()
        topic = _clean_topic(match.group("topic"))
        return ParsedSearchQuery(original_query=query, chapter_filter=chapter, semantic_query=topic or query)
    return ParsedSearchQuery(original_query=query, semantic_query=_clean_topic(query) or query)


def _clean_topic(topic: str) -> str:
    topic = COMMAND_SUFFIX_RE.sub("", topic or "").strip()
    topic = TOPIC_PREFIX_RE.sub("", topic).strip()
    topic = re.sub(r"\s+", " ", topic)
    return topic


def _chapter_pattern() -> str:
    phrases: list[str] = []
    for canonical, aliases in CHAPTER_SYNONYMS.items():
        phrases.append(canonical)
        phrases.extend(aliases)
    unique_phrases = sorted(set(phrases), key=len, reverse=True)
    return "|".join(re.escape(phrase) for phrase in unique_phrases if phrase)

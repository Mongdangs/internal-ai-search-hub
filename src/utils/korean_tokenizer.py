from __future__ import annotations

import re
from collections import Counter


TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9][가-힣A-Za-z0-9_+#.-]{1,}")
RND_RE = re.compile(r"(?i)\b(?:r\s*&\s*d|r\s*[-_/]\s*d|rnd)\b")
TRIM_CHARS = " \t\r\n\"'“”‘’.,;:!?()[]{}<>"
STOPWORDS = {
    "관련",
    "관련된",
    "찾아줘",
    "찾아",
    "있는",
    "내용",
    "검색",
    "근거",
    "사례",
    "문서",
    "페이지",
    "산출물",
    "제안서",
    "보고서",
    "보여줘",
    "알려줘",
    "포함",
    "포함된",
    "들어간",
    "및",
    "또는",
    "그리고",
    "대한",
    "위한",
    "기반",
}
KOREAN_SUFFIXES = (
    "으로",
    "에서",
    "에게",
    "까지",
    "부터",
    "하고",
    "이며",
    "이고",
    "이다",
    "와",
    "과",
    "을",
    "를",
    "이",
    "가",
    "은",
    "는",
    "에",
    "의",
    "로",
    "도",
    "만",
)


def tokenize(text: str) -> list[str]:
    expanded_text = expand_domain_synonyms(text or "")
    raw_tokens = [normalize_token(token.lower()) for token in TOKEN_RE.findall(expanded_text)]
    tokens: list[str] = []
    for token in raw_tokens:
        for expanded in _expand_token(token):
            if expanded not in STOPWORDS and len(expanded) > 1:
                tokens.append(expanded)
    return tokens


def expand_domain_synonyms(text: str) -> str:
    expanded = RND_RE.sub(" RND 연구개발 ", text)
    if re.search(r"(?i)\bai\b", expanded):
        expanded += " 인공지능"
    if "인공지능" in expanded:
        expanded += " ai"
    return expanded


def _expand_token(token: str) -> list[str]:
    expansions = [token]
    if token in {"rnd", "연구개발"}:
        expansions.extend(["연구개발", "rnd", "연구"])
    elif token == "연구":
        expansions.extend(["연구개발", "rnd"])
    elif token == "ai":
        expansions.append("인공지능")
    elif token == "인공지능":
        expansions.append("ai")
    return _unique(expansions)


def normalize_token(token: str) -> str:
    token = token.strip(TRIM_CHARS)
    for suffix in KOREAN_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            return token[: -len(suffix)].strip(TRIM_CHARS)
    return token


def unique_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for token in tokenize(text):
        if token not in tokens:
            tokens.append(token)
    return tokens


def _unique(tokens: list[str]) -> list[str]:
    seen: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.append(token)
    return seen


def top_keywords(text: str, limit: int = 12) -> list[str]:
    counter = Counter(tokenize(text))
    return [token for token, _ in counter.most_common(limit)]


def matched_keywords(query: str, text: str) -> list[str]:
    text_lower = (text or "").lower()
    matches = []
    for token in unique_tokens(query):
        if token in text_lower and token not in matches:
            matches.append(token)
    return matches


def missing_keywords(query: str, text: str) -> list[str]:
    text_lower = (text or "").lower()
    return [token for token in unique_tokens(query) if token not in text_lower]

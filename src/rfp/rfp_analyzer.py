from __future__ import annotations

import re

from src.rfp.requirement_extractor import extract_keywords, extract_requirement_sections, extract_sections
from src.utils.text_cleaner import trim_snippet


BUSINESS_TYPE_HINTS = ("ISP", "ISMP", "BPR", "PI", "컨설팅", "구축", "운영", "고도화")


class RfpAnalyzer:
    def summarize(self, text: str) -> dict:
        requirement_sections = extract_requirement_sections(text)
        keywords = extract_keywords(text, requirement_sections=requirement_sections)
        sections = extract_sections(text)
        return {
            "business_name": self._find_after_label(text, ("사업명", "용역명", "과제명")),
            "client_name": self._find_after_label(text, ("발주기관", "수요기관", "기관명")),
            "business_type": self._infer_business_type(text),
            "purpose": self._find_section(text, ("사업목적", "추진목적", "목적")),
            "main_tasks": requirement_sections[:5] or sections[:5],
            "main_requirements": requirement_sections[:8],
            "evaluation_items": [section for section in sections if "평가" in section][:5],
            "main_keywords": keywords,
            "requirement_keywords": keywords,
            "summary_text": trim_snippet(text, limit=900),
        }

    def build_queries(self, summary: dict) -> list[str]:
        return [query for query, _ in self.build_weighted_queries(summary)]

    def build_weighted_queries(self, summary: dict) -> list[tuple[str, float]]:
        weighted_queries: list[tuple[str, float]] = []
        keywords = summary.get("requirement_keywords") or summary.get("main_keywords", [])
        if keywords:
            for start in range(0, min(len(keywords), 16), 4):
                weighted_queries.append((" ".join(keywords[start : start + 4]), 1.45))
        for section in summary.get("main_requirements", [])[:6]:
            section_keywords = extract_keywords(section, requirement_sections=[section], limit=8)
            if section_keywords:
                weighted_queries.append((" ".join(section_keywords[:6]), 1.35))
        if not weighted_queries:
            fallback = " ".join((summary.get("main_keywords") or [])[:6])
            if fallback:
                weighted_queries.append((fallback, 0.8))
        return self._dedupe_weighted_queries(weighted_queries)

    def _infer_business_type(self, text: str) -> str:
        for hint in BUSINESS_TYPE_HINTS:
            if hint.lower() in text.lower():
                return hint
        return ""

    def _find_after_label(self, text: str, labels: tuple[str, ...]) -> str:
        for label in labels:
            pattern = rf"{re.escape(label)}\s*[:：]\s*(.+)"
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()[:120]
        return ""

    def _find_section(self, text: str, labels: tuple[str, ...]) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            if any(label in line for label in labels):
                section = " ".join(lines[index : index + 4])
                return trim_snippet(section, limit=400)
        return ""

    def _dedupe_weighted_queries(self, queries: list[tuple[str, float]]) -> list[tuple[str, float]]:
        deduped: list[tuple[str, float]] = []
        seen: set[str] = set()
        for query, weight in queries:
            normalized = re.sub(r"\s+", " ", query).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append((normalized, weight))
        return deduped

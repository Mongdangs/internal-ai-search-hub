from __future__ import annotations

from dataclasses import dataclass, replace
import re

from src.models import SearchResult
from src.search.nlu_query_parser import ParsedNaturalQuery


WEIGHTS: dict[str, dict[str, float]] = {
    "staff_experience": {
        "keyword_score": 0.20,
        "vector_score": 0.10,
        "chapter_score": 0.25,
        "condition_match_score": 0.20,
        "domain_coverage_score": 0.00,
        "structure_pattern_score": 0.20,
        "document_quality_score": 0.05,
    },
    "architecture_evidence": {
        "keyword_score": 0.20,
        "vector_score": 0.15,
        "chapter_score": 0.25,
        "condition_match_score": 0.10,
        "domain_coverage_score": 0.15,
        "structure_pattern_score": 0.10,
        "document_quality_score": 0.05,
    },
    "technology_trend": {
        "keyword_score": 0.20,
        "vector_score": 0.15,
        "chapter_score": 0.25,
        "condition_match_score": 0.05,
        "domain_coverage_score": 0.20,
        "structure_pattern_score": 0.10,
        "document_quality_score": 0.05,
    },
    "cost_estimation": {
        "keyword_score": 0.20,
        "vector_score": 0.10,
        "chapter_score": 0.15,
        "condition_match_score": 0.15,
        "domain_coverage_score": 0.20,
        "structure_pattern_score": 0.15,
        "document_quality_score": 0.05,
    },
    "general": {
        "keyword_score": 0.25,
        "vector_score": 0.25,
        "chapter_score": 0.10,
        "condition_match_score": 0.10,
        "domain_coverage_score": 0.20,
        "structure_pattern_score": 0.05,
        "document_quality_score": 0.05,
    },
}


@dataclass(frozen=True)
class RerankBreakdown:
    chunk_id: str
    final_score: float
    keyword_score: float
    vector_score: float
    chapter_score: float
    condition_match_score: float
    domain_coverage_score: float
    structure_pattern_score: float
    document_quality_score: float

    def as_dict(self) -> dict[str, float | str]:
        return {
            "chunk_id": self.chunk_id,
            "final_score": self.final_score,
            "keyword_score": self.keyword_score,
            "vector_score": self.vector_score,
            "chapter_score": self.chapter_score,
            "condition_match_score": self.condition_match_score,
            "domain_coverage_score": self.domain_coverage_score,
            "structure_pattern_score": self.structure_pattern_score,
            "document_quality_score": self.document_quality_score,
        }


def rerank_results(parsed: ParsedNaturalQuery, results: list[SearchResult], top_k: int | None = None) -> list[SearchResult]:
    scored = []
    for result in results:
        breakdown = score_result(parsed, result)
        scored.append((replace(result, score=breakdown.final_score), breakdown))
    scored.sort(key=lambda item: item[0].score, reverse=True)
    ranked = [result for result, _ in scored]
    return ranked[:top_k] if top_k else ranked


def score_result(parsed: ParsedNaturalQuery, result: SearchResult) -> RerankBreakdown:
    scores = {
        "keyword_score": _clamp(result.keyword_score or result.keyword_coverage or 0.0),
        "vector_score": _clamp(result.vector_score or 0.0),
        "chapter_score": _chapter_score(parsed, result),
        "condition_match_score": _condition_match_score(parsed, result),
        "domain_coverage_score": _domain_coverage_score(parsed, result),
        "structure_pattern_score": _structure_pattern_score(parsed, result),
        "document_quality_score": _document_quality_score(parsed, result),
    }
    weights = WEIGHTS.get(parsed.search_domain, WEIGHTS["general"])
    total_weight = sum(weights.values()) or 1.0
    final_score = sum(scores[key] * weights.get(key, 0.0) for key in scores) / total_weight
    return RerankBreakdown(
        chunk_id=result.chunk_id,
        final_score=round(final_score, 6),
        keyword_score=round(scores["keyword_score"], 6),
        vector_score=round(scores["vector_score"], 6),
        chapter_score=round(scores["chapter_score"], 6),
        condition_match_score=round(scores["condition_match_score"], 6),
        domain_coverage_score=round(scores["domain_coverage_score"], 6),
        structure_pattern_score=round(scores["structure_pattern_score"], 6),
        document_quality_score=round(scores["document_quality_score"], 6),
    )


def _chapter_score(parsed: ParsedNaturalQuery, result: SearchResult) -> float:
    targets = [parsed.target_chapter, parsed.target_section, parsed.target_subsection]
    targets = [target for target in targets if target]
    if not targets:
        return 0.5
    haystack = _result_haystack(result)
    compact_haystack = haystack.replace(" ", "")
    if any(target.lower().replace(" ", "") in compact_haystack for target in targets):
        return 1.0
    if parsed.search_domain == "staff_experience" and any(term in haystack for term in ("투입인력", "참여인력", "주요경력", "경력")):
        return 0.85
    return 0.2


def _condition_match_score(parsed: ParsedNaturalQuery, result: SearchResult) -> float:
    haystack = _result_haystack(result)
    conditions = [value for value in parsed.conditions.values() if value]
    if not conditions:
        topic_terms = [term for term in re.split(r"\s+", parsed.topic or "") if len(term) >= 2]
        if not topic_terms:
            return 0.5
        return _coverage(topic_terms, haystack)
    return _coverage(conditions, haystack)


def _domain_coverage_score(parsed: ParsedNaturalQuery, result: SearchResult) -> float:
    terms = [term for term in parsed.expanded_keywords if len(term) >= 2]
    if not terms:
        return 0.5
    return _coverage(terms, _result_haystack(result))


def _structure_pattern_score(parsed: ParsedNaturalQuery, result: SearchResult) -> float:
    text = _result_haystack(result)
    if parsed.search_domain == "staff_experience" and result.table_type == "staff":
        return 1.0
    if parsed.search_domain == "cost_estimation" and result.table_type == "cost":
        return 1.0
    if parsed.search_domain == "staff_experience":
        patterns = (
            r"[가-힣]{2,4}\s*(?:PM|PL|TA|AA|DA|DBA|개발|컨설턴트)",
            r"(?:특급|고급|중급|초급)",
            r"(?:성명|이름|역할|등급|주요경력|참여사업|수행경험|투입인력|참여인력)",
        )
    elif parsed.search_domain == "cost_estimation":
        patterns = (
            r"(?:원|천원|백만원|억원|비용|단가|수량|금액|라이선스|사용량)",
            r"\d[\d,]*(?:\.\d+)?",
        )
    elif parsed.search_domain == "technology_trend":
        patterns = (r"(?:동향|트렌드|최신기술|적용사례|시사점|기술)",)
    elif parsed.search_domain == "architecture_evidence":
        patterns = (r"(?:목표모델|아키텍처|구성도|설계|To-Be|DR|MSA|클라우드|보안|데이터)",)
    else:
        patterns = (r"(?:근거|사례|방안|구성|계획)",)
    hits = sum(1 for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE))
    return min(1.0, hits / max(len(patterns), 1))


def _document_quality_score(parsed: ParsedNaturalQuery, result: SearchResult) -> float:
    text = " ".join(
        [
            result.document_title,
            result.file_path,
            result.chapter_title,
            result.heading_path,
            result.canonical_heading_path,
            result.domain_keywords,
        ]
    ).lower()
    score = 0.45
    if parsed.target_chapter and parsed.target_chapter.lower().replace(" ", "") in text.replace(" ", ""):
        score += 0.25
    if parsed.search_domain == "staff_experience" and any(term in text for term in ("제안", "인력", "경력", "정성")):
        score += 0.2
    elif parsed.search_domain == "cost_estimation" and any(term in text for term in ("비용", "견적", "예산", "가격")):
        score += 0.2
    elif parsed.search_domain == "technology_trend" and any(term in text for term in ("동향", "기술", "trend")):
        score += 0.2
    elif parsed.search_domain == "architecture_evidence" and any(term in text for term in ("목표", "모델", "설계", "아키텍처")):
        score += 0.2
    if any(term in text for term in ("최종", "final", "정성")):
        score += 0.1
    return _clamp(score)


def _coverage(terms: list[str], haystack: str) -> float:
    if not terms:
        return 0.0
    normalized = haystack.lower()
    hits = 0
    for term in terms:
        term_value = str(term).lower().strip()
        if term_value and term_value in normalized:
            hits += 1
    return hits / len(terms)


def _result_haystack(result: SearchResult) -> str:
    values = [
        result.project_name,
        result.client_name,
        result.document_title,
        result.document_type,
        result.file_path,
        result.chapter_title,
        result.section_title,
        result.heading_path,
        result.canonical_chapter_title,
        result.canonical_section_title,
        result.canonical_subsection_title,
        result.canonical_heading_path,
        result.raw_heading_path,
        result.table_type,
        result.domain_keywords,
        result.parent_context,
        result.matched_text,
        " ".join(result.document_keywords),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 1.0))

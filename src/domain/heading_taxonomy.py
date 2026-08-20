from __future__ import annotations

from difflib import SequenceMatcher
import re


CANONICAL_CHAPTER_ALIASES: dict[str, list[str]] = {
    "일반현황": ["일반현황", "일반 현황", "사업개요", "사업 개요", "제안개요", "회사현황", "제안사 일반"],
    "현황분석": ["현황분석", "현황 분석", "As-Is", "ASIS", "업무현황", "업무 현황", "시스템현황", "환경분석"],
    "정보기술동향": ["정보기술동향", "정보 기술 동향", "기술동향", "기술 동향", "IT동향", "최신기술", "기술트렌드", "Technology Trend"],
    "요구사항분석": ["요구사항분석", "요구사항 분석", "요구사항", "Requirement", "Requirements", "요구사항 정의"],
    "목표모델": ["목표모델", "목표 모델", "목표아키텍처", "목표 아키텍처", "To-Be", "TOBE", "To Be", "목표시스템", "개선모델", "미래모델"],
    "이행계획": ["이행계획", "이행 계획", "추진계획", "추진 계획", "로드맵", "Roadmap", "실행계획", "전환계획"],
    "비용산정": ["비용산정", "비용 산정", "소요예산", "소요 예산", "사업비", "견적", "산출내역", "TCO", "총소유비용"],
    "투입인력": ["투입인력", "투입 인력", "참여인력", "참여 인력", "수행인력", "인력투입", "전담인력", "조직 및 인력", "수행조직"],
    "수행방법론": ["수행방법론", "수행 방법론", "방법론", "추진방법론", "개발방법론", "컨설팅 방법론"],
    "품질관리": ["품질관리", "품질 관리", "품질보증", "품질 보증", "테스트", "시험", "검증"],
    "보안관리": ["보안관리", "보안 관리", "정보보안", "개인정보보호", "접근통제", "권한관리"],
    "사업관리": ["사업관리", "사업 관리", "프로젝트관리", "프로젝트 관리", "PMO", "일정관리", "위험관리"],
}


CANONICAL_SECTION_ALIASES: dict[str, list[str]] = {
    "인프라 아키텍처": ["인프라", "인프라 아키텍처", "기술 인프라", "시스템 구성", "시스템 구성도", "서버 구성", "네트워크 구성"],
    "애플리케이션 아키텍처": ["애플리케이션 아키텍처", "어플리케이션 아키텍처", "응용 아키텍처", "애플리케이션 구조", "서비스 구조"],
    "데이터 아키텍처": ["데이터 아키텍처", "데이터 구조", "데이터 모델", "데이터 설계", "DB 설계", "데이터 표준"],
    "보안 아키텍처": ["보안 아키텍처", "보안 구성", "정보보안", "접근통제", "권한관리", "개인정보보호"],
    "업무 아키텍처": ["업무 아키텍처", "업무 구조", "업무 프로세스", "프로세스 설계", "업무 개선"],
    "기술 동향": ["기술 동향", "기술트렌드", "최신 기술", "적용사례", "시사점"],
    "비용 산정 기준": ["비용 산정 기준", "산정 기준", "단가", "수량", "견적", "소요예산", "TCO"],
    "인력 운영": ["인력 운영", "투입 계획", "참여 인력", "수행 조직", "역할 및 책임", "주요 경력"],
}


CANONICAL_SUBSECTION_ALIASES: dict[str, list[str]] = {
    "DR/백업/이중화": ["DR", "재해복구", "재난복구", "장애복구", "백업", "이중화", "DR센터", "재해복구센터", "RTO", "RPO"],
    "클라우드 비용": ["클라우드 비용", "비용산정", "TCO", "총소유비용", "단가", "사용량", "라이선스", "운영비", "구축비"],
    "인력 경력": ["주요경력", "주요 경력", "유사사업", "유사 사업", "참여사업", "참여 사업", "수행경험", "수행 경험"],
    "MSA/컨테이너": ["MSA", "마이크로서비스", "마이크로 서비스", "API Gateway", "서비스 메시", "컨테이너", "Kubernetes", "K8s"],
    "데이터 이관": ["데이터 이관", "마이그레이션", "전환", "ETL", "데이터 검증", "데이터 정제"],
    "보안/권한": ["보안", "접근통제", "권한관리", "인증", "암호화", "개인정보보호"],
}


_ROMAN_CHARS = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫIVXLCDM"
_PREFIX_RE = re.compile(
    rf"^\s*(?:[제第]\s*\d+\s*장|chapter\s*\d+|[{_ROMAN_CHARS}]+|\d+(?:\.\d+)*|\(\d+\)|[①-⑳])\s*[.)．:\-]?\s*|^\s*[가-힣]\s*[.)．:\-]\s*",
    re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[^0-9a-zA-Z가-힣]+")


def normalize_heading_text(text: str) -> str:
    value = (text or "").strip().lower()
    previous = None
    while value and previous != value:
        previous = value
        value = _PREFIX_RE.sub("", value)
    value = re.sub(r"\s+", "", value)
    return _PUNCT_RE.sub("", value)


def canonicalize_heading(title: str, aliases: dict[str, list[str]], threshold: float = 0.72) -> dict:
    title_norm = normalize_heading_text(title)
    if not title_norm:
        return {"canonical": "", "confidence": 0.0, "reason": ""}

    best = {"canonical": "", "confidence": 0.0, "reason": ""}
    for canonical, alias_values in aliases.items():
        candidates = [canonical, *alias_values]
        for alias in candidates:
            alias_norm = normalize_heading_text(alias)
            if not alias_norm:
                continue
            if title_norm == alias_norm:
                return {"canonical": canonical, "confidence": 1.0, "reason": f"exact:{alias}"}
            if alias_norm in title_norm or title_norm in alias_norm:
                confidence = 0.92 if alias_norm in title_norm else 0.86
                best = _better(best, canonical, confidence, f"alias_contains:{alias}")
                continue
            overlap = _token_overlap(title, alias)
            if overlap >= 0.5:
                best = _better(best, canonical, min(0.88, 0.60 + overlap * 0.35), f"token_overlap:{alias}")
            similarity = SequenceMatcher(None, title_norm, alias_norm).ratio()
            if similarity >= threshold:
                best = _better(best, canonical, min(0.91, similarity), f"similarity:{alias}")

    if best["confidence"] < threshold:
        return {"canonical": "", "confidence": round(best["confidence"], 2), "reason": best["reason"]}
    return {"canonical": best["canonical"], "confidence": round(best["confidence"], 2), "reason": best["reason"]}


def classify_heading_hierarchy(chapter_title: str, section_title: str, heading_path: str) -> dict:
    raw_chapter = chapter_title or ""
    raw_section = section_title or ""
    raw_path = heading_path or ""
    path_parts = [part.strip() for part in raw_path.split(">") if part.strip()]
    chapter_match = _best_match([raw_chapter, raw_path, *path_parts], CANONICAL_CHAPTER_ALIASES)
    section_match = _best_match([raw_section, raw_path, *path_parts], CANONICAL_SECTION_ALIASES)
    subsection_match = _best_match([raw_section, raw_path, *path_parts], CANONICAL_SUBSECTION_ALIASES)

    canonical_parts = [
        chapter_match["canonical"],
        section_match["canonical"],
        subsection_match["canonical"],
    ]
    canonical_path = " > ".join(part for part in canonical_parts if part)
    matched = [item for item in (chapter_match, section_match, subsection_match) if item["canonical"]]
    confidence = max((float(item["confidence"]) for item in matched), default=0.0)
    reasons = " | ".join(item["reason"] for item in matched if item["reason"])

    return {
        "raw_chapter_title": raw_chapter,
        "raw_section_title": raw_section,
        "raw_heading_path": raw_path,
        "canonical_chapter_title": chapter_match["canonical"],
        "canonical_section_title": section_match["canonical"],
        "canonical_subsection_title": subsection_match["canonical"],
        "canonical_heading_path": canonical_path,
        "heading_classification_confidence": round(confidence, 2),
        "heading_classification_reason": reasons,
    }


def _best_match(values: list[str], aliases: dict[str, list[str]]) -> dict:
    best = {"canonical": "", "confidence": 0.0, "reason": ""}
    for value in values:
        match = canonicalize_heading(value, aliases)
        best = _better(best, match["canonical"], match["confidence"], match["reason"])
    return best


def _better(current: dict, canonical: str, confidence: float, reason: str) -> dict:
    if confidence > float(current.get("confidence") or 0.0):
        return {"canonical": canonical, "confidence": confidence, "reason": reason}
    return current


def _token_overlap(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _tokens(text: str) -> set[str]:
    values = re.split(r"[\s/|,()\-_.]+", (text or "").lower())
    return {normalize_heading_text(value) for value in values if len(normalize_heading_text(value)) >= 2}

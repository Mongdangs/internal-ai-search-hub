from __future__ import annotations

from collections import Counter
import re

from src.indexing.design_keywords import target_model_design_keywords
from src.utils.korean_tokenizer import tokenize
from src.utils.text_cleaner import clean_text


REQUIREMENT_SECTION_HINTS = (
    "컨설팅요구사항",
    "컨설팅 요구사항",
    "과업요구사항",
    "과업 요구사항",
    "상세요구사항",
    "상세 요구사항",
    "기능요구사항",
    "기능 요구사항",
    "비기능요구사항",
    "비기능 요구사항",
    "제안요청사항",
    "제안 요청사항",
    "제안요청 내용",
    "과업내용",
    "과업 내용",
    "과업범위",
    "과업 범위",
    "주요과업",
    "주요 과업",
    "제안요청",
    "요구사항",
    "수행내용",
    "수행 내용",
    "수행방안",
    "수행 방안",
    "컨설팅",
)
CONSULTING_CONTENT_HINTS = (
    "현황분석",
    "현황 분석",
    "환경분석",
    "환경 분석",
    "업무분석",
    "업무 분석",
    "목표모델",
    "목표 모델",
    "목표아키텍처",
    "목표 아키텍처",
    "이행계획",
    "이행 계획",
    "To-Be",
    "TO-BE",
    "프로세스",
    "아키텍처",
    "정보화전략",
    "데이터아키텍처",
    "데이터 아키텍처",
    "기술아키텍처",
    "기술 아키텍처",
    "클라우드",
    "클라우드네이티브",
    "MSA",
    "마이크로서비스",
    "API",
    "인터페이스",
    "연계",
    "보안",
    "데이터",
    "품질",
    "표준",
    "거버넌스",
    "마이그레이션",
    "전환",
)
REQUIREMENT_ACTION_HINTS = (
    "분석",
    "진단",
    "정의",
    "설계",
    "수립",
    "도출",
    "제시",
    "마련",
    "개선",
    "전환",
    "검토",
    "구성",
    "구체화",
)
ADMINISTRATIVE_HINTS = (
    "사업명",
    "용역명",
    "과제명",
    "사업기간",
    "용역기간",
    "계약기간",
    "수행기간",
    "사업예산",
    "추정가격",
    "배정예산",
    "입찰",
    "계약",
    "낙찰",
    "공고",
    "개찰",
    "제안서 제출",
    "제출기한",
    "제출 서류",
    "평가항목",
    "평가기준",
    "배점",
    "가격평가",
    "기술평가",
    "참가자격",
    "유의사항",
    "일반사항",
    "서식",
    "붙임",
    "목차",
    "표지",
    "문의처",
    "담당자",
    "보증금",
)
NOISE_KEYWORDS = {
    "사업명",
    "용역명",
    "과제명",
    "사업기간",
    "용역기간",
    "계약기간",
    "수행기간",
    "기간",
    "개월",
    "예산",
    "금액",
    "추정가격",
    "배정예산",
    "입찰",
    "계약",
    "낙찰",
    "제안요청서",
    "제안서",
    "평가",
    "평가항목",
    "배점",
    "제출",
    "서식",
    "붙임",
    "목차",
    "표지",
    "일반사항",
    "유의사항",
    "컨설팅",
    "구축",
    "사업",
    "용역",
    "수행",
    "목표모델",
    "목표아키텍처",
    "목표시스템",
    "설계",
    "수립",
    "전략",
    "방안",
    "통해",
    "추진",
    "단계별",
    "도출한다",
    "분석",
    "체계",
    "관리체계",
    "대상",
    "시스템",
    "전환",
}
PRIORITY_REQUIREMENT_PHRASES = (
    ("클라우드네이티브", ("클라우드네이티브", "클라우드 네이티브", "cloud native", "cloud-native")),
    ("클라우드", ("클라우드", "cloud")),
    ("MSA", ("msa", "마이크로서비스", "마이크로 서비스")),
    ("API", ("api", "openapi", "오픈api", "오픈 api")),
    ("데이터아키텍처", ("데이터아키텍처", "데이터 아키텍처")),
    ("기술아키텍처", ("기술아키텍처", "기술 아키텍처")),
    ("보안아키텍처", ("보안아키텍처", "보안 아키텍처")),
    ("인터페이스", ("인터페이스", "interface", "연계")),
    ("마이그레이션", ("마이그레이션", "migration", "전환")),
    ("데이터거버넌스", ("데이터거버넌스", "데이터 거버넌스")),
    ("메타데이터", ("메타데이터", "meta data", "metadata")),
    ("데이터표준", ("데이터표준", "데이터 표준", "표준화")),
    ("데이터품질", ("데이터품질", "데이터 품질", "품질관리")),
)
MONEY_OR_PERIOD_RE = re.compile(
    r"(?:\d[\d,]*(?:원|천원|만원|백만원|억원)|\d+\s*(?:개월|일|년)|\d{4}[./-]\d{1,2}(?:[./-]\d{1,2})?)"
)
SECTION_NUMBER_RE = re.compile(r"^\s*(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[IVX]+|\d+(?:\.\d+)*)[.)]?\s+", re.IGNORECASE)


def extract_sections(text: str, limit: int = 8) -> list[str]:
    return extract_requirement_sections(text, limit=limit)


def extract_requirement_sections(text: str, limit: int = 12) -> list[str]:
    sections: list[str] = []
    paragraphs = [clean_text(part) for part in text.split("\n") if clean_text(part)]
    requirement_context = 0
    for index, paragraph in enumerate(paragraphs):
        if _is_administrative_noise(paragraph):
            requirement_context = max(0, requirement_context - 1)
            continue

        if _is_requirement_heading(paragraph):
            requirement_context = 6
            if not _is_title_like(paragraph) and _requirement_score(paragraph) >= 2:
                sections.append(paragraph)
        elif requirement_context > 0 and _requirement_score(paragraph) >= 1:
            sections.append(paragraph)
            requirement_context -= 1
        elif _requirement_score(paragraph) >= 3:
            sections.append(paragraph)

        if sections and index + 1 < len(paragraphs) and _is_requirement_heading(paragraphs[index + 1]):
            requirement_context = max(requirement_context, 4)
        if len(sections) >= limit:
            break
    return _dedupe_sections(sections)[:limit]


def extract_keywords(text: str, limit: int = 15, requirement_sections: list[str] | None = None) -> list[str]:
    sections = requirement_sections if requirement_sections is not None else extract_requirement_sections(text)
    source_text = "\n".join(sections) if sections else clean_text(text)
    weighted: Counter[str] = Counter()
    lowered_source = source_text.lower()

    for keyword, variants in PRIORITY_REQUIREMENT_PHRASES:
        if any(variant.lower() in lowered_source for variant in variants) and _is_valid_requirement_keyword(keyword):
            weighted[keyword] += 24

    for keyword in target_model_design_keywords(source_text, limit=limit * 2):
        if _is_valid_requirement_keyword(keyword):
            weighted[keyword] += 12

    for section in sections:
        for token in tokenize(section):
            if not _is_valid_requirement_keyword(token):
                continue
            weighted[token] += 4 if _is_consulting_design_token(token) else 1

    if not weighted:
        for keyword in target_model_design_keywords(text, limit=limit * 2):
            if _is_valid_requirement_keyword(keyword):
                weighted[keyword] += 1

    return _dedupe_keywords([keyword for keyword, _ in weighted.most_common(limit * 2)])[:limit]


def _requirement_score(paragraph: str) -> int:
    compact = _compact(paragraph)
    score = 0
    if any(_compact(hint) in compact for hint in REQUIREMENT_SECTION_HINTS):
        score += 4
    if any(_compact(hint) in compact for hint in CONSULTING_CONTENT_HINTS):
        score += 3
    if any(hint in paragraph for hint in REQUIREMENT_ACTION_HINTS):
        score += 1
    if MONEY_OR_PERIOD_RE.search(paragraph):
        score -= 3
    if _is_title_like(paragraph):
        score -= 1
    return score


def _is_requirement_heading(paragraph: str) -> bool:
    compact = _compact(paragraph)
    return any(_compact(hint) in compact for hint in REQUIREMENT_SECTION_HINTS)


def _is_administrative_noise(paragraph: str) -> bool:
    compact = _compact(paragraph)
    if MONEY_OR_PERIOD_RE.search(paragraph) and not any(_compact(hint) in compact for hint in CONSULTING_CONTENT_HINTS):
        return True
    return any(_compact(hint) in compact for hint in ADMINISTRATIVE_HINTS)


def _is_title_like(paragraph: str) -> bool:
    stripped = SECTION_NUMBER_RE.sub("", paragraph).strip()
    if len(stripped) > 32:
        return False
    has_action = any(hint in stripped for hint in REQUIREMENT_ACTION_HINTS)
    has_sentence_marker = any(marker in stripped for marker in ("한다", "하여", "하고", "위해", "통해", "방안", "체계"))
    return not has_action and not has_sentence_marker


def _is_valid_requirement_keyword(keyword: str) -> bool:
    compact = _compact(keyword)
    if not compact or len(compact) < 2 or len(compact) > 20:
        return False
    if MONEY_OR_PERIOD_RE.search(keyword) or compact.isdigit():
        return False
    return not any(_compact(noise) in compact for noise in NOISE_KEYWORDS)


def _is_consulting_design_token(token: str) -> bool:
    compact = _compact(token)
    return any(_compact(hint) in compact for hint in (*CONSULTING_CONTENT_HINTS, *REQUIREMENT_ACTION_HINTS))


def _dedupe_sections(sections: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for section in sections:
        key = _compact(section)[:120]
        if key and key not in seen:
            seen.add(key)
            deduped.append(section)
    return deduped


def _dedupe_keywords(keywords: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        compact = _compact(keyword)
        if compact in seen or not _is_valid_requirement_keyword(keyword):
            continue
        seen.add(compact)
        deduped.append(keyword)
    return deduped


def _compact(text: str) -> str:
    compact = (text or "").lower()
    for mark in (" ", "\t", "\n", ".", "/", "\\", "-", "_", ",", "·", ":", "：", "(", ")", "[", "]"):
        compact = compact.replace(mark, "")
    return compact

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

from src.utils.korean_tokenizer import expand_domain_synonyms, tokenize


TECHNICAL_DESIGN_PHRASES = (
    ("AI", ("ai", "인공지능", "artificial intelligence")),
    ("클라우드네이티브", ("클라우드네이티브", "클라우드 네이티브", "cloud native", "cloud-native")),
    ("클라우드", ("클라우드", "cloud")),
    ("MSA", ("msa", "마이크로서비스", "마이크로 서비스", "microservice", "micro-service")),
    ("API", ("api", "openapi", "오픈api", "오픈 api")),
    ("API Gateway", ("api gateway", "api 게이트웨이", "apigateway")),
    ("컨테이너", ("컨테이너", "container", "docker", "도커")),
    ("Kubernetes", ("kubernetes", "k8s", "쿠버네티스")),
    ("DevOps", ("devops", "dev ops", "데브옵스")),
    ("CI/CD", ("ci/cd", "cicd", "ci cd", "지속적 통합", "지속적 배포")),
    ("IaC", ("iac", "terraform", "테라폼", "infrastructure as code")),
    ("서비스메시", ("서비스 메시", "서비스메시", "service mesh", "istio")),
    ("서버리스", ("서버리스", "serverless", "lambda")),
    ("오토스케일링", ("오토스케일링", "auto scaling", "autoscaling", "자동확장")),
    ("하이브리드클라우드", ("하이브리드 클라우드", "하이브리드클라우드", "hybrid cloud")),
    ("멀티클라우드", ("멀티 클라우드", "멀티클라우드", "multi cloud", "multicloud")),
    ("SaaS", ("saas", "서비스형 소프트웨어")),
    ("PaaS", ("paas", "서비스형 플랫폼")),
    ("IaaS", ("iaas", "서비스형 인프라")),
    ("AWS", ("aws", "amazon web services")),
    ("Azure", ("azure", "애저")),
    ("GCP", ("gcp", "google cloud")),
    ("NCP", ("ncp", "네이버클라우드", "naver cloud")),
)

RESEARCH_DOMAIN_PHRASES = (
    ("연구개발", ("연구개발", "r&d", "rnd", "research and development")),
    ("연구관리", ("연구관리", "연구 과제", "연구과제", "과제관리", "과제 관리")),
    ("연구비", ("연구비", "연구비관리", "연구비 관리")),
    ("IRIS", ("iris", "범부처 연구지원", "범부처통합연구지원")),
)

ARCHITECTURE_PHRASES = (
    ("기술아키텍처", ("기술 아키텍처", "기술아키텍처")),
    ("애플리케이션아키텍처", ("애플리케이션 아키텍처", "어플리케이션 아키텍처", "app architecture")),
    ("데이터아키텍처", ("데이터 아키텍처", "데이터아키텍처")),
    ("인프라아키텍처", ("인프라 아키텍처", "인프라아키텍처")),
    ("보안아키텍처", ("보안 아키텍처", "보안아키텍처")),
    ("연계아키텍처", ("연계 아키텍처", "연계아키텍처")),
    ("시스템구성", ("시스템 구성", "시스템구성", "구성도")),
    ("기능설계", ("기능 설계", "기능설계", "기능정의", "기능 정의")),
    ("데이터모델", ("데이터 모델", "데이터모델", "데이터 설계", "데이터설계")),
    ("인터페이스", ("인터페이스", "interface", "연계")),
    ("운영모델", ("운영 모델", "운영모델")),
    ("보안설계", ("보안 설계", "보안설계")),
)

GENERIC_ANCHOR_TERMS = {
    "목표모델",
    "목표 모델",
    "목표아키텍처",
    "목표 아키텍처",
    "목표시스템",
    "목표 시스템",
    "to-be",
    "tobe",
    "미래모델",
    "개선모델",
    "모델",
    "목표",
    "설계",
    "아키텍처",
    "구조",
    "isp",
    "ismp",
    "bpr",
    "bprisp",
    "bprismp",
    "ispismp",
    "api",
    "gateway",
    "cloud",
    "native",
    "네이티브",
    "분석보고서",
    "종합보고서",
    "iiac",
    "성과물",
    "제출",
    "발전법",
    "주요내용",
    "rev",
    "버전관리",
    "번호",
    "원본제안사",
    "원본 제안사",
    "일반현황",
    "일반 현황",
    "tsp",
    "컨설팅",
    "고도화",
    "전사",
    "제안요약",
    "제안요약서",
    "정성",
    "정량",
    "정성제안",
    "정량제안",
    "표지",
    "목차",
    "참고",
    "참조",
    "수행실적",
    "수립",
    "투입인력",
    "넥스트아이앤아",
    "제안사",
    "컨소시엄",
    "중심",
    "구축",
    "통합",
    "기능",
    "업무",
    "rnd",
    "r&d",
}

DOMAIN_STOPWORDS = {
    "01",
    "02",
    "03",
    "04",
    "05",
    "h",
    "pdf",
    "ppt",
    "pptx",
    "final",
    "copy",
    "제안",
    "제안서",
    "제안요약",
    "제안요약서",
    "정성",
    "정량",
    "정성제안",
    "정량제안",
    "표지",
    "목차",
    "참고",
    "참조",
    "수행실적",
    "수립",
    "투입인력",
    "넥스트아이앤아",
    "제안사",
    "컨소시엄",
    "보고서",
    "사업수행",
    "수행",
    "산출물",
    "최종",
    "초안",
    "본문",
    "별첨",
    "사본",
    "용역",
    "사업",
    "프로젝트",
    "목표모델",
    "목표아키텍처",
    "목표시스템",
    "설계",
    "isp",
    "ismp",
    "bpr",
    "bprisp",
    "bprismp",
    "ispismp",
    "분석보고서",
    "종합보고서",
    "iiac",
    "성과물",
    "제출",
    "발전법",
    "주요내용",
    "rev",
    "버전관리",
    "번호",
    "원본제안사",
    "원본 제안사",
    "컨설팅",
    "고도화",
    "전사",
    "중심",
    "구축",
    "통합",
    "기능",
    "업무",
    "rnd",
    "r&d",
    "일반현황",
    "일반 현황",
    "tsp",
}


def target_model_design_keywords(text: str, section_title: str = "", context: str = "", limit: int = 12) -> list[str]:
    normalized_context = _normalize_context(context)
    haystack = " ".join(part for part in (section_title, text, normalized_context) if part)
    lowered = " ".join(part for part in (haystack, context) if part).lower()
    weighted: Counter[str] = Counter()

    for keyword, variants in TECHNICAL_DESIGN_PHRASES:
        if any(variant.lower() in lowered for variant in variants):
            weighted[keyword] += 14

    for keyword, variants in RESEARCH_DOMAIN_PHRASES:
        if any(variant.lower() in lowered for variant in variants):
            weighted[keyword] += 11

    for keyword, variants in ARCHITECTURE_PHRASES:
        if any(variant.lower() in lowered for variant in variants):
            weighted[keyword] += 8

    for token in _domain_tokens(context):
        weighted[token] += 7

    for token in tokenize(haystack):
        if _is_generic_anchor(token) or _is_canonical_variant_token(token) or _is_domain_stopword(token):
            continue
        weighted[token] += 1
        if _is_technical_design_token(token):
            weighted[token] += 4

    return [keyword for keyword, _ in weighted.most_common(limit)]


def _domain_tokens(context: str) -> list[str]:
    normalized = _normalize_context(context)
    tokens: list[str] = []
    for token in tokenize(normalized):
        if token in DOMAIN_STOPWORDS or _is_generic_anchor(token) or _is_domain_stopword(token):
            continue
        if len(token) < 2 or token.isdigit():
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens[:8]


def _normalize_context(context: str) -> str:
    if not context:
        return ""
    path_text = expand_domain_synonyms(str(Path(context)))
    for mark in ("\\", "/", "_", "-", ".", "(", ")", "[", "]"):
        path_text = path_text.replace(mark, " ")
    return path_text


def _is_generic_anchor(token: str) -> bool:
    return _compact_generic(token) in GENERIC_ANCHOR_COMPACT_TERMS


def _is_canonical_variant_token(token: str) -> bool:
    return _compact_generic(token) in CANONICAL_VARIANT_COMPACT_TERMS


def _is_domain_stopword(token: str) -> bool:
    compact = _compact_generic(token)
    return (
        compact in DOMAIN_STOPWORD_COMPACT_TERMS
        or token.isdigit()
        or compact.isdigit()
        or len(compact) > 14
        or _looks_like_organization_name(compact)
        or _looks_like_vendor_name(compact)
        or _looks_like_non_design_acronym(token)
        or _looks_like_broken_rnd_fragment(compact)
        or _looks_like_predicate(token)
        or "ismp" in compact
        or "ispismp" in compact
        or "bpr" in compact
        or "제안서" in compact
        or "보고서" in compact
    )


def _looks_like_predicate(token: str) -> bool:
    return token.endswith(("한다", "된다", "했다", "있다", "없다", "한다면", "되도록"))


def _looks_like_broken_rnd_fragment(compact: str) -> bool:
    return bool(re.search(r"[가-힣]{3,}r$", compact))


def _looks_like_non_design_acronym(token: str) -> bool:
    lowered = token.lower()
    return token.isascii() and token.isalpha() and len(token) >= 3 and lowered not in ALLOWED_ACRONYMS


def _looks_like_vendor_name(compact: str) -> bool:
    return "아이앤아" in compact or compact.endswith(("컨소시엄", "주식회사"))


def _looks_like_organization_name(compact: str) -> bool:
    return compact.endswith(("공사", "공단", "평가원", "연구원", "재단", "위원회", "진흥원", "협회", "청", "부"))


def _compact_generic(text: str) -> str:
    compact = text.lower()
    for mark in (" ", ".", "/", "\\", "-", "_", ",", "·"):
        compact = compact.replace(mark, "")
    return compact


def _is_technical_design_token(token: str) -> bool:
    return any(
        term in token
        for term in (
            "클라우드",
            "msa",
            "마이크로서비스",
            "api",
            "컨테이너",
            "쿠버네티스",
            "kubernetes",
            "데브옵스",
            "cicd",
            "데이터",
            "인터페이스",
            "연계",
            "보안",
            "인프라",
            "서비스",
            "플랫폼",
        )
    )


GENERIC_ANCHOR_COMPACT_TERMS = {_compact_generic(term) for term in GENERIC_ANCHOR_TERMS}
DOMAIN_STOPWORD_COMPACT_TERMS = {_compact_generic(term) for term in DOMAIN_STOPWORDS}
CANONICAL_VARIANT_COMPACT_TERMS = {
    _compact_generic(variant)
    for _, variants in (*TECHNICAL_DESIGN_PHRASES, *RESEARCH_DOMAIN_PHRASES, *ARCHITECTURE_PHRASES)
    for variant in variants
}
ALLOWED_ACRONYMS = {
    "ai",
    "msa",
    "api",
    "iris",
    "aws",
    "azure",
    "gcp",
    "ncp",
    "saas",
    "paas",
    "iaas",
    "devops",
    "kubernetes",
    "openapi",
    "docker",
    "terraform",
    "istio",
    "lambda",
}

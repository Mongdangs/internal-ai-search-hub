from __future__ import annotations

from pathlib import Path
import re


def is_temp_or_hidden(path: Path) -> bool:
    return any(part.startswith(".") or _is_temp_folder_name(part) for part in path.parts) or path.name.startswith("~$")


def is_old_path(path: Path) -> bool:
    return any(_is_old_folder_name(part) for part in path.parts)


def is_reference_path(path: Path) -> bool:
    return any(_is_reference_folder_name(part) for part in path.parts)


def _is_old_folder_name(name: str) -> bool:
    normalized = name.strip().lower()
    return normalized == "old" or normalized.endswith(".old") or normalized.endswith("_old") or normalized.endswith("-old")


def _is_reference_folder_name(name: str) -> bool:
    normalized = _compact_name(name)
    return (
        "참고자료" in normalized
        or "참조자료" in normalized
        or "참고용" in normalized
        or "참조용" in normalized
        or "참고요약" in normalized
        or "참조요약" in normalized
        or "참고" in normalized
        or "참조" in normalized
        or normalized in {"참고", "참조"}
        or normalized.startswith("참고")
        or normalized.startswith("참조")
        or "고객제공자료" in normalized
        or "고객제공" in normalized
        or _is_admin_material_name(normalized)
        or normalized in {"reference", "references"}
        or normalized.endswith(".reference")
        or normalized.endswith(".references")
    )


def _compact_name(name: str) -> str:
    compact = name.strip().lower()
    for mark in (" ", "_", "-", ".", "(", ")", "[", "]"):
        compact = compact.replace(mark, "")
    return re.sub(r"^[0-9]+", "", compact)


def _is_temp_folder_name(name: str) -> bool:
    normalized = _compact_name(name)
    return normalized in {"temp", "tmp", "임시"}


def _is_admin_material_name(normalized: str) -> bool:
    admin_terms = (
        "관리산출물",
        "사업관리",
        "계약",
        "계약cm",
        "cm30",
        "cm50",
        "증빙",
        "증빙서류",
        "신용평가",
        "건강보험",
        "자격득실",
        "등급확인",
        "착수계",
        "서약서",
        "공문",
        "발신공문",
        "수신공문",
        "의사소통관리",
        "보안관리",
        "감리",
        "양식",
        "출입증",
        "업체등록",
        "사업자등록증",
        "sw제품",
        "상용sw",
        "라이선스",
        "보증",
        "하자",
        "하자보증",
        "검수",
        "검사",
        "완료검사",
        "납품",
        "납품확인",
        "확약서",
        "구매",
        "물품",
        "자료요청",
        "요청의건",
        "실적",
        "투입인력",
        "프로파일",
        "수행조직",
        "정보화조직",
        "조견표",
        "일반현황",
        "제안업체",
        "템플릿",
        "기타문서",
        "차량주차등록",
        "주차장이용",
    )
    return any(term in normalized for term in admin_terms)


def has_exclude_pattern(path: Path, patterns: tuple[str, ...]) -> bool:
    text = str(path).lower()
    normalized = text.replace("/", "\\")
    return any(pattern and (pattern.lower() in text or pattern.lower() in normalized) for pattern in patterns)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

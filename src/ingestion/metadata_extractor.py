from __future__ import annotations

import hashlib
import re
from pathlib import Path

from src.models import DocumentMetadata, ProjectMetadata


YEAR_RE = re.compile(r"(20\d{2})")
DATE_RE = re.compile(r"(20\d{2})(\d{4})$")
SHORT_DATE_RE = re.compile(r"(\d{2})(\d{4})$")
BUSINESS_TYPES = ("ISP", "ISMP", "BPR", "PI", "컨설팅", "구축", "운영")
DOCUMENT_TYPE_RULES = (
    ("제안요청서", "RFP"),
    ("rfp", "RFP"),
    ("제안서", "제안서"),
    ("보고서", "보고서"),
    ("회의록", "회의록"),
    ("요구사항", "요구사항정의서"),
    ("이행계획", "이행계획서"),
    ("목표모델", "목표모델"),
)


def stable_id(value: str, prefix: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{prefix}_{digest}"


class MetadataExtractor:
    def __init__(self, root_folder: str | Path) -> None:
        self.root_folder = Path(root_folder).resolve()

    def project_for(self, file_path: str | Path) -> ProjectMetadata:
        path = Path(file_path).resolve()
        try:
            relative = path.relative_to(self.root_folder)
        except ValueError:
            relative = path
        project_folder = relative.parts[0] if len(relative.parts) > 1 else self.root_folder.name
        project_name, client_name, year, business_type = self._parse_project_folder(project_folder)
        folder_path = str(self.root_folder / project_folder) if project_folder != self.root_folder.name else str(self.root_folder)
        return ProjectMetadata(
            project_id=stable_id(folder_path, "prj"),
            project_name=project_name,
            client_name=client_name,
            year=year,
            business_type=business_type,
            folder_path=folder_path,
        )

    def document_for(self, file_path: str | Path, project_id: str) -> DocumentMetadata:
        path = Path(file_path).resolve()
        return DocumentMetadata(
            document_id=stable_id(str(path), "doc"),
            project_id=project_id,
            document_title=path.stem,
            document_type=infer_document_type(path),
            file_path=str(path),
            file_type=path.suffix.lower().lstrip("."),
            file_name=path.name,
            is_final=1 if any(word in path.stem.lower() for word in ("final", "최종", "완료")) else 0,
        )

    def _parse_project_folder(self, folder_name: str) -> tuple[str, str, str, str]:
        parts = [part for part in re.split(r"[_\-\s]+", folder_name) if part]
        year = ""
        client_name = ""
        business_type = ""
        project_terms: list[str] = []

        for part in parts:
            parsed_year = parse_year_token(part)
            if not year and parsed_year:
                year = parsed_year
                continue
            if not client_name:
                client_name = part
                continue
            if any(kind.lower() == part.lower() for kind in BUSINESS_TYPES):
                business_type = part
            project_terms.append(part)

        project_name = " ".join(project_terms) if project_terms else folder_name
        return project_name, client_name, year, business_type


def infer_document_type(path: str | Path) -> str:
    lower_name = Path(path).name.lower()
    for pattern, document_type in DOCUMENT_TYPE_RULES:
        if pattern.lower() in lower_name:
            return document_type
    return "기타 산출물"


def parse_year_token(token: str) -> str:
    if YEAR_RE.fullmatch(token):
        return token
    match = DATE_RE.fullmatch(token)
    if match:
        return match.group(1)
    match = SHORT_DATE_RE.fullmatch(token)
    if match:
        year = int(match.group(1))
        return f"20{year:02d}" if year < 70 else f"19{year:02d}"
    return ""

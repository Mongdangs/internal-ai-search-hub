from __future__ import annotations

from pathlib import Path

from src.ingestion.exceptions import PasswordProtectedDocument
from src.ingestion.heading_extractor import enrich_units_with_headings
from src.models import ParsedUnit
from src.utils.page_label import extract_display_page_label
from src.utils.text_cleaner import clean_text


class PdfParser:
    supported = (".pdf",)

    def parse(self, path: str | Path) -> list[ParsedUnit]:
        file_path = Path(path)
        errors: list[str] = []
        for parser in (self._parse_with_pymupdf, self._parse_with_pdfplumber):
            try:
                units = parser(file_path)
                if units:
                    return enrich_units_with_headings(units)
            except PasswordProtectedDocument:
                raise
            except ImportError as exc:
                errors.append(str(exc))
            except Exception as exc:
                errors.append(f"{parser.__name__}: {exc}")
        raise RuntimeError(f"PDF parsing failed for {file_path}: {'; '.join(errors)}")

    def _parse_with_pymupdf(self, path: Path) -> list[ParsedUnit]:
        import fitz

        units: list[ParsedUnit] = []
        with fitz.open(path) as doc:
            if doc.needs_pass:
                raise PasswordProtectedDocument(f"Password protected PDF skipped: {path}")
            for index, page in enumerate(doc, start=1):
                text = clean_text(page.get_text("text"))
                if text:
                    units.append(ParsedUnit(page_no=index, text=text, display_page=extract_display_page_label(text, index)))
        return units

    def _parse_with_pdfplumber(self, path: Path) -> list[ParsedUnit]:
        import pdfplumber

        units: list[ParsedUnit] = []
        with pdfplumber.open(path) as pdf:
            if getattr(pdf, "is_encrypted", False):
                raise PasswordProtectedDocument(f"Password protected PDF skipped: {path}")
            for index, page in enumerate(pdf.pages, start=1):
                text = clean_text(page.extract_text() or "")
                if text:
                    units.append(ParsedUnit(page_no=index, text=text, display_page=extract_display_page_label(text, index)))
        return units

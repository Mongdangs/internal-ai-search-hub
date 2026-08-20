from __future__ import annotations

from pathlib import Path

from src.ingestion.heading_extractor import enrich_units_with_headings
from src.models import ParsedUnit
from src.utils.text_cleaner import clean_text


class DocxParser:
    supported = (".docx",)

    def parse(self, path: str | Path) -> list[ParsedUnit]:
        from docx import Document

        document = Document(str(path))
        units: list[ParsedUnit] = []
        buffer: list[str] = []
        page_no = 1
        section_title = ""

        for paragraph in document.paragraphs:
            text = clean_text(paragraph.text)
            if not text:
                continue
            if paragraph.style and paragraph.style.name.lower().startswith("heading"):
                if buffer:
                    units.append(ParsedUnit(page_no=page_no, text=clean_text("\n".join(buffer)), section_title=section_title, display_page=str(page_no)))
                    page_no += 1
                    buffer = []
                section_title = text
            buffer.append(text)
            if sum(len(item) for item in buffer) >= 1200:
                units.append(ParsedUnit(page_no=page_no, text=clean_text("\n".join(buffer)), section_title=section_title, display_page=str(page_no)))
                page_no += 1
                buffer = []

        if buffer:
            units.append(ParsedUnit(page_no=page_no, text=clean_text("\n".join(buffer)), section_title=section_title, display_page=str(page_no)))
        return enrich_units_with_headings(units)

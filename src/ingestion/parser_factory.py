from __future__ import annotations

from pathlib import Path

from .docx_parser import DocxParser
from .pdf_parser import PdfParser
from .ppt_parser import PptParser
from .pptx_parser import PptxParser


class ParserFactory:
    def __init__(self) -> None:
        self.parsers = {
            ".pdf": PdfParser(),
            ".docx": DocxParser(),
            ".ppt": PptParser(),
            ".pptx": PptxParser(),
        }

    def parse(self, path: str | Path):
        suffix = Path(path).suffix.lower()
        parser = self.parsers.get(suffix)
        if parser is None:
            raise NotImplementedError(f"Unsupported file type: {suffix}")
        return parser.parse(path)

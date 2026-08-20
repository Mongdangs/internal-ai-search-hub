from __future__ import annotations

from pathlib import Path

from src.ingestion.parser_factory import ParserFactory
from src.utils.text_cleaner import clean_text


class RfpParser:
    def __init__(self) -> None:
        self.factory = ParserFactory()

    def parse_text(self, path: str | Path) -> str:
        units = self.factory.parse(path)
        return clean_text("\n\n".join(unit.text for unit in units))

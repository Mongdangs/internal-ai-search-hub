from __future__ import annotations

from pathlib import Path

from src.models import ParsedUnit


class HwpParser:
    supported = (".hwp", ".hwpx")

    def parse(self, path: str | Path) -> list[ParsedUnit]:
        raise NotImplementedError(f"HWP parsing is unsupported in this PoC: {path}")

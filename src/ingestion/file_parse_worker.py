from __future__ import annotations

import contextlib
import json
import sys

from src.ingestion.parser_factory import ParserFactory


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1]
    with contextlib.redirect_stdout(sys.stderr):
        units = ParserFactory().parse(path)
    print(
        json.dumps(
            [
                {
                    "page_no": unit.page_no,
                    "text": unit.text,
                    "section_title": unit.section_title,
                    "display_page": unit.display_page,
                    "chapter_title": unit.chapter_title,
                    "heading_path": unit.heading_path,
                }
                for unit in units
            ],
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

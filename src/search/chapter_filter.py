from __future__ import annotations


class ChapterFilterNotFound(ValueError):
    def __init__(self, chapter_filter: str, suggestions: list[str], metadata_ready: bool = True) -> None:
        self.chapter_filter = chapter_filter
        self.suggestions = suggestions
        self.metadata_ready = metadata_ready
        if metadata_ready:
            message = f"'{chapter_filter}' 챕터명을 찾지 못했습니다."
        else:
            message = "현재 인덱스에 챕터/섹션 메타데이터가 없습니다. 재인덱싱이 필요합니다."
        super().__init__(message)

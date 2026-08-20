from __future__ import annotations

from pathlib import Path

from src.utils.file_utils import has_exclude_pattern, is_old_path, is_reference_path, is_temp_or_hidden


class FolderScanner:
    def __init__(
        self,
        supported_extensions: tuple[str, ...],
        exclude_patterns: tuple[str, ...] = (),
        exclude_reference_materials: bool = True,
    ) -> None:
        self.supported_extensions = tuple(ext.lower() for ext in supported_extensions)
        self.exclude_patterns = exclude_patterns
        self.exclude_reference_materials = exclude_reference_materials
        self.last_excluded: list[dict[str, str]] = []

    def scan(self, root_folder: str | Path) -> list[Path]:
        root = Path(root_folder).expanduser()
        if not root.exists():
            raise FileNotFoundError(f"Folder not found: {root}")
        files: list[Path] = []
        self.last_excluded = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if is_temp_or_hidden(path):
                self._exclude(path, "temp_or_hidden")
                continue
            if is_old_path(path):
                self._exclude(path, "old_path")
                continue
            if self.exclude_reference_materials and is_reference_path(path):
                self._exclude(path, "reference_material")
                continue
            if path.suffix.lower() not in self.supported_extensions:
                self._exclude(path, "unsupported_extension")
                continue
            if has_exclude_pattern(path, self.exclude_patterns):
                self._exclude(path, "exclude_pattern")
                continue
            files.append(path)
        return sorted(files, key=lambda p: str(p).lower())

    def _exclude(self, path: Path, reason: str) -> None:
        self.last_excluded.append({"file_path": str(path), "reason": reason})

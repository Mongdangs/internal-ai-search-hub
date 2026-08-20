from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IndexingConfig:
    supported_extensions: tuple[str, ...] = (".pdf", ".docx", ".ppt", ".pptx")
    chunk_size: int = 1000
    chunk_overlap: int = 150
    use_ocr: bool = False
    parse_timeout_seconds: int = 120


@dataclass(frozen=True)
class SearchConfig:
    top_k: int = 20
    keyword_weight: float = 0.4
    vector_weight: float = 0.6


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str = "hashing"
    model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    dimensions: int = 384


@dataclass(frozen=True)
class SecurityConfig:
    exclude_patterns: tuple[str, ...] = ("견적", "원가", "계약", "개인정보")
    enable_acl: bool = False
    exclude_reference_materials: bool = True


@dataclass(frozen=True)
class UiConfig:
    page_title: str = "사내 산출물·제안서 근거형 검색 PoC"


@dataclass(frozen=True)
class AppConfig:
    root_folders: tuple[str, ...]
    data_dir: Path
    indexing: IndexingConfig
    search: SearchConfig
    embedding: EmbeddingConfig
    security: SecurityConfig
    ui: UiConfig

    @property
    def database_path(self) -> Path:
        return self.data_dir / "db" / "search.sqlite3"

    @property
    def vector_index_path(self) -> Path:
        return self.data_dir / "indexes" / "vectors.json"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError:
        return _read_simple_yaml(text)
    data = yaml.safe_load(text) or {}
    return data


def _read_simple_yaml(text: str) -> dict[str, Any]:
    lines = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append((indent, raw_line.strip()))

    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    for index, (indent, content) in enumerate(lines):
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if content.startswith("- "):
            if isinstance(parent, list):
                parent.append(_parse_scalar(content[2:].strip()))
            continue

        if ":" not in content:
            continue
        key, raw_value = content.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value:
            parent[key] = _parse_scalar(raw_value)
            continue

        next_content = lines[index + 1][1] if index + 1 < len(lines) else ""
        container: list[Any] | dict[str, Any] = [] if next_content.startswith("- ") else {}
        parent[key] = container
        stack.append((indent, container))

    return root


def _parse_scalar(value: str) -> Any:
    if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
        return value[1:-1]
    lower = value.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path
    data = _read_yaml(config_path)

    data_dir = Path(data.get("data_dir", "data"))
    if not data_dir.is_absolute():
        data_dir = config_path.parent / data_dir

    indexing = data.get("indexing", {})
    search = data.get("search", {})
    embedding = data.get("embedding", {})
    security = data.get("security", {})
    ui = data.get("ui", {})

    return AppConfig(
        root_folders=_root_folders(data),
        data_dir=data_dir,
        indexing=IndexingConfig(
            supported_extensions=tuple(ext.lower() for ext in indexing.get("supported_extensions", [".pdf", ".docx", ".ppt", ".pptx"])),
            chunk_size=int(indexing.get("chunk_size", 1000)),
            chunk_overlap=int(indexing.get("chunk_overlap", 150)),
            use_ocr=bool(indexing.get("use_ocr", False)),
            parse_timeout_seconds=int(indexing.get("parse_timeout_seconds", 120)),
        ),
        search=SearchConfig(
            top_k=int(search.get("top_k", 20)),
            keyword_weight=float(search.get("keyword_weight", 0.4)),
            vector_weight=float(search.get("vector_weight", 0.6)),
        ),
        embedding=EmbeddingConfig(
            provider=str(embedding.get("provider", "hashing")),
            model_name=str(embedding.get("model_name", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")),
            dimensions=int(embedding.get("dimensions", 384)),
        ),
        security=SecurityConfig(
            exclude_patterns=tuple(
                security.get(
                    "exclude_patterns",
                    ["견적", "원가", "계약", "개인정보", "\\old\\", "/old/", "backup", "백업", "sample", "temp", "임시", "~$"],
                )
            ),
            enable_acl=bool(security.get("enable_acl", False)),
            exclude_reference_materials=bool(security.get("exclude_reference_materials", True)),
        ),
        ui=UiConfig(page_title=str(ui.get("page_title", "사내 산출물·제안서 근거형 검색 PoC"))),
    )


def _root_folders(data: dict[str, Any]) -> tuple[str, ...]:
    folders = data.get("root_folders")
    if isinstance(folders, str):
        return (folders,)
    if folders:
        return tuple(str(folder) for folder in folders)
    return (str(data.get("root_folder", "D:/Projects")),)

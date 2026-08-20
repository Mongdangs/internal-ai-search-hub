from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from dataclasses import replace

from src.config import AppConfig
from src.db.repositories import SearchRepository
from src.ingestion.heading_extractor import DEFAULT_CHAPTER_TITLE, chapter_filter_norms
from src.indexing.chunker import Chunker
from src.indexing.document_dedup import (
    DocumentProfile,
    canonical_document_key,
    content_similarity,
    document_signature,
    file_mtime as dedup_file_mtime,
    newest_first,
)
from src.indexing.index_metadata import INDEX_VERSION, backup_existing_index, utc_now, write_reindex_report
from src.indexing.vector_index import VectorIndex, cosine_similarity, create_embedding_provider, create_vector_index
from src.ingestion.exceptions import PasswordProtectedDocument
from src.ingestion.folder_scanner import FolderScanner
from src.ingestion.metadata_extractor import MetadataExtractor
from src.ingestion.parser_factory import ParserFactory
from src.models import IndexSummary, ParsedUnit, SearchResult
from src.search.chapter_filter import ChapterFilterNotFound
from src.search.ranking import rank_chunk_ids
from src.search.recency import file_mtime, recency_boost
from src.search.filters import active_file_path_prefixes, file_path_matches_filters
from src.search.scope_boost import scoped_boost
from src.utils.logger import get_logger


logger = get_logger(__name__)


class SearchService:
    def __init__(self, config: AppConfig, repository: SearchRepository) -> None:
        self.config = config
        self.repository = repository
        provider = create_embedding_provider(
            config.embedding.provider,
            config.embedding.model_name,
            config.embedding.dimensions,
        )
        self.embedding_provider = provider
        self._vector_index: VectorIndex | None = None
        self.parser_factory = ParserFactory()
        self.chunker = Chunker(config.indexing.chunk_size, config.indexing.chunk_overlap)

    @property
    def vector_index(self) -> VectorIndex:
        if self._vector_index is None:
            self._vector_index = create_vector_index(self.config.vector_index_path, self.embedding_provider)
        return self._vector_index

    def index_folder(self, root_folder: str | list[str] | tuple[str, ...], rebuild: bool = False) -> IndexSummary:
        started_at = utc_now()
        backup_path = ""
        if rebuild:
            backup_path = str(backup_existing_index(self.config.data_dir))
            self.repository.clear()
            self.vector_index.clear()

        scanner = FolderScanner(
            self.config.indexing.supported_extensions,
            self.config.security.exclude_patterns,
            self.config.security.exclude_reference_materials,
        )
        unsupported: list[str] = []
        failed_documents: list[dict] = []
        excluded_files: list[dict] = []
        indexed_documents: list[dict] = []
        project_ids: set[str] = set()
        document_ids: set[str] = set()
        chunk_count = 0
        profiles_by_project = _profiles_by_project([] if rebuild else self.repository.iter_document_profiles())
        existing_document_ids = set() if rebuild else self.repository.document_ids()

        root_folders = [root_folder] if isinstance(root_folder, (str, Path)) else list(root_folder)
        for root in root_folders:
            metadata = MetadataExtractor(root)
            scanned_files = scanner.scan(root)
            excluded_files.extend(scanner.last_excluded)
            files = newest_first(scanned_files) if rebuild else scanned_files
            logger.info("Index scan root=%s files=%s rebuild=%s", root, len(files), rebuild)
            skipped_count = 0
            for path in files:
                try:
                    project = metadata.project_for(path)
                    document = metadata.document_for(path, project.project_id)
                    if not rebuild and document.document_id in existing_document_ids:
                        skipped_count += 1
                        continue
                    units = self._parse_file(path)
                    full_text = "\n".join(unit.text for unit in units)
                    signature = document_signature(full_text)
                    canonical_key = canonical_document_key(path, root)
                    mtime = dedup_file_mtime(path)
                    duplicate = _find_duplicate(
                        project.project_id,
                        canonical_key,
                        signature,
                        mtime,
                        profiles_by_project,
                    )
                    if duplicate and duplicate.file_mtime >= mtime:
                        skipped_count += 1
                        excluded_files.append(
                            {
                                "file_path": str(path),
                                "reason": "duplicate_older_or_same",
                                "duplicate_document_id": duplicate.document_id,
                            }
                        )
                        continue
                    if duplicate:
                        removed_chunk_ids = self.repository.delete_documents([duplicate.document_id])
                        self.vector_index.delete_chunks(removed_chunk_ids, save=False)
                        profiles_by_project[project.project_id] = [
                            profile
                            for profile in profiles_by_project.get(project.project_id, [])
                            if profile.document_id != duplicate.document_id
                        ]
                    document = replace(
                        document,
                        canonical_key=canonical_key,
                        content_signature=signature,
                        file_mtime=mtime,
                    )
                    chunks = self.chunker.build_chunks(document, units, project)
                    self.repository.upsert_project(project)
                    self.repository.upsert_document(document)
                    self.repository.replace_chunks(document, project, chunks)
                    self.vector_index.upsert_chunks(chunks, save=False)
                    indexed_documents.append(
                        {
                            "source_file": document.file_name,
                            "file_path": document.file_path,
                            "document_id": document.document_id,
                            "project_id": project.project_id,
                            "chunk_count": len(chunks),
                            "chapters": sorted({chunk.chapter_title for chunk in chunks if chunk.chapter_title}),
                        }
                    )
                    project_ids.add(project.project_id)
                    document_ids.add(document.document_id)
                    existing_document_ids.add(document.document_id)
                    chunk_count += len(chunks)
                    profiles_by_project.setdefault(project.project_id, []).append(
                        DocumentProfile(
                            document_id=document.document_id,
                            project_id=project.project_id,
                            canonical_key=canonical_key,
                            content_signature=signature,
                            file_mtime=mtime,
                        )
                    )
                    if len(document_ids) % 25 == 0:
                        logger.info(
                            "Index progress root=%s indexed_docs=%s chunks=%s skipped=%s current=%s",
                            root,
                            len(document_ids),
                            chunk_count,
                            skipped_count,
                            path,
                        )
                except NotImplementedError:
                    unsupported.append(str(path))
                    failed_documents.append({"source_file": str(path), "error": "unsupported parser"})
                except PasswordProtectedDocument as exc:
                    logger.info("%s", exc)
                    unsupported.append(str(path))
                    failed_documents.append({"source_file": str(path), "error": str(exc)})
                except subprocess.CalledProcessError as exc:
                    detail = (exc.stderr or exc.stdout or str(exc))[-800:]
                    logger.warning("Failed to index %s: %s", path, detail)
                    unsupported.append(str(path))
                    failed_documents.append({"source_file": str(path), "error": detail})
                except Exception as exc:
                    logger.warning("Failed to index %s: %s", path, exc)
                    unsupported.append(str(path))
                    failed_documents.append({"source_file": str(path), "error": str(exc)})

        self.vector_index.save()
        validation = self.validate_index()
        chapters = self.repository.chapter_report(limit=500)
        report_path = write_reindex_report(
            self.config.data_dir,
            {
                "started_at": started_at,
                "finished_at": utc_now(),
                "index_version": INDEX_VERSION,
                "backup_path": backup_path,
                "rebuild": rebuild,
                "root_folders": [str(folder) for folder in root_folders],
                "summary": {
                    "project_count": len(project_ids),
                    "document_count": len(document_ids),
                    "chunk_count": chunk_count,
                    "unsupported_count": len(unsupported),
                    "excluded_file_count": len(excluded_files),
                },
                "excluded_files": excluded_files,
                "indexed_documents": indexed_documents,
                "failed_documents": failed_documents,
                "chapters": chapters,
                "validation": validation,
            },
        )

        return IndexSummary(
            project_count=len(project_ids),
            document_count=len(document_ids),
            chunk_count=chunk_count,
            unsupported_files=unsupported,
            backup_path=backup_path,
            report_path=str(report_path),
            index_version=INDEX_VERSION,
            chapters=chapters,
            validation=validation,
            failed_documents=failed_documents,
        )

    def validate_index(self) -> dict:
        return self.repository.validate_index_metadata(INDEX_VERSION)

    def reindex_document(self, file_path: str | Path) -> IndexSummary:
        started_at = utc_now()
        path = Path(file_path)
        backup_path = str(backup_existing_index(self.config.data_dir))
        root = _matching_root(path, self.config.root_folders)
        metadata = MetadataExtractor(root)
        project = metadata.project_for(path)
        document = metadata.document_for(path, project.project_id)

        units = self._parse_file(path)
        full_text = "\n".join(unit.text for unit in units)
        signature = document_signature(full_text)
        canonical_key = canonical_document_key(path, root)
        mtime = dedup_file_mtime(path)
        profiles_by_project = _profiles_by_project(self.repository.iter_document_profiles())
        duplicate = _find_duplicate(project.project_id, canonical_key, signature, mtime, profiles_by_project)
        if duplicate and duplicate.document_id != document.document_id and duplicate.file_mtime >= mtime:
            validation = self.validate_index()
            report_path = write_reindex_report(
                self.config.data_dir,
                {
                    "started_at": started_at,
                    "finished_at": utc_now(),
                    "index_version": INDEX_VERSION,
                    "backup_path": backup_path,
                    "rebuild": False,
                    "root_folders": [str(root)],
                    "summary": {
                        "project_count": 0,
                        "document_count": 0,
                        "chunk_count": 0,
                        "unsupported_count": 0,
                    },
                    "indexed_documents": [],
                    "failed_documents": [
                        {
                            "source_file": str(path),
                            "error": "newer duplicate already indexed",
                            "duplicate_document_id": duplicate.document_id,
                        }
                    ],
                    "chapters": self.repository.chapter_report(limit=500),
                    "validation": validation,
                },
            )
            return IndexSummary(
                project_count=0,
                document_count=0,
                chunk_count=0,
                unsupported_files=[],
                backup_path=backup_path,
                report_path=str(report_path),
                index_version=INDEX_VERSION,
                chapters=self.repository.chapter_report(limit=500),
                validation=validation,
                failed_documents=[
                    {
                        "source_file": str(path),
                        "error": "newer duplicate already indexed",
                        "duplicate_document_id": duplicate.document_id,
                    }
                ],
            )

        removed_chunk_ids = self.repository.delete_documents([document.document_id])
        self.vector_index.delete_chunks(removed_chunk_ids, save=False)
        if duplicate and duplicate.document_id != document.document_id:
            duplicate_chunk_ids = self.repository.delete_documents([duplicate.document_id])
            self.vector_index.delete_chunks(duplicate_chunk_ids, save=False)

        document = replace(
            document,
            canonical_key=canonical_key,
            content_signature=signature,
            file_mtime=mtime,
        )
        chunks = self.chunker.build_chunks(document, units, project)
        self.repository.upsert_project(project)
        self.repository.upsert_document(document)
        self.repository.replace_chunks(document, project, chunks)
        self.vector_index.upsert_chunks(chunks, save=False)
        self.vector_index.save()

        validation = self.validate_index()
        chapters = self.repository.chapter_report(limit=500)
        report_path = write_reindex_report(
            self.config.data_dir,
            {
                "started_at": started_at,
                "finished_at": utc_now(),
                "index_version": INDEX_VERSION,
                "backup_path": backup_path,
                "rebuild": False,
                "root_folders": [str(root)],
                "summary": {
                    "project_count": 1,
                    "document_count": 1,
                    "chunk_count": len(chunks),
                    "unsupported_count": 0,
                },
                "indexed_documents": [
                    {
                        "source_file": document.file_name,
                        "file_path": document.file_path,
                        "document_id": document.document_id,
                        "project_id": project.project_id,
                        "chunk_count": len(chunks),
                        "chapters": sorted({chunk.chapter_title for chunk in chunks if chunk.chapter_title}),
                    }
                ],
                "failed_documents": [],
                "chapters": chapters,
                "validation": validation,
            },
        )
        return IndexSummary(
            project_count=1,
            document_count=1,
            chunk_count=len(chunks),
            unsupported_files=[],
            backup_path=backup_path,
            report_path=str(report_path),
            index_version=INDEX_VERSION,
            chapters=chapters,
            validation=validation,
            failed_documents=[],
        )

    def search(self, query: str, top_k: int | None = None, filters: dict | None = None) -> list[SearchResult]:
        top_k = top_k or self.config.search.top_k
        filters = self._prepare_filters(filters)
        candidate_k = _candidate_limit(top_k, filters)
        keyword_scores = self.repository.keyword_search(query, top_k=candidate_k, filters=filters)
        rows = {}
        if self.config.embedding.provider == "hashing":
            rows = self.repository.get_chunks_by_ids(list(keyword_scores))
            vector_scores = _hashing_vector_scores(query, rows, self.embedding_provider, candidate_k)
        else:
            vector_scores = self.vector_index.search(query, top_k=candidate_k)
        ranked = rank_chunk_ids(
            keyword_scores,
            vector_scores,
            self.config.search.keyword_weight,
            self.config.search.vector_weight,
            candidate_k,
            allow_vector_only=self.config.embedding.provider != "hashing",
        )
        if not rows:
            rows = self.repository.get_chunks_by_ids([chunk_id for chunk_id, _, _, _ in ranked])
        mtimes = {chunk_id: _row_file_mtime(row) for chunk_id, row in rows.items()}
        candidate_mtimes = list(mtimes.values())
        results: list[SearchResult] = []
        for chunk_id, score, keyword_score, vector_score in ranked:
            row = rows.get(chunk_id)
            if not row:
                continue
            if not _row_matches_filters(row, filters):
                continue
            boosted_score = score * scoped_boost(row, filters) * recency_boost(mtimes.get(chunk_id, 0.0), candidate_mtimes)
            results.append(self.repository.make_search_result(row, boosted_score, keyword_score, vector_score, query))
        results.sort(key=lambda result: result.score, reverse=True)
        return results[:top_k]

    def _prepare_filters(self, filters: dict | None) -> dict | None:
        if not filters or not filters.get("chapter_filter"):
            return filters
        prepared = dict(filters)
        chapter_filter = str(prepared["chapter_filter"]).strip()
        chapter_norms = chapter_filter_norms(chapter_filter)
        prepared["chapter_norms"] = chapter_norms
        metadata_ready = self.repository.has_heading_metadata(prepared)
        if not metadata_ready or not self.repository.has_chapter_matches(chapter_norms, prepared):
            suggestions = self.repository.suggest_chapters(chapter_filter, prepared)
            raise ChapterFilterNotFound(chapter_filter, suggestions, metadata_ready=metadata_ready)
        return prepared

    def _parse_file(self, path: Path) -> list[ParsedUnit]:
        completed = subprocess.run(
            [sys.executable, "-B", "-m", "src.ingestion.file_parse_worker", str(path)],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.config.indexing.parse_timeout_seconds,
            check=True,
        )
        data = json.loads(completed.stdout)
        return [
            ParsedUnit(
                page_no=int(item["page_no"]),
                text=item["text"],
                section_title=item.get("section_title", ""),
                display_page=item.get("display_page", ""),
                chapter_title=item.get("chapter_title", "") or DEFAULT_CHAPTER_TITLE,
                heading_path=item.get("heading_path", "") or item.get("chapter_title", "") or DEFAULT_CHAPTER_TITLE,
            )
            for item in data
        ]


def _row_matches_filters(row, filters: dict | None) -> bool:
    if not filters:
        return True
    if filters.get("document_type") and row["document_type"] != filters["document_type"]:
        return False
    if not file_path_matches_filters(str(row["file_path"]), filters):
        return False
    chapter_norms = filters.get("chapter_norms") or []
    if chapter_norms:
        heading_norm = " ".join(
            str(row[key] or "")
            for key in (
                "normalized_chapter_title",
                "canonical_chapter_title",
                "canonical_section_title",
                "canonical_subsection_title",
                "canonical_heading_path",
                "raw_heading_path",
                "normalized_heading_path",
            )
            if key in row.keys()
        )
        return any(norm and norm in heading_norm for norm in chapter_norms)
    return True


def _candidate_limit(top_k: int, filters: dict | None) -> int:
    if active_file_path_prefixes(filters):
        return max(top_k * 2, 40)
    return max(top_k * 2, 40)


def _row_file_mtime(row) -> float:
    try:
        indexed_mtime = float(row["file_mtime"] or 0.0)
    except (KeyError, TypeError, ValueError):
        indexed_mtime = 0.0
    return indexed_mtime or file_mtime(row["file_path"])


def _hashing_vector_scores(query: str, rows: dict, provider, top_k: int) -> dict[str, float]:
    if not rows:
        return {}
    query_vector = provider.embed_query(query)
    scores = []
    for chunk_id, row in rows.items():
        text = (row["embedding_text"] if "embedding_text" in row.keys() else "") or row["chunk_text"] or ""
        vector = provider.embed_text(text)
        score = cosine_similarity(query_vector, vector)
        if score > 0:
            scores.append((chunk_id, score))
    scores.sort(key=lambda item: item[1], reverse=True)
    if not scores:
        return {}
    max_score = scores[0][1] or 1.0
    return {chunk_id: score / max_score for chunk_id, score in scores[:top_k]}


def _profiles_by_project(profiles: list[DocumentProfile]) -> dict[str, list[DocumentProfile]]:
    grouped: dict[str, list[DocumentProfile]] = {}
    for profile in profiles:
        grouped.setdefault(profile.project_id, []).append(profile)
    return grouped


def _find_duplicate(
    project_id: str,
    canonical_key: str,
    signature: str,
    mtime: float,
    profiles_by_project: dict[str, list[DocumentProfile]],
) -> DocumentProfile | None:
    best: DocumentProfile | None = None
    for profile in profiles_by_project.get(project_id, []):
        if content_similarity(profile.content_signature, signature) >= 0.8:
            if best is None or profile.file_mtime > best.file_mtime:
                best = profile
    return best


def _matching_root(path: Path, roots: tuple[str, ...]) -> str:
    try:
        resolved_path = path.resolve()
    except OSError:
        resolved_path = path
    for root in roots:
        root_path = Path(root)
        try:
            resolved_root = root_path.resolve()
            resolved_path.relative_to(resolved_root)
            return str(root_path)
        except (OSError, ValueError):
            continue
    return str(path.parent)

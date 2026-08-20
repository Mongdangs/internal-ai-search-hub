from __future__ import annotations

import hashlib
import json
from json import JSONDecodeError
import math
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Protocol

from src.models import Chunk
from src.utils.file_utils import ensure_parent
from src.utils.korean_tokenizer import tokenize


class EmbeddingProvider:
    def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_query(self, query: str) -> list[float]:
        return self.embed_text(query)


class HashingEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = tokenize(text)
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8", errors="ignore")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed_text(self, text: str) -> list[float]:
        vector = self.model.encode(text, normalize_embeddings=True)
        return [float(value) for value in vector]


def create_embedding_provider(provider: str, model_name: str, dimensions: int) -> EmbeddingProvider:
    if provider == "sentence-transformers":
        return SentenceTransformerEmbeddingProvider(model_name)
    return HashingEmbeddingProvider(dimensions=dimensions)


class VectorIndex(Protocol):
    load_error: str | None

    def save(self) -> None:
        ...

    def clear(self) -> None:
        ...

    def upsert_chunks(self, chunks: list[Chunk], save: bool = True) -> None:
        ...

    def delete_chunks(self, chunk_ids: list[str], save: bool = True) -> None:
        ...

    def search(self, query: str, top_k: int = 20, candidate_ids: set[str] | None = None) -> dict[str, float]:
        ...


def create_vector_index(path: Path, provider: EmbeddingProvider) -> VectorIndex:
    try:
        import faiss  # noqa: F401
        import numpy  # noqa: F401
    except Exception:
        return JsonVectorIndex(path, provider)
    return FaissVectorIndex(path, provider)


class JsonVectorIndex:
    def __init__(self, path: Path, provider: EmbeddingProvider) -> None:
        self.path = Path(path)
        self.provider = provider
        self.vectors: dict[str, list[float]] = {}
        self.load_error: str | None = None
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.vectors = {}
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self.vectors = {item["chunk_id"]: item["vector"] for item in data.get("vectors", [])}
        except (JSONDecodeError, OSError, KeyError, TypeError) as exc:
            self.load_error = f"Vector index was ignored because it could not be read: {exc}"
            self.vectors = {}
            self._backup_corrupt_file()

    def save(self) -> None:
        self.save_from_vectors(self.vectors)

    def save_from_vectors(self, vectors: dict[str, list[float]]) -> None:
        ensure_parent(self.path)
        data = {"vectors": [{"chunk_id": chunk_id, "vector": vector} for chunk_id, vector in vectors.items()]}
        tmp_path = self.path.with_name(f"{self.path.name}.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f)
        for attempt in range(5):
            try:
                os.replace(tmp_path, self.path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2 * (attempt + 1))

    def clear(self) -> None:
        self.vectors = {}
        if self.path.exists():
            self.path.unlink()

    def upsert_chunks(self, chunks: list[Chunk], save: bool = True) -> None:
        for chunk in chunks:
            self.vectors[chunk.chunk_id] = self.provider.embed_text(chunk.embedding_text or chunk.chunk_text)
        if save:
            self.save()

    def delete_chunks(self, chunk_ids: list[str], save: bool = True) -> None:
        for chunk_id in chunk_ids:
            self.vectors.pop(chunk_id, None)
        if save:
            self.save()

    def search(self, query: str, top_k: int = 20, candidate_ids: set[str] | None = None) -> dict[str, float]:
        query_vector = self.provider.embed_query(query)
        scores = []
        items = ((chunk_id, self.vectors[chunk_id]) for chunk_id in candidate_ids if chunk_id in self.vectors) if candidate_ids else self.vectors.items()
        for chunk_id, vector in items:
            score = cosine_similarity(query_vector, vector)
            if score > 0:
                scores.append((chunk_id, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        if not scores:
            return {}
        max_score = scores[0][1] or 1.0
        return {chunk_id: score / max_score for chunk_id, score in scores[:top_k]}

    def _backup_corrupt_file(self) -> None:
        if not self.path.exists():
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.path.with_name(f"{self.path.name}.corrupt.{timestamp}")
        try:
            os.replace(self.path, backup_path)
        except OSError:
            pass


class FaissVectorIndex:
    def __init__(self, path: Path, provider: EmbeddingProvider) -> None:
        self.path = Path(path)
        self.provider = provider
        self.index_path = self.path.with_suffix(".faiss")
        self.metadata_path = self.path.with_suffix(".faiss.json")
        self.vectors: dict[str, list[float]] = {}
        self.chunk_ids: list[str] = []
        self.index = None
        self.load_error: str | None = None
        self.load()

    def load(self) -> None:
        try:
            import faiss
        except Exception as exc:
            self.load_error = f"FAISS is unavailable: {exc}"
            return
        if self.index_path.exists() and self.metadata_path.exists():
            try:
                self.index = faiss.read_index(str(self.index_path))
                metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
                self.chunk_ids = [str(chunk_id) for chunk_id in metadata.get("chunk_ids", [])]
                self.vectors = self._reconstruct_vectors()
                return
            except Exception as exc:
                self.load_error = f"FAISS index was ignored because it could not be read: {exc}"
                self.vectors = {}
                self.chunk_ids = []
                self.index = None

        json_index = JsonVectorIndex(self.path, self.provider)
        self.load_error = json_index.load_error
        self.vectors = dict(json_index.vectors)
        self._rebuild_index()

    def save(self) -> None:
        self._rebuild_index()
        ensure_parent(self.index_path)
        if self.index is not None:
            import faiss

            faiss.write_index(self.index, str(self.index_path))
        self.metadata_path.write_text(json.dumps({"chunk_ids": self.chunk_ids}, ensure_ascii=False), encoding="utf-8")
        JsonVectorIndex(self.path, self.provider).save_from_vectors(self.vectors)

    def clear(self) -> None:
        self.vectors = {}
        self.chunk_ids = []
        self.index = None
        for path in (self.path, self.index_path, self.metadata_path):
            if path.exists():
                path.unlink()

    def upsert_chunks(self, chunks: list[Chunk], save: bool = True) -> None:
        for chunk in chunks:
            self.vectors[chunk.chunk_id] = self.provider.embed_text(chunk.embedding_text or chunk.chunk_text)
        if save:
            self.save()
        else:
            self._rebuild_index()

    def delete_chunks(self, chunk_ids: list[str], save: bool = True) -> None:
        for chunk_id in chunk_ids:
            self.vectors.pop(chunk_id, None)
        if save:
            self.save()
        else:
            self._rebuild_index()

    def search(self, query: str, top_k: int = 20, candidate_ids: set[str] | None = None) -> dict[str, float]:
        if not self.vectors:
            return {}
        self._rebuild_index()
        if self.index is None:
            return {}
        import numpy as np
        import faiss

        query_vector = np.array([self.provider.embed_query(query)], dtype="float32")
        faiss.normalize_L2(query_vector)
        limit = len(self.chunk_ids) if candidate_ids else min(len(self.chunk_ids), max(top_k, 1))
        distances, indexes = self.index.search(query_vector, limit)
        scores = []
        for score, index in zip(distances[0], indexes[0]):
            if index < 0 or index >= len(self.chunk_ids):
                continue
            chunk_id = self.chunk_ids[index]
            if candidate_ids and chunk_id not in candidate_ids:
                continue
            score = float(score)
            if score > 0:
                scores.append((chunk_id, score))
            if len(scores) >= top_k:
                break
        if not scores:
            return {}
        max_score = scores[0][1] or 1.0
        return {chunk_id: score / max_score for chunk_id, score in scores[:top_k]}

    def _rebuild_index(self) -> None:
        if not self.vectors:
            self.index = None
            self.chunk_ids = []
            return
        import numpy as np
        import faiss

        self.chunk_ids = list(self.vectors)
        matrix = np.array([self.vectors[chunk_id] for chunk_id in self.chunk_ids], dtype="float32")
        if matrix.ndim != 2 or matrix.shape[1] == 0:
            self.index = None
            return
        faiss.normalize_L2(matrix)
        self.index = faiss.IndexFlatIP(int(matrix.shape[1]))
        self.index.add(matrix)

    def _reconstruct_vectors(self) -> dict[str, list[float]]:
        if self.index is None:
            return {}
        vectors: dict[str, list[float]] = {}
        for index, chunk_id in enumerate(self.chunk_ids):
            try:
                vector = self.index.reconstruct(index)
            except Exception:
                continue
            vectors[chunk_id] = [float(value) for value in vector]
        return vectors


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right))

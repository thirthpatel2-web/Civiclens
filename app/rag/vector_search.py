"""Dense retrieval.

``InMemoryVectorIndex`` is an exact cosine-similarity index (NumPy) used for tests,
small corpora and as the reference for the pgvector implementation, which must
return the same ordering (pgvector ``<=>`` is cosine *distance*; similarity = 1 - d).
Dimension is validated on every insert/query so an embedding-model change cannot
silently corrupt the index.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from app.rag.models import Chunk


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    va, vb = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if va.shape != vb.shape:
        raise ValueError(f"dimension mismatch: {va.shape[0]} vs {vb.shape[0]}")
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


@dataclass(frozen=True)
class VectorHit:
    chunk_id: str
    similarity: float


class InMemoryVectorIndex:
    def __init__(self, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions
        self._ids: list[str] = []
        self._chunks: dict[str, Chunk] = {}
        self._matrix = np.zeros((0, dimensions), dtype=np.float64)

    def __len__(self) -> int:
        return len(self._ids)

    def add(self, chunk: Chunk, vector: Sequence[float]) -> None:
        v = np.asarray(vector, dtype=np.float64)
        if v.shape != (self.dimensions,):
            raise ValueError(f"expected {self.dimensions} dimensions, got {v.shape}")
        norm = np.linalg.norm(v)
        if not np.isfinite(norm) or norm == 0:
            raise ValueError("cannot index a zero or non-finite vector")
        if chunk.chunk_id in self._chunks:
            self.remove(chunk.chunk_id)
        self._ids.append(chunk.chunk_id)
        self._chunks[chunk.chunk_id] = chunk
        self._matrix = np.vstack([self._matrix, v / norm])

    def remove(self, chunk_id: str) -> None:
        if chunk_id not in self._chunks:
            return
        idx = self._ids.index(chunk_id)
        self._ids.pop(idx)
        del self._chunks[chunk_id]
        self._matrix = np.delete(self._matrix, idx, axis=0)

    def remove_document(self, document_id: str) -> int:
        ids = [cid for cid, c in self._chunks.items() if c.document_id == document_id]
        for cid in ids:
            self.remove(cid)
        return len(ids)

    def search(
        self,
        query_vector: Sequence[float],
        top_k: int = 20,
        *,
        min_similarity: float = -1.0,
        visible: Callable[[Chunk], bool] | None = None,
    ) -> list[VectorHit]:
        q = np.asarray(query_vector, dtype=np.float64)
        if q.shape != (self.dimensions,):
            raise ValueError(f"expected {self.dimensions} dimensions, got {q.shape}")
        norm = np.linalg.norm(q)
        if not self._ids or norm == 0:
            return []
        sims = self._matrix @ (q / norm)
        hits = [
            VectorHit(cid, float(s))
            for cid, s in zip(self._ids, sims, strict=True)
            if s >= min_similarity and (visible is None or visible(self._chunks[cid]))
        ]
        hits.sort(key=lambda h: (-h.similarity, h.chunk_id))
        return hits[:top_k]

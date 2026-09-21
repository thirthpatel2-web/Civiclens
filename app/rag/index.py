"""The searchable corpus: chunk store + BM25 index + vector index kept consistent."""

from __future__ import annotations

from collections.abc import Sequence

from app.rag.bm25 import BM25Index
from app.rag.models import Chunk
from app.rag.vector_search import InMemoryVectorIndex


class RagIndex:
    def __init__(self, bm25: BM25Index, vectors: InMemoryVectorIndex | None) -> None:
        self.chunks: dict[str, Chunk] = {}
        self.bm25, self.vectors = bm25, vectors

    def add_document(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]] | None) -> None:
        """All-or-nothing: on any failure the partially added document is removed again."""
        if vectors is not None and len(vectors) != len(chunks):
            raise ValueError("vector count does not match chunk count")
        try:
            for i, c in enumerate(chunks):
                self.chunks[c.chunk_id] = c
                self.bm25.add(c)
                if vectors is not None and self.vectors is not None:
                    self.vectors.add(c, vectors[i])
        except Exception:
            for c in chunks:
                self._drop_chunk(c.chunk_id)
            raise

    def _drop_chunk(self, chunk_id: str) -> None:
        self.chunks.pop(chunk_id, None)
        self.bm25.remove(chunk_id)
        if self.vectors is not None:
            self.vectors.remove(chunk_id)

    def remove_document(self, document_id: str) -> int:
        ids = [cid for cid, c in self.chunks.items() if c.document_id == document_id]
        for cid in ids:
            self._drop_chunk(cid)
        return len(ids)

    def __len__(self) -> int:
        return len(self.chunks)

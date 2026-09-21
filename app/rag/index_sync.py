"""Keeps a process's in-memory BM25/vector index in step with the database.

Documents are ingested by worker processes; web processes serve queries. Each process holds a
``RagIndex`` (BM25 needs corpus statistics) and calls ``refresh`` periodically: READY documents that
are new or changed are (re)indexed, documents no longer READY are dropped. The source is a Protocol
so the logic is testable without a database.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.rag.index import RagIndex
from app.rag.models import Chunk


class ChunkSource(Protocol):
    def ready_documents(self) -> dict[str, datetime]: ...
    def load_chunks(self, document_id: str) -> tuple[list[Chunk], list[list[float]] | None]: ...


class IndexSynchronizer:
    def __init__(self, source: ChunkSource, index: RagIndex) -> None:
        self._source, self._index = source, index
        self._seen: dict[str, datetime] = {}

    def refresh(self) -> dict[str, int]:
        ready = self._source.ready_documents()
        added = removed = 0
        for doc_id in [d for d in self._seen if d not in ready]:
            self._index.remove_document(doc_id)
            del self._seen[doc_id]
            removed += 1
        for doc_id, updated in ready.items():
            if self._seen.get(doc_id) == updated:
                continue
            chunks, vectors = self._source.load_chunks(doc_id)
            self._index.remove_document(doc_id)
            self._index.add_document(chunks, vectors)
            self._seen[doc_id] = updated
            added += 1
        return {"added_or_updated": added, "removed": removed, "documents": len(self._seen), "chunks": len(self._index)}

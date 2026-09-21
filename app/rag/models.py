"""Plain data types shared across the RAG package."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    """A retrievable unit of a document (what gets embedded/indexed/cited)."""

    chunk_id: str
    document_id: str
    document_name: str
    text: str
    document_type: str = "unknown"
    page: int | None = None
    heading: str | None = None
    chunk_index: int = 0
    entities: dict[str, list[str]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)  # department, ward, owner_id …


@dataclass
class RetrievedChunk:
    """A chunk plus how it was found and how it scored."""

    chunk: Chunk
    found_via: list[str] = field(default_factory=list)
    bm25_score: float | None = None
    semantic_similarity: float | None = None
    fused_score: float = 0.0
    rerank_score: float | None = None


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

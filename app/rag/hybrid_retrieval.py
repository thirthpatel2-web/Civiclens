"""Hybrid retrieval: BM25 + dense vectors -> RRF -> rerank -> relevance gate.

Behaviour worth knowing:
* **Access is enforced inside retrieval** (``visible`` predicate) so unauthorised
  chunks are never scored, fused, reranked or shown to the model.
* If embeddings are unavailable the retriever degrades to BM25-only and says so in
  ``warnings``; it never pretends semantic search ran.
* **Relevance gate** – candidates whose rerank score is below ``min_relevance`` are
  dropped, and query identifiers (numbers such as ``4291``) must literally appear in
  a passage for it to count as evidence about that identifier.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.core.exceptions import CivicLensError
from app.rag.bm25 import BM25Index
from app.rag.models import Chunk, RetrievalResult, RetrievedChunk
from app.rag.ollama import EmbeddingProvider
from app.rag.reranker import LexicalReranker, Reranker
from app.rag.rrf import reciprocal_rank_fusion
from app.rag.text import identifier_tokens, tokenize
from app.rag.vector_search import InMemoryVectorIndex

logger = logging.getLogger("civiclens.rag.retrieval")


@dataclass(frozen=True)
class RetrievalConfig:
    bm25_top_k: int = 30
    vector_top_k: int = 30
    rrf_k: int = 60
    rerank_top_k: int = 20
    final_top_k: int = 5
    min_relevance: float = 0.15
    similarity_threshold: float = 0.0
    enforce_identifiers: bool = True


class HybridRetriever:
    def __init__(
        self,
        chunks: dict[str, Chunk],
        bm25: BM25Index,
        vectors: InMemoryVectorIndex | None,
        embedder: EmbeddingProvider | None,
        reranker: Reranker | None = None,
        config: RetrievalConfig | None = None,
    ) -> None:
        self._chunks, self._bm25, self._vectors, self._embedder = chunks, bm25, vectors, embedder
        self._reranker = reranker or LexicalReranker()
        self.config = config or RetrievalConfig()

    def retrieve(self, query: str, *, visible: Callable[[Chunk], bool] | None = None) -> RetrievalResult:
        cfg = self.config
        warnings: list[str] = []
        bm25_hits = self._bm25.search(query, cfg.bm25_top_k, visible=visible)

        vector_hits = []
        if self._vectors is not None and self._embedder is not None and len(self._vectors):
            try:
                qvec = self._embedder.embed([query])[0]
                vector_hits = self._vectors.search(qvec, cfg.vector_top_k, min_similarity=cfg.similarity_threshold, visible=visible)
            except (CivicLensError, ValueError) as exc:
                msg = getattr(exc, "message", str(exc))
                warnings.append(f"Semantic search unavailable ({msg}); results are keyword-only.")
        else:
            warnings.append("Semantic search is not configured; results are keyword-only.")

        fused = reciprocal_rank_fusion(
            {"bm25": [h.chunk_id for h in bm25_hits], "semantic": [h.chunk_id for h in vector_hits]}, k=cfg.rrf_k
        )
        bm25_by_id = {h.chunk_id: h.score for h in bm25_hits}
        sim_by_id = {h.chunk_id: h.similarity for h in vector_hits}
        pool: list[RetrievedChunk] = []
        for f in fused[: cfg.rerank_top_k]:
            pool.append(
                RetrievedChunk(
                    chunk=self._chunks[f.item_id],
                    found_via=[name for name in ("semantic", "bm25") if name in f.ranks],
                    bm25_score=bm25_by_id.get(f.item_id),
                    semantic_similarity=sim_by_id.get(f.item_id),
                    fused_score=f.score,
                )
            )

        ordered, rerank_warning = self._reranker.rerank(query, pool)
        if rerank_warning:
            warnings.append(rerank_warning)

        kept = ordered
        dropped_low = 0
        if any(c.rerank_score is not None for c in ordered):
            kept = [c for c in ordered if (c.rerank_score or 0.0) >= cfg.min_relevance]
            dropped_low = len(ordered) - len(kept)
        dropped_ident = 0
        if cfg.enforce_identifiers:
            required = identifier_tokens(query)
            if required:
                before = len(kept)
                kept = [c for c in kept if set(required) <= set(tokenize(c.chunk.text))]
                dropped_ident = before - len(kept)

        return RetrievalResult(
            chunks=kept[: cfg.final_top_k],
            warnings=warnings,
            stats={
                "bm25Count": len(bm25_hits), "semanticCount": len(vector_hits), "fusedCount": len(fused),
                "rerankedCount": len(ordered), "droppedLowRelevance": dropped_low,
                "droppedMissingIdentifier": dropped_ident, "reranker": self._reranker.name,
            },
        )  # fmt: skip

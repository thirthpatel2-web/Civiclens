"""RagService: the single entry point behind /assistant/ask, /rag/query, /rag/retrieve.

Flow: route -> (allowlisted DB query) -> hybrid retrieval (access-filtered) ->
grounded generation. Database-derived facts and model-written explanation are kept in
separate response fields so the UI can label them differently.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.authorization import AuthContext
from app.core.exceptions import CivicLensError
from app.rag.grounded_generation import AnswerStatus, GeneratedAnswer, GroundedGenerator
from app.rag.hybrid_retrieval import HybridRetriever
from app.rag.models import Chunk, RetrievalResult
from app.rag.query_router import QueryRegistry, QueryRouter, RoutePlan

logger = logging.getLogger("civiclens.rag.service")
SMALLTALK_REPLY = "Hello! Ask me about complaints, RTI applications, departments or your documents."


@dataclass
class RagResponse:
    status: str
    answer: str | None
    citations: list[dict[str, Any]] = field(default_factory=list)
    database_facts: Any = None
    database_query: str | None = None
    warnings: list[str] = field(default_factory=list)
    quarantined: list[dict[str, Any]] = field(default_factory=list)
    route: dict[str, Any] = field(default_factory=dict)
    timings_ms: dict[str, float] = field(default_factory=dict)
    retrieval_stats: dict[str, Any] = field(default_factory=dict)

    @property
    def insufficient_evidence(self) -> bool:
        return self.status == AnswerStatus.INSUFFICIENT_EVIDENCE


class RagService:
    def __init__(
        self,
        retriever: HybridRetriever,
        generator: GroundedGenerator,
        registry: QueryRegistry,
        *,
        access_filter: Callable[[AuthContext, Chunk], bool],
    ) -> None:
        self._retriever, self._generator = retriever, generator
        self._registry, self._router = registry, QueryRouter(registry)
        self._access = access_filter

    def retrieve(self, question: str, ctx: AuthContext) -> RetrievalResult:
        """Evidence only (backs POST /documents/search and /rag/retrieve)."""
        return self._retriever.retrieve(question, visible=lambda c: self._access(ctx, c))

    @property
    def router(self) -> QueryRouter:
        return self._router

    def query_catalogue(self) -> list[tuple[str, str]]:
        """(name, description) of every allowlisted query - what an LLM router may choose from."""
        return [(n, spec.description) for n in self._registry.names() if (spec := self._registry.get(n)) is not None]

    def ask(self, question: str, ctx: AuthContext, *, language: str = "English", plan: RoutePlan | None = None) -> RagResponse:
        """``plan`` lets a caller supply a route it already validated (e.g. an allowlisted LLM
        suggestion via ``router.validate_llm_route``); by default the rule-based router decides."""
        timings: dict[str, float] = {}
        t0 = time.perf_counter()
        plan = plan or self._router.route(question)
        route = {"needsDb": plan.needs_db, "query": plan.query_name, "needsDocs": plan.needs_docs, "reasons": plan.reasons}
        if plan.smalltalk:
            return RagResponse("smalltalk", SMALLTALK_REPLY, route=route)

        warnings: list[str] = []
        facts: Any = None
        if plan.needs_db and plan.query_name:
            try:
                facts = self._registry.execute(plan.query_name, plan.params, ctx).data
            except CivicLensError as exc:  # permission/validation problems are reported, not hidden
                warnings.append(f"Database lookup not performed: {exc.message}")
            timings["database"] = (time.perf_counter() - t0) * 1000

        retrieval = RetrievalResult(chunks=[])
        if plan.needs_docs:
            t1 = time.perf_counter()
            retrieval = self.retrieve(question, ctx)
            timings["retrieval"] = (time.perf_counter() - t1) * 1000
            warnings.extend(retrieval.warnings)

        t2 = time.perf_counter()
        gen: GeneratedAnswer = self._generator.generate(question, retrieval.chunks, database_facts=facts, language=language)
        timings["generation"] = (time.perf_counter() - t2) * 1000
        warnings.extend(gen.warnings)
        logger.info("rag.ask status=%s", gen.status, extra={"extra_fields": {"timings_ms": timings}})
        return RagResponse(
            status=str(gen.status), answer=gen.answer, citations=[c.to_dict() for c in gen.citations],
            database_facts=gen.database_facts, database_query=plan.query_name if facts is not None else None,
            warnings=warnings, quarantined=gen.quarantined, route=route, timings_ms=timings,
            retrieval_stats=retrieval.stats,
        )  # fmt: skip

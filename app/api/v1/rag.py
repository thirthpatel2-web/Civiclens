"""/api/v1/rag: direct retrieval + grounded query. POST only."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.serialize import to_jsonable
from app.container import AppContainer
from app.core.authorization import AuthContext, Permission
from app.core.dependencies import get_container, guard, limited
from app.rag.citation_builder import build_citations
from app.schemas.api import AskBody, SearchBody

router = APIRouter(prefix="/rag", tags=["rag"])
USE = Depends(guard(Permission.ASSISTANT_USE))


@router.post("/query")
def query(body: AskBody, ctx: AuthContext = USE, c: AppContainer = Depends(get_container), _: None = Depends(limited("expensive"))) -> dict:  # type: ignore[type-arg]
    r = c.rag.ask(body.question, ctx, language=body.language)
    return to_jsonable({"status": r.status, "answer": r.answer, "citations": r.citations, "database_facts": r.database_facts, "database_query": r.database_query, "warnings": r.warnings, "quarantined": r.quarantined, "route": r.route, "timings_ms": r.timings_ms, "retrieval_stats": r.retrieval_stats})  # type: ignore[no-any-return]


@router.post("/retrieve")
def retrieve(body: SearchBody, ctx: AuthContext = USE, c: AppContainer = Depends(get_container), _: None = Depends(limited("expensive"))) -> dict:  # type: ignore[type-arg]
    res = c.rag.retrieve(body.query, ctx)
    return {"citations": [x.to_dict() for x in build_citations(res.chunks)], "warnings": res.warnings, "stats": res.stats}

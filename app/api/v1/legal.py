"""/api/v1/legal: evidence-first Legal Analyzer over the verified precedent index (metadata only) plus,
when a query matches, real full-text excerpts from the ingested judgment corpus (app/legal/judgment_search.py)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.serialize import to_jsonable
from app.container import AppContainer
from app.core.authorization import AuthContext, Permission
from app.core.dependencies import get_container, guard, limited
from app.schemas.api import LegalBody
from app.services.document_service import extract_pages, validate_upload

router = APIRouter(prefix="/legal", tags=["legal"])
LEGAL = Depends(guard(Permission.LEGAL_ANALYZE))


def _view(rec) -> dict:  # type: ignore[no-untyped-def,type-arg]
    return {"id": rec.id, "created_at": rec.created_at.isoformat(), **rec.result}


@router.post("/analyze")
def analyze(body: LegalBody, ctx: AuthContext = LEGAL, c: AppContainer = Depends(get_container), _: None = Depends(limited("expensive"))) -> dict:  # type: ignore[type-arg]
    return _view(c.legal.analyze(ctx, body.problem, disposal=body.disposal, year=body.year))


@router.post("/analyze-document")
async def analyze_document(file: UploadFile = File(...), ctx: AuthContext = LEGAL, c: AppContainer = Depends(get_container), _: None = Depends(limited("upload"))) -> dict:  # type: ignore[type-arg]
    data = await file.read(c.settings.max_upload_bytes + 1)
    v = validate_upload(file.filename or "case", data, max_bytes=c.settings.max_upload_bytes, declared_mime=file.content_type)
    text = " ".join(t for _p, t in extract_pages(v.mime, data, None))[:8000]
    return {"extracted_chars": len(text), **_view(c.legal.analyze(ctx, text, source="document"))}


@router.get("/analyses")
def analyses(ctx: AuthContext = LEGAL, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": [{"id": r.id, "created_at": r.created_at.isoformat(), "status": r.status, "problem": r.problem[:200]} for r in c.legal.list_mine(ctx)]}


@router.get("/analyses/{analysis_id}")
def analysis(analysis_id: str, ctx: AuthContext = LEGAL, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return _view(c.legal.get_mine(ctx, analysis_id))


@router.post("/precedents/search")
def search_precedents(body: LegalBody, ctx: AuthContext = LEGAL, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    hits = c.precedents.search(body.problem, top_k=10, disposal=body.disposal, year=body.year)
    return {"count": len(hits), "coverage": c.precedents.stats(), "items": [{"cnr": h.record.cnr, "neutral_citation": h.record.neutral_citation, "title": h.record.title, "decision_date": h.record.decision_date.isoformat(), "matched_on": h.matched_on} for h in hits]}


@router.get("/precedents/{cnr}")
def precedent(cnr: str, ctx: AuthContext = LEGAL, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    from app.core.exceptions import NotFound

    r = c.precedents.get(cnr)
    if r is None:
        raise NotFound("Precedent not found in the verified index.")
    return {**to_jsonable(r), "has_judgment_text": False, "note": "Metadata only: this index does not contain the judgment text."}

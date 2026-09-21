"""/api/v1/documents: upload -> validate -> store -> (queued) extract/chunk/embed/index -> READY."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.serialize import to_jsonable
from app.container import AppContainer
from app.core.authorization import AuthContext, Permission, Role
from app.core.dependencies import get_container, guard, limited
from app.core.exceptions import NotConfigured, NotFound, PermissionDenied, ValidationFailed
from app.core.transactions import run_in_uow
from app.rag.citation_builder import build_citations
from app.schemas.api import LinkBody, SearchBody

router = APIRouter(prefix="/documents", tags=["documents"])
UP = Depends(guard(Permission.EVIDENCE_UPLOAD))
LINKABLE = ("complaint", "rti", "legal_case")


def _ingestor(c: AppContainer, uow):  # type: ignore[no-untyped-def]
    if c.ingestor_factory is None:
        raise NotConfigured("Document ingestion is not configured.")
    return c.ingestor_factory(uow)


@router.post("", status_code=202)
async def upload(file: UploadFile = File(...), visibility: str = Form("private"), ctx: AuthContext = UP, c: AppContainer = Depends(get_container), _: None = Depends(limited("upload"))) -> dict:  # type: ignore[type-arg]
    if visibility != "private" and ctx.role is Role.CITIZEN:
        raise PermissionDenied("Citizens can only upload private documents.")
    data = await file.read(c.settings.max_upload_bytes + 1)

    def op(uow):  # type: ignore[no-untyped-def]
        doc = _ingestor(c, uow).upload(ctx.user_id, file.filename or "document", data, max_bytes=c.settings.max_upload_bytes, declared_mime=file.content_type, visibility=visibility,
                                       department_id=ctx.department_id if visibility == "department" else None)  # fmt: skip
        job, _created = c.jobs.enqueue(uow, "document.ingest", {"document_id": doc.id}, f"ingest:{doc.id}")
        return doc, job

    doc, job = run_in_uow(c, op)
    c.jobs.dispatch([job])
    return to_jsonable(doc)  # type: ignore[no-any-return]


@router.get("")
def list_mine(ctx: AuthContext = UP, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": to_jsonable(run_in_uow(c, lambda uow: uow.documents.list_for_owner(ctx.user_id)))}


def _own(uow, ctx: AuthContext, doc_id: str):  # type: ignore[no-untyped-def]
    doc = uow.documents.get(doc_id)
    if doc is None or doc.owner_id != ctx.user_id:
        raise NotFound("Document not found.")
    return doc


@router.get("/{doc_id}")
def status(doc_id: str, ctx: AuthContext = UP, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(run_in_uow(c, lambda uow: _own(uow, ctx, doc_id)))  # type: ignore[no-any-return]


@router.post("/{doc_id}/retry", status_code=202)
def retry(doc_id: str, ctx: AuthContext = UP, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    def op(uow):  # type: ignore[no-untyped-def]
        doc = _own(uow, ctx, doc_id)
        if str(doc.status) != "failed":
            raise ValidationFailed("Only failed documents can be retried.")
        job, _created = c.jobs.enqueue(uow, "document.ingest", {"document_id": doc.id}, f"ingest-retry:{doc.id}:{doc.attempts}")
        return doc, job

    doc, job = run_in_uow(c, op)
    c.jobs.dispatch([job])
    return to_jsonable(doc)  # type: ignore[no-any-return]


@router.post("/{doc_id}/link")
def link(doc_id: str, body: LinkBody, ctx: AuthContext = UP, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    if body.linked_type not in LINKABLE:
        raise ValidationFailed("Unknown link type.", details={"allowed": list(LINKABLE)})

    def op(uow):  # type: ignore[no-untyped-def]
        _own(uow, ctx, doc_id)
        if body.linked_type == "complaint":
            cm = uow.complaints.get(body.linked_id)
            if cm is None or cm.citizen_id != ctx.user_id:
                raise NotFound("Complaint not found.")
        elif body.linked_type == "rti":
            app = uow.rti.get(body.linked_id)
            if app is None or app.owner_id != ctx.user_id:
                raise NotFound("RTI application not found.")
        uow.documents.link(doc_id, body.linked_type, body.linked_id)

    run_in_uow(c, op)
    return {"ok": True}


@router.post("/search")
def search(body: SearchBody, ctx: AuthContext = Depends(guard(Permission.ASSISTANT_USE)), c: AppContainer = Depends(get_container), _: None = Depends(limited("expensive"))) -> dict:  # type: ignore[type-arg]
    res = c.rag.retrieve(body.query, ctx)  # access filter applied inside retrieval
    return {"items": [x.to_dict() for x in build_citations(res.chunks)], "warnings": res.warnings, "stats": res.stats}

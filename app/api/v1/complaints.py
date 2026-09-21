"""/api/v1/complaints: intake, evidence, tracking, feedback and server-side drafts (offline sync)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Response, UploadFile

from app.api.serialize import complaint_json, to_jsonable
from app.container import AppContainer
from app.core.authorization import AuthContext, Permission
from app.core.dependencies import get_container, guard, limited
from app.schemas.api import (
    AttachEvidenceBody,
    ClassifyPreviewBody,
    ComplaintBody,
    DraftBody,
    FeedbackBody,
    GovSubmitBody,
)
from app.services.complaint_service import ComplaintInput

router = APIRouter(prefix="/complaints", tags=["complaints"])
CITIZEN = Depends(guard(Permission.COMPLAINT_READ_OWN))


@router.post("", status_code=201)
def create(body: ComplaintBody, ctx: AuthContext = Depends(guard(Permission.COMPLAINT_CREATE)), c: AppContainer = Depends(get_container), _: None = Depends(limited("expensive"))) -> dict:  # type: ignore[type-arg]
    r = c.complaints.create(ctx, ComplaintInput(**body.model_dump()))
    return {"complaint": complaint_json(r.complaint), "replayed": r.replayed, "warnings": r.warnings}


@router.post("/classify-preview")
def classify_preview(body: ClassifyPreviewBody, ctx: AuthContext = Depends(guard(Permission.COMPLAINT_CREATE)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    """Live 'AI suggests...' preview while the citizen is still typing or speaking: the same rules-only
    classifier and routing the real submission uses, run read-only. Nothing is saved."""
    return c.complaints.preview_classification(ctx, body.title, body.description, body.ward)


@router.get("")
def list_mine(filter: str = "all", limit: int = 50, offset: int = 0, ctx: AuthContext = CITIZEN, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": to_jsonable(c.complaints.list_mine(ctx, filter_name=filter, limit=min(limit, 100), offset=max(offset, 0)))}


@router.post("/evidence", status_code=201)
async def upload_evidence(file: UploadFile = File(...), ctx: AuthContext = Depends(guard(Permission.EVIDENCE_UPLOAD)), c: AppContainer = Depends(get_container), _: None = Depends(limited("upload"))) -> dict:  # type: ignore[type-arg]
    data = await file.read(c.settings.max_upload_bytes + 1)
    return to_jsonable(c.complaints.upload_evidence(ctx, file.filename or "upload", data, file.content_type))  # type: ignore[no-any-return]


@router.get("/evidence/{evidence_id}/file")
def evidence_file(evidence_id: str, ctx: AuthContext = Depends(guard(Permission.EVIDENCE_UPLOAD, mfa_for_privileged=False)), c: AppContainer = Depends(get_container)) -> Response:
    ev, data = c.complaints.read_evidence(ctx, evidence_id)
    disposition = "inline" if ev.mime.startswith("image/") else "attachment"
    return Response(data, media_type=ev.mime, headers={"Content-Disposition": f'{disposition}; filename="{ev.id}"', "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.post("/evidence/{evidence_id}/analyze", status_code=202)
def evidence_analyze(evidence_id: str, ctx: AuthContext = Depends(guard(Permission.EVIDENCE_UPLOAD)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.complaints.request_analysis(ctx, evidence_id))  # type: ignore[no-any-return]


@router.post("/drafts")
def save_draft(body: DraftBody, ctx: AuthContext = Depends(guard(Permission.COMPLAINT_CREATE)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.drafts.save(ctx, body.kind, body.payload, body.client_request_id))  # type: ignore[no-any-return]


@router.get("/drafts")
def list_drafts(ctx: AuthContext = Depends(guard(Permission.COMPLAINT_CREATE)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": to_jsonable(c.drafts.list(ctx))}


@router.post("/drafts/{draft_id}/pending")
def mark_pending(draft_id: str, ctx: AuthContext = Depends(guard(Permission.COMPLAINT_CREATE)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.drafts.mark_pending(ctx, draft_id))  # type: ignore[no-any-return]


@router.post("/drafts/{draft_id}/sync")
def sync_draft(draft_id: str, ctx: AuthContext = Depends(guard(Permission.COMPLAINT_CREATE)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.drafts.sync(ctx, draft_id))  # type: ignore[no-any-return]


@router.delete("/drafts/{draft_id}", status_code=204)
def discard_draft(draft_id: str, ctx: AuthContext = Depends(guard(Permission.COMPLAINT_CREATE)), c: AppContainer = Depends(get_container)) -> None:
    c.drafts.discard(ctx, draft_id)


@router.post("/{complaint_id}/evidence", status_code=201)
def attach_evidence(complaint_id: str, body: AttachEvidenceBody, ctx: AuthContext = Depends(guard(Permission.EVIDENCE_UPLOAD)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.complaints.add_evidence(ctx, complaint_id, body.evidence_id))  # type: ignore[no-any-return]


@router.get("/{complaint_id}")
def detail(complaint_id: str, ctx: AuthContext = CITIZEN, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    d = c.complaints.detail_for_citizen(ctx, complaint_id)
    out = to_jsonable({k: v for k, v in d.items() if k != "complaint"})
    out["complaint"] = complaint_json(d["complaint"])
    return out  # type: ignore[no-any-return]


@router.post("/{complaint_id}/feedback", status_code=201)
def feedback(complaint_id: str, body: FeedbackBody, ctx: AuthContext = Depends(guard(Permission.COMPLAINT_FEEDBACK)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.complaints.add_feedback(ctx, complaint_id, body.rating, body.comment))  # type: ignore[no-any-return]




@router.get("/{complaint_id}/government-submissions")
def government_states(complaint_id: str, ctx: AuthContext = CITIZEN, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    """Per-platform state of sharing this complaint with a government platform (never claims a submission that did not happen)."""
    return {"items": c.government.states(ctx, complaint_id)}


@router.post("/{complaint_id}/government-submissions", status_code=202)
def request_government_submission(complaint_id: str, body: GovSubmitBody, ctx: AuthContext = Depends(guard(Permission.COMPLAINT_READ_OWN)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.government.request(ctx, complaint_id, body.platform))  # type: ignore[no-any-return]

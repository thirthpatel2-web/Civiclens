"""/api/v1/rti: drafting, persistence, reference, deadline/countdown, PDF, ownership-scoped."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.serialize import to_jsonable
from app.container import AppContainer
from app.core.authorization import AuthContext, Permission
from app.core.dependencies import get_container, guard
from app.core.transactions import run_in_uow
from app.schemas.api import RtiBody, RtiFileBody, RtiQuestionsPreviewBody
from app.services.rti_service import RTI_CATEGORY_RECORDS, RtiDraft, build_rti_questions, default_records_for_category

router = APIRouter(prefix="/rti", tags=["rti"])
OWNER = Depends(guard(Permission.RTI_MANAGE_OWN))


def _draft(b: RtiBody) -> RtiDraft:
    return RtiDraft(b.subject, b.public_authority, tuple(b.questions), b.applicant_name, b.applicant_address, b.language, b.purpose, b.life_or_liberty, b.below_poverty_line, tuple(b.attachments))


@router.get("/categories")
def categories(ctx: AuthContext = OWNER) -> dict:  # type: ignore[type-arg]
    """The same statutory-records checklist the web app's RTI drafter offers, keyed by civic category."""
    return {"categories": [{"code": code, "default_records": list(records)} for code, records in RTI_CATEGORY_RECORDS.items()]}


@router.post("/questions/preview")
def preview_questions(body: RtiQuestionsPreviewBody, ctx: AuthContext = OWNER) -> dict:  # type: ignore[type-arg]
    """Composes precise statutory RTI questions from a category + record checklist, without saving anything."""
    records = tuple(body.records_requested) or default_records_for_category(body.category)
    qs = build_rti_questions(
        subject=body.subject,
        location=body.location,
        records_requested=records,
        tender_reference=body.tender_reference,
        time_period=body.time_period,
        custom_questions=tuple(body.custom_questions),
    )
    return {"questions": list(qs), "records_used": list(records)}


@router.post("", status_code=201)
def create(body: RtiBody, ctx: AuthContext = OWNER, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(run_in_uow(c, lambda uow: c.rti_for(uow).create(ctx, _draft(body))))  # type: ignore[no-any-return]


@router.get("")
def list_mine(ctx: AuthContext = OWNER, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": to_jsonable(run_in_uow(c, lambda uow: uow.rti.list_for_owner(ctx.user_id)))}


@router.get("/{app_id}")
def track(app_id: str, ctx: AuthContext = OWNER, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    app, cd = run_in_uow(c, lambda uow: c.rti_for(uow).track(ctx, app_id))
    return {"application": to_jsonable(app), "countdown": to_jsonable(cd)}


@router.put("/{app_id}")
def update(app_id: str, body: RtiBody, ctx: AuthContext = OWNER, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(run_in_uow(c, lambda uow: c.rti_for(uow).update_draft(ctx, app_id, _draft(body))))  # type: ignore[no-any-return]


@router.post("/{app_id}/generate")
def generate(app_id: str, ctx: AuthContext = OWNER, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(run_in_uow(c, lambda uow: c.rti_for(uow).generate(ctx, app_id)))  # type: ignore[no-any-return]


@router.post("/{app_id}/file")
def mark_filed(app_id: str, body: RtiFileBody, ctx: AuthContext = OWNER, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(run_in_uow(c, lambda uow: c.rti_for(uow).mark_filed(ctx, app_id, received_at=body.received_at)))  # type: ignore[no-any-return]


@router.post("/{app_id}/responded")
def responded(app_id: str, ctx: AuthContext = OWNER, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(run_in_uow(c, lambda uow: c.rti_for(uow).mark_responded(ctx, app_id)))  # type: ignore[no-any-return]


@router.get("/{app_id}/pdf")
def pdf(app_id: str, ctx: AuthContext = OWNER, c: AppContainer = Depends(get_container)) -> Response:
    data = run_in_uow(c, lambda uow: c.rti_for(uow).export_pdf(ctx, app_id, font_path=c.settings.rti_pdf_font or None))
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="rti-{app_id[:8]}.pdf"'})

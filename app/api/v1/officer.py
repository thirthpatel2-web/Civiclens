"""/api/v1/officer: department queue, complaint actions and investigation mode (department-isolated)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.serialize import to_jsonable
from app.container import AppContainer
from app.core.authorization import AuthContext, Permission
from app.core.dependencies import get_container, guard
from app.core.exceptions import ValidationFailed
from app.schemas.api import (
    AssignBody,
    CoordinationBody,
    CorrectCategoryBody,
    DuplicateDecisionBody,
    EscalateBody,
    FieldVisitBody,
    GovSubmitBody,
    InspectionBody,
    NoteBody,
    OpenInvestigationBody,
    ProgressBody,
    RemarkBody,
    ResolveBody,
    StatusBody,
    TriageBody,
    WorkOrderBody,
)
from app.services.complaint_status import ComplaintStatus

router = APIRouter(prefix="/officer", tags=["officer"])
READ = Depends(guard(Permission.COMPLAINT_READ_DEPARTMENT))
STATUS = Depends(guard(Permission.COMPLAINT_UPDATE_STATUS))
FIELD = Depends(guard(Permission.COMPLAINT_FIELD_ACTION))
ASSIGN = Depends(guard(Permission.COMPLAINT_ASSIGN))
INVEST = Depends(guard(Permission.INVESTIGATION_RUN))


@router.get("/queue")
def queue(mine_only: bool = False, status: str | None = None, limit: int = 50, offset: int = 0, ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    try:
        statuses = [ComplaintStatus(status)] if status else None
    except ValueError:
        raise ValidationFailed("Unknown status.") from None
    return {"items": to_jsonable(c.officer.queue(ctx, mine_only=mine_only, statuses=statuses, limit=min(limit, 100), offset=max(offset, 0)))}


@router.get("/complaints/{cid}")
def detail(cid: str, ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.officer.detail(ctx, cid))  # type: ignore[no-any-return]


@router.post("/complaints/{cid}/status")
def set_status(cid: str, body: StatusBody, ctx: AuthContext = STATUS, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    try:
        target = ComplaintStatus(body.status)
    except ValueError:
        raise ValidationFailed("Unknown status.") from None
    return to_jsonable(c.officer.update_status(ctx, cid, target, body.remarks))  # type: ignore[no-any-return]


@router.post("/complaints/{cid}/resolve")
def resolve(cid: str, body: ResolveBody, ctx: AuthContext = STATUS, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.officer.resolve(ctx, cid, body.resolution_notes))  # type: ignore[no-any-return]


@router.post("/complaints/{cid}/assign")
def assign(cid: str, body: AssignBody, ctx: AuthContext = ASSIGN, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.officer.assign(ctx, cid, body.officer_id))  # type: ignore[no-any-return]


@router.post("/complaints/{cid}/triage")
def triage(cid: str, body: TriageBody, ctx: AuthContext = ASSIGN, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.officer.triage(ctx, cid, body.department_code))  # type: ignore[no-any-return]


@router.post("/complaints/{cid}/remark")
def remark(cid: str, body: RemarkBody, ctx: AuthContext = Depends(guard(Permission.COMPLAINT_REMARK)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.officer.remark(ctx, cid, body.text, internal=body.internal))  # type: ignore[no-any-return]


@router.post("/complaints/{cid}/field-visit")
def field_visit(cid: str, body: FieldVisitBody, ctx: AuthContext = FIELD, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.officer.field_visit(ctx, cid, body.scheduled_for, body.notes))  # type: ignore[no-any-return]


@router.post("/complaints/{cid}/inspection")
def inspection(cid: str, body: InspectionBody, ctx: AuthContext = FIELD, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.officer.inspection(ctx, cid, body.findings, body.notes))  # type: ignore[no-any-return]


@router.post("/complaints/{cid}/work-order")
def work_order(cid: str, body: WorkOrderBody, ctx: AuthContext = FIELD, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.officer.work_order(ctx, cid, body.order_ref, body.description, body.team))  # type: ignore[no-any-return]


@router.post("/complaints/{cid}/coordination")
def coordination(cid: str, body: CoordinationBody, ctx: AuthContext = FIELD, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.officer.coordination_note(ctx, cid, body.with_team, body.note))  # type: ignore[no-any-return]


@router.post("/complaints/{cid}/progress")
def progress(cid: str, body: ProgressBody, ctx: AuthContext = FIELD, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.officer.progress(ctx, cid, body.percent, body.notes))  # type: ignore[no-any-return]


@router.post("/complaints/{cid}/escalate")
def escalate(cid: str, body: EscalateBody, ctx: AuthContext = STATUS, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.officer.escalate(ctx, cid, body.reason))  # type: ignore[no-any-return]


@router.post("/complaints/{cid}/category")
def correct_category(cid: str, body: CorrectCategoryBody, ctx: AuthContext = Depends(guard(Permission.COMPLAINT_REMARK)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    """Transparent correction: captured to the learning log, then applied for real (see OfficerService.correct_category)."""
    return to_jsonable(c.officer.correct_category(ctx, cid, body.category))  # type: ignore[no-any-return]


# ---- investigation mode
@router.post("/investigations", status_code=201)
def open_investigation(body: OpenInvestigationBody, ctx: AuthContext = INVEST, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.investigations.open(ctx, body.subject_type, body.subject_id))  # type: ignore[no-any-return]


@router.get("/investigations")
def list_investigations(ctx: AuthContext = INVEST, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": to_jsonable(c.investigations.list(ctx))}


@router.get("/investigations/{inv_id}")
def investigation_report(inv_id: str, ctx: AuthContext = INVEST, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.investigations.report(ctx, inv_id))  # type: ignore[no-any-return]


@router.post("/investigations/{inv_id}/notes")
def add_note(inv_id: str, body: NoteBody, ctx: AuthContext = INVEST, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.investigations.add_note(ctx, inv_id, body.text))  # type: ignore[no-any-return]


@router.post("/investigations/{inv_id}/close")
def close(inv_id: str, ctx: AuthContext = INVEST, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.investigations.close(ctx, inv_id))  # type: ignore[no-any-return]


# ---- duplicate review (advisory; never merges)
DUP = Depends(guard(Permission.DUPLICATE_REVIEW))


@router.get("/complaints/{cid}/duplicates")
def duplicate_candidates(cid: str, ctx: AuthContext = DUP, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": to_jsonable(c.duplicate_reviews.candidates(ctx, cid))}


@router.post("/complaints/{cid}/duplicates/decision", status_code=201)
def duplicate_decision(cid: str, body: DuplicateDecisionBody, ctx: AuthContext = DUP, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.duplicate_reviews.decide(ctx, cid, body.other_complaint_id, body.decision, body.note))  # type: ignore[no-any-return]


# ---- government platforms
@router.get("/complaints/{cid}/government-submissions")
def officer_government_states(cid: str, ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": c.government.states(ctx, cid)}


@router.post("/complaints/{cid}/government-submissions", status_code=202)
def officer_request_government(cid: str, body: GovSubmitBody, ctx: AuthContext = STATUS, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.government.request(ctx, cid, body.platform))  # type: ignore[no-any-return]

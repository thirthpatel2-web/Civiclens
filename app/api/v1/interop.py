"""/api/v1/interop: the interoperability layer's mobile-facing surface.

Mirrors the web app's "/interop" page (app/ui/pages/citizen.py) as real REST endpoints: the
fragmentation diagnostic, the live Common Data Model normalization demo, the integration
exception queue, Golden Record (master data) linking, and honest manual cross-portal tracking.
See app/interop/ for the pure functions this composes and app/services/interop_service.py for
the persistence-backed services.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.serialize import to_jsonable
from app.container import AppContainer
from app.core.authorization import AuthContext, Permission
from app.core.dependencies import get_container, guard
from app.core.exceptions import ValidationFailed
from app.interop.adapters import SYSTEMS, corrupt_payload
from app.interop.common_data_model import score_quality
from app.interop.fragmentation import (
    NATIONAL_UMANG_DEPARTMENTS,
    NATIONAL_UMANG_SERVICES,
    NATIONAL_UMANG_SOURCE,
    personal_diagnostic,
)
from app.schemas.api import (
    AddExternalLinkBody,
    LinkExternalIdBody,
    LogExceptionBody,
    NormalizeDemoBody,
    ResolveExceptionBody,
    UpdateExternalLinkStatusBody,
)

router = APIRouter(prefix="/interop", tags=["interop"])
ANY = Depends(guard(Permission.ASSISTANT_USE))  # every role (citizen/officer/admin/super_admin) holds this


@router.get("/systems")
def systems(ctx: AuthContext = ANY) -> dict:  # type: ignore[type-arg]
    return {"items": [{"code": k, "label": v[0]} for k, v in SYSTEMS.items()]}


@router.post("/normalize-demo")
def normalize_demo(body: NormalizeDemoBody, ctx: AuthContext = ANY) -> dict:  # type: ignore[type-arg]
    """Runs a real adapter against its (fixture) payload - the actual technical mechanism, not a mockup."""
    if body.system not in SYSTEMS:
        raise ValidationFailed("Unknown system.", details={"allowed": list(SYSTEMS)})
    _label, fixture, adapt = SYSTEMS[body.system]
    payload = corrupt_payload(fixture) if body.corrupt else dict(fixture)
    record = adapt(payload)
    quality = score_quality(record)
    return {
        "payload": payload,
        "record": {"source_system": record.source_system, "external_id": record.external_id, "category": record.category, "status": record.status, "title": record.title,
                   "department": record.department, "citizen_name": record.citizen_name, "citizen_contact": record.citizen_contact, "location": record.location, "filed_on": record.filed_on},  # fmt: skip
        "quality": {"score": quality.score, "grade": quality.grade, "issues": list(quality.issues)},
    }


@router.get("/fragmentation")
def fragmentation(ctx: AuthContext = Depends(guard(Permission.COMPLAINT_READ_OWN)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    mine = c.complaints.list_mine(ctx, filter_name="all")
    diag = personal_diagnostic([m.department_code for m in mine])
    return {
        "national": {"services": NATIONAL_UMANG_SERVICES, "departments": NATIONAL_UMANG_DEPARTMENTS, "source": NATIONAL_UMANG_SOURCE},
        "personal": {"distinct_departments": diag.distinct_departments, "total_filings": diag.total_filings, "profile_reuses": diag.profile_reuses},
    }


# ---- integration exceptions (logging is open to any authenticated caller; viewing/resolving is admin-only)
@router.post("/exceptions", status_code=201)
def log_exception(body: LogExceptionBody, ctx: AuthContext = ANY, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.exceptions.log(source_system=body.source_system, reason=body.reason, payload=body.payload))  # type: ignore[no-any-return]


@router.get("/exceptions")
def list_exceptions(status: str | None = None, ctx: AuthContext = Depends(guard(Permission.ADMIN_INTEGRATIONS)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": to_jsonable(c.exceptions.list(ctx, status=status))}


@router.get("/exceptions/counts")
def exception_counts(ctx: AuthContext = Depends(guard(Permission.ADMIN_INTEGRATIONS)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return c.exceptions.counts(ctx)


@router.post("/exceptions/{exception_id}/resolve")
def resolve_exception(exception_id: str, body: ResolveExceptionBody, ctx: AuthContext = Depends(guard(Permission.ADMIN_INTEGRATIONS)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    c.exceptions.resolve(ctx, exception_id, note=body.note, ignore=body.ignore)
    return {"ok": True}


# ---- Golden Record: link external government IDs to one CivicLens profile (master-data management)
@router.get("/master-data")
def list_master_data(ctx: AuthContext = Depends(guard(Permission.PROFILE_MANAGE)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": to_jsonable(c.master_data.list_mine(ctx))}


@router.post("/master-data", status_code=201)
def link_master_data(body: LinkExternalIdBody, ctx: AuthContext = Depends(guard(Permission.PROFILE_MANAGE)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.master_data.link(ctx, body.id_type, body.raw_value))  # type: ignore[no-any-return]


@router.delete("/master-data/{record_id}", status_code=204)
def unlink_master_data(record_id: str, ctx: AuthContext = Depends(guard(Permission.PROFILE_MANAGE)), c: AppContainer = Depends(get_container)) -> None:
    c.master_data.unlink(ctx, record_id)


# ---- honest manual cross-portal tracking (unified application tracking for portals with no API)
@router.get("/external-links")
def list_external_links(ctx: AuthContext = Depends(guard(Permission.PROFILE_MANAGE)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": to_jsonable(c.external_links.list_mine(ctx))}


@router.post("/external-links", status_code=201)
def add_external_link(body: AddExternalLinkBody, ctx: AuthContext = Depends(guard(Permission.PROFILE_MANAGE)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.external_links.add(ctx, platform=body.platform, external_reference=body.external_reference, title=body.title, status_note=body.status_note))  # type: ignore[no-any-return]


@router.put("/external-links/{record_id}")
def update_external_link(record_id: str, body: UpdateExternalLinkStatusBody, ctx: AuthContext = Depends(guard(Permission.PROFILE_MANAGE)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    c.external_links.update_status(ctx, record_id, body.status_note)
    return {"ok": True}


@router.delete("/external-links/{record_id}", status_code=204)
def remove_external_link(record_id: str, ctx: AuthContext = Depends(guard(Permission.PROFILE_MANAGE)), c: AppContainer = Depends(get_container)) -> None:
    c.external_links.remove(ctx, record_id)

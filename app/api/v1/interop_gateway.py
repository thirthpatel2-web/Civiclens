"""/api/v1/interop-gateway: the no-reupload cross-department demo, as real REST endpoints.

Distinct from app/api/v1/interop.py (which is the citizen-facing fragmentation/master-data/
exceptions surface) - this router is the console over InteropGatewayService: trigger a document
exchange, act on the consent it requires, resolve ambiguous identity matches, and inspect the
connector registry / transaction / timeline history that resulted. See
app/services/interop_gateway_service.py for what each endpoint actually does.

Two permissions gate most of this router (held by ADMIN/SUPER_ADMIN, and by the dedicated
INTEGRATION_ADMIN/AUDITOR roles - see app/core/authorization.py): INTEROP_READ for every GET here,
INTEROP_MANAGE for anything that changes state (an AUDITOR holds only the former - it can watch
every exchange, consent and identity decision, but can never make one). The three consent-decision
routes (grant/deny/revoke) are the one exception: they accept any authenticated caller, because
InteropGatewayService itself enforces the real rule (Section 8, citizen-controlled consent) - an
INTEROP_MANAGE holder OR the citizen the grant is attributed to, never anyone else. /my-consents is
the citizen-facing list, gated on PROFILE_MANAGE (every role holds it) rather than INTEROP_READ.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.serialize import to_jsonable
from app.container import AppContainer
from app.core.authorization import AuthContext, Permission
from app.core.dependencies import get_container, get_ctx, guard
from app.schemas.api import (
    MarkExceptionDeadBody,
    RequestDocumentExchangeBody,
    ResolveIdentityCandidateBody,
    RevokeConsentBody,
    SetConnectorEnabledBody,
)

router = APIRouter(prefix="/interop-gateway", tags=["interop-gateway"])
READ = Depends(guard(Permission.INTEROP_READ))
MANAGE = Depends(guard(Permission.INTEROP_MANAGE))


@router.post("/document-exchange")
def request_document_exchange(body: RequestDocumentExchangeBody, ctx: AuthContext = MANAGE, c: AppContainer = Depends(get_container)) -> dict:
    return to_jsonable(c.interop_gateway.request_document_exchange(ctx, application_no=body.application_no, document_type=body.document_type))


@router.get("/timeline/{application_no}")
def get_timeline(application_no: str, ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:
    return to_jsonable(c.interop_gateway.get_timeline(ctx, application_no=application_no))


@router.get("/transactions")
def list_transactions(limit: int = 50, ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:
    return {"items": to_jsonable(c.interop_gateway.list_transactions(ctx, limit=limit))}


# ---- consent lifecycle
@router.get("/consents")
def list_consents(status: str | None = None, ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:
    return {"items": to_jsonable(c.interop_gateway.list_consents(ctx, status=status))}


@router.get("/my-consents")
def list_my_consents(status: str | None = None, ctx: AuthContext = Depends(guard(Permission.PROFILE_MANAGE)), c: AppContainer = Depends(get_container)) -> dict:
    return {"items": to_jsonable(c.interop_gateway.list_my_consents(ctx, status=status))}


@router.post("/consents/{consent_id}/grant")
def grant_consent(consent_id: str, ctx: AuthContext = Depends(get_ctx), c: AppContainer = Depends(get_container)) -> dict:
    return to_jsonable(c.interop_gateway.grant_consent(ctx, consent_id=consent_id))


@router.post("/consents/{consent_id}/deny")
def deny_consent(consent_id: str, ctx: AuthContext = Depends(get_ctx), c: AppContainer = Depends(get_container)) -> dict:
    return to_jsonable(c.interop_gateway.deny_consent(ctx, consent_id=consent_id))


@router.post("/consents/{consent_id}/revoke")
def revoke_consent(consent_id: str, body: RevokeConsentBody, ctx: AuthContext = Depends(get_ctx), c: AppContainer = Depends(get_container)) -> dict:
    return to_jsonable(c.interop_gateway.revoke_consent(ctx, consent_id=consent_id, reason=body.reason))


# ---- manual identity review queue
@router.get("/identity-candidates")
def list_identity_candidates(status: str = "pending", ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:
    return {"items": to_jsonable(c.interop_gateway.list_identity_candidates(ctx, status=status))}


@router.post("/identity-candidates/{candidate_id}/resolve")
def resolve_identity_candidate(candidate_id: str, body: ResolveIdentityCandidateBody, ctx: AuthContext = MANAGE, c: AppContainer = Depends(get_container)) -> dict:
    return to_jsonable(c.interop_gateway.resolve_identity_candidate(ctx, candidate_id=candidate_id, approve=body.approve))


# ---- connector registry
@router.get("/connectors")
def list_connectors(ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:
    return {"items": to_jsonable(c.interop_gateway.list_connectors(ctx))}


@router.post("/connectors/{connector_id}/health-check")
def connector_health(connector_id: str, ctx: AuthContext = MANAGE, c: AppContainer = Depends(get_container)) -> dict:
    return to_jsonable(c.interop_gateway.connector_health(ctx, connector_id=connector_id))


@router.put("/connectors/{connector_id}/enabled")
def set_connector_enabled(connector_id: str, body: SetConnectorEnabledBody, ctx: AuthContext = MANAGE, c: AppContainer = Depends(get_container)) -> dict:
    return to_jsonable(c.interop_gateway.set_connector_enabled(ctx, connector_id=connector_id, enabled=body.enabled))


# ---- configurable workflows (read surfaces - see app/interop/workflow/)
@router.get("/workflows")
def list_workflow_definitions(ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:
    return {"items": to_jsonable(c.interop_gateway.list_workflow_definitions(ctx))}


@router.get("/workflow-executions")
def list_workflow_executions(workflow_id: str | None = None, status: str | None = None, limit: int = 50, ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:
    return {"items": to_jsonable(c.interop_gateway.list_workflow_executions(ctx, workflow_id=workflow_id, status=status, limit=limit))}


@router.get("/workflow-executions/{execution_id}")
def get_workflow_execution(execution_id: str, ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:
    return to_jsonable(c.interop_gateway.get_workflow_execution(ctx, execution_id=execution_id))


# ---- central exception management (Section 16-18 - see app/interop/exceptions/)
@router.get("/exceptions")
def list_exceptions(resolution_state: str | None = None, error_code: str | None = None, correlation_id: str | None = None, limit: int = 100, ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:
    return {"items": to_jsonable(c.interop_gateway.list_exceptions(ctx, resolution_state=resolution_state, error_code=error_code, correlation_id=correlation_id, limit=limit))}


@router.post("/exceptions/{exception_id}/retry")
def retry_exception(exception_id: str, ctx: AuthContext = MANAGE, c: AppContainer = Depends(get_container)) -> dict:
    return to_jsonable(c.interop_gateway.retry_exception(ctx, exception_id=exception_id))


@router.post("/exceptions/{exception_id}/resolve")
def resolve_exception(exception_id: str, ctx: AuthContext = MANAGE, c: AppContainer = Depends(get_container)) -> dict:
    return to_jsonable(c.interop_gateway.resolve_exception(ctx, exception_id=exception_id))


@router.post("/exceptions/{exception_id}/mark-dead")
def mark_exception_dead(exception_id: str, body: MarkExceptionDeadBody, ctx: AuthContext = MANAGE, c: AppContainer = Depends(get_container)) -> dict:
    return to_jsonable(c.interop_gateway.mark_exception_dead(ctx, exception_id=exception_id, reason=body.reason))


# ---- monitoring: SLA/alerts (Section 19-20) + distributed transaction tracing (Section 21)
@router.get("/alerts")
def list_alerts(connector_id: str | None = None, acknowledged: bool | None = None, limit: int = 100, ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:
    return {"items": to_jsonable(c.interop_gateway.list_alerts(ctx, connector_id=connector_id, acknowledged=acknowledged, limit=limit))}


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, ctx: AuthContext = MANAGE, c: AppContainer = Depends(get_container)) -> dict:
    return to_jsonable(c.interop_gateway.acknowledge_alert(ctx, alert_id=alert_id))


@router.get("/trace/{correlation_id}")
def get_trace(correlation_id: str, ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:
    return to_jsonable(c.interop_gateway.get_trace(ctx, correlation_id=correlation_id))


# ---- service catalog & field mapping catalog (Section 8/22-23)
@router.get("/service-catalog")
def list_service_catalog(active: bool | None = None, ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:
    return {"items": to_jsonable(c.interop_gateway.list_service_catalog(ctx, active=active))}


@router.get("/field-mappings")
def list_field_mappings(service_id: str | None = None, system_id: str | None = None, ctx: AuthContext = READ, c: AppContainer = Depends(get_container)) -> dict:
    return {"items": to_jsonable(c.interop_gateway.list_field_mappings(ctx, service_id=service_id, system_id=system_id))}

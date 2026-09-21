"""/api/v1/admin: users/roles, reference data, routing rules, SLA policies, audit, anomalies."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.serialize import to_jsonable
from app.container import AppContainer
from app.core.authorization import AuthContext, Permission, Role
from app.core.dependencies import get_container, guard
from app.core.exceptions import ValidationFailed
from app.schemas.api import (
    ActiveBody,
    AnomalyStatusBody,
    CityBody,
    DepartmentBody,
    EmergencyBody,
    OfficeBody,
    RoleBody,
    RuleBody,
    ServiceBody,
    SlaBody,
    StaffBody,
    WardBody,
    WorkflowRuleBody,
)

router = APIRouter(prefix="/admin", tags=["admin"])
ADM = Depends(guard(Permission.ADMIN_DASHBOARD))


def _role(v: str) -> Role:
    try:
        return Role(v)
    except ValueError:
        raise ValidationFailed("Unknown role.") from None


@router.get("/reference-data")
def reference_data(ctx: AuthContext = ADM, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.admin.reference_data(ctx))  # type: ignore[no-any-return]


@router.get("/users")
def users(role: str | None = None, limit: int = 100, offset: int = 0, ctx: AuthContext = Depends(guard(Permission.ADMIN_USERS)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": to_jsonable(c.admin.list_users(ctx, role=_role(role) if role else None, limit=min(limit, 200), offset=max(offset, 0)))}


@router.post("/users", status_code=201)
def create_staff(body: StaffBody, ctx: AuthContext = Depends(guard(Permission.ADMIN_USERS)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.admin.create_staff(ctx, body.email, body.password, body.full_name, _role(body.role), body.department_code))  # type: ignore[no-any-return]


@router.put("/users/{user_id}/role")
def change_role(user_id: str, body: RoleBody, ctx: AuthContext = Depends(guard(Permission.ADMIN_USERS)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.admin.change_role(ctx, user_id, _role(body.role), body.department_code))  # type: ignore[no-any-return]


@router.put("/users/{user_id}/active")
def set_active(user_id: str, body: ActiveBody, ctx: AuthContext = Depends(guard(Permission.ADMIN_USERS)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.admin.set_user_active(ctx, user_id, body.active))  # type: ignore[no-any-return]


DEP = Depends(guard(Permission.ADMIN_DEPARTMENTS))


@router.put("/departments")
def save_department(body: DepartmentBody, ctx: AuthContext = DEP, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.admin.save_department(ctx, body.code, body.name, body.active))  # type: ignore[no-any-return]


@router.put("/wards")
def save_ward(body: WardBody, ctx: AuthContext = DEP, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.admin.save_ward(ctx, body.code, body.name, body.city_code))  # type: ignore[no-any-return]


@router.put("/cities")
def save_city(body: CityBody, ctx: AuthContext = DEP, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.admin.save_city(ctx, body.code, body.name, body.state, body.lat, body.lng))  # type: ignore[no-any-return]


@router.put("/services")
def save_service(body: ServiceBody, ctx: AuthContext = DEP, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.admin.save_service(ctx, body.code, body.name, body.department_code))  # type: ignore[no-any-return]


@router.put("/offices")
def save_office(body: OfficeBody, ctx: AuthContext = DEP, c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.admin.save_office(ctx, body.id, body.name, body.department_code, body.lat, body.lng, body.address))  # type: ignore[no-any-return]


@router.put("/routing-rules/{rule_id}")
def save_rule(rule_id: str, body: RuleBody, ctx: AuthContext = Depends(guard(Permission.ADMIN_ROUTING_RULES)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    try:
        rule = c.admin.save_routing_rule(ctx, rule_id, body.priority, body.department_code, categories=body.categories, keywords_any=body.keywords_any, wards=body.wards,
                                         min_severity=body.min_severity, service_code=body.service_code, active=body.active)  # fmt: skip
    except ValueError as exc:  # unknown department raised by the runtime router validation
        raise ValidationFailed(str(exc)) from exc
    return to_jsonable(rule)  # type: ignore[no-any-return]


@router.delete("/routing-rules/{rule_id}", status_code=204)
def delete_rule(rule_id: str, ctx: AuthContext = Depends(guard(Permission.ADMIN_ROUTING_RULES)), c: AppContainer = Depends(get_container)) -> None:
    c.admin.delete_routing_rule(ctx, rule_id)


@router.put("/sla-policies/{policy_id}")
def save_sla(policy_id: str, body: SlaBody, ctx: AuthContext = Depends(guard(Permission.ADMIN_WORKFLOW_RULES)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.admin.save_sla_policy(ctx, policy_id, body.priority, body.resolution_hours, department_code=body.department_code, escalation_gap_hours=body.escalation_gap_hours, max_level=body.max_level))  # type: ignore[no-any-return]


@router.delete("/sla-policies/{policy_id}", status_code=204)
def delete_sla(policy_id: str, ctx: AuthContext = Depends(guard(Permission.ADMIN_WORKFLOW_RULES)), c: AppContainer = Depends(get_container)) -> None:
    c.admin.delete_sla_policy(ctx, policy_id)


@router.get("/audit")
def audit(action_prefix: str | None = None, actor_id: str | None = None, limit: int = 100, ctx: AuthContext = Depends(guard(Permission.ADMIN_AUDIT)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": to_jsonable(c.admin.audit_log(ctx, action_prefix=action_prefix, actor_id=actor_id, limit=min(limit, 500)))}


@router.get("/anomalies")
def anomalies(status: str | None = "open", ctx: AuthContext = Depends(guard(Permission.ADMIN_MONITORING)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": to_jsonable(c.admin.anomalies(ctx, status=status))}


@router.put("/anomalies/{anomaly_id}/status")
def anomaly_status(anomaly_id: str, body: AnomalyStatusBody, ctx: AuthContext = Depends(guard(Permission.ADMIN_MONITORING)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.admin.set_anomaly_status(ctx, anomaly_id, body.status))  # type: ignore[no-any-return]


@router.get("/workflow-rules")
def workflow_rules(ctx: AuthContext = Depends(guard(Permission.ADMIN_WORKFLOW_RULES)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.admin.workflow_overview(ctx))  # type: ignore[no-any-return]


@router.put("/workflow-rules/{rule_id}")
def save_workflow_rule(rule_id: str, body: WorkflowRuleBody, ctx: AuthContext = Depends(guard(Permission.ADMIN_WORKFLOW_RULES)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.admin.save_workflow_rule(ctx, rule_id, body.name, body.trigger, body.action, conditions=body.conditions, params=body.params, priority=body.priority, active=body.active))  # type: ignore[no-any-return]


@router.delete("/workflow-rules/{rule_id}", status_code=204)
def delete_workflow_rule(rule_id: str, ctx: AuthContext = Depends(guard(Permission.ADMIN_WORKFLOW_RULES)), c: AppContainer = Depends(get_container)) -> None:
    c.admin.delete_workflow_rule(ctx, rule_id)


@router.get("/emergency-contacts")
def emergency_contacts(ctx: AuthContext = Depends(guard(Permission.ADMIN_CONFIG)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return {"items": to_jsonable(c.admin.emergency_contacts(ctx))}


@router.put("/emergency-contacts/{contact_id}")
def save_emergency_contact(contact_id: str, body: EmergencyBody, ctx: AuthContext = Depends(guard(Permission.ADMIN_CONFIG)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    return to_jsonable(c.admin.save_emergency_contact(ctx, contact_id, body.number, body.name, description=body.description, scope=body.scope, city_code=body.city_code, translations=body.translations, active=body.active, sort_order=body.sort_order))  # type: ignore[no-any-return]


@router.delete("/emergency-contacts/{contact_id}", status_code=204)
def delete_emergency_contact(contact_id: str, ctx: AuthContext = Depends(guard(Permission.ADMIN_CONFIG)), c: AppContainer = Depends(get_container)) -> None:
    c.admin.delete_emergency_contact(ctx, contact_id)


@router.post("/users/{user_id}/password-reset")
def issue_password_reset(user_id: str, ctx: AuthContext = Depends(guard(Permission.ADMIN_USERS)), c: AppContainer = Depends(get_container)) -> dict:  # type: ignore[type-arg]
    """One-time reset token for a user who cannot receive e-mail (shown once; the admin never sets a password)."""
    return c.admin.issue_password_reset(ctx, user_id)

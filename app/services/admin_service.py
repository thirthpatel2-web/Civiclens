"""Administration: users/roles, departments, wards, cities, services, routing rules, SLA policies,
audit, anomalies. Every mutation is authorised server-side and audited; validation reuses the
same domain classes the runtime uses (a rule that would break routing cannot be saved)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.core.authorization import (
    AuthContext,
    Permission,
    Role,
    is_privileged_role,
    require,
    require_mfa_for_privileged,
)
from app.core.exceptions import NotFound, PermissionDenied, ValidationFailed
from app.services.audit_service import AuditEvent
from app.services.auth_service import AuthService, UserRecord
from app.services.classification_service import CATEGORIES, SEVERITIES
from app.services.emergency_service import validate_contact
from app.services.ports import (
    AnomalyRecord,
    CityRecord,
    CivicServiceRecord,
    DepartmentRecord,
    EmergencyContactRecord,
    GovOfficeRecord,
    WardRecord,
    WorkflowRuleRecord,
)
from app.services.routing_service import DepartmentRouter, RoutingRule
from app.services.sla_service import SlaPolicy
from app.services.uow import UowFactory
from app.services.workflow_service import validate_rule

PRIORITIES = ("low", "medium", "high", "critical")


class AdminService:
    def __init__(self, uow_factory: UowFactory, auth_factory: Callable[[Any], AuthService], clock: Callable[[], datetime] | None = None) -> None:
        self._uow, self._auth, self._clock = uow_factory, auth_factory, clock or (lambda: datetime.now(UTC))

    def _guard(self, ctx: AuthContext, perm: Permission) -> None:
        try:
            require(ctx, perm)
            require_mfa_for_privileged(ctx)
        except PermissionDenied:
            self._denied(ctx, "admin.access_denied", {"permission": str(perm)})
            raise

    def _denied(self, ctx: AuthContext, action: str, meta: dict[str, Any]) -> None:
        """Record a refused privileged action in its OWN transaction: the failed operation's
        transaction is rolled back, but the security event must survive."""
        with self._uow() as uow:
            self._audit(uow, ctx, action, "admin", None, meta)
            uow.commit()

    def _audit(self, uow: Any, ctx: AuthContext, action: str, rtype: str, rid: str | None, meta: dict[str, Any] | None = None) -> None:
        from app.services.audit_service import AuditService

        AuditService(uow.audit, self._clock).record(action, actor_id=ctx.user_id, resource_type=rtype, resource_id=rid, metadata=meta or {})

    def _dept_scope(self, ctx: AuthContext, department_code: str | None) -> None:
        if ctx.department_id is not None and department_code != ctx.department_id:
            raise PermissionDenied("You may only administer your own department.")

    # ---------------------------------------------------------------- users
    def list_users(self, ctx: AuthContext, *, role: Role | None = None, limit: int = 100, offset: int = 0) -> list[UserRecord]:
        self._guard(ctx, Permission.ADMIN_USERS)
        with self._uow() as uow:
            users = uow.users.list(role=role, limit=limit, offset=offset)
        return [u for u in users if ctx.department_id is None or u.department_id == ctx.department_id]

    def create_staff(self, ctx: AuthContext, email: str, password: str, full_name: str, role: Role, department_id: str | None) -> UserRecord:
        self._guard(ctx, Permission.ADMIN_USERS)
        if role is Role.OFFICER:
            self._dept_scope(ctx, department_id)
        try:
            with self._uow() as uow:
                if role is Role.OFFICER and department_id not in {d.code for d in uow.config.departments() if d.active}:
                    raise ValidationFailed("Unknown department.", details={"field": "department_id"})
                user = self._auth(uow).create_staff(ctx, email, password, full_name, role, department_id)
                uow.commit()
        except PermissionDenied:  # after the failed transaction has rolled back, persist the refusal
            self._denied(ctx, "admin.create_staff_denied", {"role": str(role)})
            raise
        return user

    def change_role(self, ctx: AuthContext, user_id: str, role: Role, department_id: str | None) -> UserRecord:
        self._guard(ctx, Permission.ADMIN_USERS)
        try:
            with self._uow() as uow:
                user = self._auth(uow).change_role(ctx, user_id, role, department_id)
                uow.commit()
        except PermissionDenied:
            self._denied(ctx, "admin.role_change_denied", {"target": user_id, "role": str(role)})
            raise
        return user

    def set_user_active(self, ctx: AuthContext, user_id: str, active: bool) -> UserRecord:
        self._guard(ctx, Permission.ADMIN_USERS)
        try:
            with self._uow() as uow:
                user = self._auth(uow).set_active(ctx, user_id, active)
                uow.commit()
        except PermissionDenied:
            self._denied(ctx, "admin.user_active_denied", {"target": user_id})
            raise
        return user

    # ---------------------------------------------------------------- reference data
    def save_department(self, ctx: AuthContext, code: str, name: str, active: bool = True) -> DepartmentRecord:
        self._guard(ctx, Permission.ADMIN_DEPARTMENTS)
        if ctx.department_id is not None:
            raise PermissionDenied("Only organisation-wide administrators can manage departments.")
        code = (code or "").strip().lower()
        if not (2 <= len(code) <= 40) or not code.replace("_", "").replace("-", "").isalnum() or not 2 <= len((name or "").strip()) <= 120:
            raise ValidationFailed("Department code (2-40 letters/digits/_-) and name are required.")
        rec = DepartmentRecord(code, name.strip(), active)
        with self._uow() as uow:
            uow.config.save_department(rec)
            self._audit(uow, ctx, "admin.department_saved", "department", code, {"active": active})
            uow.commit()
        return rec

    def save_ward(self, ctx: AuthContext, code: str, name: str, city_code: str | None) -> WardRecord:
        self._guard(ctx, Permission.ADMIN_DEPARTMENTS)
        rec = WardRecord(_slug(code), _name(name), city_code)
        with self._uow() as uow:
            if city_code and city_code not in {c.code for c in uow.config.cities()}:
                raise ValidationFailed("Unknown city.")
            uow.config.save_ward(rec)
            self._audit(uow, ctx, "admin.ward_saved", "ward", rec.code)
            uow.commit()
        return rec

    def save_city(self, ctx: AuthContext, code: str, name: str, state: str | None, lat: float | None, lng: float | None) -> CityRecord:
        self._guard(ctx, Permission.ADMIN_DEPARTMENTS)
        from app.services.location_service import validate_location

        loc = validate_location(lat, lng)
        rec = CityRecord(_slug(code), _name(name), state, loc.lat, loc.lng)
        with self._uow() as uow:
            uow.config.save_city(rec)
            self._audit(uow, ctx, "admin.city_saved", "city", rec.code)
            uow.commit()
        return rec

    def save_service(self, ctx: AuthContext, code: str, name: str, department_code: str) -> CivicServiceRecord:
        self._guard(ctx, Permission.ADMIN_DEPARTMENTS)
        self._dept_scope(ctx, department_code)
        rec = CivicServiceRecord(_slug(code), _name(name), department_code)
        with self._uow() as uow:
            if department_code not in {d.code for d in uow.config.departments()}:
                raise ValidationFailed("Unknown department.")
            uow.config.save_service(rec)
            self._audit(uow, ctx, "admin.service_saved", "service", rec.code)
            uow.commit()
        return rec

    def save_office(self, ctx: AuthContext, office_id: str, name: str, department_code: str | None, lat: float, lng: float, address: str | None = None, city_code: str | None = None) -> GovOfficeRecord:
        self._guard(ctx, Permission.ADMIN_DEPARTMENTS)
        from app.services.location_service import validate_location

        loc = validate_location(lat, lng, address=address)
        if loc.lat is None:
            raise ValidationFailed("Office coordinates are required.")
        # ``city_code`` is what lets the Civic Locator group and filter offices by city, so an
        # unknown code is rejected here rather than stored and silently never matching a city.
        if city_code:
            with self._uow() as uow:
                if city_code not in {x.code for x in uow.config.cities()}:
                    raise ValidationFailed(f"Unknown city code: {city_code}")
        rec = GovOfficeRecord(_slug(office_id), _name(name), department_code, loc.lat, loc.lng or 0.0, loc.address, city_code or None)
        with self._uow() as uow:
            uow.config.save_office(rec)
            self._audit(uow, ctx, "admin.office_saved", "office", rec.id)
            uow.commit()
        return rec

    # ---------------------------------------------------------------- routing rules & SLA
    def save_routing_rule(self, ctx: AuthContext, rule_id: str, priority: int, department_code: str, *, categories: list[str] | None = None, keywords_any: list[str] | None = None,
                          wards: list[str] | None = None, min_severity: str | None = None, service_code: str | None = None, active: bool = True) -> RoutingRule:  # fmt: skip
        self._guard(ctx, Permission.ADMIN_ROUTING_RULES)
        self._dept_scope(ctx, department_code)
        errors: dict[str, str] = {}
        if not isinstance(priority, int) or isinstance(priority, bool) or not 0 <= priority <= 1000:
            errors["priority"] = "Priority must be 0-1000 (lower runs first)."
        if any(c not in CATEGORIES for c in categories or []):
            errors["categories"] = "Unknown category."
        if min_severity and min_severity not in SEVERITIES:
            errors["min_severity"] = "Unknown severity."
        if not (categories or keywords_any or wards or min_severity):
            errors["conditions"] = "A rule needs at least one condition; an empty rule would match nothing."
        if errors:
            raise ValidationFailed("Invalid routing rule.", details=errors)
        rule = RoutingRule(_slug(rule_id), priority, department_code, service_code, frozenset(categories or []), tuple(k.strip() for k in keywords_any or [] if k.strip()), frozenset(wards or []), min_severity, active)
        with self._uow() as uow:
            depts = frozenset(d.code for d in uow.config.departments() if d.active)
            DepartmentRouter([rule], depts)  # raises ValueError for unknown department: reuse runtime validation
            uow.config.save_routing_rule(rule)
            self._audit(uow, ctx, "admin.routing_rule_saved", "routing_rule", rule.id, {"department": department_code, "priority": priority, "active": active})
            uow.commit()
        return rule

    def delete_routing_rule(self, ctx: AuthContext, rule_id: str) -> None:
        self._guard(ctx, Permission.ADMIN_ROUTING_RULES)
        with self._uow() as uow:
            existing = next((r for r in uow.config.routing_rules() if r.id == rule_id), None)
            if existing is None:
                raise NotFound("Routing rule not found.")
            self._dept_scope(ctx, existing.department_code)
            uow.config.delete_routing_rule(rule_id)
            self._audit(uow, ctx, "admin.routing_rule_deleted", "routing_rule", rule_id)
            uow.commit()

    def save_sla_policy(self, ctx: AuthContext, policy_id: str, priority: str, resolution_hours: int, *, department_code: str | None = None, escalation_gap_hours: int = 48, max_level: int = 3) -> SlaPolicy:
        self._guard(ctx, Permission.ADMIN_WORKFLOW_RULES)
        self._dept_scope(ctx, department_code)
        if priority not in PRIORITIES:
            raise ValidationFailed("Unknown priority.", details={"field": "priority"})
        try:
            pol = SlaPolicy(_slug(policy_id), priority, resolution_hours, department_code, 0.25, escalation_gap_hours, max_level)
        except (ValueError, TypeError) as exc:
            raise ValidationFailed("Invalid SLA policy.", details={"reason": str(exc)}) from exc
        with self._uow() as uow:
            if department_code and department_code not in {d.code for d in uow.config.departments()}:
                raise ValidationFailed("Unknown department.")
            uow.config.save_sla_policy(pol)
            self._audit(uow, ctx, "admin.sla_policy_saved", "sla_policy", pol.id, {"priority": priority, "hours": resolution_hours, "department": department_code})
            uow.commit()
        return pol

    def delete_sla_policy(self, ctx: AuthContext, policy_id: str) -> None:
        self._guard(ctx, Permission.ADMIN_WORKFLOW_RULES)
        with self._uow() as uow:
            existing = next((p for p in uow.config.sla_policies() if p.id == policy_id), None)
            if existing is None:
                raise NotFound("SLA policy not found.")
            self._dept_scope(ctx, existing.department_code)
            uow.config.delete_sla_policy(policy_id)
            self._audit(uow, ctx, "admin.sla_policy_deleted", "sla_policy", policy_id)
            uow.commit()

    def issue_password_reset(self, ctx: AuthContext, user_id: str) -> dict[str, Any]:
        """Admin-assisted reset for users who cannot receive e-mail: returns a ONE-TIME token/link to hand over out-of-band.
        The admin never sees or sets a password. Privileged accounts can be reset only by a super-admin."""
        self._guard(ctx, Permission.ADMIN_USERS)
        with self._uow() as uow:
            target = uow.users.get_by_id(user_id)
            if target is None or (ctx.department_id is not None and target.department_id != ctx.department_id):
                raise NotFound("User not found.")
            if is_privileged_role(target.role) and ctx.role is not Role.SUPER_ADMIN:
                raise PermissionDenied("Only a super-admin can reset an administrator's password.")
            token = self._auth(uow).issue_reset_for_user(user_id)
            self._audit(uow, ctx, "admin.password_reset_issued", "user", user_id)
            uow.commit()
        return {"token": token, "expires_in_minutes": 60, "note": "Give this to the user securely. It works once and expires; it is shown only now."}

    # ---------------------------------------------------------------- workflow rules & emergency contacts (organisation-wide)
    def _org_wide(self, ctx: AuthContext) -> None:
        if ctx.department_id is not None:
            raise PermissionDenied("This setting is organisation-wide.")

    def save_workflow_rule(self, ctx: AuthContext, rule_id: str, name: str, trigger: str, action: str, *, conditions: dict[str, Any] | None = None, params: dict[str, Any] | None = None,
                           priority: int = 100, active: bool = True) -> WorkflowRuleRecord:  # fmt: skip
        self._guard(ctx, Permission.ADMIN_WORKFLOW_RULES)
        self._org_wide(ctx)
        rule = validate_rule(WorkflowRuleRecord(rule_id.strip().lower(), name.strip(), trigger, conditions or {}, action, params or {}, priority, active, ctx.user_id, self._clock()))
        with self._uow() as uow:
            uow.workflow.save_rule(rule)
            self._audit(uow, ctx, "admin.workflow_rule_saved", "workflow_rule", rule.id, {"trigger": trigger, "action": action, "active": active})
            uow.commit()
        return rule

    def delete_workflow_rule(self, ctx: AuthContext, rule_id: str) -> None:
        self._guard(ctx, Permission.ADMIN_WORKFLOW_RULES)
        self._org_wide(ctx)
        with self._uow() as uow:
            if not uow.workflow.delete_rule(rule_id):
                raise NotFound("Workflow rule not found.")
            self._audit(uow, ctx, "admin.workflow_rule_deleted", "workflow_rule", rule_id)
            uow.commit()

    def workflow_overview(self, ctx: AuthContext) -> dict[str, Any]:
        self._guard(ctx, Permission.ADMIN_WORKFLOW_RULES)
        with self._uow() as uow:
            return {"rules": uow.workflow.list_rules(), "executions": uow.workflow.list_executions(limit=50)}

    def save_emergency_contact(self, ctx: AuthContext, contact_id: str, number: str, name: str, *, description: str = "", scope: str = "national", city_code: str | None = None,
                               translations: dict[str, dict[str, str]] | None = None, active: bool = True, sort_order: int = 100) -> EmergencyContactRecord:  # fmt: skip
        self._guard(ctx, Permission.ADMIN_CONFIG)
        self._org_wide(ctx)
        rec = validate_contact(EmergencyContactRecord(contact_id.strip().lower(), number.strip(), name.strip(), description.strip(), scope, city_code, translations or {}, active, sort_order))
        with self._uow() as uow:
            if rec.city_code and rec.city_code not in {c.code for c in uow.config.cities()}:
                raise ValidationFailed("Unknown city.")
            uow.emergency.save(rec)
            self._audit(uow, ctx, "admin.emergency_contact_saved", "emergency_contact", rec.id, {"number": rec.number, "active": active})
            uow.commit()
        return rec

    def delete_emergency_contact(self, ctx: AuthContext, contact_id: str) -> None:
        self._guard(ctx, Permission.ADMIN_CONFIG)
        self._org_wide(ctx)
        with self._uow() as uow:
            if not uow.emergency.delete(contact_id):
                raise NotFound("Contact not found.")
            self._audit(uow, ctx, "admin.emergency_contact_deleted", "emergency_contact", contact_id)
            uow.commit()

    def emergency_contacts(self, ctx: AuthContext) -> list[EmergencyContactRecord]:
        self._guard(ctx, Permission.ADMIN_CONFIG)
        with self._uow() as uow:
            return uow.emergency.list(active_only=False)

    # ---------------------------------------------------------------- read models
    def reference_data(self, ctx: AuthContext) -> dict[str, Any]:
        self._guard(ctx, Permission.ADMIN_DASHBOARD)
        with self._uow() as uow:
            c = uow.config
            return {"departments": c.departments(), "wards": c.wards(), "cities": c.cities(), "services": c.services(), "offices": c.offices(), "routing_rules": c.routing_rules(), "sla_policies": c.sla_policies()}

    def audit_log(self, ctx: AuthContext, *, action_prefix: str | None = None, actor_id: str | None = None, since: datetime | None = None, limit: int = 100) -> list[AuditEvent]:
        self._guard(ctx, Permission.ADMIN_AUDIT)
        if ctx.department_id is not None:
            raise PermissionDenied("The audit log is available to organisation-wide administrators only.")
        with self._uow() as uow:
            self._audit(uow, ctx, "admin.audit_viewed", "audit_log", None, {"filter": action_prefix})
            events = uow.audit.query(action_prefix=action_prefix, actor_id=actor_id, since=since, limit=min(limit, 500))
            uow.commit()
        return events

    def anomalies(self, ctx: AuthContext, *, status: str | None = "open") -> list[AnomalyRecord]:
        self._guard(ctx, Permission.ADMIN_MONITORING)
        with self._uow() as uow:
            return uow.anomalies.list(status=status, department_code=ctx.department_id)

    def set_anomaly_status(self, ctx: AuthContext, anomaly_id: str, status: str) -> AnomalyRecord:
        self._guard(ctx, Permission.ADMIN_MONITORING)
        if status not in ("acknowledged", "resolved"):
            raise ValidationFailed("Status must be 'acknowledged' or 'resolved'.")
        with self._uow() as uow:
            a = uow.anomalies.get(anomaly_id)
            if a is None or (ctx.department_id is not None and a.department_code != ctx.department_id):
                raise NotFound("Anomaly not found.")
            a.status = status
            uow.anomalies.update(a)
            self._audit(uow, ctx, "admin.anomaly_status", "anomaly", anomaly_id, {"status": status})
            uow.commit()
        return a


def _slug(v: str) -> str:
    s = (v or "").strip().lower()
    if not (2 <= len(s) <= 60) or not s.replace("_", "").replace("-", "").isalnum():
        raise ValidationFailed("Code must be 2-60 characters: letters, digits, '-' or '_'.")
    return s


def _name(v: str) -> str:
    s = (v or "").strip()
    if not 2 <= len(s) <= 120:
        raise ValidationFailed("Name must be 2-120 characters.")
    return s

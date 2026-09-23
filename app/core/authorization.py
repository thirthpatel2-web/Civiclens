"""Role-based access control with server-side department isolation.

The :class:`AuthContext` is built from the *database* user row and session, never
from anything the browser sends. All decisions in this module are pure functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.core.exceptions import PermissionDenied


class Role(StrEnum):
    CITIZEN = "citizen"
    OFFICER = "officer"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
    INTEGRATION_ADMIN = "integration_admin"  # manages the interoperability platform only - not users/departments/routing rules
    AUDITOR = "auditor"  # read-only across audit trail, interop transactions/timeline, analytics - never a write permission


class Permission(StrEnum):
    # citizen
    COMPLAINT_CREATE = "complaint.create"
    COMPLAINT_READ_OWN = "complaint.read_own"
    EVIDENCE_UPLOAD = "evidence.upload"
    COMPLAINT_FEEDBACK = "complaint.feedback"
    RTI_MANAGE_OWN = "rti.manage_own"
    LEGAL_ANALYZE = "legal.analyze"
    GIS_VIEW = "gis.view"
    ASSISTANT_USE = "assistant.use"
    PROFILE_MANAGE = "profile.manage"
    NOTIFICATION_READ_OWN = "notification.read_own"
    # officer
    COMPLAINT_READ_DEPARTMENT = "complaint.read_department"
    COMPLAINT_UPDATE_STATUS = "complaint.update_status"
    COMPLAINT_REMARK = "complaint.remark"
    COMPLAINT_ASSIGN = "complaint.assign"
    COMPLAINT_FIELD_ACTION = "complaint.field_action"
    SLA_VIEW = "sla.view"
    DASHBOARD_DEPARTMENT = "dashboard.department"
    DUPLICATE_REVIEW = "duplicate.review"
    INVESTIGATION_RUN = "investigation.run"
    # admin
    ADMIN_DASHBOARD = "admin.dashboard"
    ADMIN_USERS = "admin.users"
    ADMIN_DEPARTMENTS = "admin.departments"
    ADMIN_ROUTING_RULES = "admin.routing_rules"
    ADMIN_WORKFLOW_RULES = "admin.workflow_rules"
    ADMIN_INTEGRATIONS = "admin.integrations"
    ADMIN_AUDIT = "admin.audit"
    ADMIN_CONFIG = "admin.config"
    ADMIN_MONITORING = "admin.monitoring"
    ANALYTICS_VIEW = "analytics.view"
    COMPLAINT_READ_ALL = "complaint.read_all"
    # interoperability platform - distinct from ADMIN_INTEGRATIONS (which also gates the older
    # government-submission/integration-exception surfaces): a citizen/officer never holds these,
    # and an AUDITOR holds INTEROP_READ without INTEROP_MANAGE
    INTEROP_MANAGE = "interop.manage"
    INTEROP_READ = "interop.read"
    # super-admin only
    ROLE_ASSIGN_PRIVILEGED = "role.assign_privileged"


P = Permission

_CITIZEN = frozenset(
    {
        P.COMPLAINT_CREATE, P.COMPLAINT_READ_OWN, P.EVIDENCE_UPLOAD, P.COMPLAINT_FEEDBACK,
        P.RTI_MANAGE_OWN, P.LEGAL_ANALYZE, P.GIS_VIEW, P.ASSISTANT_USE, P.PROFILE_MANAGE,
        P.NOTIFICATION_READ_OWN,
    }
)  # fmt: skip
_OFFICER = frozenset(
    {
        P.COMPLAINT_READ_DEPARTMENT, P.COMPLAINT_UPDATE_STATUS, P.COMPLAINT_REMARK,
        P.COMPLAINT_ASSIGN, P.COMPLAINT_FIELD_ACTION, P.SLA_VIEW, P.DASHBOARD_DEPARTMENT,
        P.DUPLICATE_REVIEW, P.INVESTIGATION_RUN, P.GIS_VIEW, P.ASSISTANT_USE,
        P.PROFILE_MANAGE, P.NOTIFICATION_READ_OWN,
    }
)  # fmt: skip
_ADMIN = frozenset(
    {
        P.ADMIN_DASHBOARD, P.ADMIN_USERS, P.ADMIN_DEPARTMENTS, P.ADMIN_ROUTING_RULES,
        P.ADMIN_WORKFLOW_RULES, P.ADMIN_INTEGRATIONS, P.ADMIN_AUDIT, P.ADMIN_CONFIG,
        P.ADMIN_MONITORING, P.ANALYTICS_VIEW, P.COMPLAINT_READ_ALL, P.COMPLAINT_READ_DEPARTMENT,
        P.COMPLAINT_ASSIGN, P.SLA_VIEW, P.DUPLICATE_REVIEW, P.INVESTIGATION_RUN,
        P.DASHBOARD_DEPARTMENT, P.GIS_VIEW, P.ASSISTANT_USE, P.PROFILE_MANAGE,
        P.NOTIFICATION_READ_OWN, P.INTEROP_MANAGE, P.INTEROP_READ,
    }
)  # fmt: skip
_INTEGRATION_ADMIN = frozenset(
    {
        P.INTEROP_MANAGE, P.INTEROP_READ, P.ADMIN_INTEGRATIONS, P.ADMIN_MONITORING,
        P.GIS_VIEW, P.ASSISTANT_USE, P.PROFILE_MANAGE, P.NOTIFICATION_READ_OWN,
    }
)  # fmt: skip - scoped to the interop platform, not admin.users/departments/routing_rules/workflow_rules/audit/config
_AUDITOR = frozenset(
    {
        P.INTEROP_READ, P.ADMIN_AUDIT, P.ANALYTICS_VIEW,
        P.ASSISTANT_USE, P.PROFILE_MANAGE, P.NOTIFICATION_READ_OWN,
    }
)  # fmt: skip - read-only: no INTEROP_MANAGE, no ADMIN_USERS/DEPARTMENTS/*_RULES/CONFIG

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.CITIZEN: _CITIZEN,
    Role.OFFICER: _OFFICER,
    Role.ADMIN: _ADMIN,
    Role.SUPER_ADMIN: frozenset(Permission),
    Role.INTEGRATION_ADMIN: _INTEGRATION_ADMIN,
    Role.AUDITOR: _AUDITOR,
}

_PRIVILEGED = {Role.ADMIN, Role.SUPER_ADMIN, Role.INTEGRATION_ADMIN, Role.AUDITOR}


def is_privileged_role(role: Role) -> bool:
    """True for any role that requires MFA this session and extra care assigning/resetting -
    the single source of truth ``admin_service.py`` and ``require_mfa_for_privileged`` both use."""
    return role in _PRIVILEGED


@dataclass(frozen=True)
class AuthContext:
    """Who is acting. Built server-side from the session and the user row."""

    user_id: str
    role: Role
    department_id: str | None = None  # officers/department admins; None = not scoped
    mfa_verified: bool = False

    def has(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS[self.role]


def require(ctx: AuthContext, permission: Permission) -> None:
    if not ctx.has(permission):
        raise PermissionDenied("You do not have permission to perform this action.")


def require_mfa_for_privileged(ctx: AuthContext) -> None:
    """Privileged roles must have completed a second factor this session."""
    if is_privileged_role(ctx.role) and not ctx.mfa_verified:
        raise PermissionDenied("Two-factor authentication is required for this role.")


def can_access_complaint(
    ctx: AuthContext, *, owner_id: str, department_id: str | None, write: bool = False
) -> bool:
    """Decide record-level access.

    * Citizen: only their own complaints, read-only through this check.
    * Officer: only complaints of their own department.
    * Admin bound to a department: only that department; unbound admin: all.
    * Super-admin: all.
    """
    if ctx.role is Role.CITIZEN:
        return not write and owner_id == ctx.user_id and ctx.has(Permission.COMPLAINT_READ_OWN)
    if ctx.role is Role.OFFICER:
        return (
            ctx.department_id is not None
            and department_id is not None
            and ctx.department_id == department_id
            and ctx.has(Permission.COMPLAINT_READ_DEPARTMENT)
        )
    if ctx.role is Role.ADMIN:
        if write:
            return False  # admins administer; officers action complaints
        if ctx.department_id is None:
            return True
        return department_id == ctx.department_id
    return True  # SUPER_ADMIN


def require_complaint_access(
    ctx: AuthContext, *, owner_id: str, department_id: str | None, write: bool = False
) -> None:
    if not can_access_complaint(ctx, owner_id=owner_id, department_id=department_id, write=write):
        # Same message for "exists but not yours" and "does not exist" upstream.
        raise PermissionDenied("You do not have access to this record.")


_STAFF_MANAGERS = {Role.ADMIN, Role.SUPER_ADMIN}  # who may assign non-privileged roles at all - narrower
# than is_privileged_role(): an AUDITOR or INTEGRATION_ADMIN must never manage other users' roles


def can_assign_role(actor: AuthContext, *, target_user_id: str, new_role: Role) -> bool:
    """No self-promotion; only super-admins grant privileged roles; admins manage below."""
    if actor.user_id == target_user_id:
        return False
    if is_privileged_role(new_role):
        return actor.role is Role.SUPER_ADMIN
    return actor.role in _STAFF_MANAGERS

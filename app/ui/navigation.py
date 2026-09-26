"""Navigation model: groups, routes, icons and which roles see them. The static audit test checks
that every route here has a registered page."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.authorization import Role

ALL = frozenset(Role)
CIT = frozenset({Role.CITIZEN})
STAFF = frozenset({Role.OFFICER})
ADMINS = frozenset({Role.ADMIN, Role.SUPER_ADMIN})
OFFICER_UP = frozenset({Role.OFFICER, Role.ADMIN, Role.SUPER_ADMIN})
# Everyone who holds INTEROP_READ: the interoperability console (auditors see it read-only). Officers
# do not hold it - consent and identity data stay with the platform team, not the complaint desk.
GATEWAY = frozenset({Role.ADMIN, Role.SUPER_ADMIN, Role.INTEGRATION_ADMIN, Role.AUDITOR})


@dataclass(frozen=True)
class NavItem:
    key: str
    route: str
    icon: str
    roles: frozenset[Role]


@dataclass(frozen=True)
class NavGroup:
    key: str | None
    items: tuple[NavItem, ...]


NAVIGATION: tuple[NavGroup, ...] = (
    NavGroup(None, (NavItem("nav.dashboard", "/dashboard", "dashboard", CIT), NavItem("nav.assistant", "/assistant", "record_voice_over", ALL))),
    NavGroup("nav.services", (NavItem("nav.report", "/report", "add_circle", CIT), NavItem("nav.rti", "/rti", "gavel", CIT), NavItem("nav.legal", "/legal", "balance", CIT))),
    NavGroup("nav.intelligence", (NavItem("nav.copilot", "/copilot", "smart_toy", ALL), NavItem("nav.gis", "/gis", "map", ALL), NavItem("nav.locator", "/locator", "place", ALL), NavItem("nav.interop", "/interop", "hub", ALL))),
    NavGroup("nav.track", (NavItem("nav.grievances", "/grievances", "assignment", CIT), NavItem("nav.my_data", "/my-data", "how_to_reg", CIT))),
    NavGroup("nav.interop_gateway", (NavItem("nav.interop_gateway", "/gateway", "hub", GATEWAY),)),
    NavGroup("nav.emergency", (NavItem("nav.emergency", "/emergency", "emergency", ALL),)),
    NavGroup("nav.account", (NavItem("nav.profile", "/profile", "person", CIT), NavItem("nav.my_profile", "/profile", "person", ALL - CIT), NavItem("nav.settings", "/settings", "shield", ALL), NavItem("nav.notifications", "/notifications", "notifications", ALL),
                             NavItem("nav.documents", "/documents", "folder", ALL), NavItem("nav.security", "/security", "lock", ALL))),
    NavGroup("nav.officer", (NavItem("nav.dashboard", "/officer", "space_dashboard", OFFICER_UP), NavItem("nav.officer_queue", "/officer/queue", "inbox", STAFF),
                             NavItem("nav.investigations", "/officer/investigations", "search", OFFICER_UP))),
    NavGroup("nav.administration", (NavItem("nav.admin_overview", "/admin", "admin_panel_settings", ADMINS), NavItem("nav.users", "/admin/users", "group", ADMINS), NavItem("nav.departments", "/admin/departments", "apartment", ADMINS),
                                    NavItem("nav.wards", "/admin/wards", "location_city", ADMINS), NavItem("nav.civic_services", "/admin/services", "miscellaneous_services", ADMINS),
                                    NavItem("nav.routing", "/admin/routing-rules", "alt_route", ADMINS), NavItem("nav.workflow", "/admin/workflow-rules", "account_tree", ADMINS), NavItem("nav.sla", "/admin/sla", "timer", ADMINS), NavItem("nav.integrations", "/admin/integrations", "hub", ADMINS),
                                    NavItem("nav.audit", "/admin/audit", "fact_check", ADMINS), NavItem("nav.analytics", "/admin/analytics", "insights", ADMINS), NavItem("nav.anomalies", "/admin/anomalies", "warning", ADMINS),
                                    NavItem("nav.triage", "/admin/triage", "call_split", ADMINS), NavItem("nav.investigations", "/admin/investigations", "policy", ADMINS), NavItem("nav.emergency_admin", "/admin/emergency", "emergency", ADMINS), NavItem("nav.monitoring", "/admin/monitoring", "monitor_heart", ADMINS),
                                    NavItem("nav.exceptions", "/admin/exceptions", "report_problem", ADMINS))),
)


def home_for(role: Role) -> str:
    if role is Role.CITIZEN:
        return "/dashboard"
    if role is Role.OFFICER:
        return "/officer"
    if role in (Role.INTEGRATION_ADMIN, Role.AUDITOR):
        return "/gateway"  # neither holds admin-page permissions; /admin would bounce them in a loop
    return "/admin"


def visible(role: Role) -> list[NavGroup]:
    out = []
    for g in NAVIGATION:
        items = tuple(i for i in g.items if role in i.roles)
        if items:
            out.append(NavGroup(g.key, items))
    return out

"""Administration pages. Every table renders persisted data; every form calls AdminService (which authorises and audits)."""

from __future__ import annotations

import json
from typing import Any

from nicegui import ui

from app.container import AppContainer
from app.core.authorization import Role
from app.core.exceptions import CivicLensError
from app.core.transactions import run_in_uow
from app.services.classification_service import CATEGORIES, SEVERITIES
from app.services.workflow_service import ACTIONS as WF_ACTIONS
from app.services.workflow_service import TRIGGERS as WF_TRIGGERS
from app.ui.base import UiUser, data_table, info_banner, page, tr
from app.ui.components import (
    chip,
    confirm_dialog,
    page_header,
    section_title,
    stat_tile,
    state_panel,
)
from app.ui.navigation import ADMINS


def _act(c: AppContainer, fn: Any) -> Any:
    def run(*a: Any) -> None:
        try:
            fn(*a)
        except (CivicLensError, ValueError) as exc:
            # `details` only exists on CivicLensError, not on a plain ValueError, hence getattr
            # rather than a direct attribute access - looked up once and reused, so mypy is never
            # asked to accept `exc.details` unconditionally on the union type.
            details = getattr(exc, "details", None)
            ui.notify(getattr(exc, "message", str(exc)) + (f" {details}" if details else ""), type="negative")
            return
        ui.notify(tr(c, "msg.saved"), type="positive")
        ui.navigate.reload()

    return run


def _danger_action(c: AppContainer, label: str, on_click: Any) -> None:
    """A destructive action that must be confirmed before it runs - deletes/deactivations were one click away before."""
    open_dialog = confirm_dialog(label, tr(c, "ad.confirm_undone"), confirm_label=label, cancel_label=tr(c, "act.cancel"), danger=True, on_confirm=_act(c, on_click))
    ui.button(label, icon="delete_outline", on_click=open_dialog).props("outline dense color=negative")


def _status_rows(s: dict[str, Any]) -> None:
    """The platform's moving parts as plain-language rows with a coloured state, instead of raw dict dumps."""
    q = s.get("queue") or {}
    by = q.get("by_status") or {}
    rag = s.get("rag") or {}
    adapters = s.get("adapters") or {}
    connected = sum(1 for v in adapters.values() if v == "CONNECTED")
    rows = [
        ("Job queue", "success" if q.get("backend_reachable") else "danger", "reachable" if q.get("backend_reachable") else "not reachable",
         ", ".join(f"{v} {k}" for k, v in sorted(by.items())) or "no jobs yet"),
        ("Background workers", "success" if q.get("workers") else "warning", f"{len(q.get('workers') or {})} running",
         "jobs wait in the queue until a worker starts" if not q.get("workers") else "heartbeats received"),
        ("Knowledge base", "success" if rag.get("chunks") else "warning", f"{rag.get('chunks', 0)} passages",
         f"semantic search {'on' if rag.get('semantic_search') else 'off'} · language model {'connected' if rag.get('model') else 'not connected'}"),
        ("Live updates", "info", f"{s.get('websocket_connections', 0)} open", "browsers and phones receiving real-time pushes"),
        ("Government platforms", "success" if connected else "muted", f"{connected}/{len(adapters)} connected",
         "no credentials supplied yet - nothing is sent" if not connected else ", ".join(k for k, v in adapters.items() if v == "CONNECTED")),
    ]  # fmt: skip
    for name, tone, state, detail in rows:
        with ui.row().classes("items-center w-full gap-2"):
            ui.label(name).classes("text-sm font-medium").style("color: var(--cl-fg); min-width: 150px;")
            chip(state, color=tone)
            ui.label(detail).classes("text-xs").style("color: var(--cl-fg-subtle);")


# A starting point an admin applies in one click and then edits - hours rise as priority drops and
# the lowest tier stays inside the 21-day ceiling CPGRAMS sets for public grievances.
SUGGESTED_SLA = (("sla-critical", "critical", 24, 12), ("sla-high", "high", 72, 24), ("sla-medium", "medium", 168, 48), ("sla-low", "low", 504, 72))

# One-click workflow templates, each a rule WorkflowService's validator accepts.
WORKFLOW_TEMPLATES: tuple[tuple[str, str, str, str, dict[str, Any], dict[str, Any]], ...] = (
    ("critical-alert", "Alert admins about every critical complaint", "complaint.created", "notify_admins", {"priority_min": "critical"}, {}),
    ("auto-assign", "Assign new complaints to the least-loaded officer", "complaint.created", "assign_least_loaded", {}, {}),
    ("stale-escalate", "Escalate complaints still open after 72 hours", "scheduled", "escalate", {"age_hours_min": 72, "statuses": ["submitted", "ai_routed", "assigned"]}, {}),
    ("auto-close", "Close resolved complaints after 7 days without feedback", "scheduled", "auto_close", {"age_hours_min": 168, "statuses": ["resolved"]}, {}),
)


TRIGGER_WORDS = {"complaint.created": "When a complaint is filed", "complaint.status_changed": "When a complaint's status changes", "scheduled": "Every 15 minutes, for complaints"}
ACTION_WORDS = {"notify_admins": "alert the administrators", "escalate": "escalate it one level", "auto_close": "close it", "assign_least_loaded": "assign it to the least-loaded officer",
                "add_internal_note": "add an internal note"}  # fmt: skip


def _duration(hours: float) -> str:
    return f"{hours:.0f} h" if hours < 48 else f"{hours / 24:.0f} days" if hours % 24 == 0 else f"{hours / 24:.1f} days"


def _conditions(cond: dict[str, Any]) -> str:
    """A workflow rule's conditions as a phrase an administrator can read aloud."""
    parts = []
    if cond.get("priority_min"):
        parts.append(f"priority {cond['priority_min']} or higher")
    if cond.get("categories"):
        parts.append("category " + " / ".join(cond["categories"]))
    if cond.get("departments"):
        parts.append("department " + " / ".join(cond["departments"]))
    if cond.get("wards"):
        parts.append("ward " + " / ".join(cond["wards"]))
    if cond.get("statuses"):
        parts.append("status " + " / ".join(s.replace("_", " ") for s in cond["statuses"]))
    if cond.get("languages"):
        parts.append("language " + " / ".join(cond["languages"]))
    if cond.get("unrouted"):
        parts.append("not yet routed")
    if cond.get("age_hours_min") is not None:
        parts.append(f"older than {_duration(float(cond['age_hours_min']))}")
    return ", ".join(parts) or "any complaint"


def register(c: AppContainer) -> None:
    def _shortcuts() -> None:
        """Where an admin usually goes next - one click instead of hunting through the sidebar."""
        with ui.row().classes("gap-2 flex-wrap w-full"):
            for label, icon, route in (("Interoperability Gateway", "hub", "/gateway"), ("Unrouted complaints", "call_split", "/admin/triage"), ("SLA policies", "timer", "/admin/sla"),
                                       ("Workflow rules", "account_tree", "/admin/workflow-rules"), ("Audit log", "fact_check", "/admin/audit"), ("System health", "monitor_heart", "/admin/monitoring")):  # fmt: skip
                ui.button(label, icon=icon, on_click=lambda r=route: ui.navigate.to(r)).props("outline dense no-caps")

    @page(c, "/admin", "nav.admin_overview", roles=ADMINS)
    def overview(c: AppContainer, user: UiUser) -> None:
        d = c.dashboards.admin(user.ctx)
        page_header(tr(c, "nav.admin_overview"), icon="admin_panel_settings")
        with ui.row().classes("gap-3 w-full flex-wrap"):
            stat_tile(tr(c, "ad.total_complaints"), d["total"], color="primary", icon="assignment")
            stat_tile(tr(c, "card.open"), d["open"], color="info", icon="pending_actions")
            stat_tile(tr(c, "card.overdue"), d["sla"]["breached"], color="danger", icon="report")
            stat_tile(tr(c, "card.at_risk"), d["sla"]["at_risk"], color="warning", icon="schedule")
            stat_tile(tr(c, "card.escalated"), d["escalated"], color="danger", icon="trending_up")
            stat_tile(tr(c, "col.unrouted"), d["unrouted"], color="muted", icon="alt_route")
        if d["resolution_hours"]:
            with ui.row().classes("cl-card w-full items-center gap-2"):
                ui.icon("timer").style("color: var(--cl-fg-muted);")
                ui.label(f"Resolution time: median {d['resolution_hours']['median']} h over {d['resolution_hours']['count']} resolved complaints.").classes("text-sm").style("color: var(--cl-fg-muted);")
        with ui.row().classes("gap-4 w-full flex-wrap"):
            with ui.column().classes("cl-card gap-2").style("flex: 1; min-width: 300px;"):
                section_title(tr(c, "ad.routing_accuracy"), tr(c, "ad.routing_accuracy_sub"))
                with ui.row().classes("gap-2 flex-wrap"):
                    if d["routing_sources"]:
                        how = {"rule": "matched a routing rule", "ai": "AI fallback", "manual": "routed by hand", "unrouted": "waiting for triage"}
                        for k, v in d["routing_sources"].items():
                            chip(f"{v} {how.get(k, k)}", color="info", outline=True)
                    else:
                        ui.label(tr(c, "msg.no_data")).classes("text-sm").style("color: var(--cl-fg-subtle);")
            with ui.column().classes("cl-card gap-2").style("flex: 1; min-width: 300px;"):
                section_title(tr(c, "col.system"))
                _status_rows(d["system"] or {})
        _shortcuts()
        section_title(tr(c, "ad.recent_audit"))
        labels = run_in_uow(c, lambda uow: {a: uow.officers.user_label(a) for a in {e.actor_id for e in d["recent_audit"] if e.actor_id}})
        data_table([("at", tr(c, "legal.col_when")), ("action", tr(c, "col.action")), ("actor", tr(c, "col.actor"))],
                   [{"id": str(i), "at": e.occurred_at.strftime("%d %b %H:%M"), "action": e.action.replace("_", " "), "actor": labels.get(e.actor_id or "") or (e.actor_id or "system")[:8]} for i, e in enumerate(d["recent_audit"])])  # fmt: skip
        if not d["has_data"]:
            info_banner(tr(c, "msg.no_data"))

    @page(c, "/admin/users", "nav.users", roles=ADMINS)
    def users(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.users"), icon="group")
        depts = [x.code for x in c.admin.reference_data(user.ctx)["departments"]]
        items = c.admin.list_users(user.ctx)
        with ui.row().classes("gap-6 w-full flex-wrap"):
            with ui.column().classes("gap-3").style("flex: 1.4; min-width: 380px;"):
                data_table([("email", tr(c, "lbl.email")), ("name", tr(c, "col.name")), ("role", tr(c, "col.role")), ("dept", tr(c, "lbl.department")), ("active", tr(c, "filter.active"))], [{"id": u.id, "email": u.email, "name": u.full_name, "role": u.role.value.replace("_", " "), "dept": u.department_id or "-", "active": u.is_active} for u in items],
                           search="Search name, e-mail or role")
            with ui.column().classes("gap-4").style("flex: 1; min-width: 300px;"):
                with ui.column().classes("cl-card gap-2 w-full"):
                    section_title(tr(c, "ad.create_staff"))
                    email, name = ui.input(tr(c, "lbl.email")).props("outlined dense").classes("w-full"), ui.input(tr(c, "fullName")).props("outlined dense").classes("w-full")
                    pw = ui.input(tr(c, "lbl.password"), password=True).props("outlined dense").classes("w-full")
                    roles = [Role.OFFICER.value] + ([Role.ADMIN.value, Role.SUPER_ADMIN.value] if user.ctx.role is Role.SUPER_ADMIN else [])
                    role, dept = ui.select(roles, value=roles[0], label=tr(c, "col.role")).props("outlined dense").classes("w-full"), ui.select(depts, label=tr(c, "lbl.department")).props("outlined dense").classes("w-full")
                    ui.button(tr(c, "act.submit"), icon="person_add", on_click=_act(c, lambda: c.admin.create_staff(user.ctx, email.value or "", pw.value or "", name.value or "", Role(role.value), dept.value))).props("color=primary unelevated").classes("w-full")
                with ui.column().classes("cl-card gap-2 w-full"):
                    section_title(tr(c, "ad.change_role_deactivate"))
                    uid = ui.select({u.id: f"{u.email} ({u.role.value})" for u in items}, label=tr(c, "col.user")).props("outlined dense").classes("w-full")
                    new_role, new_dept = ui.select([r.value for r in Role], label=tr(c, "ad.new_role")).props("outlined dense").classes("w-full"), ui.select(depts, label=tr(c, "lbl.department")).props("outlined dense").classes("w-full")
                    with ui.row().classes("gap-2 flex-wrap"):
                        ui.button(tr(c, "ad.change_role"), on_click=_act(c, lambda: c.admin.change_role(user.ctx, uid.value, Role(new_role.value), new_dept.value))).props("outline dense")
                        ui.button(tr(c, "act.reactivate"), on_click=_act(c, lambda: c.admin.set_user_active(user.ctx, uid.value, True))).props("outline dense")
                        _danger_action(c, tr(c, "act.deactivate"), lambda: c.admin.set_user_active(user.ctx, uid.value, False))
                with ui.column().classes("cl-card gap-2 w-full"):
                    section_title(tr(c, "ad.reset_no_email"))

                    def issue() -> None:
                        try:
                            r = c.admin.issue_password_reset(user.ctx, uid.value)
                        except (CivicLensError, ValueError) as exc:
                            ui.notify(getattr(exc, "message", str(exc)), type="negative")
                            return
                        with ui.dialog() as dlg, ui.column().classes("cl-card gap-2 w-full max-w-md"):
                            ui.label(tr(c, "ad.reset_link_once")).classes("text-base font-semibold").style("color: var(--cl-fg);")
                            ui.label(f"{c.public_base_url.rstrip('/')}/reset-password?token={r['token']}").classes("cl-mono text-xs break-all cl-surface-alt q-pa-sm")
                            ui.label(r["note"]).classes("text-xs").style("color: var(--cl-fg-subtle);")
                            ui.button(tr(c, "act.close"), on_click=dlg.close).props("outline")
                        dlg.open()

                    ui.button(tr(c, "ad.issue_reset_link"), icon="key", on_click=issue).props("outline dense")

    @page(c, "/admin/departments", "nav.departments", roles=ADMINS)
    def departments(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.departments"), icon="apartment")
        ref = c.admin.reference_data(user.ctx)
        data_table([("code", tr(c, "col.code")), ("name", tr(c, "col.name")), ("active", tr(c, "filter.active"))], [{"id": d.code, "code": d.code, "name": d.name, "active": d.active} for d in ref["departments"]])
        with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
            code, name, active = ui.input(tr(c, "col.code")).props("outlined dense"), ui.input(tr(c, "col.name")).props("outlined dense"), ui.switch("Active", value=True).props("color=primary")
            ui.button(tr(c, "act.save"), icon="check", on_click=_act(c, lambda: c.admin.save_department(user.ctx, code.value or "", name.value or "", bool(active.value)))).props("color=primary unelevated")

    @page(c, "/admin/wards", "nav.wards", roles=ADMINS)
    def wards(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.wards"), icon="location_city")
        ref = c.admin.reference_data(user.ctx)
        section_title(tr(c, "col.cities"))
        data_table([("code", tr(c, "col.code")), ("name", tr(c, "col.name")), ("state", tr(c, "col.state")), ("lat", "Lat"), ("lng", "Lng")], [{"id": x.code, "code": x.code, "name": x.name, "state": x.state or "-", "lat": x.lat, "lng": x.lng} for x in ref["cities"]], empty=tr(c, "ad.no_cities"))
        with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
            cc, cn, cs, cla, cln = ui.input(tr(c, "ad.city_code")).props("outlined dense"), ui.input(tr(c, "col.name")).props("outlined dense"), ui.input(tr(c, "col.state")).props("outlined dense"), ui.number(tr(c, "col.lat")).props("outlined dense"), ui.number(tr(c, "col.lng")).props("outlined dense")
            ui.button(tr(c, "ad.save_city"), icon="check", on_click=_act(c, lambda: c.admin.save_city(user.ctx, cc.value or "", cn.value or "", cs.value, cla.value, cln.value))).props("color=primary unelevated")
        section_title(tr(c, "col.wards"))
        data_table([("code", tr(c, "col.code")), ("name", tr(c, "col.name")), ("city", tr(c, "col.city"))], [{"id": x.code, "code": x.code, "name": x.name, "city": x.city_code or "-"} for x in ref["wards"]], empty=tr(c, "ad.no_wards"))
        with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
            wc, wn, wcity = ui.input(tr(c, "ad.ward_code")).props("outlined dense"), ui.input(tr(c, "col.name")).props("outlined dense"), ui.select([x.code for x in ref["cities"]], label=tr(c, "col.city")).props("outlined dense")
            ui.button(tr(c, "ad.save_ward"), icon="check", on_click=_act(c, lambda: c.admin.save_ward(user.ctx, wc.value or "", wn.value or "", wcity.value))).props("color=primary unelevated")

    @page(c, "/admin/services", "nav.civic_services", roles=ADMINS)
    def services(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.civic_services"), icon="miscellaneous_services")
        ref = c.admin.reference_data(user.ctx)
        section_title(tr(c, "ad.civic_services"))
        data_table([("code", tr(c, "col.code")), ("name", tr(c, "col.name")), ("dept", tr(c, "lbl.department"))], [{"id": x.code, "code": x.code, "name": x.name, "dept": x.department_code} for x in ref["services"]], empty=tr(c, "ad.no_services"))
        with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
            sc, sn, sd = ui.input(tr(c, "col.code")).props("outlined dense"), ui.input(tr(c, "col.name")).props("outlined dense"), ui.select([d.code for d in ref["departments"]], label=tr(c, "lbl.department")).props("outlined dense")
            ui.button(tr(c, "act.save"), icon="check", on_click=_act(c, lambda: c.admin.save_service(user.ctx, sc.value or "", sn.value or "", sd.value))).props("color=primary unelevated")
        section_title(tr(c, "ad.gov_offices"), tr(c, "ad.gov_offices_sub"))
        data_table([("name", tr(c, "col.name")), ("dept", tr(c, "lbl.department")), ("city", tr(c, "col.city")), ("lat", tr(c, "col.lat")), ("lng", tr(c, "col.lng"))], [{"id": x.id, "name": x.name, "dept": x.department_code or "-", "city": x.city_code or "-", "lat": x.lat, "lng": x.lng} for x in ref["offices"]], empty=tr(c, "ad.no_offices"))
        with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
            oi, on, od, ola, oln, oa = ui.input("Id").props("outlined dense"), ui.input(tr(c, "col.name")).props("outlined dense"), ui.select([d.code for d in ref["departments"]], label=tr(c, "lbl.department")).props("outlined dense"), ui.number(tr(c, "col.lat")).props("outlined dense"), ui.number(tr(c, "col.lng")).props("outlined dense"), ui.input(tr(c, "lbl.address")).props("outlined dense")
            oc = ui.select([x.code for x in ref["cities"]], label=tr(c, "col.city")).props("outlined dense")
            ui.button(tr(c, "ad.save_office"), icon="check", on_click=_act(c, lambda: c.admin.save_office(user.ctx, oi.value or "", on.value or "", od.value, ola.value, oln.value, oa.value, oc.value))).props("color=primary unelevated")

    @page(c, "/admin/routing-rules", "nav.routing", roles=ADMINS)
    def routing(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.routing"), icon="alt_route")
        ref = c.admin.reference_data(user.ctx)
        info_banner(tr(c, "ad.routing_note"))
        data_table([("id", tr(c, "col.rule")), ("prio", tr(c, "lbl.priority")), ("dept", tr(c, "lbl.department")), ("cats", tr(c, "col.categories")), ("kw", tr(c, "col.keywords")), ("active", tr(c, "filter.active"))],
                   [{"id": r.id, "prio": r.priority, "dept": {d.code: d.name for d in ref["departments"]}.get(r.department_code, r.department_code), "cats": ", ".join(sorted(r.categories)) or "-", "kw": ", ".join(r.keywords_any) or "-", "active": r.active}
                    for r in ref["routing_rules"]], empty=tr(c, "ad.no_routing_rules"))  # fmt: skip
        with ui.column().classes("cl-card gap-3 w-full"):
            with ui.row().classes("gap-3 items-end flex-wrap"):
                rid, prio = ui.input(tr(c, "ad.rule_id")).props("outlined dense"), ui.number(tr(c, "lbl.priority"), value=100, format="%d").props("outlined dense")
                dept = ui.select([d.code for d in ref["departments"] if d.active], label=tr(c, "lbl.department")).props("outlined dense")
                sev = ui.select([""] + list(SEVERITIES), value="", label=tr(c, "ad.min_severity")).props("outlined dense")
            cats = ui.select(list(CATEGORIES), multiple=True, label=tr(c, "col.categories")).props("outlined dense").classes("w-full")
            kws = ui.input(tr(c, "ad.keywords")).props("outlined dense").classes("w-full")
            ui.button(tr(c, "act.save"), icon="check", on_click=_act(c, lambda: c.admin.save_routing_rule(user.ctx, rid.value or "", int(prio.value), dept.value or "", categories=list(cats.value or []), keywords_any=[k for k in (kws.value or "").split(",") if k.strip()], min_severity=sev.value or None))).props("color=primary unelevated")
        with ui.row().classes("gap-3 items-end"):
            delete = ui.select([r.id for r in ref["routing_rules"]], label=tr(c, "ad.delete_rule")).props("outlined dense").classes("w-56")
            _danger_action(c, tr(c, "act.delete"), lambda: c.admin.delete_routing_rule(user.ctx, delete.value))

    @page(c, "/admin/workflow-rules", "nav.workflow", roles=ADMINS)
    def workflow_rules(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.workflow"), icon="account_tree")
        ov = c.admin.workflow_overview(user.ctx)
        info_banner(tr(c, "ad.workflow_note"))
        existing = {r.id for r in ov["rules"]}
        todo = [t for t in WORKFLOW_TEMPLATES if t[0] not in existing]
        if todo:
            with ui.column().classes("cl-card gap-2 w-full"):
                section_title("Quick start templates", "Each adds one ready-made rule; edit or delete it afterwards.")
                with ui.row().classes("gap-2 flex-wrap"):
                    for tpl in todo:
                        ui.button(tpl[1], icon="add", on_click=_act(c, lambda a=tpl: c.admin.save_workflow_rule(user.ctx, a[0], a[1], a[2], a[3], conditions=a[4], params=a[5]))).props("outline dense no-caps")
        data_table([("name", tr(c, "col.name")), ("rule", "What it does"), ("active", tr(c, "filter.active"))],
                   [{"id": r.id, "name": r.name, "rule": f"{TRIGGER_WORDS.get(r.trigger, r.trigger)} ({_conditions(r.conditions)}), {ACTION_WORDS.get(r.action, r.action)}.", "active": r.active} for r in ov["rules"]],
                   empty=tr(c, "ad.no_workflow_rules"))  # fmt: skip
        with ui.column().classes("cl-card gap-3 w-full"):
            with ui.row().classes("gap-3 items-end flex-wrap"):
                rid, name = ui.input(tr(c, "ad.rule_id")).props("outlined dense"), ui.input(tr(c, "col.name")).props("outlined dense")
                trig, act = ui.select(list(WF_TRIGGERS), value=WF_TRIGGERS[0], label=tr(c, "col.trigger")).props("outlined dense"), ui.select(list(WF_ACTIONS), value=WF_ACTIONS[0], label=tr(c, "col.action")).props("outlined dense")
            cond = ui.textarea(tr(c, "ad.conditions_json"), value='{"priority_min": "critical"}').props("outlined").classes("w-full")
            params = ui.textarea(tr(c, "ad.params_json"), value="{}").props("outlined").classes("w-full")

            def save_wf() -> None:
                try:
                    conditions = json.loads(cond.value or "{}")
                    parsed_params = json.loads(params.value or "{}")
                except json.JSONDecodeError as exc:
                    ui.notify(f"Invalid JSON: {exc.msg} (line {exc.lineno}, col {exc.colno}).", type="negative")
                    return
                _act(c, lambda: c.admin.save_workflow_rule(user.ctx, rid.value or "", name.value or "", trig.value, act.value, conditions=conditions, params=parsed_params))()

            ui.button(tr(c, "act.save"), icon="check", on_click=save_wf).props("color=primary unelevated")
        with ui.row().classes("gap-3 items-end"):
            dele = ui.select([r.id for r in ov["rules"]], label=tr(c, "ad.delete_rule")).props("outlined dense").classes("w-56")
            _danger_action(c, tr(c, "act.delete"), lambda: c.admin.delete_workflow_rule(user.ctx, dele.value))
        section_title(tr(c, "ad.recent_executions"))
        refs = run_in_uow(c, lambda uow: {e.complaint_id: (x.reference if (x := uow.complaints.get(e.complaint_id)) else e.complaint_id[:8]) for e in ov["executions"]})
        data_table([("when", tr(c, "legal.col_when")), ("rule", tr(c, "col.rule")), ("complaint", tr(c, "col.complaint")), ("action", tr(c, "col.action"))], [{"id": str(i), "when": e.executed_at.strftime("%d %b %H:%M"), "rule": {r.id: r.name for r in ov["rules"]}.get(e.rule_id, e.rule_id), "complaint": refs.get(e.complaint_id, e.complaint_id[:8]), "action": ACTION_WORDS.get(e.outcome, e.outcome.replace("_", " "))} for i, e in enumerate(ov["executions"])], empty=tr(c, "ad.no_rule_runs"))

    @page(c, "/admin/emergency", "nav.emergency_admin", roles=ADMINS)
    def emergency_admin(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.emergency_admin"), icon="emergency")
        items = c.admin.emergency_contacts(user.ctx)
        if not items:
            state_panel(icon="support_agent", title=tr(c, "em.none_title"), body=tr(c, "ad.em_empty_body"),
                        action_label=tr(c, "ad.em_seed"), on_action=_act(c, lambda: c.emergency.seed_defaults()))
        else:
            data_table([("id", "Id"), ("number", tr(c, "col.number")), ("name", tr(c, "col.name")), ("scope", tr(c, "col.scope")), ("active", tr(c, "filter.active"))], [{"id": x.id, "number": x.number, "name": x.name, "scope": x.scope, "active": x.active} for x in items])
        with ui.column().classes("cl-card gap-3 w-full"):
            with ui.row().classes("gap-3 items-end flex-wrap"):
                cid, num, nm = ui.input("Id").props("outlined dense"), ui.input(tr(c, "col.number")).props("outlined dense"), ui.input(tr(c, "col.name")).props("outlined dense")
                scope = ui.select(["national", "city"], value="national", label=tr(c, "col.scope")).props("outlined dense")
                city = ui.select([x.code for x in c.admin.reference_data(user.ctx)["cities"]], label=tr(c, "ad.city_scope")).props("outlined dense")
            desc = ui.input(tr(c, "lbl.description")).props("outlined dense").classes("w-full")
            ui.button(tr(c, "act.save"), icon="check", on_click=_act(c, lambda: c.admin.save_emergency_contact(user.ctx, cid.value or "", num.value or "", nm.value or "", description=desc.value or "", scope=scope.value, city_code=city.value))).props("color=primary unelevated")
        if items:
            with ui.row().classes("gap-3 items-end"):
                dele = ui.select([x.id for x in items], label=tr(c, "ad.delete_contact")).props("outlined dense").classes("w-56")
                _danger_action(c, tr(c, "act.delete"), lambda: c.admin.delete_emergency_contact(user.ctx, dele.value))

    @page(c, "/admin/sla", "nav.sla", roles=ADMINS)
    def sla(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.sla"), icon="timer")
        ref = c.admin.reference_data(user.ctx)
        info_banner(tr(c, "ad.sla_note"), "orange")
        if not ref["sla_policies"]:
            def apply_suggested() -> None:
                for pid, prio, hrs, gap in SUGGESTED_SLA:
                    c.admin.save_sla_policy(user.ctx, pid, prio, hrs, escalation_gap_hours=gap)

            with ui.column().classes("cl-card gap-2 w-full"):
                section_title("Start from a suggested policy", "Critical 24 h · High 3 days · Medium 7 days · Low 21 days (the CPGRAMS ceiling). Apply, then edit any row to match your citizen charter.")
                ui.button("Apply suggested policies", icon="auto_fix_high", on_click=_act(c, apply_suggested)).props("color=primary unelevated")
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        data_table([("prio", tr(c, "lbl.priority")), ("dept", tr(c, "lbl.department")), ("hours", "Resolve within"), ("gap", "Escalate again every"), ("max", tr(c, "col.max_level")), ("id", tr(c, "col.policy"))],
                   [{"id": p.id, "prio": p.priority.capitalize(), "dept": p.department_code or "All departments", "hours": _duration(p.resolution_hours), "gap": _duration(p.escalation_gap_hours), "max": f"up to level {p.max_level}"}
                    for p in sorted(ref["sla_policies"], key=lambda x: (order.get(x.priority, 9), x.department_code or ""))], empty=tr(c, "ad.no_sla"))  # fmt: skip
        with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
            pid, prio, hours = ui.input(tr(c, "ad.policy_id")).props("outlined dense"), ui.select(["low", "medium", "high", "critical"], label=tr(c, "lbl.priority")).props("outlined dense"), ui.number(tr(c, "ad.resolution_hours"), value=72, format="%d").props("outlined dense")
            dept = ui.select([""] + [d.code for d in ref["departments"]], value="", label=tr(c, "lbl.department")).props("outlined dense")
            ui.button(tr(c, "act.save"), icon="check", on_click=_act(c, lambda: c.admin.save_sla_policy(user.ctx, pid.value or "", prio.value or "", int(hours.value), department_code=dept.value or None))).props("color=primary unelevated")
        with ui.row().classes("gap-3 items-end"):
            d = ui.select([p.id for p in ref["sla_policies"]], label=tr(c, "ad.delete_policy")).props("outlined dense").classes("w-56")
            _danger_action(c, tr(c, "act.delete"), lambda: c.admin.delete_sla_policy(user.ctx, d.value))

    @page(c, "/admin/integrations", "nav.integrations", roles=ADMINS)
    def integrations(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.integrations"), icon="hub")
        info_banner(tr(c, "ad.integration_note"))
        rows = []
        for a in c.adapters.values():
            h = a.health_snapshot("missing: " + ", ".join(a.config.missing()) if not a.is_configured() else "not probed since start")
            rows.append({"id": a.platform, "name": a.display_name, "state": h.state.value, "detail": h.detail, "last_ok": h.last_success_at.strftime("%d %b %H:%M") if h.last_success_at else "-", "err": h.last_error or "-", "avg": f"{h.avg_response_ms:.0f} ms" if h.avg_response_ms else "-"})
        data_table([("name", tr(c, "col.platform")), ("state", tr(c, "col.state")), ("detail", tr(c, "col.detail")), ("last_ok", tr(c, "col.last_success")), ("err", tr(c, "col.last_error")), ("avg", tr(c, "col.avg_response"))], rows)

        def check() -> None:
            if c.health is None:
                raise CivicLensError("Integration health persistence is not configured.")
            c.health.check_all(c.adapters)

        ui.button(tr(c, "ad.run_health"), icon="health_and_safety", on_click=_act(c, check)).props("color=primary unelevated")

    @page(c, "/admin/audit", "nav.audit", roles=ADMINS)
    def audit(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.audit"), icon="fact_check")
        with ui.row().classes("gap-2 items-center w-full"):
            prefix = ui.input(tr(c, "ad.action_prefix")).props("outlined dense").classes("w-72")
            ui.button(icon="search", on_click=lambda: draw()).props("round unelevated color=primary")
        box = ui.column().classes("w-full")

        def draw() -> None:
            box.clear()
            with box:
                ev = c.admin.audit_log(user.ctx, action_prefix=prefix.value or None, limit=200)
                names = {u.id: u.full_name or u.email for u in c.admin.list_users(user.ctx, limit=1000)}

                def details(meta: Any) -> str:
                    # readable "key: value" pairs; empty values dropped, so no raw dicts or 'None' reach the table
                    if not isinstance(meta, dict):
                        return str(meta or "")[:140]
                    return " · ".join(f"{k.replace('_', ' ')}: {v}" for k, v in meta.items() if v not in (None, "", [], {}))[:140]

                data_table([("at", tr(c, "legal.col_when")), ("action", tr(c, "col.action")), ("actor", tr(c, "col.actor")), ("res", tr(c, "col.resource")), ("meta", tr(c, "col.details"))],
                           [{"id": str(i), "at": e.occurred_at.strftime("%d %b %Y %H:%M:%S"), "action": e.action, "actor": names.get(e.actor_id or "", (e.actor_id or "system")[:8]),
                             "res": f"{(e.resource_type or '').replace('_', ' ')} {(e.resource_id or '')[:8]}".strip(), "meta": details(e.metadata)} for i, e in enumerate(ev)])  # fmt: skip

        prefix.on("keydown.enter", draw)
        draw()

    @page(c, "/admin/analytics", "nav.analytics", roles=ADMINS)
    def analytics(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.analytics"), icon="insights")
        d = c.dashboards.admin(user.ctx)
        if not d["has_data"]:
            state_panel(icon="insights", title=tr(c, "msg.no_data"))
            return
        from app.services.analytics_service import InsufficientData, forecast_linear

        axis = {"axisLabel": {"color": "#9aa3b8"}, "axisLine": {"lineStyle": {"color": "#2a3148"}}, "splitLine": {"lineStyle": {"color": "#1f2538"}}}
        palette = ["#6c7cff", "#22c3a6", "#f5a524", "#ef4f5f", "#a78bfa", "#38bdf8", "#84cc16", "#f472b6"]
        names = run_in_uow(c, lambda uow: {"dept": {x.code: x.name for x in uow.config.departments()}, "ward": {w.code: w.name for w in uow.config.wards()}})

        def bars(counts: dict[str, int], labels: dict[str, str]) -> dict[str, Any]:
            items = sorted(counts.items(), key=lambda kv: -kv[1])
            # horizontal bars: long names stay readable instead of being clipped by a rotated axis
            return {"tooltip": {}, "grid": {"left": 8, "right": 24, "top": 8, "bottom": 8, "containLabel": True},
                    "xAxis": {"type": "value", **axis}, "yAxis": {"type": "category", "inverse": True, "data": [labels.get(k, k).replace(" Department", "") for k, _ in items], **axis},
                    "series": [{"type": "bar", "barMaxWidth": 18, "itemStyle": {"borderRadius": [0, 6, 6, 0]},
                                "data": [{"value": v, "itemStyle": {"color": palette[i % len(palette)]}} for i, (_, v) in enumerate(items)]}]}  # fmt: skip

        with ui.row().classes("gap-4 w-full flex-wrap"):
            with ui.column().classes("cl-card").style("flex: 1; min-width: 320px;"):
                section_title(tr(c, "ad.by_department"))
                ui.echart(bars(d["by_department"], names["dept"])).classes("w-full h-64")
            with ui.column().classes("cl-card").style("flex: 1; min-width: 320px;"):
                section_title(tr(c, "ad.by_ward"))
                ui.echart(bars({k: v for k, v in d["by_ward"].items() if k}, names["ward"])).classes("w-full h-64")
        f = forecast_linear([t["count"] for t in d["trend_daily"]], 7)
        with ui.column().classes("cl-card w-full"):
            section_title(tr(c, "ad.trend_30d"), "Solid: complaints filed per day. Dashed: a 7-day linear projection - an estimate, not a fact.")
            days = [t["date"][5:] for t in d["trend_daily"]]
            actual = [t["count"] for t in d["trend_daily"]]
            series: list[dict[str, Any]] = [{"name": "Filed", "type": "line", "smooth": True, "areaStyle": {"opacity": 0.25}, "color": "#6c7cff", "data": actual + [None] * 7}]
            if not isinstance(f, InsufficientData):
                series.append({"name": "Projection", "type": "line", "smooth": True, "color": "#a78bfa", "lineStyle": {"type": "dashed"}, "data": [None] * (len(actual) - 1) + [actual[-1]] + [round(v, 1) for v in f.values]})
            ui.echart({"tooltip": {"trigger": "axis"}, "legend": {"textStyle": {"color": "#c7cde0"}}, "grid": {"left": 36, "right": 16, "top": 36, "bottom": 28},
                       "xAxis": {"type": "category", "data": days + [f"+{i}d" for i in range(1, 8)], **axis}, "yAxis": {"type": "value", **axis}, "series": series}).classes("w-full h-64")  # fmt: skip
            if isinstance(f, InsufficientData):
                ui.label(f"Projection: not enough history yet ({f.have}/{f.needed} days).").classes("text-xs").style("color: var(--cl-fg-subtle);")
        with ui.row().classes("gap-2 flex-wrap"):
            chip(f"Backlog: {d['backlog']}", color="muted", outline=True)
            chip(f"Escalated: {d['escalated']}", color="danger", outline=True)
            chip(f"SLA breached: {d['sla'].get('breached', 0)}", color="warning", outline=True)
        section_title(tr(c, "ad.snapshot_history"))
        hist = c.dashboards.history(user.ctx, days=30)
        if not hist["has_data"]:
            state_panel(icon="history", title=tr(c, "ad.no_snapshots"), body=tr(c, "ad.no_snapshots_body"))
        else:
            xs = [p["taken_at"].strftime("%d %b %H:%M") for p in hist["points"]]
            with ui.column().classes("cl-card w-full"):
                ui.echart({"tooltip": {"trigger": "axis"}, "legend": {"textStyle": {"color": "#c7cde0"}}, "grid": {"left": 40, "right": 12, "top": 36, "bottom": 28},
                           "xAxis": {"type": "category", "data": xs, **axis}, "yAxis": {"type": "value", **axis},
                           "series": [{"name": k.replace("_", " ").capitalize(), "type": "line", "smooth": True, "showSymbol": False, "color": col, "data": [p[k] for p in hist["points"]]}
                                      for k, col in (("open", "#6c7cff"), ("breached", "#ef4f5f"), ("at_risk", "#f5a524"), ("backlog", "#22c3a6"))]}).classes("w-full h-64")  # fmt: skip
        ui.button(tr(c, "ad.run_anomaly"), icon="troubleshoot", on_click=_act(c, lambda: c.anomaly_job.run(c.clock()))).props("outline")

    @page(c, "/admin/anomalies", "nav.anomalies", roles=ADMINS)
    def anomalies(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.anomalies"), icon="warning")
        items = c.admin.anomalies(user.ctx, status=None)
        data_table([("at", tr(c, "col.detected")), ("kind", tr(c, "col.kind")), ("subject", tr(c, "col.subject")), ("sev", tr(c, "lbl.severity")), ("status", tr(c, "lbl.status")), ("why", tr(c, "col.explanation"))],
                   [{"id": a.id, "at": a.detected_at.strftime("%d %b %H:%M"), "kind": a.kind, "subject": a.subject, "sev": a.severity, "status": a.status, "why": a.explanation} for a in items], empty=tr(c, "ad.no_anomalies"))
        with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
            sel = ui.select({a.id: f"{a.kind}: {a.subject}" for a in items if a.status == "open"}, label=tr(c, "ad.open_anomaly")).props("outlined dense").classes("w-96")
            ui.button(tr(c, "act.acknowledge"), icon="visibility", on_click=_act(c, lambda: c.admin.set_anomaly_status(user.ctx, sel.value, "acknowledged"))).props("outline dense")
            ui.button(tr(c, "col.resolve"), icon="check", on_click=_act(c, lambda: c.admin.set_anomaly_status(user.ctx, sel.value, "resolved"))).props("outline dense")
            ui.button(tr(c, "act.investigate"), icon="search", on_click=_act(c, lambda: c.investigations.open(user.ctx, "anomaly", sel.value))).props("outline dense")

    @page(c, "/admin/investigations", "nav.investigations", roles=ADMINS)
    def admin_investigations(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.investigations"), icon="policy")
        items = c.investigations.list(user.ctx)
        from app.ui.pages.staff import investigation_subjects

        subjects = investigation_subjects(c, items)
        data_table([("subject", tr(c, "col.subject")), ("status", tr(c, "lbl.status")), ("dept", tr(c, "lbl.department"))], [{"id": i.id, "subject": subjects[i.id], "status": i.status, "dept": i.department_code or "-"} for i in items],
                   on_row=lambda r: ui.navigate.to(f"/officer/investigations/{r['id']}"), empty=tr(c, "of.no_investigations"))

    @page(c, "/admin/triage", "nav.triage", roles=ADMINS)
    def triage(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.triage"), icon="call_split")
        ref = c.admin.reference_data(user.ctx)
        items = run_in_uow(c, lambda uow: uow.complaints.list_unrouted())
        if not items:
            state_panel(icon="task_alt", title=tr(c, "ad.nothing_manual_routing"))
            return
        depts = [d.code for d in ref["departments"] if d.active]
        with ui.column().classes("gap-3 w-full"):
            for cm in items:
                with ui.row().classes("cl-card w-full items-end justify-between gap-3 flex-wrap"):
                    with ui.column().classes("gap-1"):
                        ui.label(f"{cm.reference} - {cm.title}").classes("text-sm font-semibold").style("color: var(--cl-fg);")
                        ui.label(cm.routing.get("explanation", "")).classes("text-xs").style("color: var(--cl-fg-muted);")
                    with ui.row().classes("gap-2 items-end"):
                        sel = ui.select(depts, label=tr(c, "lbl.department")).props("outlined dense").classes("w-56")
                        ui.button(tr(c, "act.route"), icon="alt_route", on_click=_act(c, lambda cid=cm.id, s=sel: c.officer.triage(user.ctx, cid, s.value))).props("color=primary unelevated")

    @page(c, "/admin/monitoring", "nav.monitoring", roles=ADMINS)
    def monitoring(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.monitoring"), icon="monitor_heart")
        s = c.system_status()
        q = s["queue"]
        section_title(tr(c, "ad.queue_workers"))
        with ui.column().classes("cl-card w-full gap-2"):
            _status_rows(s)
            ui.label(f"Queue depth right now: {q['backend_depth']}").classes("text-xs").style("color: var(--cl-fg-subtle);")
        data_table([("id", tr(c, "col.worker")), ("seen", tr(c, "col.last_seen"))], [{"id": k, "seen": v.get("last_seen", "-")} for k, v in q["workers"].items()], empty=tr(c, "ad.no_heartbeats"))
        section_title(tr(c, "ad.recent_jobs"), "queued -> running -> succeeded | retrying -> dead")
        jobs = run_in_uow(c, lambda uow: uow.jobs.list_recent(30))
        data_table([("kind", tr(c, "col.kind")), ("status", tr(c, "lbl.status")), ("att", tr(c, "col.attempts")), ("started", tr(c, "col.started")), ("finished", tr(c, "col.finished")), ("err", tr(c, "col.error"))],
                   [{"id": j.id, "kind": j.kind, "status": j.status, "att": j.attempts, "started": j.started_at.strftime("%H:%M:%S") if j.started_at else "-", "finished": j.finished_at.strftime("%H:%M:%S") if j.finished_at else "-", "err": j.error or ""} for j in jobs], empty=tr(c, "ad.no_jobs"))
        if any(j.status == "dead" for j in jobs):
            with ui.row().classes("gap-3 items-end"):
                dead = ui.select({j.id: f"{j.kind} - {j.error or ''}"[:80] for j in jobs if j.status == "dead"}, label=tr(c, "ad.dead_job")).props("outlined dense").classes("w-96")
                ui.button(tr(c, "ad.retry_dead_job"), icon="replay", on_click=_act(c, lambda: c.jobs.retry_dead(dead.value))).props("outline dense")
        section_title(tr(c, "ad.notification_delivery"))
        counts = run_in_uow(c, lambda uow: uow.notifications.status_counts())
        data_table([("channel", tr(c, "col.channel")), ("states", "queued / sending / delivered / failed / not_configured")], [{"id": ch, "channel": ch, "states": ", ".join(f"{k}: {v}" for k, v in sorted(st.items()))} for ch, st in counts.items()], empty=tr(c, "ad.no_notifications"))
        with ui.row().classes("gap-2 flex-wrap"):
            chip(f"E-mail sender: {'configured' if c.mailer else 'NOT configured'}", color="success" if c.mailer else "muted")
            chip(f"Push (Expo): {'enabled' if c.push_sender else 'NOT enabled'}", color="success" if c.push_sender else "muted")
        gov = run_in_uow(c, lambda uow: uow.government.counts_by_state())
        ui.label("Government submissions: " + (", ".join(f"{k}: {v}" for k, v in sorted(gov.items())) or "none yet")).classes("text-xs").style("color: var(--cl-fg-muted);")
        ui.label("Translation coverage (extras): " + str(c.ui_text.extras_coverage())).classes("text-xs").style("color: var(--cl-fg-subtle);")

    @page(c, "/admin/exceptions", "nav.exceptions", roles=ADMINS)
    def exceptions(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.exceptions"), tr(c, "ad.exceptions_note"), icon="report_problem")
        counts = c.exceptions.counts(user.ctx)
        with ui.row().classes("gap-3 flex-wrap"):
            stat_tile(tr(c, "card.open"), counts.get("open", 0), color="danger", icon="report_problem")
            stat_tile(tr(c, "card.resolved"), counts.get("resolved", 0), color="success", icon="check_circle")
            stat_tile(tr(c, "col.ignored"), counts.get("ignored", 0), color="muted", icon="visibility_off")

        status_filter = ui.select({"": "All", "open": tr(c, "card.open"), "resolved": tr(c, "card.resolved"), "ignored": tr(c, "col.ignored")}, value="open", label=tr(c, "lbl.status")).props("outlined dense").classes("w-48")
        box = ui.column().classes("gap-2 w-full")

        def draw() -> None:
            box.clear()
            items = c.exceptions.list(user.ctx, status=status_filter.value or None)
            with box:
                if not items:
                    state_panel(icon="task_alt", title=tr(c, "ad.nothing_here"), body=tr(c, "ad.no_exceptions_filter"))
                for ex in items:
                    with ui.column().classes("cl-card gap-2 w-full"):
                        with ui.row().classes("items-center justify-between w-full flex-wrap"):
                            chip(ex.source_system, color="info", outline=True)
                            chip(ex.status, color={"open": "danger", "resolved": "success", "ignored": "muted"}.get(ex.status, "muted"))
                        ui.label(ex.reason).classes("text-sm").style("color: var(--cl-fg);")
                        ui.label(ex.detected_at.strftime("%d %b %Y %H:%M")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                        with ui.expansion(tr(c, "interop.raw_payload")).classes("w-full"):
                            import json as _json

                            ui.markdown(f"```json\n{_json.dumps(ex.payload, indent=2, ensure_ascii=False)}\n```").classes("cl-mono text-xs")
                        if ex.resolution_note:
                            ui.label(f"Resolution: {ex.resolution_note}").classes("text-xs").style("color: var(--cl-success);")
                        if ex.status == "open":
                            note = ui.input(tr(c, "ad.resolution_note")).props("outlined dense").classes("w-full max-w-md")
                            with ui.row().classes("gap-2"):
                                ui.button(tr(c, "col.resolve"), icon="check", on_click=_act(c, lambda i=ex.id, n=note: c.exceptions.resolve(user.ctx, i, note=n.value or "", ignore=False))).props("outline dense")
                                ui.button(tr(c, "act.ignore"), icon="visibility_off", on_click=_act(c, lambda i=ex.id, n=note: c.exceptions.resolve(user.ctx, i, note=n.value or "", ignore=True))).props("flat dense")

        status_filter.on_value_change(lambda e: draw())
        draw()

        section_title(tr(c, "ad.learned_corrections"), tr(c, "ad.corrections_note"))
        corrections = c.classification_corrections.recent(user.ctx)
        data_table([("when", tr(c, "legal.col_when")), ("from", "Was"), ("to", tr(c, "col.corrected_to")), ("text", tr(c, "col.complaint_text"))],
                   [{"id": r.id, "when": r.corrected_at.strftime("%d %b %Y %H:%M"), "from": r.previous_category, "to": r.corrected_category, "text": r.text_snapshot[:100]} for r in corrections],
                   empty=tr(c, "ad.no_corrections"))

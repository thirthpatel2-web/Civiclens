"""Administration pages. Every table renders persisted data; every form calls AdminService (which authorises and audits)."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from app.container import AppContainer
from app.core.authorization import Role
from app.core.transactions import run_in_uow
from app.core.exceptions import CivicLensError
import json

from app.services.classification_service import CATEGORIES, SEVERITIES
from app.services.workflow_service import ACTIONS as WF_ACTIONS
from app.services.workflow_service import TRIGGERS as WF_TRIGGERS
from app.ui.base import UiUser, data_table, info_banner, page, tr
from app.ui.components import chip, confirm_dialog, page_header, section_title, state_panel, stat_tile
from app.ui.navigation import ADMINS


def _act(fn: Any) -> Any:
    def run(*a: Any) -> None:
        try:
            fn(*a)
        except (CivicLensError, ValueError) as exc:
            ui.notify(getattr(exc, "message", str(exc)) + (f" {exc.details}" if getattr(exc, "details", None) else ""), type="negative")
            return
        ui.notify("Saved.", type="positive")
        ui.navigate.reload()

    return run


def _danger_action(label: str, on_click: Any) -> None:
    """A destructive action that must be confirmed before it runs - deletes/deactivations were one click away before."""
    open_dialog = confirm_dialog(label, "This cannot be undone. Are you sure?", confirm_label=label, danger=True, on_confirm=_act(on_click))
    ui.button(label, icon="delete_outline", on_click=open_dialog).props("outline dense color=negative")


def register(c: AppContainer) -> None:
    @page(c, "/admin", "nav.admin_overview", roles=ADMINS)
    def overview(c: AppContainer, user: UiUser) -> None:
        d = c.dashboards.admin(user.ctx)
        page_header(tr(c, "nav.admin_overview"), icon="admin_panel_settings")
        with ui.row().classes("gap-3 w-full flex-wrap"):
            stat_tile("Total complaints", d["total"], color="primary", icon="assignment")
            stat_tile(tr(c, "card.open"), d["open"], color="info", icon="pending_actions")
            stat_tile(tr(c, "card.overdue"), d["sla"]["breached"], color="danger", icon="report")
            stat_tile(tr(c, "card.at_risk"), d["sla"]["at_risk"], color="warning", icon="schedule")
            stat_tile(tr(c, "card.escalated"), d["escalated"], color="danger", icon="trending_up")
            stat_tile("Unrouted", d["unrouted"], color="muted", icon="alt_route")
        if d["resolution_hours"]:
            with ui.row().classes("cl-card w-full items-center gap-2"):
                ui.icon("timer").style("color: var(--cl-fg-muted);")
                ui.label(f"Resolution time: median {d['resolution_hours']['median']} h over {d['resolution_hours']['count']} resolved complaints.").classes("text-sm").style("color: var(--cl-fg-muted);")
        with ui.row().classes("gap-4 w-full flex-wrap"):
            with ui.column().classes("cl-card gap-2").style("flex: 1; min-width: 300px;"):
                section_title("Routing accuracy indicator", "How complaints were routed.")
                with ui.row().classes("gap-2 flex-wrap"):
                    if d["routing_sources"]:
                        for k, v in d["routing_sources"].items():
                            chip(f"{k}: {v}", color="info", outline=True)
                    else:
                        ui.label(tr(c, "msg.no_data")).classes("text-sm").style("color: var(--cl-fg-subtle);")
            with ui.column().classes("cl-card gap-2").style("flex: 1; min-width: 300px;"):
                s = d["system"] or {}
                section_title("System")
                q = s.get("queue", {})
                ui.label(f"Queue: {'reachable' if q.get('backend_reachable') else 'NOT reachable / not configured'} · jobs {q.get('by_status')}").classes("text-xs").style("color: var(--cl-fg-muted);")
                ui.label(f"Workers: {list((q.get('workers') or {}).keys())}").classes("text-xs").style("color: var(--cl-fg-muted);")
                ui.label(f"RAG: {s.get('rag')} · Ollama: {s.get('ollama')} · WebSocket connections: {s.get('websocket_connections')}").classes("text-xs").style("color: var(--cl-fg-muted);")
                ui.label("Integrations: " + ", ".join(f"{k}={v}" for k, v in (s.get("adapters") or {}).items())).classes("text-xs").style("color: var(--cl-fg-muted);")
        section_title("Recent audit activity")
        data_table([("at", "When"), ("action", "Action"), ("actor", "Actor")], [{"id": str(i), "at": e.occurred_at.strftime("%d %b %H:%M"), "action": e.action, "actor": (e.actor_id or "system")[:8]} for i, e in enumerate(d["recent_audit"])])
        if not d["has_data"]:
            info_banner(tr(c, "msg.no_data"))

    @page(c, "/admin/users", "nav.users", roles=ADMINS)
    def users(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.users"), icon="group")
        depts = [x.code for x in c.admin.reference_data(user.ctx)["departments"]]
        items = c.admin.list_users(user.ctx)
        with ui.row().classes("gap-6 w-full flex-wrap"):
            with ui.column().classes("gap-3").style("flex: 1.4; min-width: 380px;"):
                data_table([("email", tr(c, "lbl.email")), ("name", "Name"), ("role", "Role"), ("dept", tr(c, "lbl.department")), ("active", "Active")], [{"id": u.id, "email": u.email, "name": u.full_name, "role": u.role.value, "dept": u.department_id or "-", "active": u.is_active} for u in items])
            with ui.column().classes("gap-4").style("flex: 1; min-width: 300px;"):
                with ui.column().classes("cl-card gap-2 w-full"):
                    section_title("Create staff account")
                    email, name = ui.input(tr(c, "lbl.email")).props("outlined dense").classes("w-full"), ui.input("Full name").props("outlined dense").classes("w-full")
                    pw = ui.input(tr(c, "lbl.password"), password=True).props("outlined dense").classes("w-full")
                    roles = [Role.OFFICER.value] + ([Role.ADMIN.value, Role.SUPER_ADMIN.value] if user.ctx.role is Role.SUPER_ADMIN else [])
                    role, dept = ui.select(roles, value=roles[0], label="Role").props("outlined dense").classes("w-full"), ui.select(depts, label=tr(c, "lbl.department")).props("outlined dense").classes("w-full")
                    ui.button(tr(c, "act.submit"), icon="person_add", on_click=_act(lambda: c.admin.create_staff(user.ctx, email.value or "", pw.value or "", name.value or "", Role(role.value), dept.value))).props("color=primary unelevated").classes("w-full")
                with ui.column().classes("cl-card gap-2 w-full"):
                    section_title("Change role / deactivate")
                    uid = ui.select({u.id: f"{u.email} ({u.role.value})" for u in items}, label="User").props("outlined dense").classes("w-full")
                    new_role, new_dept = ui.select([r.value for r in Role], label="New role").props("outlined dense").classes("w-full"), ui.select(depts, label=tr(c, "lbl.department")).props("outlined dense").classes("w-full")
                    with ui.row().classes("gap-2 flex-wrap"):
                        ui.button("Change role", on_click=_act(lambda: c.admin.change_role(user.ctx, uid.value, Role(new_role.value), new_dept.value))).props("outline dense")
                        ui.button("Reactivate", on_click=_act(lambda: c.admin.set_user_active(user.ctx, uid.value, True))).props("outline dense")
                        _danger_action("Deactivate", lambda: c.admin.set_user_active(user.ctx, uid.value, False))
                with ui.column().classes("cl-card gap-2 w-full"):
                    section_title("Password reset for a user without e-mail")

                    def issue() -> None:
                        try:
                            r = c.admin.issue_password_reset(user.ctx, uid.value)
                        except (CivicLensError, ValueError) as exc:
                            ui.notify(getattr(exc, "message", str(exc)), type="negative")
                            return
                        with ui.dialog() as dlg, ui.column().classes("cl-card gap-2 w-full max-w-md"):
                            ui.label("One-time reset link (shown once)").classes("text-base font-semibold").style("color: var(--cl-fg);")
                            ui.label(f"{c.public_base_url.rstrip('/')}/reset-password?token={r['token']}").classes("cl-mono text-xs break-all cl-surface-alt q-pa-sm")
                            ui.label(r["note"]).classes("text-xs").style("color: var(--cl-fg-subtle);")
                            ui.button(tr(c, "act.close"), on_click=dlg.close).props("outline")
                        dlg.open()

                    ui.button("Issue reset link", icon="key", on_click=issue).props("outline dense")

    @page(c, "/admin/departments", "nav.departments", roles=ADMINS)
    def departments(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.departments"), icon="apartment")
        ref = c.admin.reference_data(user.ctx)
        data_table([("code", "Code"), ("name", "Name"), ("active", "Active")], [{"id": d.code, "code": d.code, "name": d.name, "active": d.active} for d in ref["departments"]])
        with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
            code, name, active = ui.input("Code").props("outlined dense"), ui.input("Name").props("outlined dense"), ui.switch("Active", value=True).props("color=primary")
            ui.button(tr(c, "act.save"), icon="check", on_click=_act(lambda: c.admin.save_department(user.ctx, code.value or "", name.value or "", bool(active.value)))).props("color=primary unelevated")

    @page(c, "/admin/wards", "nav.wards", roles=ADMINS)
    def wards(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.wards"), icon="location_city")
        ref = c.admin.reference_data(user.ctx)
        section_title("Cities")
        data_table([("code", "Code"), ("name", "Name"), ("state", "State"), ("lat", "Lat"), ("lng", "Lng")], [{"id": x.code, "code": x.code, "name": x.name, "state": x.state or "-", "lat": x.lat, "lng": x.lng} for x in ref["cities"]], empty="No cities yet.")
        with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
            cc, cn, cs, cla, cln = ui.input("City code").props("outlined dense"), ui.input("Name").props("outlined dense"), ui.input("State").props("outlined dense"), ui.number("Lat").props("outlined dense"), ui.number("Lng").props("outlined dense")
            ui.button("Save city", icon="check", on_click=_act(lambda: c.admin.save_city(user.ctx, cc.value or "", cn.value or "", cs.value, cla.value, cln.value))).props("color=primary unelevated")
        section_title("Wards")
        data_table([("code", "Code"), ("name", "Name"), ("city", "City")], [{"id": x.code, "code": x.code, "name": x.name, "city": x.city_code or "-"} for x in ref["wards"]], empty="No wards yet.")
        with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
            wc, wn, wcity = ui.input("Ward code").props("outlined dense"), ui.input("Name").props("outlined dense"), ui.select([x.code for x in ref["cities"]], label="City").props("outlined dense")
            ui.button("Save ward", icon="check", on_click=_act(lambda: c.admin.save_ward(user.ctx, wc.value or "", wn.value or "", wcity.value))).props("color=primary unelevated")

    @page(c, "/admin/services", "nav.civic_services", roles=ADMINS)
    def services(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.civic_services"), icon="miscellaneous_services")
        ref = c.admin.reference_data(user.ctx)
        section_title("Civic services")
        data_table([("code", "Code"), ("name", "Name"), ("dept", tr(c, "lbl.department"))], [{"id": x.code, "code": x.code, "name": x.name, "dept": x.department_code} for x in ref["services"]], empty="No services yet.")
        with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
            sc, sn, sd = ui.input("Code").props("outlined dense"), ui.input("Name").props("outlined dense"), ui.select([d.code for d in ref["departments"]], label=tr(c, "lbl.department")).props("outlined dense")
            ui.button(tr(c, "act.save"), icon="check", on_click=_act(lambda: c.admin.save_service(user.ctx, sc.value or "", sn.value or "", sd.value))).props("color=primary unelevated")
        section_title("Government offices", "Shown on the citizen GIS radar.")
        data_table([("name", "Name"), ("dept", tr(c, "lbl.department")), ("lat", "Lat"), ("lng", "Lng")], [{"id": x.id, "name": x.name, "dept": x.department_code or "-", "lat": x.lat, "lng": x.lng} for x in ref["offices"]], empty="No offices yet.")
        with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
            oi, on, od, ola, oln, oa = ui.input("Id").props("outlined dense"), ui.input("Name").props("outlined dense"), ui.select([d.code for d in ref["departments"]], label=tr(c, "lbl.department")).props("outlined dense"), ui.number("Lat").props("outlined dense"), ui.number("Lng").props("outlined dense"), ui.input("Address").props("outlined dense")
            ui.button("Save office", icon="check", on_click=_act(lambda: c.admin.save_office(user.ctx, oi.value or "", on.value or "", od.value, ola.value, oln.value, oa.value))).props("color=primary unelevated")

    @page(c, "/admin/routing-rules", "nav.routing", roles=ADMINS)
    def routing(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.routing"), icon="alt_route")
        ref = c.admin.reference_data(user.ctx)
        info_banner("Rules run in ascending priority; the first match wins. AI is only a recorded fallback when no rule matches.")
        data_table([("id", "Rule"), ("prio", "Priority"), ("dept", tr(c, "lbl.department")), ("cats", "Categories"), ("kw", "Keywords"), ("active", "Active")],
                   [{"id": r.id, "prio": r.priority, "dept": r.department_code, "cats": ", ".join(sorted(r.categories)), "kw": ", ".join(r.keywords_any), "active": r.active} for r in ref["routing_rules"]], empty="No routing rules - every complaint will need manual triage.")
        with ui.column().classes("cl-card gap-3 w-full"):
            with ui.row().classes("gap-3 items-end flex-wrap"):
                rid, prio = ui.input("Rule id").props("outlined dense"), ui.number("Priority", value=100, format="%d").props("outlined dense")
                dept = ui.select([d.code for d in ref["departments"] if d.active], label=tr(c, "lbl.department")).props("outlined dense")
                sev = ui.select([""] + list(SEVERITIES), value="", label="Min severity").props("outlined dense")
            cats = ui.select(list(CATEGORIES), multiple=True, label="Categories").props("outlined dense").classes("w-full")
            kws = ui.input("Keywords (comma separated)").props("outlined dense").classes("w-full")
            ui.button(tr(c, "act.save"), icon="check", on_click=_act(lambda: c.admin.save_routing_rule(user.ctx, rid.value or "", int(prio.value), dept.value or "", categories=list(cats.value or []), keywords_any=[k for k in (kws.value or "").split(",") if k.strip()], min_severity=sev.value or None))).props("color=primary unelevated")
        with ui.row().classes("gap-3 items-end"):
            delete = ui.select([r.id for r in ref["routing_rules"]], label="Delete rule").props("outlined dense").classes("w-56")
            _danger_action("Delete", lambda: c.admin.delete_routing_rule(user.ctx, delete.value))

    @page(c, "/admin/workflow-rules", "nav.workflow", roles=ADMINS)
    def workflow_rules(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.workflow"), icon="account_tree")
        ov = c.admin.workflow_overview(user.ctx)
        info_banner("Automation on complaint events. A rule runs at most once per complaint; every run is recorded on the complaint (internal) and in the audit log. Scheduled rules need an age condition.")
        data_table([("id", "Rule"), ("name", "Name"), ("trigger", "Trigger"), ("cond", "Conditions"), ("action", "Action"), ("active", "Active")],
                   [{"id": r.id, "name": r.name, "trigger": r.trigger, "cond": json.dumps(r.conditions, ensure_ascii=False), "action": r.action, "active": r.active} for r in ov["rules"]], empty="No workflow rules configured.")
        with ui.column().classes("cl-card gap-3 w-full"):
            with ui.row().classes("gap-3 items-end flex-wrap"):
                rid, name = ui.input("Rule id").props("outlined dense"), ui.input("Name").props("outlined dense")
                trig, act = ui.select(list(WF_TRIGGERS), value=WF_TRIGGERS[0], label="Trigger").props("outlined dense"), ui.select(list(WF_ACTIONS), value=WF_ACTIONS[0], label="Action").props("outlined dense")
            cond = ui.textarea("Conditions (JSON)", value='{"priority_min": "critical"}').props("outlined").classes("w-full")
            params = ui.textarea("Params (JSON, e.g. {\"text\": \"...\"})", value="{}").props("outlined").classes("w-full")

            def save_wf() -> None:
                try:
                    conditions = json.loads(cond.value or "{}")
                    parsed_params = json.loads(params.value or "{}")
                except json.JSONDecodeError as exc:
                    ui.notify(f"Invalid JSON: {exc.msg} (line {exc.lineno}, col {exc.colno}).", type="negative")
                    return
                _act(lambda: c.admin.save_workflow_rule(user.ctx, rid.value or "", name.value or "", trig.value, act.value, conditions=conditions, params=parsed_params))()

            ui.button(tr(c, "act.save"), icon="check", on_click=save_wf).props("color=primary unelevated")
        with ui.row().classes("gap-3 items-end"):
            dele = ui.select([r.id for r in ov["rules"]], label="Delete rule").props("outlined dense").classes("w-56")
            _danger_action("Delete", lambda: c.admin.delete_workflow_rule(user.ctx, dele.value))
        section_title("Recent executions")
        data_table([("when", "When"), ("rule", "Rule"), ("complaint", "Complaint"), ("action", "Action")], [{"id": str(i), "when": e.executed_at.strftime("%d %b %H:%M"), "rule": e.rule_id, "complaint": e.complaint_id[:8], "action": e.outcome} for i, e in enumerate(ov["executions"])], empty="No rule has run yet.")

    @page(c, "/admin/emergency", "nav.emergency_admin", roles=ADMINS)
    def emergency_admin(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.emergency_admin"), icon="emergency")
        items = c.admin.emergency_contacts(user.ctx)
        if not items:
            state_panel(icon="support_agent", title="No emergency contacts configured", body="The public Emergency Hub shows an empty state until you add some.",
                        action_label="Load the six national helplines from the original app", on_action=_act(lambda: c.emergency.seed_defaults()))
        else:
            data_table([("id", "Id"), ("number", "Number"), ("name", "Name"), ("scope", "Scope"), ("active", "Active")], [{"id": x.id, "number": x.number, "name": x.name, "scope": x.scope, "active": x.active} for x in items])
        with ui.column().classes("cl-card gap-3 w-full"):
            with ui.row().classes("gap-3 items-end flex-wrap"):
                cid, num, nm = ui.input("Id").props("outlined dense"), ui.input("Number").props("outlined dense"), ui.input("Name").props("outlined dense")
                scope = ui.select(["national", "city"], value="national", label="Scope").props("outlined dense")
                city = ui.select([x.code for x in c.admin.reference_data(user.ctx)["cities"]], label="City (city scope)").props("outlined dense")
            desc = ui.input("Description").props("outlined dense").classes("w-full")
            ui.button(tr(c, "act.save"), icon="check", on_click=_act(lambda: c.admin.save_emergency_contact(user.ctx, cid.value or "", num.value or "", nm.value or "", description=desc.value or "", scope=scope.value, city_code=city.value))).props("color=primary unelevated")
        if items:
            with ui.row().classes("gap-3 items-end"):
                dele = ui.select([x.id for x in items], label="Delete contact").props("outlined dense").classes("w-56")
                _danger_action("Delete", lambda: c.admin.delete_emergency_contact(user.ctx, dele.value))

    @page(c, "/admin/sla", "nav.sla", roles=ADMINS)
    def sla(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.sla"), icon="timer")
        ref = c.admin.reference_data(user.ctx)
        info_banner("SLA hours are business policy configured here; none are seeded. A complaint with no matching policy has no SLA and says so.", "orange")
        data_table([("id", "Policy"), ("prio", tr(c, "lbl.priority")), ("dept", tr(c, "lbl.department")), ("hours", "Hours"), ("gap", "Escalation gap (h)"), ("max", "Max level")],
                   [{"id": p.id, "prio": p.priority, "dept": p.department_code or "(all)", "hours": p.resolution_hours, "gap": p.escalation_gap_hours, "max": p.max_level} for p in ref["sla_policies"]], empty="No SLA policies configured.")
        with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
            pid, prio, hours = ui.input("Policy id").props("outlined dense"), ui.select(["low", "medium", "high", "critical"], label=tr(c, "lbl.priority")).props("outlined dense"), ui.number("Resolution hours", value=72, format="%d").props("outlined dense")
            dept = ui.select([""] + [d.code for d in ref["departments"]], value="", label=tr(c, "lbl.department")).props("outlined dense")
            ui.button(tr(c, "act.save"), icon="check", on_click=_act(lambda: c.admin.save_sla_policy(user.ctx, pid.value or "", prio.value or "", int(hours.value), department_code=dept.value or None))).props("color=primary unelevated")
        with ui.row().classes("gap-3 items-end"):
            d = ui.select([p.id for p in ref["sla_policies"]], label="Delete policy").props("outlined dense").classes("w-56")
            _danger_action("Delete", lambda: c.admin.delete_sla_policy(user.ctx, d.value))

    @page(c, "/admin/integrations", "nav.integrations", roles=ADMINS)
    def integrations(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.integrations"), icon="hub")
        info_banner("NOT_CONFIGURED means no credentials/endpoints were supplied: nothing has ever been sent to that platform. CONNECTED means the last health check succeeded.")
        rows = []
        for a in c.adapters.values():
            h = a.health_snapshot("missing: " + ", ".join(a.config.missing()) if not a.is_configured() else "not probed since start")
            rows.append({"id": a.platform, "name": a.display_name, "state": h.state.value, "detail": h.detail, "last_ok": h.last_success_at.strftime("%d %b %H:%M") if h.last_success_at else "-", "err": h.last_error or "-", "avg": f"{h.avg_response_ms:.0f} ms" if h.avg_response_ms else "-"})
        data_table([("name", "Platform"), ("state", "State"), ("detail", "Detail"), ("last_ok", "Last success"), ("err", "Last error"), ("avg", "Avg response")], rows)

        def check() -> None:
            if c.health is None:
                raise CivicLensError("Integration health persistence is not configured.")
            c.health.check_all(c.adapters)

        ui.button("Run health checks", icon="health_and_safety", on_click=_act(check)).props("color=primary unelevated")

    @page(c, "/admin/audit", "nav.audit", roles=ADMINS)
    def audit(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.audit"), icon="fact_check")
        with ui.row().classes("gap-2 items-center w-full"):
            prefix = ui.input("Action prefix (e.g. auth., complaint., admin.)").props("outlined dense").classes("w-72")
            ui.button(icon="search", on_click=lambda: draw()).props("round unelevated color=primary")
        box = ui.column().classes("w-full")

        def draw() -> None:
            box.clear()
            with box:
                ev = c.admin.audit_log(user.ctx, action_prefix=prefix.value or None, limit=200)
                data_table([("at", "When"), ("action", "Action"), ("actor", "Actor"), ("res", "Resource"), ("meta", "Details")],
                           [{"id": str(i), "at": e.occurred_at.strftime("%d %b %Y %H:%M:%S"), "action": e.action, "actor": (e.actor_id or "system")[:8], "res": f"{e.resource_type or ''} {(e.resource_id or '')[:8]}", "meta": str(e.metadata)[:120]} for i, e in enumerate(ev)])

        prefix.on("keydown.enter", draw)
        draw()

    @page(c, "/admin/analytics", "nav.analytics", roles=ADMINS)
    def analytics(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.analytics"), icon="insights")
        d = c.dashboards.admin(user.ctx)
        if not d["has_data"]:
            state_panel(icon="insights", title=tr(c, "msg.no_data"))
            return
        with ui.row().classes("gap-4 w-full flex-wrap"):
            with ui.column().classes("cl-card").style("flex: 1; min-width: 320px;"):
                section_title("By department")
                ui.echart({"grid": {"left": 40, "right": 12, "top": 12, "bottom": 40}, "xAxis": {"type": "category", "data": list(d["by_department"]), "axisLabel": {"rotate": 30}}, "yAxis": {"type": "value"}, "series": [{"type": "bar", "data": list(d["by_department"].values())}]}).classes("w-full h-56")
            with ui.column().classes("cl-card").style("flex: 1; min-width: 320px;"):
                section_title("By ward")
                ui.echart({"grid": {"left": 40, "right": 12, "top": 12, "bottom": 40}, "xAxis": {"type": "category", "data": list(d["by_ward"]), "axisLabel": {"rotate": 30}}, "yAxis": {"type": "value"}, "series": [{"type": "bar", "data": list(d["by_ward"].values())}]}).classes("w-full h-56")
            with ui.column().classes("cl-card").style("flex: 1.4; min-width: 380px;"):
                section_title("Trend (30 d)")
                ui.echart({"grid": {"left": 36, "right": 12, "top": 12, "bottom": 24}, "xAxis": {"type": "category", "data": [t["date"][5:] for t in d["trend_daily"]]}, "yAxis": {"type": "value"}, "series": [{"type": "line", "areaStyle": {}, "data": [t["count"] for t in d["trend_daily"]]}]}).classes("w-full h-56")
        from app.services.analytics_service import InsufficientData, forecast_linear

        f = forecast_linear([t["count"] for t in d["trend_daily"]], 7)
        with ui.row().classes("cl-card w-full items-center gap-2"):
            if isinstance(f, InsufficientData):
                ui.icon("hourglass_empty").style("color: var(--cl-fg-muted);")
                ui.label(f"Forecast: not enough history ({f.have}/{f.needed} days).").classes("text-sm").style("color: var(--cl-fg-muted);")
            else:
                ui.icon("query_stats").style("color: var(--cl-info);")
                ui.label(f"Forecast (estimate, not a fact): next 7 days ~ {list(f.values)} [{f.label}]").classes("text-sm").style("color: var(--cl-info);")
        with ui.row().classes("gap-2 flex-wrap"):
            chip(f"Backlog: {d['backlog']}", color="muted", outline=True)
            chip(f"Escalated: {d['escalated']}", color="danger", outline=True)
            chip(f"SLA breached: {d['sla'].get('breached', 0)}", color="warning", outline=True)
        section_title("History (from hourly snapshots)")
        hist = c.dashboards.history(user.ctx, days=30)
        if not hist["has_data"]:
            state_panel(icon="history", title="No snapshots yet", body="They accumulate hourly once the scheduler is running.")
        else:
            xs = [p["taken_at"].strftime("%d %b %H:%M") for p in hist["points"]]
            with ui.column().classes("cl-card w-full"):
                ui.echart({"legend": {}, "grid": {"left": 40, "right": 12, "top": 32, "bottom": 24}, "xAxis": {"type": "category", "data": xs}, "yAxis": {"type": "value"},
                           "series": [{"name": k, "type": "line", "data": [p[k] for p in hist["points"]]} for k in ("open", "breached", "at_risk", "backlog")]}).classes("w-full h-64")
        ui.button("Run anomaly detection now", icon="troubleshoot", on_click=_act(lambda: c.anomaly_job.run(c.clock()))).props("outline")

    @page(c, "/admin/anomalies", "nav.anomalies", roles=ADMINS)
    def anomalies(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.anomalies"), icon="warning")
        items = c.admin.anomalies(user.ctx, status=None)
        data_table([("at", "Detected"), ("kind", "Kind"), ("subject", "Subject"), ("sev", "Severity"), ("status", tr(c, "lbl.status")), ("why", "Explanation")],
                   [{"id": a.id, "at": a.detected_at.strftime("%d %b %H:%M"), "kind": a.kind, "subject": a.subject, "sev": a.severity, "status": a.status, "why": a.explanation} for a in items], empty="No anomalies detected (or not enough history yet).")
        with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
            sel = ui.select({a.id: f"{a.kind}: {a.subject}" for a in items if a.status == "open"}, label="Open anomaly").props("outlined dense").classes("w-96")
            ui.button("Acknowledge", icon="visibility", on_click=_act(lambda: c.admin.set_anomaly_status(user.ctx, sel.value, "acknowledged"))).props("outline dense")
            ui.button("Resolve", icon="check", on_click=_act(lambda: c.admin.set_anomaly_status(user.ctx, sel.value, "resolved"))).props("outline dense")
            ui.button("Investigate", icon="search", on_click=_act(lambda: c.investigations.open(user.ctx, "anomaly", sel.value))).props("outline dense")

    @page(c, "/admin/investigations", "nav.investigations", roles=ADMINS)
    def admin_investigations(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.investigations"), icon="policy")
        items = c.investigations.list(user.ctx)
        data_table([("subject", "Subject"), ("status", tr(c, "lbl.status")), ("dept", tr(c, "lbl.department"))], [{"id": i.id, "subject": f"{i.subject_type} {i.subject_id[:8]}", "status": i.status, "dept": i.department_code or "-"} for i in items],
                   on_row=lambda r: ui.navigate.to(f"/officer/investigations/{r['id']}"), empty="No investigations yet.")

    @page(c, "/admin/triage", "nav.triage", roles=ADMINS)
    def triage(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.triage"), icon="call_split")
        ref = c.admin.reference_data(user.ctx)
        items = run_in_uow(c, lambda uow: uow.complaints.list_unrouted())
        if not items:
            state_panel(icon="task_alt", title="Nothing waiting for manual routing")
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
                        ui.button("Route", icon="alt_route", on_click=_act(lambda cid=cm.id, s=sel: c.officer.triage(user.ctx, cid, s.value))).props("color=primary unelevated")

    @page(c, "/admin/monitoring", "nav.monitoring", roles=ADMINS)
    def monitoring(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.monitoring"), icon="monitor_heart")
        s = c.system_status()
        q = s["queue"]
        section_title("Queue & workers")
        with ui.row().classes("cl-card w-full items-center gap-2"):
            chip("Redis reachable" if q["backend_reachable"] else "Redis unreachable", color="success" if q["backend_reachable"] else "danger")
            ui.label(f"depth {q['backend_depth']} · jobs by status: {q['by_status']}").classes("text-xs").style("color: var(--cl-fg-muted);")
        data_table([("id", "Worker"), ("seen", "Last seen")], [{"id": k, "seen": v.get("last_seen", "-")} for k, v in q["workers"].items()], empty="No worker heartbeats (workers not running or Redis unavailable).")
        section_title("Recent jobs", "queued -> running -> succeeded | retrying -> dead")
        jobs = run_in_uow(c, lambda uow: uow.jobs.list_recent(30))
        data_table([("kind", "Kind"), ("status", tr(c, "lbl.status")), ("att", "Attempts"), ("started", "Started"), ("finished", "Finished"), ("err", "Error")],
                   [{"id": j.id, "kind": j.kind, "status": j.status, "att": j.attempts, "started": j.started_at.strftime("%H:%M:%S") if j.started_at else "-", "finished": j.finished_at.strftime("%H:%M:%S") if j.finished_at else "-", "err": j.error or ""} for j in jobs], empty="No jobs yet.")
        if any(j.status == "dead" for j in jobs):
            with ui.row().classes("gap-3 items-end"):
                dead = ui.select({j.id: f"{j.kind} - {j.error or ''}"[:80] for j in jobs if j.status == "dead"}, label="Dead job").props("outlined dense").classes("w-96")
                ui.button("Retry dead job", icon="replay", on_click=_act(lambda: c.jobs.retry_dead(dead.value))).props("outline dense")
        section_title("Notification delivery")
        counts = run_in_uow(c, lambda uow: uow.notifications.status_counts())
        data_table([("channel", "Channel"), ("states", "queued / sending / delivered / failed / not_configured")], [{"id": ch, "channel": ch, "states": ", ".join(f"{k}: {v}" for k, v in sorted(st.items()))} for ch, st in counts.items()], empty="No notifications yet.")
        with ui.row().classes("gap-2 flex-wrap"):
            chip(f"E-mail sender: {'configured' if c.mailer else 'NOT configured'}", color="success" if c.mailer else "muted")
            chip(f"Push (Expo): {'enabled' if c.push_sender else 'NOT enabled'}", color="success" if c.push_sender else "muted")
        gov = run_in_uow(c, lambda uow: uow.government.counts_by_state())
        ui.label("Government submissions: " + (", ".join(f"{k}: {v}" for k, v in sorted(gov.items())) or "none yet")).classes("text-xs").style("color: var(--cl-fg-muted);")
        ui.label(f"RAG index: {s['rag']} · Ollama: {s['ollama']} · WebSocket connections: {s['websocket_connections']}").classes("text-xs").style("color: var(--cl-fg-muted);")
        ui.label(f"Adapters: {s['adapters']}").classes("text-xs").style("color: var(--cl-fg-muted);")
        ui.label("Translation coverage (extras): " + str(c.ui_text.extras_coverage())).classes("text-xs").style("color: var(--cl-fg-subtle);")

    @page(c, "/admin/exceptions", "nav.exceptions", roles=ADMINS)
    def exceptions(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.exceptions"), "Records that failed the interoperability layer's data-quality checks, queued for review instead of silently dropped.", icon="report_problem")
        counts = c.exceptions.counts(user.ctx)
        with ui.row().classes("gap-3 flex-wrap"):
            stat_tile("Open", counts.get("open", 0), color="danger", icon="report_problem")
            stat_tile("Resolved", counts.get("resolved", 0), color="success", icon="check_circle")
            stat_tile("Ignored", counts.get("ignored", 0), color="muted", icon="visibility_off")

        status_filter = ui.select({"": "All", "open": "Open", "resolved": "Resolved", "ignored": "Ignored"}, value="open", label=tr(c, "lbl.status")).props("outlined dense").classes("w-48")
        box = ui.column().classes("gap-2 w-full")

        def draw() -> None:
            box.clear()
            items = c.exceptions.list(user.ctx, status=status_filter.value or None)
            with box:
                if not items:
                    state_panel(icon="task_alt", title="Nothing here", body="No exceptions match this filter.")
                for ex in items:
                    with ui.column().classes("cl-card gap-2 w-full"):
                        with ui.row().classes("items-center justify-between w-full flex-wrap"):
                            chip(ex.source_system, color="info", outline=True)
                            chip(ex.status, color={"open": "danger", "resolved": "success", "ignored": "muted"}.get(ex.status, "muted"))
                        ui.label(ex.reason).classes("text-sm").style("color: var(--cl-fg);")
                        ui.label(ex.detected_at.strftime("%d %b %Y %H:%M")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                        with ui.expansion("Raw payload").classes("w-full"):
                            import json as _json

                            ui.markdown(f"```json\n{_json.dumps(ex.payload, indent=2, ensure_ascii=False)}\n```").classes("cl-mono text-xs")
                        if ex.resolution_note:
                            ui.label(f"Resolution: {ex.resolution_note}").classes("text-xs").style("color: var(--cl-success);")
                        if ex.status == "open":
                            note = ui.input("Resolution note").props("outlined dense").classes("w-full max-w-md")
                            with ui.row().classes("gap-2"):
                                ui.button("Resolve", icon="check", on_click=_act(lambda i=ex.id, n=note: c.exceptions.resolve(user.ctx, i, note=n.value or "", ignore=False))).props("outline dense")
                                ui.button("Ignore", icon="visibility_off", on_click=_act(lambda i=ex.id, n=note: c.exceptions.resolve(user.ctx, i, note=n.value or "", ignore=True))).props("flat dense")

        status_filter.on_value_change(lambda e: draw())
        draw()

        section_title("Learned corrections", "Every time staff corrects a misclassified complaint's category, it's captured here - transparent and inspectable, never a silent black-box re-weight.")
        corrections = c.classification_corrections.recent(user.ctx)
        data_table([("when", "When"), ("from", "Was"), ("to", "Corrected to"), ("text", "Complaint text")],
                   [{"id": r.id, "when": r.corrected_at.strftime("%d %b %Y %H:%M"), "from": r.previous_category, "to": r.corrected_category, "text": r.text_snapshot[:100]} for r in corrections],
                   empty="No corrections recorded yet.")

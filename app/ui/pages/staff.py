"""Officer pages: department dashboard, queue, complaint detail with workflow actions, investigation mode."""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any

from nicegui import ui

from app.container import AppContainer
from app.core.authorization import Role
from app.core.exceptions import CivicLensError
from app.services.complaint_status import TRANSITIONS, ComplaintStatus
from app.ui import theme
from app.ui.base import UiUser, data_table, info_banner, page, tr
from app.ui.components import chip, divider, page_header, section_title, state_panel, stat_tile
from app.ui.navigation import OFFICER_UP, STAFF
from app.ui.pages.citizen import _events, _timeline, government_panel


def _act(fn: Any, success: str = "Saved.") -> Any:
    def run(*a: Any) -> None:
        try:
            fn(*a)
        except CivicLensError as exc:
            ui.notify(exc.message + (f" {exc.details}" if exc.details else ""), type="negative")
            return
        ui.notify(success, type="positive")
        ui.navigate.reload()

    return run


def register(c: AppContainer) -> None:
    @page(c, "/officer", "nav.officer", roles=OFFICER_UP)
    def officer_dashboard(c: AppContainer, user: UiUser) -> None:
        d = c.dashboards.department(user.ctx)
        page_header(tr(c, "nav.officer"), d["department_code"] or "All departments", icon="space_dashboard")
        if not d["has_data"]:
            state_panel(icon="inbox", title=tr(c, "msg.no_data"))
            return
        with ui.row().classes("gap-3 w-full flex-wrap"):
            stat_tile(tr(c, "card.open"), d["open"], color="info", icon="assignment")
            stat_tile(tr(c, "card.resolved"), d["resolved"], color="success", icon="task_alt")
            stat_tile(tr(c, "card.overdue"), d["sla"]["breached"], color="danger", icon="report")
            stat_tile(tr(c, "card.at_risk"), d["sla"]["at_risk"], color="warning", icon="schedule")
            stat_tile(tr(c, "card.escalated"), d["escalated"], color="danger", icon="trending_up")
            stat_tile("Unrouted", d["unrouted"], color="muted", icon="alt_route")
        if d["resolution_hours"]:
            with ui.row().classes("cl-card w-full items-center gap-2"):
                ui.icon("timer").style("color: var(--cl-fg-muted);")
                ui.label(f"Resolution time: median {d['resolution_hours']['median']} h, mean {d['resolution_hours']['mean']} h over {d['resolution_hours']['count']} resolved.").classes("text-sm").style("color: var(--cl-fg-muted);")
        with ui.row().classes("gap-4 w-full flex-wrap"):
            with ui.column().classes("cl-card").style("flex: 1; min-width: 320px;"):
                section_title("By category")
                ui.echart({"tooltip": {}, "series": [{"type": "pie", "radius": "70%", "data": [{"name": k, "value": v} for k, v in d["by_category"].items()]}]}).classes("w-full h-56")
            with ui.column().classes("cl-card").style("flex: 1.4; min-width: 380px;"):
                section_title("Complaints per day (30 d)")
                ui.echart({"grid": {"left": 36, "right": 12, "top": 12, "bottom": 24}, "xAxis": {"type": "category", "data": [t["date"][5:] for t in d["trend_daily"]]}, "yAxis": {"type": "value"}, "series": [{"type": "line", "areaStyle": {}, "data": [t["count"] for t in d["trend_daily"]]}]}).classes("w-full h-56")
        section_title("Workload")
        data_table([("officer", "Officer"), ("open", "Open")], [{"id": k, "officer": k[:8], "open": v} for k, v in d["workload"].items()], empty="No assigned work.")
        if d["anomalies"]:
            section_title("Open anomalies")
            with ui.column().classes("gap-2 w-full"):
                for a in d["anomalies"]:
                    info_banner(f"[{a.severity}] {a.explanation}", "orange")

    @page(c, "/officer/queue", "nav.officer_queue", roles=STAFF)
    def queue(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.officer_queue"), icon="inbox")
        with ui.row().classes("gap-3 items-center w-full flex-wrap"):
            mine = ui.switch("Only mine").props("color=primary")
            status = ui.select({"": "All", **{s.value: s.value.replace("_", " ") for s in ComplaintStatus}}, value="", label=tr(c, "lbl.status")).props("outlined dense").classes("w-52")
        box = ui.column().classes("w-full")

        def draw() -> None:
            box.clear()
            with box:
                items = c.officer.queue(user.ctx, mine_only=mine.value, statuses=[ComplaintStatus(status.value)] if status.value else None)
                rows = [{"id": x.id, "ref": x.reference, "title": x.title, "status": str(x.status).replace("_", " "), "prio": x.priority, "ward": x.ward or "-", "due": x.sla_due_at.strftime("%d %b %H:%M") if x.sla_due_at else "no SLA"} for x in items]
                data_table([("ref", tr(c, "lbl.reference")), ("title", tr(c, "lbl.title")), ("status", tr(c, "lbl.status")), ("prio", tr(c, "lbl.priority")), ("ward", tr(c, "lbl.ward")), ("due", tr(c, "lbl.due"))], rows,
                           on_row=lambda r: ui.navigate.to(f"/officer/complaints/{r['id']}"))

        mine.on_value_change(lambda e: draw())
        status.on_value_change(lambda e: draw())
        draw()

    @page(c, "/officer/complaints/{cid}", "nav.officer_queue", roles=OFFICER_UP)
    def complaint_detail(c: AppContainer, user: UiUser, cid: str) -> None:
        d = c.officer.detail(user.ctx, cid)
        cm, sla = d["complaint"], d["sla"]
        with ui.row().classes("items-start justify-between w-full flex-wrap gap-2"):
            with ui.column().classes("gap-1"):
                ui.label(cm.reference).classes("text-xs cl-mono").style("color: var(--cl-fg-subtle);")
                ui.label(cm.title).classes("text-xl font-semibold").style("color: var(--cl-fg);")
                with ui.row().classes("gap-2 flex-wrap"):
                    chip(str(cm.status).replace("_", " "), color=theme.STATUS_COLOR.get(str(cm.status), "muted"))
                    chip(cm.priority, color=theme.PRIORITY_COLOR.get(cm.priority, "muted"))
                    chip(f"SLA {sla.state.replace('_', ' ')}", color=theme.SLA_COLOR.get(sla.state, "muted"))
                    if cm.escalation_level:
                        chip(f"Escalated L{cm.escalation_level}", color="danger")

        with ui.row().classes("gap-6 w-full flex-wrap"):
            with ui.column().classes("gap-4 flex-1").style("min-width: 340px;"):
                with ui.column().classes("cl-card gap-2 w-full"):
                    ui.label(cm.description).classes("text-sm").style("color: var(--cl-fg);")
                    divider()
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        ui.label(f"Category {cm.category} ({cm.classification.get('source')}, confidence {cm.classification.get('confidence')}) - AI status: {cm.ai_status}").classes("text-xs").style("color: var(--cl-fg-muted);")

                        def correct_category_dialog() -> None:
                            from app.services.classification_service import CATEGORIES

                            with ui.dialog() as dlg, ui.column().classes("cl-card gap-3 w-full max-w-sm"):
                                ui.label("Correct category").classes("text-base font-semibold").style("color: var(--cl-fg);")
                                ui.label("Captured for the transparent correction log, then applied for real - not a silent black-box change.").classes("text-xs").style("color: var(--cl-fg-subtle);")
                                sel = ui.select(list(CATEGORIES), value=cm.category, label="Correct category").props("outlined dense").classes("w-full")
                                ui.button("Save correction", on_click=_act(lambda: c.officer.correct_category(user.ctx, cid, sel.value))).props("color=primary unelevated")
                            dlg.open()

                        ui.button("Correct", icon="edit", on_click=correct_category_dialog).props("flat dense")
                    ui.label(f"Routing: {cm.routing.get('source')} - {cm.routing.get('explanation')}").classes("text-xs").style("color: var(--cl-fg-muted);")
                    if cm.routing.get("ai_disagreement"):
                        ui.label(f"AI disagreed with the rule: {cm.routing['ai_disagreement']}").classes("text-xs").style("color: var(--cl-warning);")
                    ui.label("Priority factors: " + "; ".join(cm.priority_factors)).classes("text-xs").style("color: var(--cl-fg-muted);")
                    if sla.remaining is not None:
                        ui.label(f"SLA due {sla.due_at:%d %b %H:%M} ({sla.remaining.total_seconds() / 3600:.1f} h remaining)").classes("text-xs").style("color: var(--cl-fg-muted);")

                if cm.lat is not None:
                    section_title("Location")
                    m = ui.leaflet(center=(cm.lat, cm.lng), zoom=15).classes("w-full h-56").style("border-radius: var(--cl-radius-md); overflow: hidden;")
                    m.marker(latlng=(cm.lat, cm.lng))

                if cm.duplicates:
                    section_title("Possible duplicates", "Advisory only - nothing is merged automatically.")
                    with ui.column().classes("gap-2 w-full"):
                        for x in c.duplicate_reviews.candidates(user.ctx, cid):
                            with ui.column().classes("cl-card gap-2 w-full"):
                                with ui.row().classes("items-center justify-between flex-wrap gap-2"):
                                    ui.label(x["reference"]).classes("text-sm font-medium cl-mono").style("color: var(--cl-fg);")
                                    chip(f"{x['verdict'].replace('_', ' ')} ({x['score']})", color="warning")
                                ui.label(x["explanation"]).classes("text-xs").style("color: var(--cl-fg-muted);")
                                if x["review"]:
                                    ui.label(f"Reviewed: {x['review']['decision'].replace('_', ' ')} at {x['review']['at']:%d %b %H:%M}" + (f" - {x['review']['note']}" if x["review"]["note"] else "")).classes("text-xs").style("color: var(--cl-success);")
                                with ui.row().classes("gap-2 items-end flex-wrap"):
                                    decision = ui.select(["confirmed_duplicate", "related", "not_duplicate"], value="related", label="Decision").props("outlined dense").classes("w-56")
                                    note = ui.input("Note").props("outlined dense").classes("w-56")
                                    ui.button("Save decision", on_click=_act(lambda o=x["complaint_id"], d=decision, n=note: c.duplicate_reviews.decide(user.ctx, cid, o, d.value, n.value))).props("outline dense")

                section_title(tr(c, "lbl.evidence"))
                if not d["evidence"]:
                    state_panel(icon="attach_file", title="No evidence attached")
                else:
                    with ui.row().classes("gap-3 flex-wrap"):
                        for ev in d["evidence"]:
                            with ui.column().classes("cl-card gap-2").style("width: 220px;"):
                                if ev.mime.startswith("image/") and ev.size <= 2_000_000:
                                    _rec, data = c.complaints.read_evidence(user.ctx, ev.id)  # authorised + audited
                                    ui.image(f"data:{ev.mime};base64,{base64.b64encode(data).decode()}").style("border-radius: var(--cl-radius-sm);")
                                ui.label(ev.name).classes("text-xs font-medium cl-clip-1").style("color: var(--cl-fg);")
                                chip(ev.analysis_status, color="info", outline=True)
                                if ev.analysis_result:
                                    ui.label(str(ev.analysis_result.get("summary"))).classes("text-xs cl-clip-2").style("color: var(--cl-fg-muted);")
                                if ev.analysis_error:
                                    ui.label(ev.analysis_error).classes("text-xs").style("color: var(--cl-danger);")
                                if ev.mime.startswith("image/"):
                                    ui.button("Re-run analysis", on_click=_act(lambda i=ev.id: c.complaints.request_analysis(user.ctx, i), "Analysis queued.")).props("flat dense")

                government_panel(c, user.ctx, cid)

                section_title("Actions")
                allowed = sorted(s.value for s in TRANSITIONS[cm.status])
                with ui.row().classes("cl-card gap-3 items-end w-full flex-wrap"):
                    target = ui.select(allowed, label="Move to", value=allowed[0] if allowed else None).props("outlined dense").classes("w-48")
                    remarks = ui.input(tr(c, "lbl.remarks")).props("outlined dense").classes("w-64 flex-1")
                    ui.button("Update status", on_click=_act(lambda: c.officer.update_status(user.ctx, cid, ComplaintStatus(target.value), remarks.value))).props("color=primary unelevated").set_enabled(bool(allowed))
                with ui.row().classes("gap-2 flex-wrap"):
                    def dialog_button(label: str, icon: str, build: Any, *, tone: str = "outline") -> None:
                        with ui.dialog() as dlg, ui.column().classes("cl-card gap-3 w-full max-w-sm"):
                            ui.label(label).classes("text-base font-semibold").style("color: var(--cl-fg);")
                            build(dlg)
                        ui.button(label, icon=icon, on_click=dlg.open).props(tone + " dense")

                    def remark_form(dlg: Any) -> None:
                        t = ui.textarea("Remark").props("outlined").classes("w-full")
                        internal = ui.checkbox("Internal (hidden from citizen)", value=True)
                        ui.button(tr(c, "act.save"), on_click=_act(lambda: c.officer.remark(user.ctx, cid, t.value, internal=internal.value))).props("color=primary unelevated")

                    def visit_form(dlg: Any) -> None:
                        when = ui.input("Scheduled for (YYYY-MM-DD HH:MM)").props("outlined").classes("w-full")
                        n = ui.textarea("Notes").props("outlined").classes("w-full")

                        def go() -> None:
                            try:
                                when_dt = datetime.fromisoformat((when.value or "").replace(" ", "T")).astimezone()
                            except ValueError:
                                ui.notify("Enter the date as YYYY-MM-DD HH:MM.", type="negative")
                                return
                            _act(lambda: c.officer.field_visit(user.ctx, cid, when_dt, n.value))()

                        ui.button(tr(c, "act.save"), on_click=go).props("color=primary unelevated")

                    def inspection_form(dlg: Any) -> None:
                        f = ui.textarea("Findings").props("outlined").classes("w-full")
                        ui.button(tr(c, "act.save"), on_click=_act(lambda: c.officer.inspection(user.ctx, cid, f.value))).props("color=primary unelevated")

                    def wo_form(dlg: Any) -> None:
                        ref, desc, team = ui.input("Work order no.").props("outlined").classes("w-full"), ui.textarea("Description").props("outlined").classes("w-full"), ui.input("Team").props("outlined").classes("w-full")
                        ui.button(tr(c, "act.save"), on_click=_act(lambda: c.officer.work_order(user.ctx, cid, ref.value, desc.value, team.value))).props("color=primary unelevated")

                    def coord_form(dlg: Any) -> None:
                        w, n = ui.input("With (team/department)").props("outlined").classes("w-full"), ui.textarea("Note").props("outlined").classes("w-full")
                        ui.button(tr(c, "act.save"), on_click=_act(lambda: c.officer.coordination_note(user.ctx, cid, w.value or "", n.value))).props("color=primary unelevated")

                    def progress_form(dlg: Any) -> None:
                        p, n = ui.slider(min=0, max=100, value=50).props("label-always color=primary"), ui.input("Notes").props("outlined").classes("w-full")
                        ui.button(tr(c, "act.save"), on_click=_act(lambda: c.officer.progress(user.ctx, cid, int(p.value), n.value))).props("color=primary unelevated")

                    def assign_form(dlg: Any) -> None:
                        from app.core.transactions import run_in_uow

                        ids = run_in_uow(c, lambda uow: uow.officers.officer_ids_for_department(cm.department_code) if cm.department_code else [])
                        sel = ui.select(ids, label="Officer", value=cm.assigned_officer_id).props("outlined dense").classes("w-full")
                        ui.button(tr(c, "act.save"), on_click=_act(lambda: c.officer.assign(user.ctx, cid, sel.value))).props("color=primary unelevated")

                    def escalate_form(dlg: Any) -> None:
                        r = ui.textarea("Reason").props("outlined").classes("w-full")
                        ui.button("Escalate", on_click=_act(lambda: c.officer.escalate(user.ctx, cid, r.value))).props("color=negative unelevated")

                    def resolve_form(dlg: Any) -> None:
                        r = ui.textarea("Resolution notes").props("outlined").classes("w-full")
                        ui.button("Resolve", on_click=_act(lambda: c.officer.resolve(user.ctx, cid, r.value))).props("color=positive unelevated")

                    for label, icon, form in (("Remark", "chat", remark_form), ("Field visit", "directions_walk", visit_form), ("Inspection", "fact_check", inspection_form), ("Work order", "build", wo_form),
                                               ("Coordination", "groups", coord_form), ("Progress", "trending_up", progress_form), ("Assign / reassign", "person_add", assign_form),
                                               ("Escalate", "priority_high", escalate_form), ("Resolve", "check_circle", resolve_form)):  # fmt: skip
                        if label == "Assign / reassign" and user.ctx.role is Role.ADMIN:
                            continue
                        dialog_button(label, icon, form)
                    ui.button("Open investigation", icon="search", on_click=_act(lambda: c.investigations.open(user.ctx, "complaint", cid), "Investigation opened.")).props("outline dense")

            with ui.column().classes("gap-4").style("min-width: 280px; max-width: 340px; flex: 1;"):
                section_title("Status timeline")
                with ui.column().classes("cl-card w-full"):
                    _timeline(c, d["timeline"])
                section_title("History (including internal notes)")
                _events(d["events"])

    @page(c, "/officer/investigations", "nav.investigations", roles=OFFICER_UP)
    def investigations(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.investigations"), icon="search")
        items = c.investigations.list(user.ctx)
        data_table([("subject", "Subject"), ("status", tr(c, "lbl.status")), ("created", tr(c, "lbl.created"))], [{"id": i.id, "subject": f"{i.subject_type} {i.subject_id[:8]}", "status": i.status, "created": i.created_at.strftime("%d %b %Y")} for i in items],
                   on_row=lambda r: ui.navigate.to(f"/officer/investigations/{r['id']}"), empty="No investigations yet.")

    @page(c, "/officer/investigations/{inv_id}", "nav.investigations", roles=OFFICER_UP)
    def investigation(c: AppContainer, user: UiUser, inv_id: str) -> None:
        rep = c.investigations.report(user.ctx, inv_id)
        inv = rep["investigation"]
        page_header(f"Investigation: {inv.subject_type} {inv.subject_id[:8]}", icon="search", actions=lambda: chip(inv.status, color="info"))
        if "complaint" in rep:
            cm = rep["complaint"]
            with ui.row().classes("gap-6 w-full flex-wrap"):
                with ui.column().classes("gap-3 flex-1").style("min-width: 320px;"):
                    with ui.column().classes("cl-card gap-2 w-full"):
                        ui.label(f"{cm.reference}: {cm.title}").classes("text-sm font-semibold").style("color: var(--cl-fg);")
                        divider()
                        ui.label(f"Location: {rep['location']}").classes("text-xs").style("color: var(--cl-fg-muted);")
                        ui.label(f"Nearby same-category complaints (500 m, 30 d): {len(rep['nearby_same_category'])}").classes("text-xs").style("color: var(--cl-fg-muted);")
                        ui.label(f"Ward/category cluster: {len(rep['ward_category_cluster'])}").classes("text-xs").style("color: var(--cl-fg-muted);")
                        ui.label("Duplicates flagged at intake: " + (", ".join(x["reference"] for x in rep["duplicates"]) or "none")).classes("text-xs").style("color: var(--cl-fg-muted);")
                        ui.label("Open anomalies: " + (", ".join(a.explanation for a in rep["anomalies"]) or "none")).classes("text-xs").style("color: var(--cl-fg-muted);")
                        ui.label("Document assistant: " + str(rep["rag_findings"].get("status")) + " - " + str(rep["rag_findings"].get("answer") or "")).classes("text-xs").style("color: var(--cl-fg-muted);")
                        ui.label("Legal sources: " + str(rep["legal_sources"].get("status")) + " (" + str(len(rep["legal_sources"].get("precedents", []))) + " verified records; metadata only)").classes("text-xs").style("color: var(--cl-fg-muted);")
                    section_title("Audit trail")
                    data_table([("at", "When"), ("action", "Action"), ("actor", "Actor")], [{"id": str(i), "at": e.occurred_at.strftime("%d %b %H:%M"), "action": e.action, "actor": (e.actor_id or "system")[:8]} for i, e in enumerate(rep["audit_trail"])])
                with ui.column().classes("gap-3").style("min-width: 280px; max-width: 340px; flex: 1;"):
                    section_title("Status timeline")
                    with ui.column().classes("cl-card w-full"):
                        _timeline(c, rep["timeline"])
        section_title("Notes")
        with ui.column().classes("cl-card gap-2 w-full max-w-2xl"):
            if not inv.notes:
                ui.label("No notes yet.").classes("text-sm").style("color: var(--cl-fg-subtle);")
            for n in inv.notes:
                ui.label(f"{n['at'][:16]} - {n['text']}").classes("text-sm").style("color: var(--cl-fg);")
            if inv.status == "open":
                divider()
                t = ui.textarea("Add note").props("outlined").classes("w-full")
                with ui.row().classes("gap-2"):
                    ui.button(tr(c, "act.save"), on_click=_act(lambda: c.investigations.add_note(user.ctx, inv_id, t.value))).props("color=primary unelevated")
                    ui.button("Close investigation", on_click=_act(lambda: c.investigations.close(user.ctx, inv_id))).props("outline")

"""Officer pages: department dashboard, queue, complaint detail with workflow actions, investigation mode."""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any

from nicegui import ui

from app.container import AppContainer
from app.core.authorization import Role
from app.core.exceptions import CivicLensError
from app.core.transactions import run_in_uow
from app.services.complaint_status import TRANSITIONS, ComplaintStatus
from app.services.sla_service import SlaCalculator, SlaSubject
from app.ui import theme
from app.ui.base import UiUser, data_table, info_banner, page, tr
from app.ui.components import chip, divider, page_header, section_title, stat_tile, state_panel
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


def investigation_subjects(c: AppContainer, items: list[Any]) -> dict[str, str]:
    """A readable subject per investigation: the complaint's reference and title instead of a UUID prefix."""

    def label(uow: Any, i: Any) -> str:
        if i.subject_type == "complaint":
            cm = uow.complaints.get(i.subject_id)
            if cm is not None:
                return f"{cm.reference} · {cm.title[:60]}"
        return f"{i.subject_type.replace('_', ' ').capitalize()} {i.subject_id[:8]}"

    return run_in_uow(c, lambda uow: {i.id: label(uow, i) for i in items})


def register(c: AppContainer) -> None:
    @page(c, "/officer", "nav.officer", roles=OFFICER_UP)
    def officer_dashboard(c: AppContainer, user: UiUser) -> None:
        d = c.dashboards.department(user.ctx)
        dept_names = run_in_uow(c, lambda uow: {x.code: x.name for x in uow.config.departments()})
        page_header(tr(c, "nav.officer"), dept_names.get(d["department_code"] or "", d["department_code"]) or "All departments", icon="space_dashboard")
        if not d["has_data"]:
            state_panel(icon="inbox", title=tr(c, "msg.no_data"))
            return
        with ui.row().classes("gap-3 w-full flex-wrap"):
            stat_tile(tr(c, "card.open"), d["open"], color="info", icon="assignment")
            stat_tile(tr(c, "card.resolved"), d["resolved"], color="success", icon="task_alt")
            stat_tile(tr(c, "card.overdue"), d["sla"]["breached"], color="danger", icon="report")
            stat_tile(tr(c, "card.at_risk"), d["sla"]["at_risk"], color="warning", icon="schedule")
            stat_tile(tr(c, "card.escalated"), d["escalated"], color="danger", icon="trending_up")
            sat = d.get("satisfaction")
            stat_tile("Citizen rating", f"{sat['average']} / 5" if sat else "-", color="warning", icon="star", hint=f"from {sat['count']} rated resolution(s)" if sat else "no ratings yet")
        if d["resolution_hours"]:
            with ui.row().classes("cl-card w-full items-center gap-2"):
                ui.icon("timer").style("color: var(--cl-fg-muted);")
                def hours(h: float) -> str:
                    return "under an hour" if h < 1 else f"{h:.0f} h" if h < 48 else f"{h / 24:.1f} days"

                rh = d["resolution_hours"]
                ui.label(f"Typical resolution time: {hours(rh['median'])} (median), {hours(rh['mean'])} on average, over {rh['count']} resolved.").classes("text-sm").style("color: var(--cl-fg-muted);")
        if user.ctx.department_id:
            # the first thing an officer needs: which complaints are about to or already missed their deadline
            calc = SlaCalculator(run_in_uow(c, lambda uow: list(uow.config.sla_policies())))
            now = c.clock()
            urgent = []
            for x in c.officer.queue(user.ctx, limit=200):
                st = calc.status(SlaSubject(x.id, x.priority, x.department_code, x.status, x.created_at, x.sla_due_at, x.escalation_level), now)
                if st.state in ("breached", "at_risk"):
                    urgent.append((0 if st.state == "breached" else 1, st.remaining.total_seconds() if st.remaining is not None else 0, x, st))
            urgent.sort(key=lambda t: (t[0], t[1]))
            with ui.row().classes("items-center justify-between w-full"):
                section_title("Needs your attention", "Overdue first, then the ones closest to their deadline.")
                ui.link("Open the full queue", "/officer/queue").classes("text-sm")
            if not urgent:
                state_panel(icon="task_alt", title="Nothing overdue or at risk", body="Every open complaint in your department is inside its deadline.", tone="success")
            with ui.column().classes("gap-2 w-full"):
                for _rank, _secs, x, st in urgent[:5]:
                    hrs = (st.remaining.total_seconds() / 3600) if st.remaining is not None else 0
                    row = ui.row().classes("cl-card cl-card-hover w-full items-center gap-3 no-wrap").style(f"border-left: 4px solid var(--cl-{'danger' if st.state == 'breached' else 'warning'});")
                    with row:
                        with ui.column().classes("gap-0 flex-1").style("min-width: 0;"):
                            ui.label(x.title).classes("text-sm font-semibold cl-clip-1").style("color: var(--cl-fg);")
                            ui.label(f"{x.reference} · {(x.ward or 'no ward').replace('_', ' ')}").classes("text-xs cl-mono").style("color: var(--cl-fg-subtle);")
                        chip(x.priority, color=theme.PRIORITY_COLOR.get(x.priority, "muted"))
                        chip(f"{-hrs:.0f} h overdue" if hrs < 0 else f"{hrs:.0f} h left", color="danger" if st.state == "breached" else "warning", icon="schedule")
                        ui.icon("chevron_right").style("color: var(--cl-fg-subtle);")
                    row.on("click", lambda _e, i=x.id: ui.navigate.to(f"/officer/complaints/{i}"))
        with ui.row().classes("gap-4 w-full flex-wrap"):
            with ui.column().classes("cl-card").style("flex: 1; min-width: 320px;"):
                section_title(tr(c, "of.by_category"))
                # donut + legend: the old outer labels overlapped whenever two small slices sat side by side
                ui.echart({"tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"}, "legend": {"orient": "vertical", "right": 0, "top": "middle", "textStyle": {"color": "#9aa3b8"}},
                           "series": [{"type": "pie", "radius": ["45%", "72%"], "center": ["38%", "50%"], "label": {"show": False}, "itemStyle": {"borderColor": "#0f1220", "borderWidth": 2},
                                       "data": [{"name": k.replace("_", " ").capitalize(), "value": v} for k, v in sorted(d["by_category"].items(), key=lambda kv: -kv[1])]}]}).classes("w-full h-56")  # fmt: skip
            with ui.column().classes("cl-card").style("flex: 1.4; min-width: 380px;"):
                section_title(tr(c, "of.per_day"))
                ui.echart({"grid": {"left": 36, "right": 12, "top": 12, "bottom": 24}, "xAxis": {"type": "category", "data": [t["date"][5:] for t in d["trend_daily"]]}, "yAxis": {"type": "value"}, "series": [{"type": "line", "areaStyle": {}, "data": [t["count"] for t in d["trend_daily"]]}]}).classes("w-full h-56")
        section_title(tr(c, "col.workload"))
        names = run_in_uow(c, lambda uow: {k: uow.officers.user_label(k) for k in d["workload"]})
        data_table([("officer", tr(c, "role.officer")), ("open", tr(c, "card.open"))], [{"id": k, "officer": names.get(k) or k[:8], "open": v} for k, v in sorted(d["workload"].items(), key=lambda kv: -kv[1])], empty=tr(c, "of.no_work"))
        if d["anomalies"]:
            section_title(tr(c, "of.open_anomalies"))
            with ui.column().classes("gap-2 w-full"):
                for a in d["anomalies"]:
                    info_banner(f"[{a.severity}] {a.explanation}", "orange")

    @page(c, "/officer/queue", "nav.officer_queue", roles=STAFF)
    def queue(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.officer_queue"), "Most urgent first: overdue, then at risk, then by priority. Click a row to act on it.", icon="inbox")
        with ui.row().classes("gap-3 items-center w-full flex-wrap"):
            search = ui.input(placeholder="Search reference or title").props("outlined dense clearable").classes("w-72")
            with search.add_slot("prepend"):
                ui.icon("search")
            mine = ui.switch("Only mine").props("color=primary")
            status = ui.select({"": "All", **{s.value: s.value.replace("_", " ") for s in ComplaintStatus}}, value="", label=tr(c, "lbl.status")).props("outlined dense").classes("w-52")
        summary = ui.row().classes("gap-2 flex-wrap")
        box = ui.column().classes("w-full")
        calc = SlaCalculator(run_in_uow(c, lambda uow: list(uow.config.sla_policies())))
        now = c.clock()
        urgency = {"breached": 0, "at_risk": 1, "on_track": 2, "no_policy": 3, "finished": 4}
        rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        label = {"breached": "Overdue", "at_risk": "At risk", "on_track": "On track", "no_policy": "No SLA policy", "finished": "Closed"}

        def draw() -> None:
            box.clear()
            summary.clear()
            items = c.officer.queue(user.ctx, mine_only=mine.value, statuses=[ComplaintStatus(status.value)] if status.value else None)
            q = (search.value or "").strip().lower()
            if q:
                items = [x for x in items if q in x.reference.lower() or q in (x.title or "").lower()]
            st = {x.id: calc.status(SlaSubject(x.id, x.priority, x.department_code, x.status, x.created_at, x.sla_due_at, x.escalation_level), now) for x in items}
            items.sort(key=lambda x: (urgency.get(st[x.id].state, 9), rank.get(x.priority, 9), x.created_at))

            def due_text(x: Any) -> str:
                s = st[x.id]
                if s.due_at is None:
                    return label[s.state]
                hours = (s.due_at - now).total_seconds() / 3600
                when = f"{abs(hours):.0f} h overdue" if hours < 0 else (f"{hours:.0f} h left" if hours < 48 else f"{hours / 24:.0f} d left")
                return f"{label[s.state]} · {when}"

            counts: dict[str, int] = {}
            for s in st.values():
                counts[s.state] = counts.get(s.state, 0) + 1
            with summary:
                chip(f"{len(items)} in view", color="muted", outline=True)
                for key, tone in (("breached", "danger"), ("at_risk", "warning"), ("on_track", "success"), ("no_policy", "muted")):
                    if counts.get(key):
                        chip(f"{label[key]}: {counts[key]}", color=tone)
                if counts.get("no_policy") and user.ctx.role is not Role.OFFICER:
                    ui.link("Set SLA policies", "/admin/sla").classes("text-xs")
            with box:
                rows = [{"id": x.id, "ref": x.reference, "title": x.title, "status": str(x.status).replace("_", " "), "prio": x.priority, "ward": x.ward or "-", "due": due_text(x)} for x in items]
                data_table([("ref", tr(c, "lbl.reference")), ("title", tr(c, "lbl.title")), ("status", tr(c, "lbl.status")), ("prio", tr(c, "lbl.priority")), ("ward", tr(c, "lbl.ward")), ("due", tr(c, "lbl.due"))], rows,
                           on_row=lambda r: ui.navigate.to(f"/officer/complaints/{r['id']}"), empty="Nothing in this view. New complaints routed to your department appear here in real time.")

        mine.on_value_change(lambda e: draw())
        status.on_value_change(lambda e: draw())
        search.on("keydown.enter", lambda e: draw())
        search.on("clear", lambda e: draw())
        search.on_value_change(lambda e: draw() if not e.value else None)
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
                                ui.label(tr(c, "of.correct_category")).classes("text-base font-semibold").style("color: var(--cl-fg);")
                                ui.label(tr(c, "of.correction_note")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                                sel = ui.select(list(CATEGORIES), value=cm.category, label=tr(c, "of.correct_category")).props("outlined dense").classes("w-full")
                                ui.button(tr(c, "of.save_correction"), on_click=_act(lambda: c.officer.correct_category(user.ctx, cid, sel.value))).props("color=primary unelevated")
                            dlg.open()

                        ui.button(tr(c, "act.correct"), icon="edit", on_click=correct_category_dialog).props("flat dense")
                        if cm.status in (ComplaintStatus.AI_ROUTED, ComplaintStatus.ASSIGNED) and user.ctx.role is Role.OFFICER:

                            def transfer_dialog() -> None:
                                depts = [x.code for x in run_in_uow(c, lambda uow: list(uow.config.departments())) if x.active and x.code != cm.department_code]
                                with ui.dialog() as dlg, ui.column().classes("cl-card gap-3 w-full max-w-sm"):
                                    ui.label("Transfer to another department").classes("text-base font-semibold").style("color: var(--cl-fg);")
                                    ui.label("Use this when the complaint is not your department's work. It moves to the other desk with its SLA recomputed, their officers are notified, and the citizen sees the hand-over.").classes("text-xs").style("color: var(--cl-fg-subtle);")
                                    to = ui.select(depts, label=tr(c, "lbl.department"), value=cm.category if cm.category in depts else None).props("outlined dense").classes("w-full")
                                    why = ui.input("Reason (the citizen sees this)", value="").props("outlined dense").classes("w-full")

                                    def do_transfer() -> None:
                                        try:
                                            c.officer.transfer(user.ctx, cid, to.value or "", why.value or "")
                                        except CivicLensError as exc:
                                            ui.notify(exc.message, type="negative")
                                            return
                                        ui.notify(f"Transferred to {to.value}.", type="positive")
                                        ui.navigate.to("/officer/queue")  # it is no longer this desk's complaint

                                    ui.button("Transfer", icon="swap_horiz", on_click=do_transfer).props("color=primary unelevated")
                                dlg.open()

                            ui.button("Transfer", icon="swap_horiz", on_click=transfer_dialog).props("flat dense")
                    ui.label(f"Routing: {cm.routing.get('source')} - {cm.routing.get('explanation')}").classes("text-xs").style("color: var(--cl-fg-muted);")
                    if cm.routing.get("ai_disagreement"):
                        ui.label(f"AI disagreed with the rule: {cm.routing['ai_disagreement']}").classes("text-xs").style("color: var(--cl-warning);")
                    ui.label("Priority factors: " + "; ".join(cm.priority_factors)).classes("text-xs").style("color: var(--cl-fg-muted);")
                    if sla.remaining is not None:
                        hrs = sla.remaining.total_seconds() / 3600
                        ui.label(f"SLA due {sla.due_at:%d %b %H:%M} · " + (f"{-hrs:.0f} h overdue" if hrs < 0 else f"{hrs:.0f} h left")).classes("text-xs font-medium").style(f"color: var(--cl-{'danger' if hrs < 0 else 'fg-muted'});")

                section_title(tr(c, "col.actions"))
                allowed = [st for st in TRANSITIONS[cm.status] if st not in (ComplaintStatus.RESOLVED, ComplaintStatus.AI_ROUTED)]  # resolve has its own form; re-route is Transfer
                # the obvious next move for this status, one click away (remarks optional)
                next_steps = {ComplaintStatus.ASSIGNED: [(ComplaintStatus.UNDER_REVIEW, "Start review", "play_arrow")],
                              ComplaintStatus.UNDER_REVIEW: [(ComplaintStatus.IN_PROGRESS, "Start work", "construction")],
                              ComplaintStatus.INSPECTION_SCHEDULED: [(ComplaintStatus.IN_PROGRESS, "Start work", "construction")],
                              ComplaintStatus.RESOLVED: [(ComplaintStatus.CLOSED, "Close complaint", "lock")]}.get(cm.status, [])  # fmt: skip
                with ui.column().classes("cl-card gap-3 w-full").style("border-color: var(--cl-primary);"):
                    remarks = ui.input(tr(c, "lbl.remarks") + " (optional, the citizen sees status remarks)").props("outlined dense").classes("w-full")
                    with ui.row().classes("gap-2 items-center w-full flex-wrap"):
                        for st, label, icon in next_steps:
                            ui.button(label, icon=icon, on_click=_act(lambda t=st: c.officer.update_status(user.ctx, cid, t, remarks.value or None))).props("color=primary unelevated no-caps")
                        others = [st for st in allowed if st not in {x[0] for x in next_steps}]
                        if others:
                            target = ui.select({st.value: st.value.replace("_", " ").capitalize() for st in others}, label=tr(c, "of.move_to")).props("outlined dense").classes("w-56")
                            ui.button(tr(c, "of.update_status"), on_click=lambda: _act(lambda: c.officer.update_status(user.ctx, cid, ComplaintStatus(target.value), remarks.value or None))() if target.value else ui.notify("Pick a status first.", type="warning")).props("outline no-caps")
                        if not next_steps and not others and cm.status not in (ComplaintStatus.IN_PROGRESS,):
                            ui.label("No status change available from here.").classes("text-xs").style("color: var(--cl-fg-subtle);")
                with ui.row().classes("gap-2 flex-wrap"):
                    def dialog_button(label: str, icon: str, build: Any, *, tone: str = "outline") -> None:
                        with ui.dialog() as dlg, ui.column().classes("cl-card gap-3 w-full max-w-sm"):
                            ui.label(label).classes("text-base font-semibold").style("color: var(--cl-fg);")
                            build(dlg)
                        ui.button(label, icon=icon, on_click=dlg.open).props(tone + " dense")

                    def remark_form(dlg: Any) -> None:
                        t = ui.textarea(tr(c, "col.remark")).props("outlined").classes("w-full")
                        internal = ui.checkbox("Internal (hidden from citizen)", value=True)
                        ui.button(tr(c, "act.save"), on_click=_act(lambda: c.officer.remark(user.ctx, cid, t.value, internal=internal.value))).props("color=primary unelevated")

                    def visit_form(dlg: Any) -> None:
                        when = ui.input(tr(c, "of.scheduled_for")).props("outlined").classes("w-full")
                        n = ui.textarea(tr(c, "col.notes")).props("outlined").classes("w-full")

                        def go() -> None:
                            try:
                                when_dt = datetime.fromisoformat((when.value or "").replace(" ", "T")).astimezone()
                            except ValueError:
                                ui.notify(tr(c, "of.date_format"), type="negative")
                                return
                            _act(lambda: c.officer.field_visit(user.ctx, cid, when_dt, n.value))()

                        ui.button(tr(c, "act.save"), on_click=go).props("color=primary unelevated")

                    def inspection_form(dlg: Any) -> None:
                        f = ui.textarea(tr(c, "col.findings")).props("outlined").classes("w-full")
                        ui.button(tr(c, "act.save"), on_click=_act(lambda: c.officer.inspection(user.ctx, cid, f.value))).props("color=primary unelevated")

                    def wo_form(dlg: Any) -> None:
                        ref, desc, team = ui.input(tr(c, "of.work_order")).props("outlined").classes("w-full"), ui.textarea(tr(c, "lbl.description")).props("outlined").classes("w-full"), ui.input(tr(c, "col.team")).props("outlined").classes("w-full")
                        ui.button(tr(c, "act.save"), on_click=_act(lambda: c.officer.work_order(user.ctx, cid, ref.value, desc.value, team.value))).props("color=primary unelevated")

                    def coord_form(dlg: Any) -> None:
                        w, n = ui.input(tr(c, "of.with_team")).props("outlined").classes("w-full"), ui.textarea(tr(c, "col.note")).props("outlined").classes("w-full")
                        ui.button(tr(c, "act.save"), on_click=_act(lambda: c.officer.coordination_note(user.ctx, cid, w.value or "", n.value))).props("color=primary unelevated")

                    def progress_form(dlg: Any) -> None:
                        p, n = ui.slider(min=0, max=100, value=50).props("label-always color=primary"), ui.input(tr(c, "col.notes")).props("outlined").classes("w-full")
                        ui.button(tr(c, "act.save"), on_click=_act(lambda: c.officer.progress(user.ctx, cid, int(p.value), n.value))).props("color=primary unelevated")

                    def assign_form(dlg: Any) -> None:
                        from app.core.transactions import run_in_uow

                        people = run_in_uow(c, lambda uow: {i: uow.officers.user_label(i) or i[:8] for i in uow.officers.officer_ids_for_department(cm.department_code)} if cm.department_code else {})
                        sel = ui.select(people, label=tr(c, "role.officer"), value=cm.assigned_officer_id if cm.assigned_officer_id in people else None).props("outlined dense").classes("w-full")
                        ui.button(tr(c, "act.save"), on_click=_act(lambda: c.officer.assign(user.ctx, cid, sel.value))).props("color=primary unelevated")

                    def escalate_form(dlg: Any) -> None:
                        r = ui.textarea(tr(c, "col.reason")).props("outlined").classes("w-full")
                        ui.button(tr(c, "col.escalate"), on_click=_act(lambda: c.officer.escalate(user.ctx, cid, r.value))).props("color=negative unelevated")

                    def resolve_form(dlg: Any) -> None:
                        r = ui.textarea(tr(c, "of.resolution_notes")).props("outlined").classes("w-full")
                        ui.button(tr(c, "col.resolve"), on_click=_act(lambda: c.officer.resolve(user.ctx, cid, r.value))).props("color=positive unelevated")

                    for label, icon, form in (("Remark", "chat", remark_form), ("Field visit", "directions_walk", visit_form), ("Inspection", "fact_check", inspection_form), ("Work order", "build", wo_form),
                                               ("Coordination", "groups", coord_form), ("Progress", "trending_up", progress_form), ("Assign / reassign", "person_add", assign_form),
                                               ("Escalate", "priority_high", escalate_form), ("Resolve", "check_circle", resolve_form)):  # fmt: skip
                        if label == "Assign / reassign" and user.ctx.role is Role.ADMIN:
                            continue
                        dialog_button(label, icon, form)
                    ui.button(tr(c, "of.open_investigation"), icon="search", on_click=_act(lambda: c.investigations.open(user.ctx, "complaint", cid), "Investigation opened.")).props("outline dense")

                if cm.lat is not None:
                    section_title(tr(c, "lbl.location"))
                    m = ui.leaflet(center=(cm.lat, cm.lng), zoom=15).classes("w-full h-56").style("border-radius: var(--cl-radius-md); overflow: hidden;")
                    m.marker(latlng=(cm.lat, cm.lng))

                if cm.duplicates:
                    section_title(tr(c, "of.duplicates"), tr(c, "of.duplicates_sub"))
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
                                    decision = ui.select(["confirmed_duplicate", "related", "not_duplicate"], value="related", label=tr(c, "col.decision")).props("outlined dense").classes("w-56")
                                    note = ui.input(tr(c, "col.note")).props("outlined dense").classes("w-56")
                                    ui.button(tr(c, "of.save_decision"), on_click=_act(lambda o=x["complaint_id"], d=decision, n=note: c.duplicate_reviews.decide(user.ctx, cid, o, d.value, n.value))).props("outline dense")

                section_title(tr(c, "lbl.evidence"))
                if not d["evidence"]:
                    state_panel(icon="attach_file", title=tr(c, "gr.no_evidence"))
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
                                    ui.button(tr(c, "of.rerun"), on_click=_act(lambda i=ev.id: c.complaints.request_analysis(user.ctx, i), "Analysis queued.")).props("flat dense")

                government_panel(c, user.ctx, cid)


            with ui.column().classes("gap-4").style("min-width: 280px; max-width: 340px; flex: 1;"):
                section_title(tr(c, "gr.status_timeline"))
                with ui.column().classes("cl-card w-full"):
                    _timeline(c, d["timeline"])
                section_title(tr(c, "of.history"))
                _events(d["events"])

    @page(c, "/officer/investigations", "nav.investigations", roles=OFFICER_UP)
    def investigations(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.investigations"), icon="search")
        items = c.investigations.list(user.ctx)
        subjects = investigation_subjects(c, items)
        data_table([("subject", tr(c, "col.subject")), ("status", tr(c, "lbl.status")), ("created", tr(c, "lbl.created"))], [{"id": i.id, "subject": subjects[i.id], "status": i.status, "created": i.created_at.strftime("%d %b %Y")} for i in items],
                   on_row=lambda r: ui.navigate.to(f"/officer/investigations/{r['id']}"), empty=tr(c, "of.no_investigations"))

    @page(c, "/officer/investigations/{inv_id}", "nav.investigations", roles=OFFICER_UP)
    def investigation(c: AppContainer, user: UiUser, inv_id: str) -> None:
        rep = c.investigations.report(user.ctx, inv_id)
        inv = rep["investigation"]
        subject = investigation_subjects(c, [inv])[inv.id]
        page_header(f"Investigation · {subject}", "Everything CivicLens knows about this case, gathered in one place.", icon="search", actions=lambda: chip(inv.status, color="info" if inv.status == "open" else "muted"))
        if "complaint" in rep:
            cm = rep["complaint"]
            loc = rep.get("location") or {}
            where = ", ".join(str(x) for x in (loc.get("address"), loc.get("ward") and f"ward {loc['ward']}", loc.get("city")) if x) if isinstance(loc, dict) else str(loc)
            if isinstance(loc, dict) and loc.get("lat") is not None and not where:
                where = f"{loc['lat']:.4f}, {loc['lng']:.4f} (GPS only)"
            rag, legal = rep["rag_findings"], rep["legal_sources"]
            findings = [
                ("place", "Location", where or "No location given"),
                ("near_me", "Same-category complaints within 500 m (30 days)", str(len(rep["nearby_same_category"]))),
                ("hub", "Same ward and category", str(len(rep["ward_category_cluster"]))),
                ("content_copy", "Possible duplicates flagged at intake", ", ".join(x["reference"] for x in rep["duplicates"]) or "None"),
                ("warning", "Open anomalies", "; ".join(a.explanation for a in rep["anomalies"]) or "None"),
                ("description", "From the citizen's documents", (rag.get("answer") or "").strip() if rag.get("status") == "answered" else "Nothing relevant found in the documents on file"),
                ("gavel", "Legal sources", f"{len(legal.get('precedents', []))} verified precedent record(s)" + (" - metadata only" if legal.get("status") == "precedents_only" else "")),
            ]  # fmt: skip
            actors = run_in_uow(c, lambda uow: {a: uow.officers.user_label(a) for a in {e.actor_id for e in rep["audit_trail"] if e.actor_id}})
            with ui.row().classes("gap-6 w-full flex-wrap"):
                with ui.column().classes("gap-3 flex-1").style("min-width: 320px;"):
                    with ui.column().classes("cl-card gap-3 w-full"):
                        with ui.row().classes("items-center justify-between w-full gap-2"):
                            ui.label(f"{cm.reference}: {cm.title}").classes("text-sm font-semibold").style("color: var(--cl-fg);")
                            ui.button("Open complaint", icon="open_in_new", on_click=lambda: ui.navigate.to(f"/officer/complaints/{cm.id}")).props("flat dense no-caps")
                        divider()
                        for icon, label, value in findings:
                            with ui.row().classes("items-start gap-3 w-full no-wrap"):
                                ui.icon(icon).classes("text-[18px] q-mt-xs").style("color: var(--cl-primary);")
                                with ui.column().classes("gap-0").style("min-width: 0;"):
                                    ui.label(label).classes("text-xs").style("color: var(--cl-fg-subtle);")
                                    ui.label(value).classes("text-sm").style("color: var(--cl-fg);")
                    section_title(tr(c, "of.audit_trail"))
                    data_table([("at", tr(c, "legal.col_when")), ("action", tr(c, "col.action")), ("actor", tr(c, "col.actor"))],
                               [{"id": str(i), "at": e.occurred_at.strftime("%d %b %H:%M"), "action": e.action.replace("_", " "), "actor": actors.get(e.actor_id or "") or (e.actor_id or "system")[:8]} for i, e in enumerate(rep["audit_trail"])])  # fmt: skip
                with ui.column().classes("gap-3").style("min-width: 280px; max-width: 340px; flex: 1;"):
                    section_title(tr(c, "gr.status_timeline"))
                    with ui.column().classes("cl-card w-full"):
                        _timeline(c, rep["timeline"])
        section_title(tr(c, "col.notes"))
        with ui.column().classes("cl-card gap-2 w-full max-w-2xl"):
            if not inv.notes:
                ui.label(tr(c, "of.no_notes")).classes("text-sm").style("color: var(--cl-fg-subtle);")
            for n in inv.notes:
                with ui.row().classes("items-start gap-3 w-full no-wrap"):
                    ui.label(str(n["at"])[:16].replace("T", " ")).classes("text-xs cl-mono").style("color: var(--cl-fg-subtle); min-width: 120px;")
                    ui.label(n["text"]).classes("text-sm").style("color: var(--cl-fg);")
            if inv.status == "open":
                divider()
                t = ui.textarea(tr(c, "of.add_note")).props("outlined").classes("w-full")
                with ui.row().classes("gap-2"):
                    ui.button(tr(c, "act.save"), on_click=_act(lambda: c.investigations.add_note(user.ctx, inv_id, t.value))).props("color=primary unelevated")
                    ui.button(tr(c, "of.close_investigation"), on_click=_act(lambda: c.investigations.close(user.ctx, inv_id))).props("outline")

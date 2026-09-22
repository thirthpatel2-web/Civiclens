"""Citizen pages: dashboard, report, tracker, RTI, legal, copilot, GIS, emergency, profile, settings, notifications, documents."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from nicegui import app, ui

from app.container import AppContainer
from app.core.exceptions import CivicLensError
from app.core.transactions import run_in_uow
from app.services.classification_service import CATEGORIES
from app.services.complaint_service import ComplaintInput
from app.services.complaint_status import TRACKER_FILTERS
from app.services.rti_service import RtiDraft, build_rti_questions, default_records_for_category
from app.ui import theme
from app.ui.base import UiUser, data_table, error_banner, info_banner, lang, page, tr
from app.ui.components import (
    chat_bubble,
    chip,
    divider,
    field_hint,
    page_header,
    run_with_loading,
    section_title,
    stat_tile,
    state_panel,
    status_timeline,
)
from app.ui.navigation import CIT


def helpline_cards(c: AppContainer) -> None:
    data = c.emergency.list(lang())
    with ui.row().classes("cl-card w-full items-center gap-3").style("background: var(--cl-emergency-soft); border-color: transparent;"):
        ui.icon("warning").classes("text-[22px]").style("color: var(--cl-emergency);")
        ui.label(tr(c, "msg.emergency_warning")).classes("text-sm font-medium").style("color: var(--cl-emergency);")
    section_title(tr(c, "emergencyHelplines"))
    if not data["configured"]:
        state_panel(icon="support_agent", title="No emergency contacts configured", body="Ask an administrator to add them under Admin -> Emergency Contacts.")
        return
    with ui.row().classes("gap-4 flex-wrap w-full"):
        for h in data["items"]:
            with ui.column().classes("cl-card gap-2").style("width: 236px;"):
                with ui.row().classes("items-center gap-2"):
                    with ui.element("div").classes("cl-stat-icon").style("background: var(--cl-emergency-soft); color: var(--cl-emergency); width:34px; height:34px;"):
                        ui.icon("call").classes("text-[16px]")
                    ui.label(h["name"]).classes("text-sm font-semibold").style("color: var(--cl-fg);")
                ui.label(h["description"]).classes("text-xs cl-clip-2").style("color: var(--cl-fg-muted); min-height: 2.4em;")
                ui.link(h["number"], h["tel_uri"]).classes("text-2xl font-extrabold no-underline").style("color: var(--cl-emergency);")
                if not h["translated"]:
                    chip("English only", color="muted", outline=True)


def government_panel(c: AppContainer, ctx: Any, complaint_id: str) -> None:
    states = c.government.states(ctx, complaint_id)
    if not states:
        return
    section_title("Government platforms", "Shared only where an integration is configured and you have consented.")
    tone_for = {"submitted": "success", "not_started": "muted", "consent_required": "warning", "not_configured": "muted", "failed": "danger"}
    with ui.column().classes("gap-2 w-full"):
        for st in states:
            with ui.row().classes("cl-card w-full items-center justify-between gap-3 flex-wrap"):
                with ui.column().classes("gap-1"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(st["display_name"]).classes("text-sm font-medium").style("color: var(--cl-fg);")
                        chip(st["state"].replace("_", " "), color=tone_for.get(st["state"], "info"))
                    if st["external_reference"]:
                        ui.label(f"Reference {st['external_reference']}").classes("text-xs").style("color: var(--cl-fg-muted);")
                    ui.label(f"Integration: {st['adapter_state']}" + ("" if st["consent_granted"] else " - consent not granted")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                    if st["last_error"]:
                        ui.label(st["last_error"]).classes("text-xs").style("color: var(--cl-warning);")
                if st["state"] in ("not_started", "consent_required", "not_configured", "failed"):
                    ui.button("Request submission", on_click=lambda p=st["platform"]: (c.government.request(ctx, complaint_id, p), ui.navigate.reload())).props("outline dense")


def _timeline(c: AppContainer, steps: list[Any]) -> None:
    status_timeline(steps)


def _events(events: list[Any]) -> None:
    with ui.column().classes("gap-2 w-full"):
        for e in reversed(events):
            with ui.row().classes("cl-card w-full items-start gap-3"):
                with ui.element("div").classes("cl-stat-icon").style("background: var(--cl-surface-alt); color: var(--cl-fg-muted); width:32px; height:32px; flex: none;"):
                    ui.icon(theme.STATUS_ICON.get(str(e.to_status), "history") if e.to_status else "notes").classes("text-[16px]")
                with ui.column().classes("gap-1 flex-1"):
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        ui.label(e.kind.replace("_", " ").title()).classes("text-sm font-medium").style("color: var(--cl-fg);")
                        if e.to_status:
                            chip(str(e.to_status).replace("_", " "), color=theme.STATUS_COLOR.get(str(e.to_status), "muted"))
                    ui.label(f"{e.actor_label or 'System'} · {e.at.strftime('%d %b %H:%M')}").classes("text-xs").style("color: var(--cl-fg-subtle);")
                    if e.remarks:
                        ui.label(e.remarks).classes("text-sm").style("color: var(--cl-fg-muted);")


# Where each IntentRouter destination actually goes *in this web app*. The label is the page that
# really opens, so the assistant never announces a screen that does not exist here (the mobile app
# has dedicated Locator/Directory screens; on web the closest real surface is the GIS map).
DEST_ROUTE: dict[str, tuple[str, str, str]] = {
    "complaint": ("add_circle", "nav.report", "/report"),
    "rti": ("gavel", "nav.rti", "/rti"),
    "legal": ("balance", "nav.legal", "/legal"),
    "track": ("assignment", "nav.grievances", "/grievances"),
    "map": ("map", "nav.gis", "/gis"),
    "locator": ("map", "nav.gis", "/gis"),
    "document": ("folder", "nav.documents", "/documents"),
    "emergency": ("emergency", "nav.emergency", "/emergency"),
}

# Browser-side recorder. NiceGUI has no built-in microphone element, so this uses MediaRecorder
# directly and hands the clip back as one base64 event. Failures (no permission, no device, an
# insecure origin) are reported to the page instead of silently doing nothing.
MIC_JS = """
window._clRec = window._clRec || {};
window.clStartRec = async function () {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    const mr = new MediaRecorder(stream);
    const chunks = [];
    mr.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    mr.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      const buf = await new Blob(chunks, {type: mr.mimeType}).arrayBuffer();
      const bytes = new Uint8Array(buf);
      let bin = '';
      for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      emitEvent('cl_audio', {mime: mr.mimeType, b64: btoa(bin)});
    };
    window._clRec.mr = mr;
    mr.start();
    return true;
  } catch (err) {
    emitEvent('cl_audio_error', {message: String(err && err.message || err)});
    return false;
  }
};
window.clStopRec = function () {
  const mr = window._clRec.mr;
  if (mr && mr.state !== 'inactive') mr.stop();
};
"""


def register(c: AppContainer) -> None:
    @page(c, "/assistant", "nav.assistant")
    def assistant_router(c: AppContainer, user: UiUser) -> None:
        """Type or speak the problem; the app works out which desk it belongs to and takes you
        there with the text already filled in. Both layers are rules-first and show their working:
        the destination comes from ``IntentRouter``, the civic category from ``ClassificationService``.
        """
        import base64

        page_header(tr(c, "nav.assistant"), tr(c, "page.assistant_help"), icon="record_voice_over")
        state: dict[str, Any] = {"text": "", "dest": None, "voice_id": None, "recording": False}
        caps = c.voice.capabilities()

        with ui.column().classes("w-full max-w-3xl gap-3"):
            with ui.element("div").classes("cl-ask w-full"):
                ui.icon("auto_awesome").classes("text-[20px]").style("color: var(--cl-ai);")
                box = ui.input(placeholder=tr(c, "assistant.placeholder")).props("borderless debounce=400").classes("flex-1")
                mic = ui.button(icon="mic").props("round unelevated").style("background: var(--cl-ai); color: #fff;")
                mic.tooltip(tr(c, "assistant.mic_tip") if caps["state"] == "CONFIGURED" else tr(c, "assistant.mic_off"))
                mic.set_enabled(caps["state"] == "CONFIGURED")
            hint = ui.label(tr(c, "assistant.hint")).classes("text-xs").style("color: var(--cl-fg-subtle);")
            out = ui.column().classes("w-full gap-3")

        def go(dest: str) -> None:
            from urllib.parse import quote

            _icon, _key, route = DEST_ROUTE[dest]
            text = (state["text"] or "")[:1500]
            sep = "&" if "?" in route else "?"
            ui.navigate.to(f"{route}{sep}text={quote(text)}" + (f"&voice={state['voice_id']}" if state["voice_id"] and dest == "complaint" else ""))

        def render() -> None:
            out.clear()
            text = (state["text"] or "").strip()
            if len(text) < 4:
                with out:
                    state_panel(icon="lightbulb", title=tr(c, "assistant.idle_title"), body=tr(c, "assistant.idle_body"))
                return
            intent = c.intent_router.route(text)
            dest = intent.destination
            state["dest"] = dest
            icon, label_key, _route = DEST_ROUTE[dest]
            with out:
                with ui.column().classes("cl-card cl-route-card w-full gap-3"):
                    with ui.row().classes("items-center gap-3 w-full flex-wrap"):
                        with ui.element("div").classes("cl-brand-chip").style("width:40px; height:40px;"):
                            ui.icon(icon).classes("text-[20px]")
                        with ui.column().classes("gap-0 flex-1"):
                            ui.label(tr(c, "assistant.goes_to")).classes("text-xs").style("color: var(--cl-fg-muted);")
                            ui.label(tr(c, label_key)).classes("text-base font-bold").style("color: var(--cl-fg);")
                        ui.button(tr(c, "assistant.take_me"), icon="arrow_forward", on_click=lambda d=dest: go(d)).props("unelevated").classes("cl-btn-glow")

                    if dest == "complaint":
                        r = c.classifier.classify("", text)
                        with ui.row().classes("gap-2 flex-wrap items-center"):
                            chip(tr(c, "lbl.category") + ": " + (r.category.replace("_", " ").title() if r.category != "other" else tr(c, "assistant.unsure")), color="info")
                            chip(tr(c, "lbl.severity") + ": " + r.severity, color={"low": "muted", "medium": "info", "high": "warning", "critical": "danger"}[r.severity])
                            chip(f"{tr(c, 'assistant.confidence')} {r.confidence:.0%}", color="muted", outline=True)
                            chip(tr(c, "assistant.decided_by_rules") if r.source == "rules" else tr(c, "assistant.decided_by_ai"), color="ai", outline=True)
                        if r.affects_safety or r.near_sensitive_site:
                            info_banner(tr(c, "assistant.safety_flag"), "orange")
                        if r.ai_status == "not_configured" and r.ambiguous:
                            info_banner(tr(c, "msg.ai_unavailable"), "orange")
                        ui.label(r.explanation or "").classes("text-xs").style("color: var(--cl-fg-subtle);")
                        if r.category == "other":
                            info_banner(tr(c, "assistant.manual_triage"), "blue")
                    else:
                        ui.label(intent.explanation).classes("text-xs").style("color: var(--cl-fg-subtle);")
                        if not intent.certain:
                            info_banner(tr(c, "assistant.ambiguous"), "orange")

                # One-tap correction. The router is never treated as final: whatever the person
                # picks here is what actually opens.
                others = [d for d in DEST_ROUTE if d != dest and d != "locator"]
                with ui.column().classes("w-full gap-2"):
                    ui.label(tr(c, "assistant.not_right")).classes("text-xs font-medium").style("color: var(--cl-fg-muted);")
                    with ui.row().classes("gap-2 flex-wrap"):
                        for d in others:
                            di, dk, _ = DEST_ROUTE[d]
                            ui.button(tr(c, dk), icon=di, on_click=lambda dd=d: go(dd)).props("outline dense size=sm")

        def on_text(e: Any) -> None:
            state["text"] = e.value or ""
            render()

        box.on_value_change(on_text)

        # ---- voice ------------------------------------------------------------------------------
        ui.add_body_html(f"<script>{MIC_JS}</script>")

        def on_audio(e: Any) -> None:
            state["recording"] = False
            mic.props("icon=mic").classes(remove="cl-mic-live")
            try:
                raw = base64.b64decode(e.args["b64"])
            except (KeyError, ValueError):
                ui.notify(tr(c, "assistant.mic_failed"), type="negative")
                return
            try:
                r = c.voice.transcribe(user.ctx, raw, e.args.get("mime") or "audio/webm", "auto" if caps["auto_detect"] else caps["languages"][0]["code"])
            except CivicLensError as exc:
                ui.notify(exc.message, type="negative")
                return
            if r.status != "OK" or not r.transcript:
                ui.notify(r.error or r.status, type="warning")
                return
            state["voice_id"] = r.id
            box.value = r.transcript  # kept in the spoken language and script - nothing is translated
            state["text"] = r.transcript
            hint.set_text(tr(c, "assistant.heard", lang=r.language_detected or "?", how=r.detected_by))
            render()

        def on_audio_error(e: Any) -> None:
            state["recording"] = False
            mic.props("icon=mic").classes(remove="cl-mic-live")
            ui.notify(tr(c, "assistant.mic_denied") + " " + str(e.args.get("message", "")), type="negative")

        ui.on("cl_audio", on_audio)
        ui.on("cl_audio_error", on_audio_error)

        async def toggle_mic() -> None:
            if state["recording"]:
                state["recording"] = False
                mic.props("icon=mic").classes(remove="cl-mic-live")
                ui.run_javascript("window.clStopRec()")
                return
            state["recording"] = True
            mic.props("icon=stop").classes(add="cl-mic-live")
            hint.set_text(tr(c, "assistant.listening"))
            await ui.run_javascript("window.clStartRec()")

        mic.on_click(toggle_mic)
        render()

    @page(c, "/dashboard", "nav.dashboard", roles=CIT)
    def dashboard(c: AppContainer, user: UiUser) -> None:
        d = c.dashboards.citizen(user.ctx)
        prof = c.profiles.get(user.ctx)
        first_name = (user.full_name or user.email).split(" ")[0]
        page_header(f"{tr(c, 'welcomeBack')}, {first_name}", tr(c, "appTagline"), icon="space_dashboard")
        if not prof.onboarding_complete:
            with ui.row().classes("cl-card w-full items-center justify-between gap-3 flex-wrap").style("background: var(--cl-info-soft); border-color: transparent;"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("info").style("color: var(--cl-info);")
                    ui.label(tr(c, "page.onboarding")).classes("text-sm").style("color: var(--cl-info);")
                ui.button(tr(c, "act.open"), on_click=lambda: ui.navigate.to("/onboarding")).props("outline dense")

        with ui.row().classes("gap-3 w-full flex-wrap"):
            stat_tile(tr(c, "card.active"), d["open"], color="info", icon="assignment")
            stat_tile(tr(c, "card.resolved"), d["resolved"], color="success", icon="task_alt")
            stat_tile(tr(c, "card.unread"), d["unread_notifications"], color="warning", icon="notifications")
            stat_tile("Awaiting your feedback", len(d["pending_feedback"]), color="ai", icon="rate_review")

        with ui.row().classes("gap-3 flex-wrap items-center"):
            ui.button(tr(c, "nav.report"), icon="add_circle", on_click=lambda: ui.navigate.to("/report")).props("unelevated size=lg").classes("cl-btn-glow")
            ui.button(tr(c, "nav.rti"), icon="gavel", on_click=lambda: ui.navigate.to("/rti")).props("outline")
            ui.button(tr(c, "nav.copilot"), icon="smart_toy", on_click=lambda: ui.navigate.to("/copilot")).props("outline")
            ui.button(tr(c, "nav.emergency"), icon="emergency", on_click=lambda: ui.navigate.to("/emergency")).props("flat").style("color: var(--cl-emergency);")

        if not d["has_data"]:
            state_panel(icon="inbox", title=tr(c, "msg.empty_complaints"), body="File your first report to start tracking it here.", action_label=tr(c, "nav.report"), on_action=lambda: ui.navigate.to("/report"))
            return

        with ui.row().classes("items-center justify-between w-full"):
            section_title(tr(c, "nav.grievances"))
            ui.link(tr(c, "act.view_all"), "/grievances").classes("text-sm")
        rows = [{"id": x.id, "ref": x.reference, "title": x.title, "status": str(x.status).replace("_", " "), "created": x.created_at.strftime("%d %b %Y")} for x in d["recent"]]
        data_table([("ref", tr(c, "lbl.reference")), ("title", tr(c, "lbl.title")), ("status", tr(c, "lbl.status")), ("created", tr(c, "lbl.created"))], rows, on_row=lambda r: ui.navigate.to(f"/grievances/{r['id']}"))

        if d["rti_countdowns"]:
            section_title(tr(c, "card.rti"))
            with ui.column().classes("cl-card w-full gap-2"):
                for r in d["rti_countdowns"]:
                    tone = "danger" if r["days_left"] <= 2 else ("warning" if r["days_left"] <= 7 else "success")
                    with ui.row().classes("items-center justify-between w-full"):
                        ui.label(r["reference"]).classes("text-sm font-medium").style("color: var(--cl-fg);")
                        chip(f"{r['days_left']} day(s) left" + (" (est.)" if r["estimate"] else ""), color=tone)

    @page(c, "/report", "nav.report", roles=CIT)
    def report(c: AppContainer, user: UiUser) -> None:
        crid = uuid.uuid4().hex
        evidence_records: dict[str, Any] = {}
        qp = ui.context.client.request.query_params if ui.context.client.request else {}  # type: ignore[union-attr]
        pre_text = (qp.get("text") or "")[:1500]
        pre_voice = qp.get("voice") or None

        page_header(tr(c, "nav.report"), tr(c, "page.report_help"), icon="add_circle")

        def receipt(cm: Any, warnings: list[str]) -> None:
            for w in warnings:
                ui.notify(w, type="warning")
            with ui.dialog() as dlg, ui.column().classes("cl-card gap-3 w-full max-w-md"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("check_circle").classes("text-[26px]").style("color: var(--cl-success);")
                    ui.label(tr(c, "report.submitted")).classes("text-lg font-semibold").style("color: var(--cl-fg);")
                with ui.column().classes("cl-surface-alt q-pa-md gap-1 w-full"):
                    ui.label(f"{tr(c, 'lbl.reference')}: {cm.reference}").classes("cl-mono text-sm font-semibold")
                    ui.label(f"{tr(c, 'lbl.department')}: {cm.department_code or tr(c, 'report.awaiting_triage')}").classes("text-sm")
                    ui.label(f"{tr(c, 'lbl.priority')}: {cm.priority}").classes("text-sm")
                    if cm.sla_due_at:
                        ui.label(f"{tr(c, 'lbl.due')}: {cm.sla_due_at.strftime('%d %b %Y %H:%M')}").classes("text-sm")
                if cm.ai_status in ("pending", "not_configured"):
                    info_banner(tr(c, "msg.ai_unavailable") if cm.ai_status == "not_configured" else tr(c, "report.ai_queued"))
                if cm.duplicates:
                    section_title(tr(c, "report.similar"))
                    for x in cm.duplicates:
                        ui.label(f"{x['reference']} - {x['explanation']}").classes("text-xs").style("color: var(--cl-fg-muted);")
                ui.button(tr(c, "nav.grievances"), icon="arrow_forward", on_click=lambda: ui.navigate.to(f"/grievances/{cm.id}")).props("color=primary unelevated").classes("w-full")
            dlg.open()

        def create(data: dict[str, Any]) -> None:
            try:
                r = c.complaints.create(user.ctx, ComplaintInput(client_request_id=crid, **{k: v for k, v in data.items() if v not in (None, "")}))
            except CivicLensError as exc:
                ui.notify(exc.message + (f" {exc.details}" if exc.details else ""), type="negative")
                return
            receipt(r.complaint, r.warnings)

        # ------------------------------------------------------------------ quick mode
        # One screen, one required field. Everything the four-step form asks for is optional and
        # is inferred (category by the classifier, department by routing) or simply left empty -
        # nothing here is invented to fill a blank.
        def derive_title(desc: str) -> str:
            s = " ".join((desc or "").split())
            for sep in (". ", "। ", "? ", "! "):
                if sep in s:
                    s = s.split(sep)[0]
                    break
            return s[:90].strip()

        panes = ui.column().classes("w-full max-w-3xl gap-3")
        with ui.element("div").classes("cl-segment w-full max-w-3xl q-mb-sm"):
            seg_items = {}
            for key, label_key, icon in (("quick", "report.mode_quick", "bolt"), ("detailed", "report.mode_detailed", "tune")):
                el = ui.element("div").classes("cl-segment-item cl-focusable" + (" cl-on cl-citizen" if key == "quick" else "")).props("role=tab tabindex=0")
                with el:
                    ui.icon(icon).classes("text-[17px]")
                    ui.label(tr(c, label_key))
                seg_items[key] = el

        def show(which: str) -> None:
            for k, el in seg_items.items():
                el.classes(add="cl-on cl-citizen") if k == which else el.classes(remove="cl-on cl-citizen")
            quick_pane.set_visibility(which == "quick")
            detail_pane.set_visibility(which == "detailed")

        for k in seg_items:
            seg_items[k].on("click", lambda kk=k: show(kk))

        with panes:
            quick_pane = ui.column().classes("w-full gap-3")
            with quick_pane, ui.column().classes("cl-card w-full gap-3"):
                q_desc = ui.textarea(tr(c, "report.q_what"), value=pre_text).props("outlined autogrow rows=4").classes("w-full")
                field_hint(tr(c, "report.q_what_hint"))
                q_where = ui.input(tr(c, "report.q_where")).props("outlined dense").classes("w-full")
                field_hint(tr(c, "report.q_where_hint"))
                q_coords = ui.label("").classes("text-xs").style("color: var(--cl-fg-subtle);")
                q_geo: dict[str, Any] = {"lat": None, "lng": None}

                def on_geo(e: Any) -> None:
                    q_geo["lat"], q_geo["lng"] = round(float(e.args["lat"]), 6), round(float(e.args["lng"]), 6)
                    q_coords.set_text(f"{tr(c, 'report.q_pinned')} {q_geo['lat']:.5f}, {q_geo['lng']:.5f}")

                def on_geo_error(e: Any) -> None:
                    q_coords.set_text(tr(c, "report.q_geo_failed") + " " + str(e.args.get("message", "")))

                ui.on("cl_geo", on_geo)
                ui.on("cl_geo_error", on_geo_error)
                q_files = ui.row().classes("gap-2 flex-wrap w-full")

                def q_redraw() -> None:
                    q_files.clear()
                    with q_files:
                        for rid, rec in evidence_records.items():
                            with ui.row().classes("cl-badge cl-badge-info items-center gap-2"):
                                ui.icon("description").classes("text-[14px]")
                                ui.label(rec.name)
                                ui.icon("close").classes("text-[14px] cursor-pointer").on("click", lambda i=rid: (evidence_records.pop(i, None), q_redraw()))

                def q_upload(e: Any) -> None:
                    try:
                        rec = c.complaints.upload_evidence(user.ctx, e.name, e.content.read(), e.type)
                    except CivicLensError as exc:
                        ui.notify(exc.message, type="negative")
                        return
                    evidence_records[rec.id] = rec
                    q_redraw()

                with ui.row().classes("gap-2 flex-wrap items-center w-full"):
                    ui.button(tr(c, "report.q_use_location"), icon="my_location", on_click=lambda: ui.run_javascript(
                        "navigator.geolocation.getCurrentPosition("
                        "p => emitEvent('cl_geo', {lat: p.coords.latitude, lng: p.coords.longitude}),"
                        "e => emitEvent('cl_geo_error', {message: e.message}));",
                    )).props("outline dense")
                    ui.upload(on_upload=q_upload, auto_upload=True, multiple=True, label=tr(c, "report.q_photo")).props("flat dense accept=image/*,.pdf").classes("flex-1")

                def q_submit() -> None:
                    desc = (q_desc.value or "").strip()
                    if len(desc) < 10:
                        ui.notify(tr(c, "report.q_too_short"), type="warning")
                        return
                    title = derive_title(desc)
                    if len(title) < 5:
                        title = desc[:90]
                    create({
                        "title": title, "description": desc, "language": lang(),
                        "address": (q_where.value or "").strip() or None,
                        "lat": q_geo["lat"], "lng": q_geo["lng"],
                        "evidence_ids": list(evidence_records.keys()), "voice_id": pre_voice,
                    })

                ui.button(tr(c, "act.submit"), icon="send", on_click=q_submit).props("unelevated size=lg").classes("cl-btn-glow w-full")
                ui.label(tr(c, "report.q_footnote")).classes("text-xs").style("color: var(--cl-fg-subtle); line-height:1.5;")

            detail_pane = ui.column().classes("w-full gap-0")
            detail_pane.set_visibility(False)

        # ------------------------------------------------------------------ detailed mode
        with detail_pane, ui.column().classes("w-full max-w-3xl gap-0"):
            with ui.stepper().props("flat animated").classes("w-full cl-card !p-0") as stepper:
                # ---- Step 1: describe -----------------------------------------------------------
                with ui.step("describe", title=tr(c, "report.step_describe"), icon="edit_note"):
                    title = ui.input(tr(c, "lbl.title"), value=derive_title(pre_text)).props("outlined dense").classes("w-full")
                    field_hint(tr(c, "report.title_hint"))
                    desc = ui.textarea(tr(c, "lbl.description"), value=pre_text).props("outlined autogrow").classes("w-full")
                    field_hint(tr(c, "report.desc_hint"))
                    from app.i18n.languages import LANGUAGES

                    language = ui.select({k: f"{v.native} ({k})" for k, v in LANGUAGES.items()}, value=lang(), label=tr(c, "lbl.language")).props("outlined dense").classes("w-56")
                    with ui.stepper_navigation():
                        ui.button(tr(c, "act.next"), icon="arrow_forward", on_click=stepper.next).props("color=primary unelevated")

                # ---- Step 2: category & location -------------------------------------------------
                with ui.step("locate", title=tr(c, "report.step_locate"), icon="place"):
                    with ui.row().classes("gap-3 w-full flex-wrap"):
                        cat = ui.select({"": tr(c, "assistant.unsure"), **{k: k.replace("_", " ").title() for k in CATEGORIES}}, value="", label=tr(c, "lbl.category")).props("outlined dense").classes("w-52")
                        ward = ui.input(tr(c, "lbl.ward") + " (" + tr(c, "lbl.optional") + ")").props("outlined dense").classes("w-40")
                    field_hint(tr(c, "report.map_hint"))
                    with ui.row().classes("gap-3 items-end w-full flex-wrap"):
                        lat = ui.number(tr(c, "lbl.latitude"), format="%.6f").props("outlined dense").classes("w-40")
                        lng = ui.number(tr(c, "lbl.longitude"), format="%.6f").props("outlined dense").classes("w-40")
                    center = (12.9716, 77.5946)
                    m = ui.leaflet(center=center, zoom=11).classes("w-full h-64").style("border-radius: var(--cl-radius-md); overflow: hidden;")
                    marker: dict[str, Any] = {}

                    def on_click(e: Any) -> None:
                        lat.value, lng.value = round(e.args["latlng"]["lat"], 6), round(e.args["latlng"]["lng"], 6)
                        if "m" in marker:
                            m.remove_layer(marker["m"])
                        marker["m"] = m.marker(latlng=(lat.value, lng.value))

                    m.on("map-click", on_click)
                    with ui.stepper_navigation():
                        ui.button(tr(c, "act.back"), on_click=stepper.previous).props("flat")
                        ui.button(tr(c, "act.next"), icon="arrow_forward", on_click=stepper.next).props("color=primary unelevated")

                # ---- Step 3: evidence --------------------------------------------------------------
                with ui.step("evidence", title=tr(c, "report.step_evidence"), icon="attach_file"):
                    section_title(tr(c, "lbl.evidence"))
                    ev_list = ui.row().classes("gap-2 flex-wrap w-full")

                    def redraw_evidence() -> None:
                        ev_list.clear()
                        with ev_list:
                            for rid, rec in evidence_records.items():
                                with ui.row().classes("cl-badge cl-badge-info items-center gap-2"):
                                    ui.icon("description").classes("text-[14px]")
                                    ui.label(f"{rec.name} · {rec.analysis_status}")
                                    ui.icon("close").classes("text-[14px] cursor-pointer").on("click", lambda i=rid: (evidence_records.pop(i, None), redraw_evidence()))

                    def on_upload(e: Any) -> None:
                        try:
                            rec = c.complaints.upload_evidence(user.ctx, e.name, e.content.read(), e.type)
                        except CivicLensError as exc:
                            ui.notify(exc.message, type="negative")
                            return
                        evidence_records[rec.id] = rec
                        redraw_evidence()
                        ui.notify(f"{rec.name} added.", type="positive")

                    ui.upload(on_upload=on_upload, auto_upload=True, multiple=True, label=tr(c, "report.dropzone")).props("flat accept=.png,.jpg,.jpeg,.pdf,.txt,.docx").classes("cl-dropzone w-full")
                    field_hint(tr(c, "report.dropzone_hint"))

                    divider()
                    section_title(tr(c, "report.voice_input"), tr(c, "lbl.optional"))
                    caps = c.voice.capabilities()
                    voice_state: dict[str, Any] = {"id": pre_voice}
                    if caps["state"] != "CONFIGURED":
                        info_banner(tr(c, "report.stt_off"), "orange")
                    else:
                        options = ({"auto": tr(c, "report.auto_detect")} if caps["auto_detect"] else {}) | {x["code"]: f"{x['native']} ({x['name']})" for x in caps["languages"]}
                        voice_lang = ui.select(options, value=next(iter(options)), label=tr(c, "report.spoken_language")).props("outlined dense").classes("w-64")
                        transcript_note = ui.label().classes("text-xs").style("color: var(--cl-fg-subtle);")

                        def on_audio(e: Any) -> None:
                            try:
                                r = c.voice.transcribe(user.ctx, e.content.read(), e.type, voice_lang.value)
                            except CivicLensError as exc:
                                ui.notify(exc.message, type="negative")
                                return
                            if r.status != "OK" or not r.transcript:
                                ui.notify(r.error or r.status, type="warning")
                                return
                            voice_state["id"] = r.id
                            desc.value = ((desc.value or "") + " " + r.transcript).strip()  # same language, native script - never translated
                            if r.language_detected in c.ui_text.languages or r.language_detected:
                                language.value = r.language_detected if r.language_detected in [k for k in language.options] else language.value
                            transcript_note.set_text(tr(c, "report.transcript_note", lang=r.language_detected or "?", how=r.detected_by) + (" " + " ".join(r.warnings) if r.warnings else ""))
                            ui.notify(tr(c, "report.transcript_added"), type="positive")

                        ui.upload(on_upload=on_audio, auto_upload=True, label=tr(c, "report.record_audio")).props("flat accept=.wav,.webm,.ogg,.mp3,.m4a").classes("cl-dropzone w-full")
                    with ui.stepper_navigation():
                        ui.button(tr(c, "act.back"), on_click=stepper.previous).props("flat")
                        ui.button(tr(c, "act.next"), icon="arrow_forward", on_click=stepper.next).props("color=primary unelevated")

                # ---- Step 4: review & submit --------------------------------------------------------
                with ui.step("review", title=tr(c, "report.step_review"), icon="task_alt"):
                    review = ui.column().classes("gap-2 w-full")

                    def draw_review() -> None:
                        review.clear()
                        with review, ui.column().classes("cl-surface-alt q-pa-md gap-2 w-full"):
                            ui.label(title.value or tr(c, "report.no_title")).classes("text-sm font-semibold").style("color: var(--cl-fg);")
                            ui.label((desc.value or tr(c, "report.no_desc"))[:280]).classes("text-sm cl-clip-2").style("color: var(--cl-fg-muted);")
                            with ui.row().classes("gap-2 flex-wrap"):
                                chip(cat.value or tr(c, "lbl.category") + ": " + tr(c, "assistant.unsure"), color="info", outline=True)
                                if ward.value:
                                    chip(f"{tr(c, 'lbl.ward')} {ward.value}", color="muted", outline=True)
                                if lat.value and lng.value:
                                    chip(f"{lat.value:.4f}, {lng.value:.4f}", color="muted", outline=True)
                                chip(tr(c, "report.n_evidence", n=len(evidence_records)), color="muted", outline=True)

                    stepper.on_value_change(lambda e: draw_review() if e.value == "review" else None)
                    draw_review()
                    status = ui.label().classes("text-xs").style("color: var(--cl-fg-subtle);")

                    def payload() -> dict[str, Any]:
                        return {"title": title.value, "description": desc.value, "language": language.value, "category": cat.value or None, "ward": ward.value or None, "lat": lat.value, "lng": lng.value, "evidence_ids": list(evidence_records.keys()), "voice_id": voice_state["id"]}

                    def autosave() -> None:
                        try:
                            c.drafts.save(user.ctx, "complaint", payload(), crid)
                            status.set_text(tr(c, "msg.saved"))
                        except CivicLensError:
                            status.set_text(tr(c, "msg.unsaved"))

                    ui.timer(10.0, autosave)  # server-side draft; survives page reloads and dropped connections

                    def submit() -> None:
                        create(payload())

                    def pending() -> None:
                        for dr in c.drafts.sync_all(user.ctx):
                            ui.notify(f"{dr.status}: {dr.result_ref or dr.error}", type="positive" if dr.status == "synced" else "negative")

                    with ui.stepper_navigation():
                        ui.button(tr(c, "act.back"), on_click=stepper.previous).props("flat")
                        ui.button(tr(c, "act.submit"), icon="send", on_click=submit).props("unelevated").classes("cl-btn-glow")
                        ui.button(tr(c, "act.sync"), icon="sync", on_click=pending).props("flat")

    @page(c, "/grievances", "nav.grievances", roles=CIT)
    def grievances(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.grievances"), icon="assignment")
        state = {"f": "all"}
        box = ui.column().classes("w-full gap-3")

        def draw() -> None:
            box.clear()
            with box:
                items = c.complaints.list_mine(user.ctx, filter_name=state["f"])
                rows = [{"id": x.id, "ref": x.reference, "title": x.title, "status": str(x.status).replace("_", " "), "dept": x.department_code or "-", "created": x.created_at.strftime("%d %b %Y")} for x in items]
                data_table([("ref", tr(c, "lbl.reference")), ("title", tr(c, "lbl.title")), ("status", tr(c, "lbl.status")), ("dept", tr(c, "lbl.department")), ("created", tr(c, "lbl.created"))], rows,
                           on_row=lambda r: ui.navigate.to(f"/grievances/{r['id']}"), empty=tr(c, "msg.empty_complaints"))

        with ui.tabs(on_change=lambda e: (state.__setitem__("f", e.value), draw())).props("dense no-caps active-color=primary indicator-color=primary").classes("w-full") as tabs:
            for f in TRACKER_FILTERS:
                ui.tab(f, label=tr(c, f"filter.{f}"))
        tabs.set_value("all")
        draw()

    @page(c, "/grievances/{cid}", "nav.grievances", roles=CIT)
    def grievance_detail(c: AppContainer, user: UiUser, cid: str) -> None:
        d = c.complaints.detail_for_citizen(user.ctx, cid)
        cm = d["complaint"]
        with ui.row().classes("items-start justify-between w-full flex-wrap gap-2"):
            with ui.column().classes("gap-1"):
                ui.label(cm.reference).classes("text-xs cl-mono").style("color: var(--cl-fg-subtle);")
                ui.label(cm.title).classes("text-xl font-semibold").style("color: var(--cl-fg);")
                with ui.row().classes("gap-2 items-center flex-wrap"):
                    chip(str(cm.status).replace("_", " "), color=theme.STATUS_COLOR.get(str(cm.status), "muted"))
                    if cm.escalation_level:
                        chip(f"Escalated L{cm.escalation_level}", color="danger")
        with ui.row().classes("gap-6 w-full flex-wrap"):
            with ui.column().classes("gap-4 flex-1").style("min-width: 320px;"):
                with ui.column().classes("cl-card gap-2 w-full"):
                    ui.label(cm.description).classes("text-sm").style("color: var(--cl-fg);")
                    divider()
                    with ui.row().classes("gap-6 flex-wrap"):
                        with ui.column().classes("gap-0"):
                            ui.label(tr(c, "lbl.department")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                            ui.label(cm.department_code or "-").classes("text-sm font-medium").style("color: var(--cl-fg);")
                        with ui.column().classes("gap-0"):
                            ui.label(tr(c, "lbl.priority")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                            chip(cm.priority, color=theme.PRIORITY_COLOR.get(cm.priority, "muted"))
                        if cm.sla_due_at:
                            with ui.column().classes("gap-0"):
                                ui.label(tr(c, "lbl.due")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                                ui.label(cm.sla_due_at.strftime("%d %b %Y %H:%M")).classes("text-sm font-medium").style("color: var(--cl-fg);")
                    if cm.translated_text:
                        divider()
                        ui.label("Translation (machine-generated; your original text above is kept)").classes("text-xs").style("color: var(--cl-fg-subtle);")
                        ui.label(cm.translated_text).classes("text-sm").style("color: var(--cl-fg-muted);")

                section_title(tr(c, "lbl.evidence"))
                if not d["evidence"]:
                    state_panel(icon="attach_file", title="No evidence attached")
                else:
                    with ui.row().classes("gap-2 flex-wrap"):
                        for ev in d["evidence"]:
                            chip(f"{ev.name} · {ev.analysis_status}", color="info", outline=True)
                if str(cm.status) not in ("closed", "rejected"):
                    def add_more(e: Any) -> None:
                        try:
                            rec = c.complaints.upload_evidence(user.ctx, e.name, e.content.read(), e.type)
                            c.complaints.add_evidence(user.ctx, cm.id, rec.id)
                        except CivicLensError as exc:
                            ui.notify(exc.message, type="negative")
                            return
                        ui.notify("Evidence added.", type="positive")
                        ui.navigate.reload()

                    ui.upload(on_upload=add_more, auto_upload=True, label="Add more evidence").props("flat accept=.png,.jpg,.jpeg,.pdf,.txt,.docx").classes("cl-dropzone w-full max-w-md")

                government_panel(c, user.ctx, cm.id)

                if str(cm.status) in ("resolved", "closed") and not d["feedback"]:
                    section_title("Rate the resolution")
                    with ui.column().classes("cl-card gap-3 w-full max-w-lg"):
                        rating = ui.slider(min=1, max=5, value=5, step=1).props("label-always color=primary").classes("w-full")
                        comment = ui.textarea(tr(c, "lbl.comment")).props("outlined").classes("w-full")

                        def send() -> None:
                            c.complaints.add_feedback(user.ctx, cm.id, int(rating.value), comment.value)
                            ui.notify(tr(c, "msg.saved"), type="positive")
                            ui.navigate.reload()

                        ui.button(tr(c, "act.submit"), on_click=send).props("color=primary unelevated")
                elif d["feedback"]:
                    chip(f"Your rating: {d['feedback'].rating}/5", color="success")

            with ui.column().classes("gap-4").style("min-width: 280px; max-width: 340px; flex: 1;"):
                section_title("Status timeline")
                with ui.column().classes("cl-card w-full"):
                    _timeline(c, d["timeline"])
                section_title("History")
                _events(d["events"])

    @page(c, "/rti", "nav.rti", roles=CIT)
    def rti(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "tabRTI"), tr(c, "tipText"), icon="gavel")
        with ui.row().classes("gap-6 w-full flex-wrap"):
            with ui.column().classes("cl-card gap-3").style("min-width: 320px; max-width: 480px; flex: 1;"):
                section_title("Subject & authority")
                subject = ui.input(tr(c, "lbl.title")).props("outlined dense").classes("w-full")
                field_hint("What this RTI is about, e.g. \"Repeated potholes on MG Road near ward 12\".")
                authority = ui.input(tr(c, "selectDepartment")).props("outlined dense").classes("w-full")
                location = ui.input(tr(c, "lbl.location") + " (" + tr(c, "lbl.optional") + ")").props("outlined dense").classes("w-full")

                divider()
                section_title("Records to request", "Pick a category to see the statutory records citizens usually ask for - edit or add your own below.")
                cat_select = ui.select({"": "General / not sure", **{k: k.replace("_", " ").title() for k in CATEGORIES}}, value="", label=tr(c, "lbl.category")).props("outlined dense").classes("w-full")
                record_boxes: dict[str, ui.checkbox] = {}
                record_list = ui.column().classes("w-full gap-1")

                def draw_records() -> None:
                    record_list.clear()
                    record_boxes.clear()
                    with record_list:
                        for rec in default_records_for_category(cat_select.value):
                            record_boxes[rec] = ui.checkbox(rec, value=True).props("dense color=primary").classes("text-sm")

                cat_select.on_value_change(lambda e: draw_records())
                draw_records()
                with ui.row().classes("gap-3 w-full flex-wrap"):
                    tender_ref = ui.input("Tender / Work Order No. (" + tr(c, "lbl.optional") + ")").props("outlined dense").classes("w-full sm:flex-1")
                    time_period = ui.input("Time period (" + tr(c, "lbl.optional") + ", e.g. FY 2025-26)").props("outlined dense").classes("w-full sm:flex-1")
                questions = ui.textarea("Additional specific questions (" + tr(c, "lbl.optional") + ", one per line)").props("outlined autogrow").classes("w-full")

                divider()
                section_title("Applicant details")
                name = ui.input(tr(c, "fullName"), value=user.full_name).props("outlined dense").classes("w-full")
                addr = ui.textarea(tr(c, "residentialAddress")).props("outlined").classes("w-full")
                purpose = ui.input("Context (optional)").props("outlined dense").classes("w-full")
                with ui.row().classes("gap-4"):
                    life = ui.checkbox(tr(c, "emergency48Hr"))
                    bpl = ui.checkbox("Below poverty line")

                def draft() -> RtiDraft:
                    selected_records = tuple(rec for rec, box in record_boxes.items() if box.value)
                    composed = build_rti_questions(
                        subject=subject.value or "", location=location.value or None, records_requested=selected_records,
                        tender_reference=tender_ref.value or None, time_period=time_period.value or None,
                        custom_questions=tuple((questions.value or "").splitlines()),
                    )
                    return RtiDraft(subject.value or "", authority.value or "", composed, name.value or "", addr.value or "", lang(), purpose.value or None, bool(life.value), bool(bpl.value))

                def create() -> None:
                    try:
                        a = run_in_uow(c, lambda uow: c.rti_for(uow).generate(user.ctx, c.rti_for(uow).create(user.ctx, draft()).id))
                    except CivicLensError as exc:
                        ui.notify(exc.message + (f" {exc.details}" if exc.details else ""), type="negative")
                        return
                    show(a.id)

                ui.button(tr(c, "generateLetterBtn"), icon="description", on_click=create).props("color=primary unelevated").classes("w-full")

            with ui.column().classes("gap-3").style("min-width: 320px; flex: 1;"):
                section_title("Preview & tracking")
                out = ui.column().classes("w-full gap-2")

                def show(app_id: str) -> None:
                    a, cd = run_in_uow(c, lambda uow: c.rti_for(uow).track(user.ctx, app_id))
                    out.clear()
                    with out, ui.column().classes("cl-card gap-3 w-full"):
                        with ui.row().classes("items-center justify-between"):
                            ui.label(a.reference).classes("cl-mono text-sm").style("color: var(--cl-fg-subtle);")
                            chip(a.status.value, color="info")
                        if a.generated_text:
                            ui.textarea(value=a.generated_text).props("outlined readonly autogrow").classes("w-full cl-mono")
                        if cd.state != "not_started":
                            tone = {"breached": "danger", "at_risk": "warning"}.get(cd.state, "success")
                            chip(f"Deadline {cd.due_at:%d %b %Y} · {cd.days_remaining} day(s)" + (" (est.)" if cd.is_estimate else ""), color=tone)
                        with ui.row().classes("gap-2 flex-wrap"):
                            if a.status.value == "generated":
                                ui.button("Mark as filed", on_click=lambda: (run_in_uow(c, lambda uow: c.rti_for(uow).mark_filed(user.ctx, app_id)), show(app_id))).props("outline dense")
                            if a.status.value == "filed":
                                ui.button("Mark as answered", on_click=lambda: (run_in_uow(c, lambda uow: c.rti_for(uow).mark_responded(user.ctx, app_id)), show(app_id))).props("outline dense")
                            ui.button(tr(c, "act.download") + " PDF", icon="download", on_click=lambda: download_pdf(app_id)).props("outline dense")

                def download_pdf(app_id: str) -> None:
                    try:
                        data = run_in_uow(c, lambda uow: c.rti_for(uow).export_pdf(user.ctx, app_id, font_path=c.settings.rti_pdf_font or None))
                    except CivicLensError as exc:
                        ui.notify(exc.message, type="negative")
                        return
                    ui.download(data, f"rti-{app_id[:8]}.pdf")

                mine = run_in_uow(c, lambda uow: uow.rti.list_for_owner(user.ctx.user_id))
                if mine:
                    section_title("My RTI applications")
                    data_table([("ref", tr(c, "lbl.reference")), ("subject", tr(c, "lbl.title")), ("status", tr(c, "lbl.status"))], [{"id": a.id, "ref": a.reference or "draft", "subject": a.draft.subject, "status": a.status.value} for a in mine], on_row=lambda r: show(r["id"]))
                else:
                    state_panel(icon="gavel", title="No RTI applications yet", body="Fill in the form to draft your first one.")

    @page(c, "/legal", "nav.legal", roles=CIT)
    async def legal(c: AppContainer, user: UiUser) -> None:
        import base64

        page_header(tr(c, "nav.legal"), icon="balance")
        info_banner(tr(c, "msg.metadata_only"), "orange")
        _qp = ui.context.client.request.query_params if ui.context.client.request else {}  # type: ignore[union-attr]
        state: dict[str, Any] = {"recording": False}
        caps = c.voice.capabilities()

        with ui.element("div").classes("cl-ask w-full max-w-3xl"):
            ui.icon("balance").classes("text-[20px]").style("color: var(--cl-ai);")
            problem = ui.textarea(tr(c, "caseInputLabel"), value=(_qp.get("text") or "")[:2000]).props("borderless autogrow").classes("flex-1")
            mic = ui.button(icon="mic").props("round unelevated").style("background: var(--cl-ai); color: #fff;")
            mic.tooltip(tr(c, "assistant.mic_tip") if caps["state"] == "CONFIGURED" else tr(c, "assistant.mic_off"))
            mic.set_enabled(caps["state"] == "CONFIGURED")
        voice_hint = ui.label("").classes("text-xs").style("color: var(--cl-fg-subtle);")

        with ui.row().classes("gap-2 flex-wrap items-center q-mt-xs"):
            ui.label(tr(c, "legal.examples_label")).classes("text-xs").style("color: var(--cl-fg-subtle);")
            for key in ("legal.example_rti", "legal.example_consumer", "legal.example_rera"):
                text = tr(c, key)
                ui.chip(text, icon="edit_note", on_click=lambda t=text: setattr(problem, "value", t)).props("outline dense")

        with ui.row().classes("gap-3 items-center q-mt-sm"):
            analyze_btn = ui.button(tr(c, "legal.analyze_btn"), icon="search", on_click=lambda: analyze(problem.value or "")).props("color=primary unelevated")
            ui.upload(on_upload=lambda e: on_doc(e), auto_upload=True, label=tr(c, "legal.upload_doc")).props("flat accept=.pdf,.txt,.docx").classes("cl-dropzone")
        result = ui.column().classes("w-full max-w-3xl gap-3")

        STATUS_KEY = {"no_verified_precedent": "legal.status_no_verified_precedent", "precedents_only": "legal.status_precedents_only", "analysed": "legal.status_analysed"}
        CONF_KEY = {"none": "legal.conf_none", "low": "legal.conf_low", "medium": "legal.conf_medium"}

        def render(r: Any) -> None:
            result.clear()
            with result:
                with ui.row().classes("items-center gap-2"):
                    ui.label(tr(c, STATUS_KEY.get(r.status, r.status))).classes("text-sm font-medium").style("color: var(--cl-fg);")
                    chip(tr(c, CONF_KEY.get(r.confidence, r.confidence)), color="muted", outline=True)
                with ui.tabs().props("dense no-caps active-color=primary indicator-color=primary").classes("w-full") as result_tabs:
                    t_analysis = ui.tab("analysis", label=tr(c, "legal.tab_analysis"))
                    t_laws = ui.tab("laws", label=tr(c, "legal.tab_laws"))
                    t_precedents = ui.tab("precedents", label=tr(c, "legal.tab_precedents"))
                with ui.tab_panels(result_tabs, value=t_analysis).classes("w-full").style("background: transparent;"):
                    with ui.tab_panel(t_analysis).classes("gap-3"):
                        if r.interpretation:
                            section_title(tr(c, "legal.ai_interpretation_title"), tr(c, "legal.ai_interpretation_sub"))
                            with ui.row().classes("cl-card w-full items-start gap-2").style("background: var(--cl-ai-soft); border-color: transparent;"):
                                ui.icon("auto_awesome").style("color: var(--cl-ai);")
                                ui.label(r.interpretation).classes("text-sm").style("color: var(--cl-fg);")
                        for w in r.warnings:
                            info_banner(w, "orange")
                        for line in r.bias_and_coverage:
                            ui.label(line).classes("text-xs").style("color: var(--cl-fg-subtle);")
                        ui.label(r.disclaimer).classes("text-xs italic").style("color: var(--cl-fg-subtle);")
                    with ui.tab_panel(t_laws).classes("gap-3"):
                        if r.concepts:
                            with ui.column().classes("cl-surface-alt q-pa-sm gap-1 w-full"):
                                ui.label(tr(c, "legal.statutes_detected")).classes("text-xs font-medium").style("color: var(--cl-fg-muted);")
                                ui.label("; ".join(r.concepts)).classes("text-sm").style("color: var(--cl-fg);")
                        else:
                            ui.label(tr(c, "legal.no_concepts")).classes("text-sm").style("color: var(--cl-fg-muted);")
                        for g in r.court_guides:
                            with ui.column().classes("cl-card w-full gap-2"):
                                ui.label(g["concept"]).classes("text-sm font-semibold").style("color: var(--cl-fg);")
                                for label_key, value in ((tr(c, "legal.forum"), g["forum"]), (tr(c, "legal.advocate_mandatory"), g["advocateMandatory"]), (tr(c, "legal.fee_basis"), g["feeBasis"])):
                                    with ui.row().classes("gap-2 items-start"):
                                        ui.label(label_key + ":").classes("text-xs font-medium").style("color: var(--cl-fg-muted); min-width: 11rem;")
                                        ui.label(value).classes("text-xs").style("color: var(--cl-fg);")
                                ui.label(tr(c, "legal.procedure") + ":").classes("text-xs font-medium q-mt-xs").style("color: var(--cl-fg-muted);")
                                for i, step in enumerate(g["steps"], 1):
                                    ui.label(f"{i}. {step}").classes("text-xs").style("color: var(--cl-fg);")
                    with ui.tab_panel(t_precedents).classes("gap-3"):
                        section_title(tr(c, "legal.verified_precedents"), tr(c, "legal.verified_precedents_sub"))
                        data_table([("cit", tr(c, "legal.col_neutral_citation")), ("title", tr(c, "legal.col_case")), ("date", tr(c, "legal.col_decided")), ("disposal", tr(c, "lbl.status")), ("how", tr(c, "legal.col_matched_on"))],
                                   [{"id": p["cnr"], "cit": p["neutralCitation"], "title": p["title"], "date": p["decisionDate"], "disposal": p["disposal"] or "-", "how": p["matchedOn"]} for p in r.precedents], empty=tr(c, "msg.no_data"))
                        if r.full_text_excerpts:
                            section_title(tr(c, "legal.full_text_title"), tr(c, "legal.full_text_sub"))
                            for e in r.full_text_excerpts:
                                with ui.expansion(f"{e.get('neutralCitation') or e['judgmentId']} - {e.get('title') or ''}").classes("w-full"):
                                    ui.label(e["text"]).classes("text-xs").style("color: var(--cl-fg-muted);")
                        from urllib.parse import quote

                        query_text = (problem.value or "")[:300]
                        with ui.row().classes("cl-card items-center justify-between w-full flex-wrap gap-2").style("background: var(--cl-info-soft); border-color: transparent;"):
                            with ui.column().classes("gap-0"):
                                ui.label(tr(c, "legal.curated_note")).classes("text-xs font-medium").style("color: var(--cl-info);")
                                ui.label(tr(c, "legal.curated_note_sub")).classes("text-xs").style("color: var(--cl-info);")
                            ui.link(tr(c, "legal.search_kanoon"), f"https://indiankanoon.org/search/?formInput={quote(query_text)}").classes("text-sm font-medium").props("target=_blank")

        async def analyze(text: str) -> None:
            result.clear()
            with result:
                ui.spinner(size="lg")
            rec = await run_with_loading(analyze_btn, c.legal.analyze, user.ctx, text)  # persisted + audited
            render(SimpleNamespace(**rec.result))

        opened = ui.context.client.request.query_params.get("open") if ui.context.client.request else None  # type: ignore[union-attr]
        if opened:
            render(SimpleNamespace(**c.legal.get_mine(user.ctx, opened).result))

        async def on_doc(e: Any) -> None:
            from app.services.document_service import extract_pages, validate_upload

            data = e.content.read()
            v = validate_upload(e.name, data, max_bytes=c.settings.max_upload_bytes, declared_mime=e.type)
            await analyze(" ".join(t for _p, t in extract_pages(v.mime, data, None))[:8000])

        # ---- voice: same mic bridge the AI triage assistant uses (MediaRecorder -> emitEvent) -----
        ui.add_body_html(f"<script>{MIC_JS}</script>")

        def on_audio(e: Any) -> None:
            state["recording"] = False
            mic.props("icon=mic").classes(remove="cl-mic-live")
            try:
                raw = base64.b64decode(e.args["b64"])
            except (KeyError, ValueError):
                ui.notify(tr(c, "assistant.mic_failed"), type="negative")
                return
            try:
                r = c.voice.transcribe(user.ctx, raw, e.args.get("mime") or "audio/webm", "auto" if caps["auto_detect"] else caps["languages"][0]["code"])
            except CivicLensError as exc:
                ui.notify(exc.message, type="negative")
                return
            if r.status != "OK" or not r.transcript:
                ui.notify(r.error or r.status, type="warning")
                return
            problem.value = ((problem.value or "") + " " + r.transcript).strip()  # spoken language/script kept, never translated
            voice_hint.set_text(tr(c, "assistant.heard", lang=r.language_detected or "?", how=r.detected_by))

        def on_audio_error(e: Any) -> None:
            state["recording"] = False
            mic.props("icon=mic").classes(remove="cl-mic-live")
            ui.notify(tr(c, "assistant.mic_denied") + " " + str(e.args.get("message", "")), type="negative")

        ui.on("cl_audio", on_audio)
        ui.on("cl_audio_error", on_audio_error)

        async def toggle_mic() -> None:
            if state["recording"]:
                state["recording"] = False
                mic.props("icon=mic").classes(remove="cl-mic-live")
                ui.run_javascript("window.clStopRec()")
                return
            state["recording"] = True
            mic.props("icon=stop").classes(add="cl-mic-live")
            voice_hint.set_text(tr(c, "assistant.listening"))
            await ui.run_javascript("window.clStartRec()")

        mic.on_click(toggle_mic)

        past = c.legal.list_mine(user.ctx)
        if past:
            section_title(tr(c, "legal.past_analyses"))
            data_table([("when", tr(c, "legal.col_when")), ("status", tr(c, "lbl.status")), ("problem", tr(c, "legal.col_matter"))], [{"id": r.id, "when": r.created_at.strftime("%d %b %Y %H:%M"), "status": r.status, "problem": r.problem[:100]} for r in past],
                       on_row=lambda row: ui.navigate.to(f"/legal?open={row['id']}"))

    @page(c, "/copilot", "nav.copilot")
    async def copilot(c: AppContainer, user: UiUser) -> None:
        state: dict[str, Any] = {"cid": None}
        page_header(tr(c, "chatbotTitle"), tr(c, "page.copilot_help"), icon="smart_toy")
        if c.llm is None:
            info_banner("No language model is configured: the assistant can show matching sources and database facts but cannot compose answers.", "orange")
        with ui.column().classes("cl-card w-full max-w-3xl !p-0 gap-0"):
            log = ui.column().classes("w-full gap-1 q-pa-md").style("min-height: 240px; max-height: 55vh; overflow-y: auto;")
            with ui.row().classes("q-pa-sm gap-2 items-center w-full cl-hairline"):
                box = ui.input(placeholder=tr(c, "chatbotPlaceholder")).props("outlined dense rounded").classes("flex-1")
                send_btn = ui.button(icon="send", on_click=lambda: send()).props("round unelevated color=primary")
        q0 = ui.context.client.request.query_params.get("q") if ui.context.client.request else None  # type: ignore[union-attr]
        if q0:
            box.value = q0

        with log:
            chat_bubble("Ask about your complaints, RTI deadlines, or civic documents. I only answer from what's actually on record.", is_user=False)

        async def send() -> None:
            text = (box.value or "").strip()
            if not text:
                return
            box.value = ""
            with log:
                chat_bubble(text, is_user=True)
                with ui.row().classes("cl-chat-row cl-assistant") as spinner_row:
                    with ui.element("div").classes("cl-chat-avatar"):
                        ui.icon("auto_awesome").classes("text-[16px]")
                    ui.spinner(size="sm")
            try:
                r = await run_with_loading(send_btn, c.assistant.ask, user.ctx, text, conversation_id=state["cid"], language={"en": "English", "hi": "Hindi", "mr": "Marathi", "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "kn": "Kannada"}[lang()])
            except CivicLensError as exc:
                spinner_row.delete()
                with log:
                    error_banner(exc.message)
                    ui.button(tr(c, "act.retry"), on_click=lambda: (setattr(box, "value", text), send())).props("flat dense")
                return
            spinner_row.delete()
            state["cid"] = r["conversation_id"]
            with log:
                answer = r["answer"] or tr(c, "msg.insufficient") if r["status"] != "model_unavailable" else "The language model is unavailable; sources are listed below."
                chat_bubble(answer, is_user=False)
                if r["database_facts"] is not None:
                    with ui.row().classes("cl-card items-start gap-2 q-ml-10").style("background: var(--cl-info-soft); border-color: transparent; max-width: 75%;"):
                        ui.icon("dataset").classes("text-[14px]").style("color: var(--cl-info);")
                        ui.label(str(r["database_facts"])).classes("text-xs").style("color: var(--cl-info);")
                for cit in r["citations"]:
                    with ui.expansion(f"[{cit['marker']}] {cit['documentName']}" + (f" - p.{cit['page']}" if cit.get("page") else "")).classes("w-full q-ml-10").style("max-width: 75%;"):
                        ui.label(cit["excerpt"]).classes("text-xs").style("color: var(--cl-fg-muted);")
                for w in r["warnings"]:
                    ui.label(w).classes("text-xs q-ml-10").style("color: var(--cl-warning);")

        box.on("keydown.enter", send)

    @page(c, "/gis", "nav.gis")
    def gis(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "heatmapTitle"), tr(c, "page.gis_help"), icon="map")
        with ui.row().classes("gap-3 items-end w-full flex-wrap"):
            cat = ui.select({"": tr(c, "filterAll"), **{k: k.title() for k in CATEGORIES}}, value="", label=tr(c, "lbl.category")).props("outlined dense").classes("w-48")
            ward = ui.input(tr(c, "lbl.ward")).props("outlined dense").classes("w-32")
            sev = ui.select({"": "Any", "medium": "Medium+", "high": "High+", "critical": "Critical"}, value="", label="Severity").props("outlined dense").classes("w-32")
            ui.button(tr(c, "act.refresh"), icon="refresh", on_click=lambda: draw()).props("color=primary unelevated")
        box = ui.column().classes("w-full gap-3")

        def draw() -> None:
            box.clear()
            r = c.gis.radar(user.ctx, category=cat.value or None, ward=ward.value or None, min_severity=sev.value or None)
            with box:
                with ui.row().classes("gap-2 items-center"):
                    chip(f"{r['mappable']} of {r['total_complaints']} mappable", color="info", outline=True)
                    if r["not_mappable"]:
                        chip(f"{r['not_mappable']} without coordinates", color="muted", outline=True)
                if r["hotspots"]:
                    lat0, lng0 = r["hotspots"][0]["lat"], r["hotspots"][0]["lng"]
                elif r["offices"]:
                    lat0, lng0 = r["offices"][0]["lat"], r["offices"][0]["lng"]
                else:
                    state_panel(icon="map", title=tr(c, "msg.no_data"), body="Reports will appear here once there is enough data to protect reporter privacy.")
                    return
                with ui.row().classes("gap-4 w-full flex-wrap items-start"):
                    m = ui.leaflet(center=(lat0, lng0), zoom=11).classes("h-96").style("flex: 2; min-width: 320px; border-radius: var(--cl-radius-md); overflow: hidden;")
                    for h in r["hotspots"]:
                        m.generic_layer(name="circleMarker", args=[(h["lat"], h["lng"]), {"radius": 6 + 3 * min(h["count"], 8), "color": "#c22a1b", "fillColor": "#c22a1b", "fillOpacity": 0.35}])
                    for o in r["offices"]:
                        m.marker(latlng=(o["lat"], o["lng"]))
                    with ui.column().classes("cl-card gap-2").style("flex: 1; min-width: 260px;"):
                        section_title("Hotspots")
                        if not r["hotspots"]:
                            ui.label("No hotspot clusters yet.").classes("text-xs").style("color: var(--cl-fg-subtle);")
                        for h in r["hotspots"][:8]:
                            with ui.row().classes("items-center justify-between w-full"):
                                ui.label(", ".join(h["wards"]) or "Unassigned ward").classes("text-sm").style("color: var(--cl-fg);")
                                chip(f"{h['count']} reports", color="danger" if h["severity_score"] >= 3 else "warning")
                        if r["ward_boundaries"] == "not_available":
                            ui.label("Ward boundary polygons are not loaded; wards are listed by name only.").classes("text-xs").style("color: var(--cl-fg-subtle);")

        draw()

    @page(c, "/interop", "nav.interop")
    def interop(c: AppContainer, user: UiUser) -> None:
        import json as _json

        from app.interop.adapters import SYSTEMS
        from app.interop.common_data_model import score_quality
        from app.interop.fragmentation import (
            NATIONAL_UMANG_DEPARTMENTS,
            NATIONAL_UMANG_SERVICES,
            NATIONAL_UMANG_SOURCE,
            personal_diagnostic,
        )

        page_header(tr(c, "nav.interop"), "Different government systems describe the same request with different field names, casing and status words. See the actual normalization mechanism, live.", icon="hub")

        section_title("Fragmentation, in numbers")
        with ui.row().classes("gap-3 w-full flex-wrap"):
            stat_tile("Services on India's own unification app", f"{NATIONAL_UMANG_SERVICES:,}+", color="info", icon="apps", hint=f"across {NATIONAL_UMANG_DEPARTMENTS}+ departments — {NATIONAL_UMANG_SOURCE}")
            mine = c.complaints.list_mine(user.ctx, filter_name="all")
            diag = personal_diagnostic([m.department_code for m in mine])
            stat_tile("Departments you've dealt with", diag.distinct_departments, color="primary", icon="apartment", hint=f"across {diag.total_filings} filing(s) through CivicLens")
            stat_tile("Re-entries avoided", diag.profile_reuses, color="success", icon="badge", hint="times your one CivicLens profile was reused instead of re-typing KYC elsewhere")

        divider()
        section_title("Live normalization demo", "Pick a system to see its real (fixture) export shape transform into CivicLens's Common Data Model.")
        info_banner("These are realistic illustrative fixtures shaped like real system exports, not a live feed — no department has given CivicLens a data-sharing agreement yet. The adapter code itself is real and directly reusable the day one exists.", "blue")

        sys_select = ui.select({k: v[0] for k, v in SYSTEMS.items()}, value=next(iter(SYSTEMS)), label="Source system").props("outlined dense").classes("w-full max-w-lg")
        corrupt = ui.checkbox("Simulate a malformed record (blank required fields, break the status code)")
        out = ui.row().classes("gap-4 w-full flex-wrap items-start q-mt-sm")

        def draw() -> None:
            out.clear()
            _label, fixture, adapt = SYSTEMS[sys_select.value]
            payload = dict(fixture)
            if corrupt.value:
                for k in list(payload.keys()):
                    if any(tok in k.lower() for tok in ("status",)):
                        payload[k] = "???" if isinstance(payload[k], str) else 99
                    if any(tok in k.lower() for tok in ("name", "mobile", "phone", "contact", "applicant", "complainant")):
                        payload[k] = ""
            record = adapt(payload)
            quality = score_quality(record)
            tone = {"excellent": "success", "good": "info", "poor": "warning", "unusable": "danger"}[quality.grade]
            with out:
                with ui.column().classes("cl-card gap-2").style("flex: 1; min-width: 300px;"):
                    section_title("Raw payload", "exactly as that system would export it")
                    ui.markdown(f"```json\n{_json.dumps(payload, indent=2, ensure_ascii=False)}\n```").classes("cl-mono text-xs w-full")
                with ui.column().classes("cl-card gap-2").style("flex: 1; min-width: 300px;"):
                    with ui.row().classes("items-center justify-between w-full"):
                        section_title("Normalized (Common Data Model)")
                        chip(f"{quality.grade} · {quality.score:.0%}", color=tone)
                    for label, value in (("External ID", record.external_id), ("Category", record.category), ("Status", record.status), ("Title", record.title),
                                         ("Department", record.department), ("Citizen", record.citizen_name), ("Contact", record.citizen_contact),
                                         ("Location", record.location), ("Filed on", record.filed_on)):  # fmt: skip
                        with ui.row().classes("items-center justify-between w-full"):
                            ui.label(label).classes("text-xs").style("color: var(--cl-fg-subtle);")
                            ui.label(str(value) if value not in (None, "") else "—").classes("text-sm font-medium cl-mono").style("color: var(--cl-fg);")
                    if quality.issues:
                        divider()
                        ui.label("Data-quality issues detected:").classes("text-xs font-medium").style("color: var(--cl-danger);")
                        for issue in quality.issues:
                            ui.label(f"• {issue}").classes("text-xs").style("color: var(--cl-danger);")
                        if quality.grade in ("poor", "unusable"):
                            def queue_exception() -> None:
                                c.exceptions.log(source_system=record.source_system, reason="; ".join(quality.issues)[:300], payload=payload)
                                ui.notify("Queued for admin review under Integration Exceptions.", type="positive")

                            ui.button("Queue as an integration exception", icon="report_problem", on_click=queue_exception).props("outline dense color=negative")

        sys_select.on_value_change(lambda e: draw())
        corrupt.on_value_change(lambda e: draw())
        draw()

    @page(c, "/emergency", "nav.emergency")
    def emergency(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.emergency"), icon="emergency")
        helpline_cards(c)

    @page(c, "/profile", "nav.profile")
    def profile(c: AppContainer, user: UiUser) -> None:
        p = c.profiles.get(user.ctx)
        page_header(tr(c, "profileSection"), icon="person")
        with ui.column().classes("cl-card w-full max-w-md gap-3"):
            name = ui.input(tr(c, "fullName"), value=p.full_name).props("outlined dense").classes("w-full")
            phone = ui.input(tr(c, "phoneNumber"), value=p.phone or "").props("outlined dense").classes("w-full")
            city = ui.input(tr(c, "selectCity"), value=p.city or "").props("outlined dense").classes("w-full")
            ward = ui.input(tr(c, "lbl.ward"), value=p.ward or "").props("outlined dense").classes("w-full")
            divider()
            with ui.row().classes("items-center gap-2"):
                ui.icon("mail").classes("text-[16px]").style("color: var(--cl-fg-subtle);")
                ui.label(f"{tr(c, 'emailAddress')}: {user.email}").classes("text-sm").style("color: var(--cl-fg-muted);")

            def save() -> None:
                c.profiles.update(user.ctx, full_name=name.value, phone=phone.value or None, city=city.value, ward=ward.value)
                ui.notify(tr(c, "msg.saved"), type="positive")

            ui.button(tr(c, "saveProfileBtn"), icon="check", on_click=save).props("color=primary unelevated")

    @page(c, "/settings", "nav.settings")
    def settings(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "settingsTitle"), icon="settings")
        with ui.column().classes("w-full max-w-2xl gap-5"):
            with ui.column().classes("cl-card gap-3 w-full"):
                section_title("Notifications")
                prefs = run_in_uow(c, lambda uow: c.notifications.preferences(user.ctx, uow.notifications))
                in_app = ui.switch("In-app notifications", value=prefs.in_app).props("color=primary")
                email = ui.switch("E-mail notifications", value=prefs.email).props("color=primary")
                if c.mailer is None:
                    field_hint("E-mail delivery is not configured on this server; e-mail notifications will be recorded as 'not sent'.")

                def save_prefs() -> None:
                    run_in_uow(c, lambda uow: c.notifications.save_preferences(user.ctx, uow.notifications, in_app=in_app.value, email=email.value, muted_kinds=list(prefs.muted_kinds)))
                    ui.notify(tr(c, "msg.saved"), type="positive")

                ui.button(tr(c, "act.save"), on_click=save_prefs).props("outline")

            with ui.column().classes("cl-card gap-3 w-full"):
                section_title("Privacy & AI consent", "You can change these at any time; AI processing never decides outcomes on its own.")
                consents = c.profiles.consents(user.ctx)
                for purpose, cstate in consents.items():
                    ui.switch(purpose.replace("_", " ").capitalize(), value=cstate["granted"], on_change=lambda e, p=purpose: (c.profiles.set_consent(user.ctx, p, bool(e.value)), ui.notify(tr(c, "msg.saved"), type="positive"))).props("color=primary")
                divider()
                ui.label("Government sharing: nothing is sent to a government platform unless an integration is configured and you consent.").classes("text-xs").style("color: var(--cl-fg-subtle);")
                with ui.row().classes("gap-2 flex-wrap"):
                    for _platform, a in c.adapters.items():
                        chip(f"{a.display_name}: {a.state.value}", color="muted", outline=True)

            with ui.column().classes("cl-card gap-3 w-full"):
                section_title("Appearance & language")
                ui.select({k: k.upper() for k in c.ui_text.languages}, value=lang(), label=tr(c, "appLanguage"),
                          on_change=lambda e: (app.storage.user.__setitem__("lang", e.value), c.profiles.update(user.ctx, language=e.value), ui.navigate.reload())).props("outlined dense").classes("w-56")
                field_hint("Use the sun/moon icon in the top bar to switch between light and dark mode.")

            with ui.column().classes("cl-card gap-3 w-full"):
                section_title("Security")
                ui.label("Manage two-factor authentication and sessions.").classes("text-sm").style("color: var(--cl-fg-muted);")
                ui.button(tr(c, "nav.security"), icon="lock", on_click=lambda: ui.navigate.to("/security")).props("outline")

            with ui.column().classes("cl-card gap-3 w-full"):
                section_title("Linked government IDs (Golden Record)", "Only a one-way hash is ever stored - never the raw number. Linking the same ID twice, even to another account, is blocked.")
                ids_list = ui.column().classes("gap-2 w-full")

                def draw_ids() -> None:
                    ids_list.clear()
                    items = c.master_data.list_mine(user.ctx)
                    with ids_list:
                        if not items:
                            ui.label("No IDs linked yet.").classes("text-sm").style("color: var(--cl-fg-subtle);")
                        for rec in items:
                            with ui.row().classes("items-center justify-between w-full"):
                                ui.label(f"{rec.id_type.replace('_', ' ').upper()} · ···{rec.last4 or '----'}").classes("text-sm cl-mono").style("color: var(--cl-fg);")
                                ui.button(icon="delete_outline", on_click=lambda i=rec.id: (c.master_data.unlink(user.ctx, i), draw_ids())).props("flat dense round color=negative")

                draw_ids()
                divider()
                with ui.row().classes("gap-3 items-end w-full flex-wrap"):
                    from app.services.interop_service import ID_TYPES

                    id_type_sel = ui.select({t: t.replace("_", " ").title() for t in ID_TYPES}, value=ID_TYPES[0], label="ID type").props("outlined dense").classes("w-48")
                    id_value = ui.input("ID value").props("outlined dense").classes("flex-1")

                    def link_id() -> None:
                        try:
                            c.master_data.link(user.ctx, id_type_sel.value, id_value.value or "")
                        except CivicLensError as exc:
                            ui.notify(exc.message, type="negative")
                            return
                        id_value.value = ""
                        ui.notify("Linked.", type="positive")
                        draw_ids()

                    ui.button("Link", icon="add_link", on_click=link_id).props("outline dense")

            with ui.column().classes("cl-card gap-3 w-full"):
                section_title("Other portals you're tracking manually", "CPGRAMS and most state portals require your own login and expose no public API - track their reference numbers here alongside your live CivicLens filings.")
                links_list = ui.column().classes("gap-2 w-full")

                def draw_links() -> None:
                    links_list.clear()
                    items = c.external_links.list_mine(user.ctx)
                    with links_list:
                        if not items:
                            ui.label("Nothing tracked yet.").classes("text-sm").style("color: var(--cl-fg-subtle);")
                        for rec in items:
                            with ui.row().classes("cl-surface-alt q-pa-sm items-center justify-between w-full gap-2"):
                                with ui.column().classes("gap-0"):
                                    ui.label(f"{rec.platform} · {rec.external_reference}").classes("text-sm font-medium cl-mono").style("color: var(--cl-fg);")
                                    ui.label(rec.title + (f" — {rec.status_note}" if rec.status_note else "")).classes("text-xs").style("color: var(--cl-fg-muted);")
                                ui.button(icon="delete_outline", on_click=lambda i=rec.id: (c.external_links.remove(user.ctx, i), draw_links())).props("flat dense round color=negative")

                draw_links()
                divider()
                with ui.row().classes("gap-3 items-end w-full flex-wrap"):
                    platform_in = ui.input("Platform (e.g. CPGRAMS)").props("outlined dense").classes("w-40")
                    ref_in = ui.input("Reference number").props("outlined dense").classes("w-40")
                    title_in = ui.input("Short title").props("outlined dense").classes("flex-1")

                    def add_link() -> None:
                        try:
                            c.external_links.add(user.ctx, platform=platform_in.value or "", external_reference=ref_in.value or "", title=title_in.value or "")
                        except CivicLensError as exc:
                            ui.notify(exc.message + (f" {exc.details}" if exc.details else ""), type="negative")
                            return
                        platform_in.value = ref_in.value = title_in.value = ""
                        ui.notify("Added.", type="positive")
                        draw_links()

                    ui.button("Track", icon="add", on_click=add_link).props("outline dense")

    @page(c, "/notifications", "nav.notifications")
    def notifications(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.notifications"), icon="notifications",
                    actions=lambda: ui.button("Mark all read", on_click=lambda: (run_in_uow(c, lambda uow: c.notifications.mark_all_read(user.ctx, uow.notifications)), ui.navigate.reload())).props("outline dense"))
        items = run_in_uow(c, lambda uow: c.notifications.list_for(user.ctx, uow.notifications, limit=100))
        if not items:
            state_panel(icon="notifications_none", title=tr(c, "msg.no_data"))
        with ui.column().classes("gap-2 w-full"):
            for n in items:
                with ui.row().classes("cl-card w-full items-start justify-between gap-3").style("" if n.read_at else "background: var(--cl-info-soft); border-color: transparent;"):
                    with ui.column().classes("gap-1"):
                        ui.label(n.title).classes("text-sm font-semibold").style("color: var(--cl-fg);")
                        ui.label(n.body).classes("text-sm").style("color: var(--cl-fg-muted);")
                        ui.label(n.created_at.strftime("%d %b %Y %H:%M")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                    if not n.read_at:
                        ui.button("Mark read", on_click=lambda i=n.id: (run_in_uow(c, lambda uow: c.notifications.mark_read(user.ctx, uow.notifications, i)), ui.navigate.reload())).props("flat dense")

    @page(c, "/documents", "nav.documents")
    def documents(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.documents"), icon="folder")

        def on_upload(e: Any) -> None:
            if c.ingestor_factory is None:
                ui.notify("Document ingestion is not configured.", type="negative")
                return
            try:
                def op(uow):  # type: ignore[no-untyped-def]
                    doc = c.ingestor_factory(uow).upload(user.ctx.user_id, e.name, e.content.read(), max_bytes=c.settings.max_upload_bytes, declared_mime=e.type)
                    job, _ = c.jobs.enqueue(uow, "document.ingest", {"document_id": doc.id}, f"ingest:{doc.id}")
                    return job

                c.jobs.dispatch([run_in_uow(c, op)])
            except CivicLensError as exc:
                ui.notify(exc.message, type="negative")
                return
            ui.notify("Uploaded; processing has been queued.", type="positive")
            ui.navigate.reload()

        ui.upload(on_upload=on_upload, auto_upload=True, label="Drop a document (PDF, DOCX, TXT, image), or click to browse").props("flat").classes("cl-dropzone w-full max-w-xl")
        if c.ingestor_factory:
            docs = run_in_uow(c, lambda uow: uow.documents.list_for_owner(user.ctx.user_id))
            if docs:
                section_title("My documents")
                data_table([("name", "Name"), ("status", tr(c, "lbl.status")), ("chunks", "Chunks"), ("err", "Error")], [{"id": d.id, "name": d.name, "status": str(d.status), "chunks": d.chunk_count, "err": d.error or ""} for d in docs])
            failed = [d for d in docs if str(d.status) == "failed"]
            for d in failed:
                ui.button(f"{tr(c, 'act.retry')} {d.name}", on_click=lambda i=d.id: (run_in_uow(c, lambda uow: c.jobs.enqueue(uow, "document.ingest", {"document_id": i}, f"ingest-retry:{i}:{int(c.clock().timestamp())}")), ui.navigate.reload())).props("outline dense")
        section_title("Search my documents")
        with ui.row().classes("gap-2 w-full max-w-xl items-center"):
            q = ui.input("Search my documents").props("outlined dense").classes("flex-1")
            ui.button(icon="search", on_click=lambda: search()).props("round unelevated color=primary")
        out = ui.column().classes("w-full max-w-xl gap-2")

        def search() -> None:
            out.clear()
            res = c.rag.retrieve(q.value or "", user.ctx)
            with out:
                if not res.chunks:
                    state_panel(icon="search_off", title=tr(c, "msg.insufficient"))
                for rc in res.chunks:
                    with ui.column().classes("cl-card gap-1 w-full"):
                        ui.label(f"{rc.chunk.document_name}" + (f" - p.{rc.chunk.page}" if rc.chunk.page else "")).classes("text-sm font-medium").style("color: var(--cl-fg);")
                        ui.label(rc.chunk.text[:400]).classes("text-xs").style("color: var(--cl-fg-muted);")

        q.on("keydown.enter", search)

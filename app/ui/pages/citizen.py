"""Citizen pages: dashboard, report, tracker, RTI, legal, copilot, GIS, emergency, profile, settings, notifications, documents."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from nicegui import app, ui

from app.container import AppContainer
from app.core.authorization import Permission, Role
from app.core.exceptions import CivicLensError
from app.core.transactions import run_in_uow
from app.services.classification_service import CATEGORIES
from app.services.complaint_service import ComplaintInput
from app.services.complaint_status import TRACKER_FILTERS
from app.services.rti_service import (
    RtiDraft,
    build_rti_questions,
    default_records_for_category,
    enhance_questions_with_llm,
)
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
        state_panel(icon="support_agent", title=tr(c, "em.none_title"), body=tr(c, "em.none_body"))
        return
    with ui.row().classes("gap-4 flex-wrap w-full items-stretch"):
        for h in data["items"]:
            # equal-height cards, number pinned to the bottom, and the whole card is a tel: link so
            # a panicking thumb on a phone doesn't have to hit the digits exactly
            with ui.link(target=h["tel_uri"]).classes("cl-card cl-card-hover cl-helpline no-underline column gap-2").style("flex: 1 1 220px; max-width: 300px;"):
                with ui.row().classes("items-center gap-2"):
                    with ui.element("div").classes("cl-stat-icon").style("background: var(--cl-emergency-soft); color: var(--cl-emergency); width:34px; height:34px;"):
                        ui.icon("call").classes("text-[16px]")
                    ui.label(h["name"]).classes("text-sm font-semibold").style("color: var(--cl-fg);")
                ui.label(h["description"]).classes("text-xs cl-clip-2").style("color: var(--cl-fg-muted); min-height: 2.4em;")
                with ui.row().classes("items-center justify-between w-full").style("margin-top: auto;"):
                    ui.label(h["number"]).classes("text-2xl font-extrabold").style("color: var(--cl-emergency);")
                    ui.icon("phone_in_talk").classes("text-[20px] cl-helpline-call").style("color: var(--cl-emergency);")
                if not h["translated"]:
                    chip(tr(c, "em.english_only"), color="muted", outline=True)


STAGE_KEYS = {"Submitted": "st.submitted", "AI Routed": "st.ai_routed", "Assigned": "st.assigned", "Under Review": "st.under_review", "In Progress": "st.in_progress", "Resolved": "st.resolved"}


def status_label(c: AppContainer, status: Any) -> str:
    """A complaint status in the reader's language (st.* keys cover every ComplaintStatus)."""
    return tr(c, f"st.{status}")


CONSENT_LABELS = {"privacy_policy": "I accept the privacy policy", "ai_processing": "Let AI help classify and route my complaints", "data_sharing_government": "Share my complaints with government grievance platforms",
                  "document_storage": "Store documents I upload", "notifications_email": "Send me updates by e-mail"}  # fmt: skip


def download_acknowledgement(c: AppContainer, ctx: Any, complaint_id: str, reference: str) -> None:
    try:
        req = ui.context.client.request
        base = c.public_base_url or (str(req.base_url) if req else "")  # the address this browser actually used, so the QR opens on a phone
        data = c.complaints.acknowledgement(ctx, complaint_id, public_base_url=base, qr_renderer=c.qr_renderer, font_path=c.settings.rti_pdf_font or None)
    except CivicLensError as exc:
        ui.notify(exc.message, type="negative")
        return
    ui.download(data, f"acknowledgement-{reference}.pdf")


def complaint_card(c: AppContainer, x: Any) -> None:
    """One complaint as a tappable card: where it is in the journey (a progress bar over the same
    stages the detail timeline uses), which department holds it, and how urgent it is."""
    from app.services.complaint_status import TIMELINE_STAGES

    status = str(x.status)
    idx = next((i for i, (_, sts) in enumerate(TIMELINE_STAGES) if x.status in sts), None)
    tone = theme.STATUS_COLOR.get(status, "muted")
    card = ui.column().classes("cl-card cl-card-hover cl-complaint-card gap-2").style(f"border-left: 4px solid var(--cl-{tone});")
    with card:
        with ui.row().classes("items-start justify-between w-full no-wrap gap-2"):
            with ui.column().classes("gap-0").style("min-width: 0;"):
                ui.label(x.title).classes("text-sm font-semibold cl-clip-1").style("color: var(--cl-fg);")
                ui.label(f"{x.reference} · {x.created_at:%d %b %Y}").classes("text-xs cl-mono").style("color: var(--cl-fg-subtle);")
            chip(status_label(c, status), color=tone)
        with ui.row().classes("items-center gap-2 flex-wrap"):
            if x.department_code:
                chip(x.department_code.replace("_", " ").capitalize(), color="muted", outline=True, icon="apartment")
            if getattr(x, "priority", None) in ("high", "critical"):
                chip(x.priority, color=theme.PRIORITY_COLOR.get(x.priority, "muted"), icon="priority_high")
            if getattr(x, "escalation_level", 0):
                chip(f"Escalated L{x.escalation_level}", color="danger", icon="trending_up")
        if idx is not None:
            n = len(TIMELINE_STAGES)
            ui.linear_progress(value=(idx + 1) / n, show_value=False, size="6px", color="positive" if idx == n - 1 else "primary").props("rounded")
            ui.label(tr(c, "card.step", n=idx + 1, total=n, stage=tr(c, STAGE_KEYS.get(TIMELINE_STAGES[idx][0], "")) if TIMELINE_STAGES[idx][0] in STAGE_KEYS else TIMELINE_STAGES[idx][0])).classes("text-[11px]").style("color: var(--cl-fg-muted);")
    card.on("click", lambda _e, i=x.id: ui.navigate.to(f"/grievances/{i}"))


def government_panel(c: AppContainer, ctx: Any, complaint_id: str) -> None:
    """Where this complaint can be forwarded. Platforms not connected on this server are one line of
    chips (nothing is sent to them); only connected platforms, or ones with a submission history,
    get a full row with an action - five dead "Request submission" buttons helped nobody."""
    states = c.government.states(ctx, complaint_id)
    if not states:
        return
    tone_for = {"submitted": "success", "not_started": "muted", "consent_required": "warning", "not_configured": "muted", "failed": "danger"}
    live = [st for st in states if st["configured"] or st["state"] not in ("not_started", "not_configured")]
    idle = [st for st in states if st not in live]
    section_title(tr(c, "gov.platforms"), tr(c, "gov.platforms_sub"))
    with ui.column().classes("cl-card gap-3 w-full"):
        for st in live:
            with ui.row().classes("items-center justify-between gap-3 w-full flex-wrap"):
                with ui.column().classes("gap-0"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(st["display_name"]).classes("text-sm font-medium").style("color: var(--cl-fg);")
                        chip(st["state"].replace("_", " "), color=tone_for.get(st["state"], "info"))
                    if st["external_reference"]:
                        ui.label(f"Reference {st['external_reference']}").classes("text-xs cl-mono").style("color: var(--cl-fg-muted);")
                    if not st["consent_granted"]:
                        ui.link("Allow sharing with government platforms in Settings first", "/settings").classes("text-xs")
                    if st["last_error"]:
                        ui.label(st["last_error"]).classes("text-xs").style("color: var(--cl-warning);")
                if st["state"] in ("not_started", "consent_required", "failed") and st["configured"]:

                    def _request_submission(p: str = st["platform"]) -> None:
                        try:
                            c.government.request(ctx, complaint_id, p)
                        except CivicLensError as exc:
                            ui.notify(exc.message, type="negative")
                            return
                        ui.navigate.reload()

                    ui.button(tr(c, "gov.request_submission"), icon="send", on_click=_request_submission).props("outline dense no-caps")
            divider()
        if idle:
            with ui.row().classes("items-center gap-2 flex-wrap"):
                ui.icon("link_off").classes("text-[18px]").style("color: var(--cl-fg-subtle);")
                for st in idle:
                    chip(st["display_name"], color="muted", outline=True)
            ui.label("Not connected on this server yet, so nothing is sent to these platforms. Once an administrator connects one, you can forward this complaint to it from here.").classes("text-xs").style("color: var(--cl-fg-subtle);")


def _timeline(c: AppContainer, steps: list[Any]) -> None:
    from types import SimpleNamespace as _NS

    # stage names in the reader's language; the step objects themselves are left untouched
    status_timeline([_NS(label=tr(c, STAGE_KEYS[s.label]) if s.label in STAGE_KEYS else s.label, state=s.state, at=getattr(s, "at", None)) for s in steps])


# What each timeline event kind means, in words a citizen or officer would use.
EVENT_LOOK: dict[str, tuple[str, str]] = {
    "status_change": ("Status changed", "sync_alt"), "ai_enriched": ("AI analysis added", "auto_awesome"), "sla": ("Response deadline set", "schedule"),
    "escalated": ("Escalated", "trending_up"), "category_corrected": ("Category corrected", "edit"), "transferred": ("Transferred to another department", "swap_horiz"),
    "field_visit": ("Field visit scheduled", "directions_walk"), "inspection": ("Inspection findings", "fact_check"), "work_order": ("Work order raised", "build"),
    "coordination": ("Coordinated with another team", "groups"), "progress": ("Progress update", "trending_up"), "remark": ("Note", "chat"),
    "assigned": ("Assigned", "assignment_ind"), "reopened": ("Reopened by the citizen", "replay"), "routed": ("Routed", "alt_route"), "workflow": ("Automation rule ran", "account_tree"), "feedback": ("Citizen feedback", "rate_review"),
}  # fmt: skip


def _events(events: list[Any]) -> None:
    with ui.column().classes("gap-2 w-full"):
        for e in reversed(events):
            title, icon = EVENT_LOOK.get(e.kind, (e.kind.replace("_", " ").capitalize(), "history"))
            with ui.row().classes("cl-card w-full items-start gap-3"):
                with ui.element("div").classes("cl-stat-icon").style("background: var(--cl-surface-alt); color: var(--cl-fg-muted); width:32px; height:32px; flex: none;"):
                    ui.icon((theme.STATUS_ICON.get(str(e.to_status)) or icon) if e.to_status else icon).classes("text-[16px]")
                with ui.column().classes("gap-1 flex-1"):
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        ui.label(title).classes("text-sm font-medium").style("color: var(--cl-fg);")
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
                mic = ui.button(icon="mic").props('round unelevated aria-label="Speak instead of typing"').style("background: var(--cl-ai); color: #fff;")
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
                    # real sentences in the scripts people actually type in - tap one to see the routing work
                    with ui.row().classes("gap-2 flex-wrap justify-center w-full"):
                        for sample in ("सड़क पर बहुत बड़ा गड्ढा है, कल एक बाइक गिर गई", "Our street has had no water supply for three days", "ನಮ್ಮ ಬೀದಿಯ ದೀಪಗಳು ವಾರದಿಂದ ಆರಿವೆ",
                                       "குப்பை ஐந்து நாட்களாக அள்ளப்படவில்லை", "I want to know how the ward road budget was spent", "माझ्या RTI अर्जाला 30 दिवसांत उत्तर मिळाले नाही"):  # fmt: skip
                            ui.chip(sample, icon="touch_app", on_click=lambda t=sample: box.set_value(t)).props("outline dense")
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
            ui.run_javascript("window.clStartRec()")  # fire-and-forget: the permission prompt can take far longer than run_javascript's 1 s timeout; failures come back as cl_audio_error

        mic.on_click(toggle_mic)
        render()

    @page(c, "/dashboard", "nav.dashboard", roles=CIT)
    def dashboard(c: AppContainer, user: UiUser) -> None:
        d = c.dashboards.citizen(user.ctx)
        prof = c.profiles.get(user.ctx)
        first_name = (user.full_name or user.email).split(" ")[0]
        # ``welcomeBack`` already carries its own trailing punctuation in every language ("Welcome
        # back," / "वापसी पर स्वागत है,"), so adding another comma here rendered "Welcome back,, UI".
        page_header(f"{tr(c, 'welcomeBack')} {first_name}", tr(c, "appTagline"), icon="space_dashboard")
        if not prof.onboarding_complete:
            with ui.row().classes("cl-card w-full items-center justify-between gap-3 flex-wrap").style("background: var(--cl-info-soft); border-color: transparent;"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("info").style("color: var(--cl-info);")
                    ui.label(tr(c, "page.onboarding")).classes("text-sm").style("color: var(--cl-info);")
                ui.button(tr(c, "act.open"), on_click=lambda: ui.navigate.to("/onboarding")).props("outline dense")

        try:  # a department asking to reuse this citizen's verified record is the one thing that needs them now
            waiting = len(c.interop_gateway.list_my_consents(user.ctx, status="pending"))
        except CivicLensError:
            waiting = 0
        if waiting:
            with ui.row().classes("cl-card w-full items-center justify-between gap-3 flex-wrap").style("border: 1.5px solid var(--cl-warning); background: var(--cl-warning-soft);"):
                with ui.row().classes("items-center gap-2 no-wrap").style("flex: 1 1 320px;"):
                    ui.icon("how_to_reg").classes("text-[22px]").style("color: var(--cl-warning);")
                    ui.label(tr(c, "dash.consent_waiting").replace("{n}", str(waiting))).classes("text-sm font-medium").style("color: var(--cl-fg);")
                ui.button(tr(c, "dash.consent_review"), icon="arrow_forward", on_click=lambda: ui.navigate.to("/my-data")).props("unelevated color=warning text-color=dark no-caps")

        with ui.row().classes("gap-3 w-full flex-wrap"):
            stat_tile(tr(c, "card.active"), d["open"], color="info", icon="assignment")
            stat_tile(tr(c, "card.resolved"), d["resolved"], color="success", icon="task_alt")
            stat_tile(tr(c, "card.unread"), d["unread_notifications"], color="warning", icon="notifications")
            stat_tile(tr(c, "card.awaiting_feedback"), len(d["pending_feedback"]), color="ai", icon="rate_review")

        with ui.row().classes("gap-3 flex-wrap items-center"):
            ui.button(tr(c, "nav.report"), icon="add_circle", on_click=lambda: ui.navigate.to("/report")).props("unelevated size=lg").classes("cl-btn-glow")
            ui.button(tr(c, "nav.rti"), icon="gavel", on_click=lambda: ui.navigate.to("/rti")).props("outline")
            ui.button(tr(c, "nav.copilot"), icon="smart_toy", on_click=lambda: ui.navigate.to("/copilot")).props("outline")
            ui.button(tr(c, "nav.emergency"), icon="emergency", on_click=lambda: ui.navigate.to("/emergency")).props("flat").style("color: var(--cl-emergency);")

        if not d["has_data"]:
            state_panel(icon="inbox", title=tr(c, "msg.empty_complaints"), body=tr(c, "msg.first_report"), action_label=tr(c, "nav.report"), on_action=lambda: ui.navigate.to("/report"))
            return

        if d["pending_feedback"]:
            first = d["pending_feedback"][0]
            with ui.row().classes("cl-card w-full items-center justify-between gap-3 flex-wrap").style("background: var(--cl-success-soft); border-color: transparent;"):
                with ui.row().classes("items-center gap-2 no-wrap"):
                    ui.icon("task_alt").classes("text-[22px]").style("color: var(--cl-success);")
                    ui.label(tr(c, "card.awaiting_feedback") + f" ({len(d['pending_feedback'])})").classes("text-sm font-medium").style("color: var(--cl-fg);")
                ui.button(tr(c, "act.open"), icon="rate_review", on_click=lambda: ui.navigate.to(f"/grievances/{first}")).props("unelevated color=positive no-caps")
        with ui.row().classes("items-center justify-between w-full"):
            section_title(tr(c, "nav.grievances"))
            ui.link(tr(c, "act.view_all"), "/grievances").classes("text-sm")
        with ui.element("div").classes("cl-card-grid w-full"):
            for x in d["recent"]:
                complaint_card(c, x)

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
        qp = ui.context.client.request.query_params if ui.context.client.request else {}
        pre_text = (qp.get("text") or "")[:1500]
        pre_voice = qp.get("voice") or None
        q_voice_state: dict[str, Any] = {"id": pre_voice}
        d_voice_state: dict[str, Any] = {"id": pre_voice}

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
                    with ui.row().classes("gap-2 items-center q-mt-xs"):
                        ui.icon("auto_awesome").classes("text-[16px]").style("color: var(--cl-ai);")
                        ui.label(f"{tr(c, 'lbl.category')}: {cm.category.replace('_', ' ').title()}").classes("text-sm font-medium").style("color: var(--cl-fg);")
                        chip(cm.severity, color=theme.PRIORITY_COLOR.get(cm.severity, "muted"))
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
                ui.button(tr(c, "gr.ack_download"), icon="receipt_long", on_click=lambda: download_acknowledgement(c, user.ctx, cm.id, cm.reference)).props("outline no-caps").classes("w-full")
                ui.button(tr(c, "nav.grievances"), icon="arrow_forward", on_click=lambda: ui.navigate.to(f"/grievances/{cm.id}")).props("color=primary unelevated").classes("w-full")
            dlg.open()

        def rotate_crid() -> None:
            # the client-request-id is an idempotency key - the backend treats a repeat submission
            # under the same one as a replay of the SAME complaint, not a new one, so a fresh id is
            # required before the form can be used to file the next complaint.
            nonlocal crid
            crid = uuid.uuid4().hex

        def create(data: dict[str, Any], on_success: Any = None) -> None:
            try:
                r = c.complaints.create(user.ctx, ComplaintInput(client_request_id=crid, **{k: v for k, v in data.items() if v not in (None, "")}))
            except CivicLensError as exc:
                ui.notify(exc.message + (f" {exc.details}" if exc.details else ""), type="negative")
                return
            receipt(r.complaint, r.warnings)
            rotate_crid()
            if on_success is not None:
                on_success()

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

        def evidence_icon(mime: str) -> str:
            if mime.startswith("image/"):
                return "image"
            if mime == "application/pdf":
                return "picture_as_pdf"
            if mime.startswith("text/"):
                return "article"
            return "description"

        def human_size(n: int) -> str:
            size = float(n)
            for unit in ("B", "KB", "MB"):
                if size < 1024 or unit == "MB":
                    return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
                size /= 1024
            return f"{size:.1f} MB"

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
        panes = ui.column().classes("w-full max-w-3xl gap-3")  # created after the mode switch so the switch sits on top

        from app.i18n.languages import LANGUAGES

        with panes:
            quick_pane = ui.column().classes("w-full gap-3")
            with quick_pane, ui.column().classes("cl-card w-full gap-3"):
                with ui.element("div").classes("cl-ask w-full"):
                    ui.icon("add_location_alt").classes("text-[20px]").style("color: var(--cl-primary, var(--cl-ai));")
                    q_desc = ui.textarea(tr(c, "report.q_what"), value=pre_text).props("borderless autogrow rows=3").classes("flex-1")
                    q_mic = ui.button(icon="mic").props('round unelevated aria-label="Speak instead of typing"')
                q_voice_hint = ui.label("").classes("text-xs").style("color: var(--cl-fg-subtle);")
                field_hint(tr(c, "report.q_what_hint"))
                # live preview with the same rule classifier the server runs first - instant, local,
                # no model call - so the citizen sees where this is heading before pressing submit
                preview = ui.row().classes("cl-route-preview items-center gap-2 w-full no-wrap")
                preview.set_visibility(False)
                with preview:
                    ui.icon("auto_awesome").classes("text-[18px]").style("color: var(--cl-ai);")
                    preview_lbl = ui.label("").classes("text-sm font-medium").style("color: var(--cl-fg);")
                    preview_chip = ui.row().classes("items-center")
                    ui.label(tr(c, "report.preview_note")).classes("text-[11px] q-ml-auto gt-xs").style("color: var(--cl-fg-subtle);")

                def update_preview() -> None:
                    from app.services.classification_service import RuleClassifier, compute_priority

                    text = (q_desc.value or "").strip()
                    r = RuleClassifier().classify(text) if len(text) >= 12 else None
                    if r is None or r.category == "other" or r.ambiguous:
                        preview.set_visibility(False)
                        return
                    pr = compute_priority(r.severity, affects_safety=r.affects_safety, near_sensitive_site=r.near_sensitive_site)["priority"]
                    preview_lbl.set_text(tr(c, "report.preview_to").replace("{dept}", r.category.replace("_", " ").capitalize()))
                    preview_chip.clear()
                    with preview_chip:
                        chip(pr, color=theme.PRIORITY_COLOR.get(pr, "muted"))
                    preview.set_visibility(True)

                q_desc.on_value_change(lambda _e: update_preview())

                with ui.row().classes("gap-2 flex-wrap items-center q-mt-xs"):
                    ui.label(tr(c, "legal.examples_label")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                    for key in ("report.example.pothole", "report.example.garbage", "report.example.power", "report.example.water"):
                        text = tr(c, key)
                        ui.chip(text, icon="edit_note", on_click=lambda t=text: setattr(q_desc, "value", t)).props("outline dense")

                divider()

                with ui.row().classes("gap-3 w-full flex-wrap items-end"):
                    q_where = ui.input(tr(c, "report.q_where")).props("outlined dense").classes("flex-1").style("min-width: 220px;")
                    q_language = ui.select({k: f"{v.native} ({k})" for k, v in LANGUAGES.items()}, value=lang(), label=tr(c, "lbl.language")).props("outlined dense").classes("w-44")
                field_hint(tr(c, "report.q_where_hint"))
                ui.label(tr(c, "report.manual_location_hint")).classes("text-xs").style("color: var(--cl-fg-subtle); font-style: italic;")
                ui.label(tr(c, "report.q_voice_lang_hint")).classes("text-xs").style("color: var(--cl-fg-subtle); font-style: italic;")

                divider()

                with ui.row().classes("gap-3 items-center w-full flex-wrap"):
                    q_locate_btn = ui.button(tr(c, "report.q_use_location"), icon="my_location").props("outline dense")
                q_pin_card = ui.row().classes("cl-badge cl-badge-info items-center gap-2")
                q_pin_card.set_visibility(False)
                with q_pin_card:
                    ui.icon("place").classes("text-[15px]")
                    q_coords = ui.label("")
                q_geo: dict[str, Any] = {"lat": None, "lng": None, "address": None, "city": None}

                def _drop_evidence(rid: str) -> None:
                    evidence_records.pop(rid, None)
                    q_redraw()

                def q_redraw() -> None:
                    q_files.clear()
                    with q_files:
                        for rid, rec in evidence_records.items():
                            with ui.row().classes("cl-badge cl-badge-info items-center gap-2"):
                                ui.icon(evidence_icon(rec.mime)).classes("text-[14px]")
                                ui.label(f"{rec.name} · {human_size(rec.size)}")
                                ui.icon("close").classes("text-[14px] cursor-pointer").on("click", lambda i=rid: _drop_evidence(i))

                def q_upload(e: Any) -> None:
                    try:
                        rec = c.complaints.upload_evidence(user.ctx, e.name, e.content.read(), e.type)
                    except CivicLensError as exc:
                        ui.notify(exc.message, type="negative")
                        return
                    evidence_records[rec.id] = rec
                    q_redraw()

                update_preview()
                ui.upload(on_upload=q_upload, auto_upload=True, multiple=True, label=tr(c, "report.q_photo")).props("flat dense accept=image/*,.pdf").classes("cl-dropzone w-full")
                q_files = ui.row().classes("gap-2 flex-wrap w-full")

                def reset_quick_form() -> None:
                    q_desc.value, q_where.value = "", ""
                    q_language.value = lang()
                    q_pin_card.set_visibility(False)
                    q_coords.set_text("")
                    q_geo["lat"] = q_geo["lng"] = q_geo["address"] = q_geo["city"] = None
                    q_voice_state["id"] = None
                    q_voice_hint.set_text("")
                    # evidence is one shared pool between Quick and Detailed mode (switching tabs keeps
                    # what you've attached) - a submitted complaint clears it for both, so redraw both.
                    evidence_records.clear()
                    q_redraw()
                    redraw_evidence()

                def q_submit() -> None:
                    desc = (q_desc.value or "").strip()
                    if len(desc) < 10:
                        ui.notify(tr(c, "report.q_too_short"), type="warning")
                        return
                    title = derive_title(desc)
                    if len(title) < 5:
                        title = desc[:90]
                    create({
                        "title": title, "description": desc, "language": q_language.value or lang(),
                        "address": (q_where.value or "").strip() or None, "city": q_geo["city"],
                        "lat": q_geo["lat"], "lng": q_geo["lng"],
                        "evidence_ids": list(evidence_records.keys()), "voice_id": q_voice_state["id"],
                    }, on_success=reset_quick_form)

                ui.button(tr(c, "act.submit"), icon="send", on_click=q_submit).props("unelevated size=lg").classes("cl-btn-glow w-full")
                ui.label(tr(c, "report.q_footnote")).classes("text-xs").style("color: var(--cl-fg-subtle); line-height:1.5;")

            detail_pane = ui.column().classes("w-full gap-0")
            detail_pane.set_visibility(False)

        # ---- shared live-mic infrastructure: one global JS bridge (MIC_JS), any number of mic
        # buttons on this page. Only one recording can ever be in progress at a time (one physical
        # microphone), so a single "which mic is active" pointer is enough to route the transcript
        # back to the right text field/language selector/hint label - registering a separate
        # cl_audio listener per mic button would make EVERY listener fire on EVERY recording.
        ui.add_body_html(f"<script>{MIC_JS}</script>")
        voice_caps = c.voice.capabilities()
        _active_mic: dict[str, Any] = {"target": None}

        def wire_mic(mic_btn: Any, target_field: Any, lang_select: Any, hint_label: Any, voice_state: dict[str, Any]) -> None:
            mic_btn.set_enabled(voice_caps["state"] == "CONFIGURED")
            mic_btn.tooltip(tr(c, "assistant.mic_tip") if voice_caps["state"] == "CONFIGURED" else tr(c, "assistant.mic_off"))

            async def toggle() -> None:
                if _active_mic["target"] is not None:
                    mic_btn.props("icon=mic").classes(remove="cl-mic-live")
                    _active_mic["target"] = None
                    ui.run_javascript("window.clStopRec()")
                    return
                _active_mic["target"] = {"field": target_field, "lang": lang_select, "hint": hint_label, "voice": voice_state, "btn": mic_btn}
                mic_btn.props("icon=stop").classes(add="cl-mic-live")
                hint_label.set_text(tr(c, "assistant.listening"))
                ui.run_javascript("window.clStartRec()")  # fire-and-forget: the permission prompt can take far longer than run_javascript's 1 s timeout; failures come back as cl_audio_error

            mic_btn.on_click(toggle)

        def on_audio(e: Any) -> None:
            target = _active_mic["target"]
            _active_mic["target"] = None
            if target is None:
                return  # a stray event with nothing active - nothing to route it to
            target["btn"].props("icon=mic").classes(remove="cl-mic-live")
            import base64 as _b64

            try:
                raw = _b64.b64decode(e.args["b64"])
            except (KeyError, ValueError):
                ui.notify(tr(c, "assistant.mic_failed"), type="negative")
                return
            try:
                r = c.voice.transcribe(user.ctx, raw, e.args.get("mime") or "audio/webm", target["lang"].value or "auto")
            except CivicLensError as exc:
                ui.notify(exc.message, type="negative")
                return
            if r.status != "OK" or not r.transcript:
                ui.notify(r.error or r.status, type="warning")
                return
            target["voice"]["id"] = r.id
            target["field"].value = ((target["field"].value or "") + " " + r.transcript).strip()  # same language, native script - never translated
            if r.language_detected and r.language_detected in target["lang"].options:
                target["lang"].value = r.language_detected
            target["hint"].set_text(tr(c, "assistant.heard", lang=r.language_detected or "?", how=r.detected_by))

        def on_audio_error(e: Any) -> None:
            target = _active_mic["target"]
            _active_mic["target"] = None
            if target is not None:
                target["btn"].props("icon=mic").classes(remove="cl-mic-live")
            ui.notify(tr(c, "assistant.mic_denied") + " " + str(e.args.get("message", "")), type="negative")

        ui.on("cl_audio", on_audio)
        ui.on("cl_audio_error", on_audio_error)

        wire_mic(q_mic, q_desc, q_language, q_voice_hint, q_voice_state)

        # ---- shared "use my location" infrastructure: same one-active-request rule as the mic -
        # each location button just registers itself via wire_locate(); the actual browser
        # geolocation call and the real reverse-geocode lookup happen once, centrally, and get
        # routed back to whichever button asked.
        _active_geo: dict[str, Any] = {"target": None}

        def wire_locate(locate_btn: Any, coords_label: Any, geo_state: dict[str, Any], where_field: Any, *, pin_card: Any = None, on_coords: Any = None) -> None:
            def start() -> None:
                _active_geo["target"] = {"coords": coords_label, "geo": geo_state, "where": where_field, "pin": pin_card, "btn": locate_btn, "on_coords": on_coords}
                if pin_card is not None:
                    pin_card.set_visibility(True)
                coords_label.set_text(tr(c, "report.q_geo_looking_up"))
                ui.run_javascript(
                    "navigator.geolocation.getCurrentPosition("
                    "p => emitEvent('cl_geo', {lat: p.coords.latitude, lng: p.coords.longitude}),"
                    "e => emitEvent('cl_geo_error', {message: e.message}));",
                )

            locate_btn.on_click(start)

        async def resolve_location(lat_v: float, lng_v: float, target: dict[str, Any]) -> None:
            """Look up and display the address for one specific point - shared by the GPS button, a
            map click and manually-typed coordinates, so however a citizen picks a location, the
            shown address always reflects THAT point, never a stale one from an earlier pick."""
            target["geo"]["lat"], target["geo"]["lng"] = lat_v, lng_v
            if target["pin"] is not None:
                target["pin"].set_visibility(True)
            target["coords"].set_text(tr(c, "report.q_geo_looking_up"))
            result = await run_with_loading(target["btn"], c.geocoding.reverse, lat_v, lng_v)
            if result is not None and (result.area or result.city or result.display_name):
                pretty = ", ".join(p for p in (result.area, result.city, result.state, result.pincode) if p) or result.display_name
                target["coords"].set_text(pretty or "")
                target["geo"]["address"], target["geo"]["city"] = pretty or result.display_name, result.city
                if target["where"] is not None:
                    target["where"].value = pretty or result.display_name or ""
            else:  # geocoding failed or returned nothing - the raw coordinates are still real and useful, never fabricated
                target["coords"].set_text(f"{tr(c, 'report.q_pinned')} {lat_v:.5f}, {lng_v:.5f}")

        async def dispatch_geo(e: Any) -> None:
            target = _active_geo["target"]
            _active_geo["target"] = None
            if target is None:
                return
            lat_v, lng_v = round(float(e.args["lat"]), 6), round(float(e.args["lng"]), 6)
            if target["on_coords"] is not None:
                target["on_coords"](lat_v, lng_v)
            await resolve_location(lat_v, lng_v, target)

        def dispatch_geo_error(e: Any) -> None:
            target = _active_geo["target"]
            _active_geo["target"] = None
            if target is not None:
                if target["pin"] is not None:
                    target["pin"].set_visibility(True)
                target["coords"].set_text(tr(c, "report.q_geo_failed") + " " + str(e.args.get("message", "")))

        ui.on("cl_geo", dispatch_geo)
        ui.on("cl_geo_error", dispatch_geo_error)

        wire_locate(q_locate_btn, q_coords, q_geo, q_where, pin_card=q_pin_card)

        # ------------------------------------------------------------------ detailed mode
        with detail_pane, ui.column().classes("w-full max-w-3xl gap-0"):
            with ui.stepper().props("flat animated").classes("w-full cl-card !p-0") as stepper:
                # ---- Step 1: describe -----------------------------------------------------------
                with ui.step("describe", title=tr(c, "report.step_describe"), icon="edit_note"):
                    title = ui.input(tr(c, "lbl.title"), value=derive_title(pre_text)).props("outlined dense").classes("w-full")
                    field_hint(tr(c, "report.title_hint"))
                    with ui.element("div").classes("cl-ask w-full"):
                        ui.icon("edit_note").classes("text-[20px]").style("color: var(--cl-ai);")
                        desc = ui.textarea(tr(c, "lbl.description"), value=pre_text).props("borderless autogrow rows=3").classes("flex-1")
                        d1_mic = ui.button(icon="mic").props('round unelevated aria-label="Speak instead of typing"')
                    d1_voice_hint = ui.label("").classes("text-xs").style("color: var(--cl-fg-subtle);")
                    field_hint(tr(c, "report.desc_hint"))

                    with ui.row().classes("gap-2 flex-wrap items-center q-mt-xs"):
                        ui.label(tr(c, "legal.examples_label")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                        for key in ("report.example.pothole", "report.example.garbage", "report.example.power", "report.example.water"):
                            example_text = tr(c, key)

                            def use_example(t: str = example_text) -> None:
                                desc.value = t
                                if not (title.value or "").strip():
                                    title.value = derive_title(t)

                            ui.chip(example_text, icon="edit_note", on_click=use_example).props("outline dense")

                    language = ui.select({k: f"{v.native} ({k})" for k, v in LANGUAGES.items()}, value=lang(), label=tr(c, "lbl.language")).props("outlined dense").classes("w-56")
                    wire_mic(d1_mic, desc, language, d1_voice_hint, d_voice_state)
                    with ui.stepper_navigation():
                        ui.button(tr(c, "act.next"), icon="arrow_forward", on_click=stepper.next).props("color=primary unelevated")

                # ---- Step 2: category & location -------------------------------------------------
                with ui.step("locate", title=tr(c, "report.step_locate"), icon="place"):
                    section_title(tr(c, "lbl.category"))
                    with ui.row().classes("gap-3 w-full flex-wrap"):
                        cat = ui.select({"": tr(c, "assistant.unsure"), **{k: k.replace("_", " ").title() for k in CATEGORIES}}, value="", label=tr(c, "lbl.category")).props("outlined dense").classes("w-52")
                        ward = ui.input(tr(c, "lbl.ward") + " (" + tr(c, "lbl.optional") + ")").props("outlined dense").classes("w-40")

                    divider()
                    section_title(tr(c, "lbl.location"))
                    d2_address = ui.input(tr(c, "report.q_where")).props("outlined dense").classes("w-full")
                    field_hint(tr(c, "report.q_where_hint"))
                    ui.label(tr(c, "report.manual_location_hint")).classes("text-xs").style("color: var(--cl-fg-subtle); font-style: italic;")
                    field_hint(tr(c, "report.map_hint"))
                    with ui.row().classes("gap-3 items-center w-full flex-wrap"):
                        d2_locate_btn = ui.button(tr(c, "report.q_use_location"), icon="my_location").props("outline dense")
                    d2_pin_card = ui.row().classes("cl-badge cl-badge-info items-center gap-2")
                    d2_pin_card.set_visibility(False)
                    with d2_pin_card:
                        ui.icon("place").classes("text-[15px]")
                        d2_coords = ui.label("")
                    d2_geo: dict[str, Any] = {"lat": None, "lng": None, "address": None, "city": None}
                    with ui.row().classes("gap-3 items-end w-full flex-wrap"):
                        lat = ui.number(tr(c, "lbl.latitude"), format="%.6f").props("outlined dense").classes("w-40")
                        lng = ui.number(tr(c, "lbl.longitude"), format="%.6f").props("outlined dense").classes("w-40")
                    field_hint(tr(c, "report.coords_hint"))
                    center = (12.9716, 77.5946)
                    m = ui.leaflet(center=center, zoom=11).classes("w-full h-64").style("border-radius: var(--cl-radius-md); overflow: hidden;")
                    marker: dict[str, Any] = {}

                    def place_marker(lat_v: float, lng_v: float, *, recenter: bool = False) -> None:
                        lat.value, lng.value = lat_v, lng_v
                        if "m" in marker:
                            m.remove_layer(marker["m"])
                        marker["m"] = m.marker(latlng=(lat_v, lng_v))
                        if recenter:
                            m.set_center((lat_v, lng_v))

                    d2_target = {"coords": d2_coords, "geo": d2_geo, "where": d2_address, "pin": d2_pin_card, "btn": d2_locate_btn}

                    async def on_click(e: Any) -> None:
                        lat_v, lng_v = round(e.args["latlng"]["lat"], 6), round(e.args["latlng"]["lng"], 6)
                        place_marker(lat_v, lng_v)
                        await resolve_location(lat_v, lng_v, d2_target)

                    async def apply_manual_coords() -> None:
                        if lat.value is None or lng.value is None:
                            return
                        lat_v, lng_v = round(float(lat.value), 6), round(float(lng.value), 6)
                        place_marker(lat_v, lng_v, recenter=True)
                        await resolve_location(lat_v, lng_v, d2_target)

                    m.on("map-click", on_click)
                    lat.on("blur", apply_manual_coords)
                    lng.on("blur", apply_manual_coords)
                    # a geocoded street address always overwrites `d2_address` (never `ward` - a distinct
                    # municipal administrative unit the reverse-geocoder cannot determine): whichever pin
                    # was set last - GPS, a map click, or typed coordinates - is the one the address must
                    # match, so a stale address from an earlier pick is never left showing.
                    wire_locate(d2_locate_btn, d2_coords, d2_geo, d2_address, pin_card=d2_pin_card, on_coords=lambda la, ln: place_marker(la, ln, recenter=True))
                    with ui.stepper_navigation():
                        ui.button(tr(c, "act.back"), on_click=stepper.previous).props("flat")
                        ui.button(tr(c, "act.next"), icon="arrow_forward", on_click=stepper.next).props("color=primary unelevated")

                # ---- Step 3: evidence --------------------------------------------------------------
                with ui.step("evidence", title=tr(c, "report.step_evidence"), icon="attach_file"):
                    section_title(tr(c, "lbl.evidence"))
                    ev_list = ui.row().classes("gap-2 flex-wrap w-full")

                    def _drop_evidence(rid: str) -> None:
                        evidence_records.pop(rid, None)
                        redraw_evidence()

                    def redraw_evidence() -> None:
                        ev_list.clear()
                        with ev_list:
                            for rid, rec in evidence_records.items():
                                with ui.row().classes("cl-badge cl-badge-info items-center gap-2"):
                                    ui.icon(evidence_icon(rec.mime)).classes("text-[14px]")
                                    ui.label(f"{rec.name} · {human_size(rec.size)}")
                                    ui.icon("close").classes("text-[14px] cursor-pointer").on("click", lambda i=rid: _drop_evidence(i))

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
                    if voice_caps["state"] != "CONFIGURED":
                        info_banner(tr(c, "report.stt_off"), "orange")
                    else:
                        with ui.row().classes("gap-3 items-center"):
                            d3_mic = ui.button(icon="mic").props('round unelevated aria-label="Speak instead of typing"')
                            ui.label(tr(c, "report.record_audio")).classes("text-sm").style("color: var(--cl-fg);")
                        d3_voice_hint = ui.label("").classes("text-xs").style("color: var(--cl-fg-subtle);")
                        wire_mic(d3_mic, desc, language, d3_voice_hint, d_voice_state)
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
                                if d2_address.value:
                                    chip(d2_address.value, color="muted", outline=True)
                                if lat.value and lng.value:
                                    chip(f"{lat.value:.4f}, {lng.value:.4f}", color="muted", outline=True)
                                chip(tr(c, "report.n_evidence", n=len(evidence_records)), color="muted", outline=True)

                    stepper.on_value_change(lambda e: draw_review() if e.value == "review" else None)
                    draw_review()
                    status = ui.label().classes("text-xs").style("color: var(--cl-fg-subtle);")

                    def payload() -> dict[str, Any]:
                        return {"title": title.value, "description": desc.value, "language": language.value, "category": cat.value or None, "ward": ward.value or None,
                                "address": (d2_address.value or "").strip() or None, "city": d2_geo["city"], "lat": lat.value, "lng": lng.value,
                                "evidence_ids": list(evidence_records.keys()), "voice_id": d_voice_state["id"]}  # fmt: skip

                    def autosave() -> None:
                        try:
                            c.drafts.save(user.ctx, "complaint", payload(), crid)
                            status.set_text(tr(c, "msg.saved"))
                        except CivicLensError:
                            status.set_text(tr(c, "msg.unsaved"))

                    ui.timer(10.0, autosave)  # server-side draft; survives page reloads and dropped connections

                    def reset_detailed_form() -> None:
                        title.value, desc.value = "", ""
                        language.value = lang()
                        cat.value, ward.value, d2_address.value = "", "", ""
                        d2_pin_card.set_visibility(False)
                        d2_coords.set_text("")
                        d2_geo["lat"] = d2_geo["lng"] = d2_geo["address"] = d2_geo["city"] = None
                        lat.value, lng.value = None, None
                        if "m" in marker:
                            m.remove_layer(marker["m"])
                            marker.pop("m", None)
                        m.set_center(center)
                        d_voice_state["id"] = None
                        d1_voice_hint.set_text("")
                        if voice_caps["state"] == "CONFIGURED":
                            d3_voice_hint.set_text("")
                        # evidence is the shared pool with Quick mode - clear and redraw both.
                        evidence_records.clear()
                        redraw_evidence()
                        q_redraw()
                        stepper.set_value("describe")
                        draw_review()

                    def submit() -> None:
                        create(payload(), on_success=reset_detailed_form)

                    def pending() -> None:
                        for dr in c.drafts.sync_all(user.ctx):
                            ui.notify(f"{dr.status}: {dr.result_ref or dr.error}", type="positive" if dr.status == "synced" else "negative")

                    with ui.stepper_navigation():
                        ui.button(tr(c, "act.back"), on_click=stepper.previous).props("flat")
                        ui.button(tr(c, "act.submit"), icon="send", on_click=submit).props("unelevated").classes("cl-btn-glow")
                        ui.button(tr(c, "act.sync"), icon="sync", on_click=pending).props("flat")

    @page(c, "/grievances", "nav.grievances", roles=CIT)
    def grievances(c: AppContainer, user: UiUser) -> None:
        def new_report() -> None:
            ui.button(tr(c, "nav.report"), icon="add_circle", on_click=lambda: ui.navigate.to("/report")).props("unelevated no-caps")

        page_header(tr(c, "nav.grievances"), icon="assignment", actions=new_report)
        state = {"f": "all"}

        def _on_filter_change(e: Any) -> None:
            state["f"] = e.value
            draw()

        # filters sit above the list they filter (they used to render underneath the table)
        with ui.tabs(on_change=_on_filter_change).props("dense no-caps align=left active-color=primary indicator-color=primary").classes("w-full") as tabs:
            for f in TRACKER_FILTERS:
                ui.tab(f, label=tr(c, f"filter.{f}"))
        box = ui.element("div").classes("cl-card-grid w-full")

        def draw() -> None:
            box.clear()
            items = c.complaints.list_mine(user.ctx, filter_name=state["f"])
            with box:
                if not items:
                    state_panel(icon="inbox", title=tr(c, "msg.empty_complaints"), body=tr(c, "msg.first_report"), action_label=tr(c, "nav.report"), on_action=lambda: ui.navigate.to("/report"))
                for x in items:
                    complaint_card(c, x)

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
                    chip(status_label(c, cm.status), color=theme.STATUS_COLOR.get(str(cm.status), "muted"))
                    if cm.escalation_level:
                        chip(f"Escalated L{cm.escalation_level}", color="danger")
            ui.button(tr(c, "gr.ack_download"), icon="receipt_long", on_click=lambda: download_acknowledgement(c, user.ctx, cm.id, cm.reference)).props("outline no-caps")
        with ui.row().classes("gap-6 w-full flex-wrap"):
            with ui.column().classes("gap-4 flex-1").style("min-width: 320px;"):
                with ui.column().classes("cl-card gap-2 w-full"):
                    ui.label(cm.description).classes("text-sm").style("color: var(--cl-fg);")
                    divider()
                    with ui.row().classes("gap-6 flex-wrap"):
                        with ui.column().classes("gap-0"):
                            ui.label(tr(c, "lbl.category")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                            ui.label(cm.category.replace("_", " ").title()).classes("text-sm font-medium").style("color: var(--cl-fg);")
                        with ui.column().classes("gap-0"):
                            ui.label(tr(c, "lbl.severity")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                            chip(cm.severity, color=theme.PRIORITY_COLOR.get(cm.severity, "muted"))
                        with ui.column().classes("gap-0"):
                            ui.label(tr(c, "lbl.department")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                            ui.label(run_in_uow(c, lambda uow: {x.code: x.name for x in uow.config.departments()}).get(cm.department_code or "", cm.department_code or "-")).classes("text-sm font-medium").style("color: var(--cl-fg);")
                        with ui.column().classes("gap-0"):
                            ui.label(tr(c, "lbl.priority")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                            chip(cm.priority, color=theme.PRIORITY_COLOR.get(cm.priority, "muted"))
                        if cm.sla_due_at:
                            with ui.column().classes("gap-0"):
                                ui.label(tr(c, "lbl.due")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                                ui.label(cm.sla_due_at.strftime("%d %b %Y %H:%M")).classes("text-sm font-medium").style("color: var(--cl-fg);")
                    if cm.translated_text:
                        divider()
                        ui.label(tr(c, "gr.translation_note")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                        ui.label(cm.translated_text).classes("text-sm").style("color: var(--cl-fg-muted);")

                from app.services.complaint_status import FINISHED

                overdue = cm.status not in FINISHED and ((cm.sla_due_at is not None and cm.sla_due_at < c.clock()) or cm.escalation_level > 0)
                if overdue:
                    # the statutory next step when a department sits on a complaint: ask, under the RTI
                    # Act, what action was taken - drafted from this complaint so nothing is retyped
                    with ui.row().classes("cl-card w-full items-center gap-3 flex-wrap").style("border: 1.5px solid var(--cl-danger); background: var(--cl-danger-soft);"):
                        ui.icon("gavel").classes("text-[26px]").style("color: var(--cl-danger);")
                        with ui.column().classes("gap-0").style("flex: 1 1 260px;"):
                            ui.label(tr(c, "rti.escalate_title")).classes("text-sm font-semibold").style("color: var(--cl-fg);")
                            ui.label(tr(c, "rti.escalate_body")).classes("text-xs").style("color: var(--cl-fg-muted);")
                        ui.button(tr(c, "rti.escalate_btn"), icon="edit_document", on_click=lambda: ui.navigate.to(f"/rti?complaint={cm.id}")).props("unelevated color=negative no-caps")

                if str(cm.status) in ("resolved", "closed") and not d["feedback"]:
                    # verified closure: the citizen confirms the fix with a rating, or says it is not fixed
                    with ui.column().classes("cl-card gap-3 w-full").style("border: 1.5px solid var(--cl-success);"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("task_alt").classes("text-[24px]").style("color: var(--cl-success);")
                            ui.label(tr(c, "fb.title")).classes("text-base font-semibold").style("color: var(--cl-fg);")
                        ui.label(tr(c, "fb.body")).classes("text-sm").style("color: var(--cl-fg-muted);")
                        stars = ui.rating(value=0, max=5, size="2.2em", icon="star_border", icon_selected="star", color="amber")
                        comment = ui.textarea(tr(c, "lbl.comment")).props("outlined autogrow rows=2").classes("w-full")

                        def send() -> None:
                            if not stars.value:
                                ui.notify(tr(c, "fb.pick_stars"), type="warning")
                                return
                            try:
                                c.complaints.add_feedback(user.ctx, cm.id, int(stars.value), comment.value)
                            except CivicLensError as exc:
                                ui.notify(exc.message, type="negative")
                                return
                            ui.notify(tr(c, "fb.thanks"), type="positive")
                            ui.navigate.reload()

                        def reopen_dialog() -> None:
                            with ui.dialog() as dlg, ui.column().classes("cl-card gap-3 w-full max-w-md"):
                                ui.label(tr(c, "fb.reopen_title")).classes("text-base font-semibold").style("color: var(--cl-fg);")
                                why = ui.textarea(tr(c, "fb.reopen_why")).props("outlined autogrow").classes("w-full")

                                def go() -> None:
                                    try:
                                        c.complaints.reopen_by_citizen(user.ctx, cm.id, why.value or "")
                                    except CivicLensError as exc:
                                        ui.notify(exc.message, type="negative")
                                        return
                                    ui.notify(tr(c, "fb.reopened"), type="positive")
                                    ui.navigate.reload()

                                ui.button(tr(c, "fb.reopen_btn"), icon="replay", on_click=go).props("unelevated color=negative no-caps")
                            dlg.open()

                        with ui.row().classes("gap-2 items-center flex-wrap"):
                            ui.button(tr(c, "act.submit"), icon="send", on_click=send).props("unelevated color=positive no-caps")
                            if str(cm.status) == "resolved":
                                ui.button(tr(c, "fb.not_fixed"), icon="replay", on_click=reopen_dialog).props("flat no-caps color=negative")
                elif d["feedback"]:
                    with ui.row().classes("items-center gap-2"):
                        ui.rating(value=d["feedback"].rating, max=5, size="1.4em", icon="star_border", icon_selected="star", color="amber").props("readonly")
                        ui.label(tr(c, "fb.your_rating")).classes("text-xs").style("color: var(--cl-fg-subtle);")

                section_title(tr(c, "lbl.evidence"))
                if not d["evidence"]:
                    state_panel(icon="attach_file", title=tr(c, "gr.no_evidence"))
                else:
                    with ui.row().classes("gap-2 flex-wrap"):
                        for ev in d["evidence"]:
                            chip(f"{ev.name} · {ev.analysis_status}", color="info", outline=True)
                if cm.status not in FINISHED:
                    def add_more(e: Any) -> None:
                        try:
                            rec = c.complaints.upload_evidence(user.ctx, e.name, e.content.read(), e.type)
                            c.complaints.add_evidence(user.ctx, cm.id, rec.id)
                        except CivicLensError as exc:
                            ui.notify(exc.message, type="negative")
                            return
                        ui.notify(tr(c, "gr.evidence_added"), type="positive")
                        ui.navigate.reload()

                    ui.upload(on_upload=add_more, auto_upload=True, label=tr(c, "gr.add_evidence")).props("flat accept=.png,.jpg,.jpeg,.pdf,.txt,.docx").classes("cl-dropzone w-full max-w-md")

                government_panel(c, user.ctx, cm.id)


            with ui.column().classes("gap-4").style("min-width: 280px; max-width: 340px; flex: 1;"):
                section_title(tr(c, "gr.status_timeline"))
                with ui.column().classes("cl-card w-full"):
                    _timeline(c, d["timeline"])
                section_title(tr(c, "col.history"))
                _events(d["events"])

    @page(c, "/rti", "nav.rti", roles=CIT)
    def rti(c: AppContainer, user: UiUser) -> None:
        import base64

        from app.i18n.languages import LANGUAGES

        page_header(tr(c, "tabRTI"), tr(c, "tipText"), icon="gavel")
        mine = run_in_uow(c, lambda uow: uow.rti.list_for_owner(user.ctx.user_id))
        last_address = next((a.draft.applicant_address for a in mine if a.draft.applicant_address), "")
        depts = c.gis.locator(user.ctx)["departments"]
        dept_options = [d["name"] for d in depts if d["name"]]
        dept_name_to_code = {d["name"]: d["code"] for d in depts if d["name"]}
        caps = c.voice.capabilities()

        prefill_note = ui.column().classes("w-full")
        with ui.row().classes("gap-6 w-full flex-wrap"):
            with ui.column().classes("cl-card gap-3").style("min-width: 320px; max-width: 520px; flex: 1;"):
                with ui.element("div").classes("cl-ask w-full"):
                    ui.icon("gavel").classes("text-[20px]").style("color: var(--cl-ai);")
                    subject = ui.textarea(tr(c, "rti.subject_label")).props("borderless autogrow rows=2").classes("flex-1")
                    r_mic = ui.button(icon="mic").props('round unelevated aria-label="Speak instead of typing"')
                    r_mic.set_enabled(caps["state"] == "CONFIGURED")
                    r_mic.tooltip(tr(c, "assistant.mic_tip") if caps["state"] == "CONFIGURED" else tr(c, "assistant.mic_off"))
                r_voice_hint = ui.label("").classes("text-xs").style("color: var(--cl-fg-subtle);")
                field_hint(tr(c, "rti.subject_hint"))

                with ui.row().classes("gap-2 flex-wrap items-center q-mt-xs"):
                    ui.label(tr(c, "legal.examples_label")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                    for ex_key in ("roads", "water", "electricity"):
                        ex_text = tr(c, f"rti.example.{ex_key}")

                        def use_rti_example(t: str = ex_text, k: str = ex_key) -> None:
                            subject.value = t
                            cat_select.value = k
                            draw_records()

                        ui.chip(ex_text, icon="edit_note", on_click=use_rti_example).props("outline dense")

                r_language = ui.select({k: f"{v.native} ({k})" for k, v in LANGUAGES.items()}, value=lang(), label=tr(c, "lbl.language")).props("outlined dense").classes("w-44")

                divider()
                authority = ui.select(dept_options, with_input=True, new_value_mode="add-unique", label=tr(c, "selectDepartment")).props("outlined dense").classes("w-full")
                dept_suggest_hint = ui.label("").classes("text-xs").style("color: var(--cl-ai);")
                field_hint(tr(c, "rti.authority_hint"))
                location = ui.input(tr(c, "lbl.location") + " (" + tr(c, "lbl.optional") + ")").props("outlined dense").classes("w-full")

                def suggest_department() -> None:
                    """Fill the department in for you from what you wrote - only when you haven't
                    already picked one yourself, and only when the classifier is actually confident;
                    an ambiguous or 'other' read is never turned into a guessed department name."""
                    subj = (subject.value or "").strip()
                    if not subj or (authority.value or "").strip():
                        return
                    preview = c.complaints.preview_classification(user.ctx, subj, subj, None)
                    if not preview["ambiguous"] and preview["category"] != "other" and preview["department_name"]:
                        authority.value = preview["department_name"]
                        dept_suggest_hint.set_text(tr(c, "rti.dept_suggested", category=preview["category"].replace("_", " ").title()))

                subject.on("blur", suggest_department)

                divider()
                cat_select = ui.select({"": tr(c, "col.general_not_sure"), **{k: k.replace("_", " ").title() for k in CATEGORIES}}, value="", label=tr(c, "lbl.category")).props("outlined dense").classes("w-full")
                field_hint(tr(c, "rti.records_sub"))
                record_boxes: dict[str, ui.checkbox] = {}

                with ui.expansion(tr(c, "rti.advanced"), icon="tune").classes("w-full cl-surface-alt"):
                    record_list = ui.column().classes("w-full gap-1")

                    def draw_records() -> None:
                        record_list.clear()
                        record_boxes.clear()
                        with record_list:
                            for rec in default_records_for_category(cat_select.value, r_language.value or "en"):
                                record_boxes[rec] = ui.checkbox(rec, value=True).props("dense color=primary").classes("text-sm")

                    cat_select.on_value_change(lambda e: draw_records())
                    r_language.on_value_change(lambda e: draw_records())
                    draw_records()
                    with ui.row().classes("gap-3 w-full flex-wrap"):
                        tender_ref = ui.input("Tender / Work Order No. (" + tr(c, "lbl.optional") + ")").props("outlined dense").classes("w-full sm:flex-1")
                        time_period = ui.input("Time period (" + tr(c, "lbl.optional") + ", e.g. FY 2025-26)").props("outlined dense").classes("w-full sm:flex-1")
                    questions = ui.textarea("Additional specific questions (" + tr(c, "lbl.optional") + ", one per line)").props("outlined autogrow").classes("w-full")
                    purpose = ui.input(tr(c, "rti.context")).props("outlined dense").classes("w-full")
                    with ui.row().classes("gap-4"):
                        life = ui.checkbox(tr(c, "emergency48Hr"))
                        bpl = ui.checkbox(tr(c, "rti.bpl"))

                divider()
                section_title(tr(c, "rti.applicant"))
                name = ui.input(tr(c, "fullName"), value=user.full_name).props("outlined dense").classes("w-full")
                addr = ui.textarea(tr(c, "residentialAddress"), value=last_address).props("outlined").classes("w-full")
                field_hint(tr(c, "rti.address_hint"))

                # opened from an overdue complaint ("Draft an RTI"): pre-fill from that complaint - only
                # the caller's own complaint can be read here, detail_for_citizen enforces ownership
                from_cid = (ui.context.client.request.query_params.get("complaint") if ui.context.client.request else None) or ""
                if from_cid:
                    try:
                        src = c.complaints.detail_for_citizen(user.ctx, from_cid)["complaint"]
                    except CivicLensError:
                        src = None
                    if src is not None:
                        subject.value = tr(c, "rti.prefill_subject").replace("{ref}", src.reference).replace("{title}", src.title).replace("{date}", src.created_at.strftime("%d %b %Y"))
                        code_to_name = {v: k for k, v in dept_name_to_code.items()}
                        if src.department_code in code_to_name:
                            authority.value = code_to_name[src.department_code]
                        location.value = src.address or (src.ward or "")
                        if src.category in CATEGORIES:
                            cat_select.value = src.category
                            draw_records()
                        questions.value = tr(c, "rti.prefill_questions").replace("{ref}", src.reference)
                        purpose.value = f"{src.reference}"
                        with prefill_note:
                            info_banner(tr(c, "rti.prefilled_from").replace("{ref}", src.reference), "blue")

                # ---- voice: same lightweight mic pattern as the Legal Analyzer screen -----------
                ui.add_body_html(f"<script>{MIC_JS}</script>")
                rec_state = {"recording": False}

                def on_audio(e: Any) -> None:
                    rec_state["recording"] = False
                    r_mic.props("icon=mic").classes(remove="cl-mic-live")
                    try:
                        raw = base64.b64decode(e.args["b64"])
                    except (KeyError, ValueError):
                        ui.notify(tr(c, "assistant.mic_failed"), type="negative")
                        return
                    try:
                        r = c.voice.transcribe(user.ctx, raw, e.args.get("mime") or "audio/webm", r_language.value or "auto")
                    except CivicLensError as exc:
                        ui.notify(exc.message, type="negative")
                        return
                    if r.status != "OK" or not r.transcript:
                        ui.notify(r.error or r.status, type="warning")
                        return
                    subject.value = ((subject.value or "") + " " + r.transcript).strip()
                    if r.language_detected and r.language_detected in r_language.options:
                        r_language.value = r.language_detected
                    r_voice_hint.set_text(tr(c, "assistant.heard", lang=r.language_detected or "?", how=r.detected_by))

                def on_audio_error(e: Any) -> None:
                    rec_state["recording"] = False
                    r_mic.props("icon=mic").classes(remove="cl-mic-live")
                    ui.notify(tr(c, "assistant.mic_denied") + " " + str(e.args.get("message", "")), type="negative")

                ui.on("cl_audio", on_audio)
                ui.on("cl_audio_error", on_audio_error)

                async def toggle_mic() -> None:
                    if rec_state["recording"]:
                        rec_state["recording"] = False
                        r_mic.props("icon=mic").classes(remove="cl-mic-live")
                        ui.run_javascript("window.clStopRec()")
                        return
                    rec_state["recording"] = True
                    r_mic.props("icon=stop").classes(add="cl-mic-live")
                    r_voice_hint.set_text(tr(c, "assistant.listening"))
                    ui.run_javascript("window.clStartRec()")  # fire-and-forget: the permission prompt can take far longer than run_javascript's 1 s timeout; failures come back as cl_audio_error

                r_mic.on_click(toggle_mic)

                def draft() -> RtiDraft:
                    selected_records = tuple(rec for rec, box in record_boxes.items() if box.value)
                    composed = build_rti_questions(
                        subject=subject.value or "", location=location.value or None, records_requested=selected_records,
                        tender_reference=tender_ref.value or None, time_period=time_period.value or None,
                        custom_questions=tuple((questions.value or "").splitlines()),
                        language=r_language.value or "en",
                    )
                    # same "deterministic baseline, then up to 3 model-specific additions" pipeline the
                    # REST /rti/preview-questions route already uses - best-effort, never blocking or
                    # required: an unconfigured/unavailable model just leaves the baseline untouched.
                    composed = enhance_questions_with_llm(subject.value or "", location.value or None, composed, c.llm, r_language.value or "en")
                    return RtiDraft(subject.value or "", authority.value or "", composed, name.value or "", addr.value or "", r_language.value or lang(), purpose.value or None, bool(life.value), bool(bpl.value))

                def do_generate() -> None:
                    try:
                        a = run_in_uow(c, lambda uow: c.rti_for(uow).generate(user.ctx, c.rti_for(uow).create(user.ctx, draft()).id))
                    except CivicLensError as exc:
                        ui.notify(exc.message + (f" {exc.details}" if exc.details else ""), type="negative")
                        return
                    show(a.id)

                pending_mismatch: dict[str, Any] = {}
                with ui.dialog() as mismatch_dlg, ui.column().classes("cl-card gap-3 w-full max-w-sm"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("warning_amber").classes("text-[22px]").style("color: var(--cl-warning);")
                        ui.label(tr(c, "rti.dept_mismatch_title")).classes("text-base font-semibold").style("color: var(--cl-fg);")
                    mismatch_body = ui.label("").classes("text-sm").style("color: var(--cl-fg-muted);")
                    with ui.row().classes("justify-end gap-2 w-full q-mt-sm"):
                        def _fix_department() -> None:
                            mismatch_dlg.close()
                            authority.value = pending_mismatch.get("suggested_name", "")

                        def _continue_anyway() -> None:
                            mismatch_dlg.close()
                            do_generate()

                        ui.button(tr(c, "rti.dept_mismatch_fix"), on_click=_fix_department).props("unelevated color=primary")
                        ui.button(tr(c, "rti.dept_mismatch_continue"), on_click=_continue_anyway).props("flat")

                def create() -> None:
                    subj = (subject.value or "").strip()
                    if subj:
                        preview = c.complaints.preview_classification(user.ctx, subj, subj, None)
                        chosen_code = dept_name_to_code.get((authority.value or "").strip())
                        # only ever checked when BOTH sides are known for certain: a confident, unambiguous
                        # classification, AND a department picked from the real directory (never guessed
                        # against free-typed text, which this can't reliably compare).
                        if not preview["ambiguous"] and preview["category"] != "other" and preview["department_code"] and chosen_code and chosen_code != preview["department_code"]:
                            pending_mismatch["suggested_name"] = preview["department_name"] or preview["department_code"]
                            mismatch_body.set_text(tr(c, "rti.dept_mismatch_body", category=preview["category"].replace("_", " ").title(), suggested=pending_mismatch["suggested_name"], chosen=authority.value))
                            mismatch_dlg.open()
                            return
                        if preview["department_name"] and not (authority.value or "").strip():
                            authority.value = preview["department_name"]
                    do_generate()

                ui.button(tr(c, "generateLetterBtn"), icon="description", on_click=create).props("color=primary unelevated").classes("w-full")

                with ui.row().classes("cl-card w-full items-start gap-3").style("background: var(--cl-warning-soft); border-color: transparent;") as translation_note:
                    ui.icon("translate").style("color: var(--cl-warning);")
                    ui.label(tr(c, "rti.template_translation_note")).classes("text-sm").style("color: var(--cl-warning);")
                translation_note.set_visibility(r_language.value != "en")
                r_language.on_value_change(lambda e: translation_note.set_visibility(e.value != "en"))

            with ui.column().classes("gap-3").style("min-width: 320px; flex: 1;"):
                section_title(tr(c, "rti.preview"))
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
                        def _mark_filed() -> None:
                            run_in_uow(c, lambda uow: c.rti_for(uow).mark_filed(user.ctx, app_id))
                            show(app_id)

                        def _mark_answered() -> None:
                            run_in_uow(c, lambda uow: c.rti_for(uow).mark_responded(user.ctx, app_id))
                            show(app_id)

                        with ui.row().classes("gap-2 flex-wrap"):
                            if a.status.value == "generated":
                                ui.button(tr(c, "rti.mark_filed"), on_click=_mark_filed).props("outline dense")
                            if a.status.value == "filed":
                                ui.button(tr(c, "rti.mark_answered"), on_click=_mark_answered).props("outline dense")
                            ui.button(tr(c, "act.download") + " PDF", icon="download", on_click=lambda: download_pdf(app_id)).props("outline dense")

                def download_pdf(app_id: str) -> None:
                    try:
                        data = run_in_uow(c, lambda uow: c.rti_for(uow).export_pdf(user.ctx, app_id, font_path=c.settings.rti_pdf_font or None))
                    except CivicLensError as exc:
                        ui.notify(exc.message, type="negative")
                        return
                    ui.download(data, f"rti-{app_id[:8]}.pdf")

                if mine:
                    section_title(tr(c, "rti.mine"))
                    data_table([("ref", tr(c, "lbl.reference")), ("subject", tr(c, "lbl.title")), ("status", tr(c, "lbl.status"))], [{"id": a.id, "ref": a.reference or "draft", "subject": a.draft.subject, "status": a.status.value} for a in mine], on_row=lambda r: show(r["id"]))
                else:
                    state_panel(icon="gavel", title=tr(c, "rti.none_title"), body=tr(c, "rti.none_body"))

    @page(c, "/legal", "nav.legal", roles=CIT)
    async def legal(c: AppContainer, user: UiUser) -> None:
        import base64

        page_header(tr(c, "nav.legal"), icon="balance")
        info_banner(tr(c, "msg.metadata_only"), "blue")
        _qp = ui.context.client.request.query_params if ui.context.client.request else {}
        state: dict[str, Any] = {"recording": False}
        caps = c.voice.capabilities()

        with ui.element("div").classes("cl-ask w-full max-w-3xl"):
            ui.icon("balance").classes("text-[20px]").style("color: var(--cl-ai);")
            problem = ui.textarea(tr(c, "caseInputLabel"), value=(_qp.get("text") or "")[:2000]).props("borderless autogrow").classes("flex-1")
            mic = ui.button(icon="mic").props('round unelevated aria-label="Speak instead of typing"').style("background: var(--cl-ai); color: #fff;")
            mic.tooltip(tr(c, "assistant.mic_tip") if caps["state"] == "CONFIGURED" else tr(c, "assistant.mic_off"))
            mic.set_enabled(caps["state"] == "CONFIGURED")
        voice_hint = ui.label("").classes("text-xs").style("color: var(--cl-fg-subtle);")

        with ui.row().classes("gap-2 flex-wrap items-center q-mt-xs"):
            ui.label(tr(c, "legal.examples_label")).classes("text-xs").style("color: var(--cl-fg-subtle);")
            for key in ("legal.example_rti", "legal.example_consumer", "legal.example_rera"):
                text = tr(c, key)
                ui.chip(text, icon="edit_note", on_click=lambda t=text: setattr(problem, "value", t)).props("outline dense")

        with ui.row().classes("gap-4 items-start q-mt-sm flex-wrap"):
            analyze_btn = ui.button(tr(c, "legal.analyze_btn"), icon="search", on_click=lambda: analyze(problem.value or "")).props("color=primary unelevated size=lg").classes("cl-btn-glow")
            with ui.column().classes("gap-1"):
                ui.upload(on_upload=lambda e: on_doc(e), auto_upload=True, label=tr(c, "legal.upload_doc")).props("flat dense accept=.pdf,.txt,.docx").classes("cl-upload-compact")
                ui.label(tr(c, "legal.attach_doc_hint")).classes("text-xs").style("color: var(--cl-fg-subtle);")
        result = ui.column().classes("w-full max-w-3xl gap-3")

        STATUS_KEY = {"no_verified_precedent": "legal.status_no_verified_precedent", "precedents_only": "legal.status_precedents_only", "analysed": "legal.status_analysed"}
        CONF_KEY = {"none": "legal.conf_none", "low": "legal.conf_low", "medium": "legal.conf_medium"}
        CONF_EXPLAIN = {"none": "legal.conf_explain_none", "low": "legal.conf_explain_low", "medium": "legal.conf_explain_medium"}

        def render(r: Any) -> None:
            result.clear()
            with result:
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    ui.label(tr(c, STATUS_KEY.get(r.status, r.status))).classes("text-base font-semibold").style("color: var(--cl-fg);")
                    chip(tr(c, CONF_KEY.get(r.confidence, r.confidence)), color="muted", outline=True)

                # ---- a short, always-present lead so the tab never opens on just a warning banner -
                # built entirely from the same concepts/court_guides the service already computed, so
                # it adapts with whatever the citizen actually described, never a fixed canned line.
                with ui.row().classes("cl-card w-full items-start gap-3").style("background: var(--cl-ai-soft); border-color: transparent;"):
                    ui.icon("lightbulb").classes("text-[20px]").style("color: var(--cl-ai);")
                    with ui.column().classes("gap-1"):
                        ui.label(tr(c, "legal.next_step_title")).classes("text-sm font-semibold").style("color: var(--cl-fg);")
                        if r.court_guides:
                            top = r.court_guides[0]
                            ui.label(tr(c, "legal.next_step_matched", concept=top["concept"])).classes("text-sm").style("color: var(--cl-fg);")
                            ui.label(tr(c, "legal.next_step_action", step=top["steps"][0])).classes("text-sm font-medium").style("color: var(--cl-fg);")
                        elif r.precedents:
                            ui.label(tr(c, "legal.next_step_precedents_only")).classes("text-sm").style("color: var(--cl-fg);")
                        else:
                            ui.label(tr(c, "legal.next_step_unmatched")).classes("text-sm").style("color: var(--cl-fg);")

                with ui.tabs().props("dense no-caps active-color=primary indicator-color=primary").classes("w-full") as result_tabs:
                    t_analysis = ui.tab("analysis", label=tr(c, "legal.tab_analysis"))
                    t_laws = ui.tab("laws", label=tr(c, "legal.tab_laws"))
                    t_precedents = ui.tab("precedents", label=tr(c, "legal.tab_precedents"))
                    t_why = ui.tab("why", label=tr(c, "legal.tab_why"))
                with ui.tab_panels(result_tabs, value=t_analysis).classes("w-full").style("background: transparent;"):
                    with ui.tab_panel(t_analysis).classes("gap-3"):
                        if r.interpretation:
                            section_title(tr(c, "legal.ai_interpretation_title"), tr(c, "legal.ai_interpretation_sub"))
                            with ui.row().classes("cl-card w-full items-start gap-2").style("background: var(--cl-ai-soft); border-color: transparent;"):
                                ui.icon("auto_awesome").style("color: var(--cl-ai);")
                                ui.markdown(r.interpretation).classes("cl-markdown text-sm").style("color: var(--cl-fg);")
                        for w in r.warnings:
                            info_banner(w, "orange")
                        # ---- a withheld/unavailable AI answer is never a dead end: the real, verified
                        # precedents already retrieved are shown right here too, with a one-click jump
                        # to the full list - "here's what we CAN give you", not just "sorry, we can't".
                        if not r.interpretation and r.precedents:
                            # An "exact citation" hit (the citizen quoted a real case number) is a
                            # solid match; a bare "metadata text match" is just BM25 word-overlap on
                            # party names/dates - genuinely often unrelated, so it's never framed with
                            # the same confidence as a real match.
                            has_exact = any(p["matchedOn"] == "exact citation" for p in r.precedents)
                            with ui.column().classes("cl-card w-full gap-2"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.icon("fact_check").classes("text-[18px]").style(f"color: var(--cl-{'success' if has_exact else 'warning'});")
                                    ui.label(tr(c, "legal.fallback_precedents_title", n=len(r.precedents))).classes("text-sm font-semibold").style("color: var(--cl-fg);")
                                for p in r.precedents[:2]:
                                    ui.label(f'{p["title"]} ({p["neutralCitation"]})').classes("text-sm cl-clip-1").style("color: var(--cl-fg-muted);")
                                if not has_exact:
                                    ui.label(tr(c, "legal.fallback_precedents_caveat")).classes("text-xs italic").style("color: var(--cl-fg-subtle);")
                                ui.button(tr(c, "legal.view_all_precedents"), icon="arrow_forward", on_click=lambda: result_tabs.set_value(t_precedents)).props("flat dense color=primary")
                        with ui.expansion(tr(c, "legal.tech_coverage"), icon="info").classes("w-full"):
                            for line in r.bias_and_coverage:
                                ui.label(line).classes("text-xs q-mb-xs").style("color: var(--cl-fg-subtle);")
                        ui.label(r.disclaimer).classes("text-xs italic").style("color: var(--cl-fg-subtle);")
                    with ui.tab_panel(t_laws).classes("gap-3"):
                        if r.concepts:
                            ui.label(tr(c, "legal.based_on_description")).classes("text-xs font-medium").style("color: var(--cl-fg-muted);")
                            with ui.row().classes("gap-2 flex-wrap"):
                                for name in r.concepts:
                                    chip(name, color="info", outline=True)
                        else:
                            ui.label(tr(c, "legal.no_concepts")).classes("text-sm").style("color: var(--cl-fg-muted);")
                        for g in r.court_guides:
                            with ui.column().classes("cl-card w-full gap-3"):
                                ui.label(g["concept"]).classes("text-base font-semibold").style("color: var(--cl-fg);")
                                with ui.row().classes("gap-4 flex-wrap"):
                                    for icon_name, label_key, value in (("gavel", tr(c, "legal.forum"), g["forum"]), ("balance", tr(c, "legal.advocate_mandatory"), g["advocateMandatory"]), ("payments", tr(c, "legal.fee_basis"), g["feeBasis"])):
                                        with ui.row().classes("items-start gap-2").style("min-width: 220px; flex: 1;"):
                                            ui.icon(icon_name).classes("text-[16px] q-mt-xs").style("color: var(--cl-fg-subtle);")
                                            with ui.column().classes("gap-0"):
                                                ui.label(label_key).classes("text-xs font-medium").style("color: var(--cl-fg-muted);")
                                                ui.label(value).classes("text-sm").style("color: var(--cl-fg);")
                                explanation = r.concept_explanations.get(g["concept"])
                                if explanation:
                                    divider()
                                    with ui.row().classes("items-center gap-2"):
                                        ui.icon("auto_awesome").classes("text-[15px]").style("color: var(--cl-ai);")
                                        ui.label(tr(c, "legal.deep_dive_title")).classes("text-xs font-semibold uppercase").style("color: var(--cl-ai); letter-spacing: .05em;")
                                    ui.markdown(explanation).classes("cl-markdown text-sm").style("color: var(--cl-fg);")
                                divider()
                                ui.label(tr(c, "legal.procedure")).classes("text-xs font-semibold uppercase").style("color: var(--cl-fg-muted); letter-spacing: .05em;")
                                for i, step in enumerate(g["steps"], 1):
                                    with ui.row().classes("items-start gap-2"):
                                        ui.label(str(i)).classes("cl-badge cl-badge-info").style("min-width: 20px; justify-content: center; flex: none;")
                                        ui.label(step).classes("text-sm").style("color: var(--cl-fg);")
                        real_guides_shown = [g for g in r.court_guides if not g.get("isFallback")]
                        if real_guides_shown and not any(r.concept_explanations.get(g["concept"]) for g in real_guides_shown):
                            info_banner(tr(c, "legal.deep_dive_unavailable"), "grey")
                    with ui.tab_panel(t_precedents).classes("gap-3"):
                        # The real, substantive content (actual quoted judgment text - what happened,
                        # what was held) comes first when it exists; the citation-only index records
                        # come after, clearly labelled as citation records rather than case summaries,
                        # so it's obvious up front why they don't answer "what happened"/"who won".
                        if r.full_text_excerpts:
                            section_title(tr(c, "legal.full_text_title"), tr(c, "legal.full_text_sub"))
                            for i, e in enumerate(r.full_text_excerpts):
                                with ui.expansion(f"{e.get('neutralCitation') or e['judgmentId']} - {e.get('title') or ''}", value=(i == 0)).classes("w-full cl-card"):
                                    ui.label(e["text"]).classes("text-sm").style("color: var(--cl-fg);")
                        section_title(tr(c, "legal.verified_precedents"), tr(c, "legal.verified_precedents_sub"))
                        if r.precedents:
                            for i, p in enumerate(r.precedents, 1):
                                with ui.column().classes("cl-card w-full gap-2"):
                                    with ui.row().classes("items-start justify-between w-full flex-wrap gap-2"):
                                        with ui.column().classes("gap-0"):
                                            ui.label(p["title"]).classes("text-sm font-semibold").style("color: var(--cl-fg);")
                                            ui.label(p["neutralCitation"]).classes("text-xs cl-mono").style("color: var(--cl-fg-subtle);")
                                        if i == 1:
                                            chip(tr(c, "legal.best_match"), color="success", outline=True)
                                    with ui.row().classes("gap-2 flex-wrap"):
                                        chip(p["court"], color="muted", outline=True)
                                        if p["disposal"]:
                                            chip(p["disposal"], color="muted", outline=True)
                                        chip(p["decisionDate"], color="muted", outline=True)
                                    if p["matchedOn"]:
                                        ui.label(f'{tr(c, "legal.matched_on_label")}: {p["matchedOn"]}').classes("text-xs").style("color: var(--cl-fg-subtle);")
                                    divider()
                                    with ui.row().classes("items-center gap-1"):
                                        ui.icon("info").classes("text-[13px]").style("color: var(--cl-fg-subtle);")
                                        ui.label(tr(c, "legal.citation_only_note")).classes("text-xs italic").style("color: var(--cl-fg-subtle);")
                        else:
                            state_panel(icon="gavel", title=tr(c, "legal.no_precedents_title"), body=tr(c, "legal.no_precedents_body"))
                        from urllib.parse import quote

                        query_text = (problem.value or "")[:300]
                        with ui.row().classes("cl-card items-center justify-between w-full flex-wrap gap-3").style("background: var(--cl-info-soft); border-color: transparent;"):
                            with ui.column().classes("gap-0"):
                                ui.label(tr(c, "legal.curated_note")).classes("text-xs font-medium").style("color: var(--cl-info);")
                                ui.label(tr(c, "legal.curated_note_sub")).classes("text-xs").style("color: var(--cl-info);")
                            with ui.link(target=f"https://indiankanoon.org/search/?formInput={quote(query_text)}", new_tab=True).classes("cl-link-btn"):
                                ui.icon("open_in_new").classes("text-[16px]")
                                ui.label(tr(c, "legal.search_kanoon"))
                    with ui.tab_panel(t_why).classes("gap-3"):
                        section_title(tr(c, "legal.why_title"), tr(c, "legal.why_sub"))

                        step_no = {"n": 0}

                        def why_step(icon_name: str, title_key: str, *lines: str, color: str = "var(--cl-fg-muted)") -> None:
                            # Numbered here, not in the translated string - a step that doesn't apply
                            # (e.g. no citation check ran) is skipped entirely by its caller below, so
                            # a fixed "4." baked into the text would leave a visible gap in the list.
                            step_no["n"] += 1
                            with ui.row().classes("items-start gap-3"):
                                ui.icon(icon_name).classes("text-[18px] q-mt-xs").style("color: var(--cl-fg-subtle);")
                                with ui.column().classes("gap-0"):
                                    ui.label(f'{step_no["n"]}. {tr(c, title_key)}').classes("text-sm font-medium").style("color: var(--cl-fg);")
                                    for line in lines:
                                        ui.label(line).classes("text-sm").style(f"color: {color};")

                        with ui.column().classes("cl-card w-full gap-3"):
                            why_step("search", "legal.why_step_keywords", ", ".join(r.concepts) if r.concepts else tr(c, "legal.why_no_concepts"))
                            divider()
                            why_step("gavel", "legal.why_step_precedents", tr(c, "legal.why_precedents_count", n=len(r.precedents)))
                            if r.full_text_excerpts:
                                divider()
                                why_step("description", "legal.why_step_fulltext", tr(c, "legal.why_fulltext_count", n=len(r.full_text_excerpts)))
                            divider()
                            verified = r.citations_check.get("verified", [])
                            bad = r.citations_check.get("unverified", []) + r.citations_check.get("unverifiable", [])
                            if verified or bad:
                                lines = []
                                if verified:
                                    lines.append(tr(c, "legal.why_citations_verified", n=len(verified)))
                                if bad:
                                    lines.append(tr(c, "legal.why_citations_unverified", n=len(bad)))
                                why_step("fact_check", "legal.why_step_citation_check", *lines)
                            else:
                                why_step("fact_check", "legal.why_step_citation_check", tr(c, "legal.why_citation_check_skipped"))
                            divider()
                            why_step("speed", "legal.why_step_confidence", tr(c, CONF_EXPLAIN.get(r.confidence, r.confidence)))

        async def analyze(text: str) -> None:
            result.clear()
            with result:
                ui.spinner(size="lg")
            rec = await run_with_loading(analyze_btn, c.legal.analyze, user.ctx, text)  # persisted + audited
            render(SimpleNamespace(**rec.result))

        opened = ui.context.client.request.query_params.get("open") if ui.context.client.request else None
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
            ui.run_javascript("window.clStartRec()")  # fire-and-forget: the permission prompt can take far longer than run_javascript's 1 s timeout; failures come back as cl_audio_error

        mic.on_click(toggle_mic)

        past = c.legal.list_mine(user.ctx)
        if past:
            section_title(tr(c, "legal.past_analyses"))
            data_table([("when", tr(c, "legal.col_when")), ("status", tr(c, "lbl.status")), ("problem", tr(c, "legal.col_matter"))], [{"id": r.id, "when": r.created_at.strftime("%d %b %Y %H:%M"), "status": r.status, "problem": r.problem[:100]} for r in past],
                       on_row=lambda row: ui.navigate.to(f"/legal?open={row['id']}"))

    @page(c, "/copilot", "nav.copilot")
    async def copilot(c: AppContainer, user: UiUser) -> None:
        """Civic Saathi: typed or spoken questions in any supported language, answered from the user's own
        records, verified documents, or clearly-labelled general guidance - never mixed up."""
        import base64
        import html
        import re

        from nicegui import run

        state: dict[str, Any] = {"cid": None, "recording": False, "busy": False, "suggestions": None}
        client = ui.context.client  # captured once: handlers may run inside elements this page later deletes (the suggestion cards)
        caps = c.voice.capabilities()
        voice_on = caps["state"] == "CONFIGURED"
        ui.add_body_html(f"<script>{MIC_JS}</script>")
        db_marker = re.compile(r"\s*[\[【]\s*DB\s*[\]】]")

        with ui.column().classes("cl-saathi gap-4"):
            with ui.row().classes("cl-saathi-hero w-full items-center gap-4"):
                with ui.element("div").classes("cl-orb"):
                    ui.icon("smart_toy").classes("text-[28px]")
                with ui.column().classes("gap-1 flex-1 cl-saathi-intro"):
                    ui.label(tr(c, "chatbotTitle")).classes("cl-title text-2xl")
                    ui.label(tr(c, "saathi.subtitle")).classes("text-sm").style("color: var(--cl-fg-muted);")
                    with ui.row().classes("gap-2 q-mt-xs flex-wrap"):
                        for icon, key in [("mic", "saathi.cap_voice"), ("folder_shared", "saathi.cap_records"), ("gavel", "saathi.cap_rti"), ("lock", "saathi.cap_private")]:
                            with ui.element("span").classes("cl-cap"):
                                ui.icon(icon)
                                ui.label(tr(c, key))
                ui.button(tr(c, "saathi.new_chat"), icon="add_comment", on_click=lambda: reset()).props("flat no-caps color=primary").classes("self-start")
            if c.llm is None:
                info_banner(tr(c, "copilot.no_model"), "orange")

            with ui.column().classes("cl-saathi-panel w-full gap-0"):
                log = ui.column().classes("cl-saathi-log w-full gap-1 q-pa-md")
                with ui.column().classes("cl-saathi-bar w-full q-pa-sm gap-1"):
                    with ui.row().classes("items-center gap-2 q-px-sm") as listening_row:
                        with ui.element("span").classes("cl-wave"):
                            for _ in range(5):
                                ui.element("span")
                        status_lbl = ui.label(tr(c, "saathi.tap_stop")).classes("text-xs").style("color: var(--cl-danger);")
                    listening_row.set_visibility(False)
                    with ui.row().classes("items-center gap-2 w-full cl-saathi-inputrow"):
                        mic = ui.button(icon="mic").props('round unelevated color=primary aria-label="Speak instead of typing"').classes("cl-mic-btn")
                        spoken_opts = {"auto": "🌐 " + tr(c, "report.auto_detect")} | {lg["code"]: lg["native"] for lg in caps["languages"]}
                        spoken = ui.select(spoken_opts, value=lang() if lang() in spoken_opts and lang() != "en" else "auto").props("dense outlined options-dense").classes("w-44 cl-spoken")
                        spoken.tooltip(tr(c, "saathi.speak_in"))
                        box = ui.input(placeholder=tr(c, "chatbotPlaceholder")).props("outlined dense rounded").classes("flex-1 cl-saathi-box")
                        send_btn = ui.button(icon="send", on_click=lambda: send()).props('round unelevated color=primary aria-label="Send"')
                    tip = ui.label(tr(c, "saathi.lang_tip")).classes("text-[11px] q-px-sm").style("color: var(--cl-fg-subtle);")
            if not voice_on:
                mic.disable()
                mic.tooltip(tr(c, "assistant.mic_off"))
                spoken.set_visibility(False)
                tip.set_visibility(False)

        def scroll() -> None:
            client.run_javascript(f"const el = document.getElementById('c{log.id}'); if (el) el.scrollTop = el.scrollHeight;")

        def avatar() -> None:
            with ui.element("div").classes("cl-chat-avatar q-mr-sm"):
                ui.icon("auto_awesome").classes("text-[16px]")

        def welcome() -> None:
            with log:
                chat_bubble(tr(c, "saathi.welcome"), is_user=False)
                with ui.column().classes("w-full q-mt-sm gap-2") as sug:
                    ui.label(tr(c, "saathi.suggest_title")).classes("text-[11px] text-weight-bold").style("color: var(--cl-fg-subtle); letter-spacing: .08em; text-transform: uppercase;")
                    with ui.element("div").classes("w-full cl-suggest-grid"):
                        for icon, key in [("assignment", "saathi.s1"), ("schedule", "saathi.s2"), ("help_outline", "saathi.s3"), ("trending_up", "saathi.s4")]:
                            q = tr(c, key)
                            with ui.row().classes("cl-suggest items-center gap-3 no-wrap").props("tabindex=0 role=button") as card:
                                ui.icon(icon).classes("text-[20px]")
                                ui.label(q).classes("text-sm")
                            card.on("click", lambda _e, q=q: send(q))
                            card.on("keydown.enter", lambda _e, q=q: send(q))
            state["suggestions"] = sug

        def reset() -> None:
            state["cid"] = None
            log.clear()
            welcome()

        def source_badge(r: dict[str, Any]) -> None:
            status = r["status"]
            if status == "answered" and r["database_facts"] is not None:
                kind, icon, key = "records", "folder_shared", "saathi.badge_records"
            elif status == "answered" and r["citations"]:
                kind, icon, key = "docs", "description", "saathi.badge_docs"
            elif status == "general_guidance":
                kind, icon, key = "guidance", "lightbulb", "saathi.badge_guidance"
            elif status in ("ungrounded", "insufficient_evidence", "model_unavailable"):
                kind, icon, key = "unverified", "help", "saathi.badge_unverified"
            else:
                return
            with ui.element("span").classes(f"cl-src {kind} q-mb-xs"):
                ui.icon(icon)
                ui.label(tr(c, key))

        def render_answer(r: dict[str, Any]) -> None:
            if r["status"] == "model_unavailable":
                text = "The language model is unavailable; sources are listed below."
            else:
                text = r["answer"] or tr(c, "msg.insufficient")
            text = db_marker.sub("", text).strip()
            with log:
                with ui.row().classes("cl-chat-row cl-assistant no-wrap"):
                    avatar()
                    with ui.column().classes("gap-1").style("max-width: 82%;"):
                        with ui.element("div").classes("cl-chat-bubble").style("max-width: 100%;"):
                            source_badge(r)
                            ui.markdown(html.escape(text, quote=False)).classes("cl-chat-md")  # model output is escaped: rendered as text, never HTML
                        with ui.row().classes("gap-1 items-center"):
                            ui.button(icon="content_copy", on_click=lambda t=text: copy(t)).props("flat round dense size=sm color=grey").tooltip(tr(c, "act.copy"))
                        for cit in r["citations"]:
                            with ui.expansion(f"[{cit['marker']}] {cit['documentName']}" + (f" - p.{cit['page']}" if cit.get("page") else ""), icon="description").classes("w-full"):
                                ui.label(cit["excerpt"]).classes("text-xs").style("color: var(--cl-fg-muted);")
                        for w in r["warnings"]:
                            ui.label(w).classes("text-[11px]").style("color: var(--cl-fg-subtle);")

        async def copy(text: str) -> None:
            import json

            client.run_javascript(f"navigator.clipboard.writeText({json.dumps(text)})")
            with log:
                ui.notify(tr(c, "msg.copied"), type="positive")

        async def send(text: str | None = None, reply_lang: str = "auto") -> None:
            if state["busy"]:
                return
            text = (text if text is not None else box.value or "").strip()
            if not text:
                return
            box.value = ""
            if state["suggestions"] is not None:
                state["suggestions"].delete()
                state["suggestions"] = None
            state["busy"] = True
            with log:
                chat_bubble(text, is_user=True)
                with ui.row().classes("cl-chat-row cl-assistant no-wrap") as typing:
                    avatar()
                    with ui.element("div").classes("cl-typing"):
                        for _ in range(3):
                            ui.element("span")
            scroll()
            try:
                r = await run_with_loading(send_btn, c.assistant.ask, user.ctx, text, conversation_id=state["cid"], language=reply_lang, ui_language=lang())
            except CivicLensError as exc:
                typing.delete()
                state["busy"] = False

                async def _retry() -> None:
                    await send(text, reply_lang)

                with log:
                    error_banner(exc.message)
                    ui.button(tr(c, "act.retry"), icon="refresh", on_click=_retry).props("flat dense")
                scroll()
                return
            typing.delete()
            state["busy"] = False
            state["cid"] = r["conversation_id"]
            render_answer(r)
            scroll()

        # ---- voice: record in the browser, transcribe server-side in the chosen (or detected) language
        def stop_ui() -> None:
            state["recording"] = False
            mic.props("icon=mic").classes(remove="cl-mic-live")

        async def on_audio(e: Any) -> None:
            stop_ui()
            try:
                raw = base64.b64decode(e.args["b64"])
            except (KeyError, ValueError):
                listening_row.set_visibility(False)
                ui.notify(tr(c, "assistant.mic_failed"), type="negative")
                return
            status_lbl.set_text(tr(c, "saathi.transcribing"))
            try:
                v = await run.io_bound(c.voice.transcribe, user.ctx, raw, e.args.get("mime") or "audio/webm", spoken.value or "auto")
            except CivicLensError as exc:
                listening_row.set_visibility(False)
                ui.notify(exc.message, type="negative")
                return
            listening_row.set_visibility(False)
            if v.status != "OK" or not v.transcript:
                ui.notify(v.error or tr(c, "assistant.mic_failed"), type="warning")
                return
            for w in v.warnings:
                ui.notify(w, type="warning")
            detected = spoken.value if spoken.value != "auto" else (v.language_detected or "auto")
            await send(v.transcript, reply_lang=detected)  # the citizen's own words, in their own script, never translated

        def on_audio_error(e: Any) -> None:
            stop_ui()
            listening_row.set_visibility(False)
            ui.notify(tr(c, "assistant.mic_denied") + " " + str(e.args.get("message", "")), type="negative")

        ui.on("cl_audio", on_audio)
        ui.on("cl_audio_error", on_audio_error)

        async def toggle_mic() -> None:
            if state["recording"]:
                stop_ui()
                ui.run_javascript("window.clStopRec()")
                return
            state["recording"] = True
            mic.props("icon=stop").classes(add="cl-mic-live")
            status_lbl.set_text(tr(c, "saathi.tap_stop"))
            listening_row.set_visibility(True)
            ui.run_javascript("window.clStartRec()")  # fire-and-forget: the permission prompt can take far longer than run_javascript's 1 s timeout; failures come back as cl_audio_error

        mic.on_click(toggle_mic)
        box.on("keydown.enter", lambda: send())

        welcome()
        q0 = ui.context.client.request.query_params.get("q") if ui.context.client.request else None
        if q0:
            box.value = q0

    @page(c, "/gis", "nav.gis")
    def gis(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "heatmapTitle"), tr(c, "page.gis_help"), icon="map")
        with ui.row().classes("gap-3 items-end w-full flex-wrap"):
            cat = ui.select({"": tr(c, "filterAll"), **{k: k.title() for k in CATEGORIES}}, value="", label=tr(c, "lbl.category")).props("outlined dense").classes("w-48")
            ref = run_in_uow(c, lambda uow: {"cities": [x for x in uow.config.cities() if x.lat is not None], "wards": list(uow.config.wards())})
            try:
                home = (c.profiles.get(user.ctx).city or "").strip().lower()
            except CivicLensError:
                home = ""
            city_by = {x.code: x for x in ref["cities"]}
            home_code = next((x.code for x in ref["cities"] if home in (x.code, x.name.lower())), None)
            city = ui.select({"": "Auto", **{x.code: x.name for x in ref["cities"]}}, value=home_code or "", label=tr(c, "col.city")).props("outlined dense").classes("w-40")
            ward = ui.select({"": tr(c, "filter.all"), **{w.code: w.name for w in ref["wards"]}}, value="", label=tr(c, "lbl.ward")).props("outlined dense").classes("w-48")
            sev = ui.select({"": tr(c, "filter.all"), "medium": tr(c, "col.medium_plus"), "high": tr(c, "col.high_plus"), "critical": tr(c, "col.critical")}, value="", label=tr(c, "lbl.severity")).props("outlined dense").classes("w-32")
            ui.button(tr(c, "act.refresh"), icon="refresh", on_click=lambda: draw()).props("color=primary unelevated")
        box = ui.column().classes("w-full gap-3")

        def draw() -> None:
            box.clear()
            if ward.value and not city.value:  # picking a ward implies its city
                city.value = next((w.city_code for w in ref["wards"] if w.code == ward.value), "") or ""
            r = c.gis.radar(user.ctx, category=cat.value or None, ward=ward.value or None, min_severity=sev.value or None)
            with box:
                with ui.row().classes("gap-2 items-center"):
                    chip(f"{r['mappable']} of {r['total_complaints']} mappable", color="info", outline=True)
                    if r["not_mappable"]:
                        chip(f"{r['not_mappable']} without coordinates", color="muted", outline=True)
                if city.value and city.value in city_by:
                    lat0, lng0 = city_by[city.value].lat, city_by[city.value].lng
                elif r["hotspots"]:
                    lat0, lng0 = r["hotspots"][0]["lat"], r["hotspots"][0]["lng"]
                elif r["offices"]:
                    lat0, lng0 = r["offices"][0]["lat"], r["offices"][0]["lng"]
                else:
                    state_panel(icon="map", title=tr(c, "msg.no_data"), body=tr(c, "gis.none_body"))
                    return
                with ui.row().classes("gap-4 w-full flex-wrap items-start"):
                    m = ui.leaflet(center=(lat0, lng0), zoom=12 if city.value else 11).classes("h-96").style("flex: 2; min-width: 320px; border-radius: var(--cl-radius-md); overflow: hidden;")
                    for h in r["hotspots"]:
                        m.generic_layer(name="circleMarker", args=[(h["lat"], h["lng"]), {"radius": 6 + 3 * min(h["count"], 8), "color": "#c22a1b", "fillColor": "#c22a1b", "fillOpacity": 0.35}])
                    for o in r["offices"]:
                        m.marker(latlng=(o["lat"], o["lng"]))
                    with ui.column().classes("cl-card gap-2").style("flex: 1; min-width: 260px;"):
                        section_title(tr(c, "gis.hotspots"))
                        if not r["hotspots"]:
                            ui.label(tr(c, "gis.no_clusters")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                        cities = run_in_uow(c, lambda uow: [(x.name, x.lat, x.lng) for x in uow.config.cities() if x.lat is not None and x.lng is not None])

                        def fly(la: float, ln: float) -> None:
                            m.set_center((la, ln))
                            m.set_zoom(15)

                        def place(h: dict[str, Any]) -> str:
                            # a ward name when the complaint carried one; otherwise the nearest known city,
                            # never a bare "Unassigned" that tells an officer nothing about where to go
                            wards = [w for w in h["wards"] if w]
                            if wards:
                                return "Ward " + ", ".join(wards)
                            if cities:
                                name = min(cities, key=lambda ct: (ct[1] - h["lat"]) ** 2 + (ct[2] - h["lng"]) ** 2)[0]
                                return tr(c, "gis.near", city=name)
                            return f"{h['lat']:.3f}, {h['lng']:.3f}"

                        for h in r["hotspots"][:8]:
                            row = ui.row().classes("items-center justify-between w-full no-wrap cl-card-hover q-pa-xs").style("border-radius: var(--cl-radius-sm);")
                            with row:
                                with ui.column().classes("gap-0"):
                                    ui.label(place(h)).classes("text-sm font-medium").style("color: var(--cl-fg);")
                                    ui.label(" · ".join(k.replace("_", " ") for k in list(h["categories"])[:3]) or "-").classes("text-xs").style("color: var(--cl-fg-subtle);")
                                chip(tr(c, "gis.reports", n=h["count"]), color="danger" if h["severity_score"] >= 3 else "warning")
                            row.on("click", lambda _e, la=h["lat"], ln=h["lng"]: fly(la, ln))
                        ui.label(tr(c, "gis.click_hint")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                        if r["ward_boundaries"] == "not_available":
                            ui.label(tr(c, "gis.no_polygons")).classes("text-xs").style("color: var(--cl-fg-subtle);")

        for control in (cat, city, ward, sev):  # filters apply as you pick them - no hunting for Refresh
            control.on_value_change(lambda _e: draw())
        draw()

    @page(c, "/locator", "nav.locator")
    def locator(c: AppContainer, user: UiUser) -> None:
        """Civic Locator: which government office to actually walk into, and where it is.

        The mobile app has had this screen for a while; the web app never did, so the real office
        directory was only reachable on a phone. Addresses come from the offices table - nothing
        here is generated.
        """
        from urllib.parse import quote

        page_header(tr(c, "nav.locator"), tr(c, "loc.help"), icon="place")
        state: dict[str, Any] = {"city": "", "dept": ""}
        controls = ui.row().classes("gap-3 items-end w-full flex-wrap")
        body = ui.column().classes("w-full gap-3")

        def draw() -> None:
            body.clear()
            r = c.gis.locator(user.ctx, city_code=state["city"] or None, department_code=state["dept"] or None)
            with body:
                if not r["offices"]:
                    state_panel(icon="place", title=tr(c, "msg.no_data"), body=tr(c, "loc.none_body"))
                    return
                ui.label(tr(c, "loc.count", shown=r["shown"], total=r["total"])).classes("text-xs").style("color: var(--cl-fg-subtle);")
                with ui.row().classes("gap-4 w-full flex-wrap items-start"):
                    mappable = [o for o in r["offices"] if o["lat"] and o["lng"]]
                    if mappable:
                        centre = (mappable[0]["lat"], mappable[0]["lng"])
                        m = ui.leaflet(center=centre, zoom=11 if state["city"] else 5).classes("h-96").style("flex: 1.2; min-width: 320px; border-radius: var(--cl-radius-md); overflow: hidden;")
                        for o in mappable:
                            m.marker(latlng=(o["lat"], o["lng"]))
                    with ui.column().classes("gap-2").style("flex: 1; min-width: 320px; max-height: 24rem; overflow-y: auto;"):
                        for o in r["offices"]:
                            with ui.column().classes("cl-card gap-1 w-full"):
                                ui.label(o["name"]).classes("text-sm font-semibold").style("color: var(--cl-fg);")
                                with ui.row().classes("gap-2 flex-wrap items-center"):
                                    if o["department_name"]:
                                        chip(o["department_name"], color="info", outline=True)
                                    if o["city_name"]:
                                        chip(o["city_name"], color="muted", outline=True)
                                if o["address"]:
                                    ui.label(o["address"]).classes("text-xs").style("color: var(--cl-fg-muted);")
                                if o["lat"] and o["lng"]:
                                    ui.link(tr(c, "loc.directions"), f"https://www.google.com/maps/dir/?api=1&destination={quote(f'{o['lat']},{o['lng']}')}").classes("text-xs").props("target=_blank")

        def _on_city_change(e: Any) -> None:
            state["city"] = e.value or ""
            draw()

        def _on_dept_change(e: Any) -> None:
            state["dept"] = e.value or ""
            draw()

        ref = c.gis.locator(user.ctx)
        try:  # open on the citizen's own city when their profile has one - not all of India
            home = (c.profiles.get(user.ctx).city or "").strip().lower()
        except CivicLensError:
            home = ""
        home_code = next((x["code"] for x in ref["cities"] if home and home in (x["code"], str(x["name"]).lower())), "")
        if home_code:
            state["city"] = home_code
        with controls:
            city = ui.select({"": tr(c, "filter.all"), **{x["code"]: x["name"] for x in ref["cities"]}}, value=home_code, label=tr(c, "col.city")).props("outlined dense").classes("w-56")
            dept = ui.select({"": tr(c, "filter.all"), **{d["code"]: d["name"] for d in ref["departments"]}}, value="", label=tr(c, "lbl.department")).props("outlined dense").classes("w-56")
            city.on_value_change(_on_city_change)
            dept.on_value_change(_on_dept_change)
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

        page_header(tr(c, "nav.interop"), tr(c, "interop.help"), icon="hub")

        section_title(tr(c, "interop.frag_numbers"))
        with ui.row().classes("gap-3 w-full flex-wrap"):
            stat_tile(tr(c, "interop.stat_umang"), f"{NATIONAL_UMANG_SERVICES:,}+", color="info", icon="apps", hint=f"across {NATIONAL_UMANG_DEPARTMENTS}+ departments — {NATIONAL_UMANG_SOURCE}")
            if user.ctx.has(Permission.COMPLAINT_READ_OWN):  # a personal diagnostic only means something for a citizen's own filings
                mine = c.complaints.list_mine(user.ctx, filter_name="all")
                diag = personal_diagnostic([m.department_code for m in mine])
                stat_tile(tr(c, "interop.stat_departments"), diag.distinct_departments, color="primary", icon="apartment", hint=tr(c, "interop.filings", n=diag.total_filings))
                stat_tile(tr(c, "interop.stat_reentries"), diag.profile_reuses, color="success", icon="badge", hint=tr(c, "interop.reuses"))
        if user.ctx.has(Permission.INTEROP_READ):
            with ui.row().classes("cl-card w-full items-center justify-between gap-3 flex-wrap"):
                ui.label("This lab shows how records are normalised. The live, consent-gated exchange between departments runs in the Gateway console.").classes("text-sm").style("color: var(--cl-fg-muted);")
                ui.button("Open Interoperability Gateway", icon="hub", on_click=lambda: ui.navigate.to("/gateway")).props("color=primary unelevated no-caps")
        elif user.ctx.role is Role.CITIZEN:
            with ui.row().classes("cl-card w-full items-center justify-between gap-3 flex-wrap"):
                ui.label(tr(c, "interop.lab_mydata")).classes("text-sm").style("color: var(--cl-fg-muted);")
                ui.button(tr(c, "nav.my_data"), icon="verified_user", on_click=lambda: ui.navigate.to("/my-data")).props("outline no-caps")

        divider()
        section_title(tr(c, "interop.demo_title"), tr(c, "interop.demo_sub"))
        info_banner(tr(c, "interop.fixtures_note"), "blue")

        sys_select = ui.select({k: v[0] for k, v in SYSTEMS.items()}, value=next(iter(SYSTEMS)), label=tr(c, "interop.source_system")).props("outlined dense").classes("w-full max-w-lg")
        corrupt = ui.checkbox(tr(c, "interop.simulate"))
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
                    section_title(tr(c, "interop.raw_payload"), tr(c, "interop.as_exported"))
                    ui.markdown(f"```json\n{_json.dumps(payload, indent=2, ensure_ascii=False)}\n```").classes("cl-mono text-xs w-full")
                with ui.column().classes("cl-card gap-2").style("flex: 1; min-width: 300px;"):
                    with ui.row().classes("items-center justify-between w-full"):
                        section_title(tr(c, "interop.normalized"))
                        chip(f"{quality.grade} · {quality.score:.0%}", color=tone)
                    for label, value in (("External ID", record.external_id), ("Category", record.category), ("Status", record.status), ("Title", record.title),
                                         ("Department", record.department), ("Citizen", record.citizen_name), ("Contact", record.citizen_contact),
                                         ("Location", record.location), ("Filed on", record.filed_on)):  # fmt: skip
                        with ui.row().classes("items-center justify-between w-full"):
                            ui.label(label).classes("text-xs").style("color: var(--cl-fg-subtle);")
                            ui.label(str(value) if value not in (None, "") else "—").classes("text-sm font-medium cl-mono").style("color: var(--cl-fg);")
                    if quality.issues:
                        divider()
                        ui.label(tr(c, "interop.dq_issues")).classes("text-xs font-medium").style("color: var(--cl-danger);")
                        for issue in quality.issues:
                            ui.label(f"• {issue}").classes("text-xs").style("color: var(--cl-danger);")
                        if quality.grade in ("poor", "unusable"):
                            def queue_exception() -> None:
                                c.exceptions.log(source_system=record.source_system, reason="; ".join(quality.issues)[:300], payload=payload)
                                ui.notify(tr(c, "interop.queued"), type="positive")

                            ui.button(tr(c, "interop.queue_btn"), icon="report_problem", on_click=queue_exception).props("outline dense color=negative")

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
        page_header(tr(c, "profileSection") if user.ctx.role is Role.CITIZEN else tr(c, "nav.my_profile"), icon="person")
        with ui.column().classes("cl-card w-full max-w-md gap-3"):
            ref = run_in_uow(c, lambda uow: {"cities": list(uow.config.cities()), "wards": list(uow.config.wards())})
            name = ui.input(tr(c, "fullName"), value=p.full_name).props("outlined dense").classes("w-full")
            phone = ui.input(tr(c, "phoneNumber"), value=p.phone or "").props("outlined dense inputmode=tel").classes("w-full")
            if user.ctx.role is Role.CITIZEN:
                field_hint(tr(c, "profile.phone_hint"))
            # pick lists instead of free text, so the city/ward match what routing and the map use;
            # a value saved before this change is kept as an option rather than silently dropped
            city_opts = {x.name: x.name for x in ref["cities"]}
            if p.city and p.city not in city_opts:
                city_opts[p.city] = p.city
            city = ui.select(city_opts, value=p.city or None, label=tr(c, "selectCity"), with_input=True).props("outlined dense clearable").classes("w-full")

            def ward_options() -> dict[str, str]:
                code = next((x.code for x in ref["cities"] if x.name == city.value), None)
                opts = {w.code: w.name for w in ref["wards"] if code is None or w.city_code == code}
                if p.ward and p.ward not in opts:
                    opts[p.ward] = p.ward
                return opts

            ward = ui.select(ward_options(), value=p.ward or None, label=tr(c, "lbl.ward"), with_input=True).props("outlined dense clearable").classes("w-full")
            def _city_changed(_e: Any) -> None:
                ward.set_options(ward_options())
                ward.set_value(None)

            city.on_value_change(_city_changed)
            divider()
            with ui.row().classes("items-center gap-2"):
                ui.icon("mail").classes("text-[16px]").style("color: var(--cl-fg-subtle);")
                ui.label(f"{tr(c, 'emailAddress')}: {user.email}").classes("text-sm").style("color: var(--cl-fg-muted);")

            def save() -> None:
                c.profiles.update(user.ctx, full_name=name.value, phone=phone.value or None, city=city.value or "", ward=ward.value or "")
                ui.notify(tr(c, "msg.saved"), type="positive")

            ui.button(tr(c, "saveProfileBtn"), icon="check", on_click=save).props("color=primary unelevated")

    @page(c, "/settings", "nav.settings")
    def settings(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "settingsTitle") if user.ctx.role is Role.CITIZEN else tr(c, "nav.settings"), icon="settings")
        with ui.column().classes("w-full max-w-2xl gap-5"):
            with ui.column().classes("cl-card gap-3 w-full"):
                section_title(tr(c, "nav.notifications"))
                prefs = run_in_uow(c, lambda uow: c.notifications.preferences(user.ctx, uow.notifications))
                in_app = ui.switch(tr(c, "set.in_app"), value=prefs.in_app).props("color=primary")
                email = ui.switch(tr(c, "set.email_notif"), value=prefs.email).props("color=primary")
                if c.mailer is None:
                    field_hint(tr(c, "set.email_not_configured"))

                def save_prefs() -> None:
                    run_in_uow(c, lambda uow: c.notifications.save_preferences(user.ctx, uow.notifications, in_app=in_app.value, email=email.value, muted_kinds=list(prefs.muted_kinds)))
                    ui.notify(tr(c, "msg.saved"), type="positive")

                ui.button(tr(c, "act.save"), on_click=save_prefs).props("outline")

            with ui.column().classes("cl-card gap-3 w-full"):
                section_title(tr(c, "set.privacy_ai"), tr(c, "set.privacy_ai_sub"))
                consents = c.profiles.consents(user.ctx)

                def _on_consent_change(e: Any, p: str) -> None:
                    c.profiles.set_consent(user.ctx, p, bool(e.value))
                    ui.notify(tr(c, "msg.saved"), type="positive")

                plain = {p: tr(c, f"consent.{p}") for p in CONSENT_LABELS}
                for purpose, cstate in consents.items():
                    ui.switch(plain.get(purpose, purpose.replace("_", " ").capitalize()), value=cstate["granted"], on_change=lambda e, p=purpose: _on_consent_change(e, p)).props("color=primary")
                divider()
                ui.label(tr(c, "set.gov_sharing")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                with ui.row().classes("gap-2 flex-wrap"):
                    for _platform, a in c.adapters.items():
                        live = a.state.value == "CONNECTED"
                        chip(f"{a.display_name}: {'connected' if live else 'not connected'}", color="success" if live else "muted", outline=not live)

            def _on_language_change(e: Any) -> None:
                app.storage.user["lang"] = e.value
                c.profiles.update(user.ctx, language=e.value)
                ui.navigate.reload()

            with ui.column().classes("cl-card gap-3 w-full"):
                section_title(tr(c, "set.appearance_language"))
                from app.i18n.languages import LANGUAGES as _LANGS

                ui.select({k: f"{_LANGS[k].native} ({k})" if k in _LANGS else k.upper() for k in c.ui_text.languages}, value=lang(), label=tr(c, "appLanguage"),
                          on_change=_on_language_change).props("outlined dense").classes("w-56")
                field_hint(tr(c, "set.theme_hint"))

            with ui.column().classes("cl-card gap-3 w-full"):
                section_title(tr(c, "col.security"))
                ui.label(tr(c, "set.security_hint")).classes("text-sm").style("color: var(--cl-fg-muted);")
                ui.button(tr(c, "nav.security"), icon="lock", on_click=lambda: ui.navigate.to("/security")).props("outline")

            with ui.column().classes("cl-card gap-3 w-full"):
                section_title(tr(c, "set.linked_ids"), tr(c, "set.linked_ids_sub"))
                ids_list = ui.column().classes("gap-2 w-full")

                def _unlink_id(i: str) -> None:
                    c.master_data.unlink(user.ctx, i)
                    draw_ids()

                def draw_ids() -> None:
                    ids_list.clear()
                    items = c.master_data.list_mine(user.ctx)
                    with ids_list:
                        if not items:
                            ui.label(tr(c, "set.no_ids")).classes("text-sm").style("color: var(--cl-fg-subtle);")
                        for rec in items:
                            with ui.row().classes("items-center justify-between w-full"):
                                ui.label(f"{rec.id_type.replace('_', ' ').upper()} · ···{rec.last4 or '----'}").classes("text-sm cl-mono").style("color: var(--cl-fg);")
                                ui.button(icon="delete_outline", on_click=lambda i=rec.id: _unlink_id(i)).props('flat dense round color=negative aria-label="Remove"')

                draw_ids()
                divider()
                with ui.row().classes("gap-3 items-end w-full flex-wrap"):
                    from app.services.interop_service import ID_TYPES

                    id_type_sel = ui.select({t: t.replace("_", " ").title() for t in ID_TYPES}, value=ID_TYPES[0], label=tr(c, "set.id_type")).props("outlined dense").classes("w-48")
                    id_value = ui.input(tr(c, "set.id_value")).props("outlined dense").classes("flex-1")

                    def link_id() -> None:
                        try:
                            c.master_data.link(user.ctx, id_type_sel.value, id_value.value or "")
                        except CivicLensError as exc:
                            ui.notify(exc.message, type="negative")
                            return
                        id_value.value = ""
                        ui.notify(tr(c, "msg.linked"), type="positive")
                        draw_ids()

                    ui.button(tr(c, "act.link"), icon="add_link", on_click=link_id).props("outline dense")

            with ui.column().classes("cl-card gap-3 w-full"):
                section_title(tr(c, "set.other_portals"), tr(c, "set.other_portals_sub"))
                links_list = ui.column().classes("gap-2 w-full")

                def _remove_link(i: str) -> None:
                    c.external_links.remove(user.ctx, i)
                    draw_links()

                def draw_links() -> None:
                    links_list.clear()
                    items = c.external_links.list_mine(user.ctx)
                    with links_list:
                        if not items:
                            ui.label(tr(c, "set.nothing_tracked")).classes("text-sm").style("color: var(--cl-fg-subtle);")
                        for rec in items:
                            with ui.row().classes("cl-surface-alt q-pa-sm items-center justify-between w-full gap-2"):
                                with ui.column().classes("gap-0"):
                                    ui.label(f"{rec.platform} · {rec.external_reference}").classes("text-sm font-medium cl-mono").style("color: var(--cl-fg);")
                                    ui.label(rec.title + (f" — {rec.status_note}" if rec.status_note else "")).classes("text-xs").style("color: var(--cl-fg-muted);")
                                ui.button(icon="delete_outline", on_click=lambda i=rec.id: _remove_link(i)).props('flat dense round color=negative aria-label="Remove"')

                draw_links()
                divider()
                with ui.row().classes("gap-3 items-end w-full flex-wrap"):
                    platform_in = ui.input(tr(c, "set.platform_eg")).props("outlined dense").classes("w-40")
                    ref_in = ui.input(tr(c, "set.ref_number")).props("outlined dense").classes("w-40")
                    title_in = ui.input(tr(c, "set.short_title")).props("outlined dense").classes("flex-1")

                    def add_link() -> None:
                        try:
                            c.external_links.add(user.ctx, platform=platform_in.value or "", external_reference=ref_in.value or "", title=title_in.value or "")
                        except CivicLensError as exc:
                            ui.notify(exc.message + (f" {exc.details}" if exc.details else ""), type="negative")
                            return
                        platform_in.value = ref_in.value = title_in.value = ""
                        ui.notify(tr(c, "msg.added"), type="positive")
                        draw_links()

                    ui.button(tr(c, "nav.track"), icon="add", on_click=add_link).props("outline dense")

    @page(c, "/notifications", "nav.notifications")
    def notifications(c: AppContainer, user: UiUser) -> None:
        def _mark_all_read() -> None:
            run_in_uow(c, lambda uow: c.notifications.mark_all_read(user.ctx, uow.notifications))
            ui.navigate.reload()

        def _render_actions() -> None:
            # page_header's `actions` is Callable[[], None]: it is called only to build widgets as
            # a side effect (see the `actions()` call inside `with ui.row(): ...` in
            # app/ui/components), and previously did `actions=lambda: ui.button(...)`, whose value
            # is the Button itself, not None.
            ui.button(tr(c, "notif.mark_all_read"), on_click=_mark_all_read).props("outline dense")

        page_header(tr(c, "nav.notifications"), icon="notifications", actions=_render_actions)
        items = run_in_uow(c, lambda uow: c.notifications.list_for(user.ctx, uow.notifications, limit=100))
        if not items:
            state_panel(icon="notifications_none", title=tr(c, "msg.no_data"))
            return

        def _target(n: Any) -> str | None:
            data = n.data or {}
            if data.get("route"):
                return str(data["route"])
            if data.get("complaint_id"):
                return f"/grievances/{data['complaint_id']}" if user.ctx.role is Role.CITIZEN else f"/officer/complaints/{data['complaint_id']}"
            return None

        def _open(n: Any) -> None:
            # opening a notification reads it and takes you to the thing it is about
            if not n.read_at:
                run_in_uow(c, lambda uow: c.notifications.mark_read(user.ctx, uow.notifications, n.id))
            target = _target(n)
            ui.navigate.to(target) if target else ui.navigate.reload()

        def _look(kind: str) -> tuple[str, str]:
            for prefix, look in (("interop.", ("how_to_reg", "warning")), ("complaint.resolved", ("task_alt", "success")), ("complaint.escalat", ("trending_up", "danger")),
                                 ("complaint.assigned", ("assignment_ind", "primary")), ("complaint.transferred", ("swap_horiz", "info")), ("complaint.created", ("add_task", "info")),
                                 ("complaint.", ("update", "info")), ("rti.", ("gavel", "ai")), ("sla.", ("schedule", "warning"))):  # fmt: skip
                if kind.startswith(prefix):
                    return look
            return ("notifications", "muted")

        def _words(n: Any) -> tuple[str, str]:
            """Notifications are stored in English when created; re-say the ones whose wording
            CivicLens owns in the reader's language. Anything else is shown as stored."""
            import re as _re

            ref = (n.data or {}).get("reference", "")
            if n.kind == "complaint.created" and ref:
                return tr(c, "notif.t_registered"), tr(c, "notif.b_registered", ref=ref)
            m = _re.search(r"is now (.+?)\.$", n.body or "")
            if n.kind in ("complaint.status_changed", "complaint.resolved") and ref and m:
                return tr(c, "notif.t_update"), tr(c, "notif.b_update", ref=ref, status=status_label(c, m.group(1).strip().replace(" ", "_")))
            if n.kind == "interop.consent_requested":
                return tr(c, "notif.t_consent"), n.body
            return n.title, n.body

        today = c.clock().date()
        groups: dict[str, list[Any]] = {}
        for n in items:
            age = (today - n.created_at.date()).days
            groups.setdefault("Today" if age <= 0 else "Yesterday" if age == 1 else "Earlier", []).append(n)
        for label, rows in groups.items():
            section_title(f"{label} · {len(rows)}")
            with ui.column().classes("gap-2 w-full"):
                for n in rows:
                    icon, tone = _look(n.kind)
                    card = ui.row().classes("cl-card cl-card-hover cl-notif w-full items-start gap-3 no-wrap" + ("" if n.read_at else " cl-notif-unread"))
                    with card:
                        with ui.element("div").classes("cl-stat-icon").style(f"background: var(--cl-{tone}-soft); color: var(--cl-{tone}); width:36px; height:36px; flex: none;"):
                            ui.icon(icon).classes("text-[18px]")
                        title, body = _words(n)
                        with ui.column().classes("gap-0 flex-1").style("min-width: 0;"):
                            ui.label(title).classes("text-sm font-semibold").style("color: var(--cl-fg);")
                            ui.label(body).classes("text-sm cl-clip-2").style("color: var(--cl-fg-muted);")
                            ui.label(n.created_at.strftime("%d %b %Y · %H:%M")).classes("text-xs q-mt-xs").style("color: var(--cl-fg-subtle);")
                        with ui.column().classes("items-end gap-1").style("flex: none;"):
                            if not n.read_at:
                                ui.element("span").classes("cl-unread-dot")
                            if _target(n):
                                ui.icon("chevron_right").classes("text-[20px]").style("color: var(--cl-fg-subtle);")
                    card.on("click", lambda _e, nn=n: _open(nn))

    @page(c, "/documents", "nav.documents")
    def documents(c: AppContainer, user: UiUser) -> None:
        page_header(tr(c, "nav.documents"), tr(c, "doc.help"), icon="folder")

        def on_upload(e: Any) -> None:
            if c.ingestor_factory is None:
                ui.notify(tr(c, "doc.not_configured"), type="negative")
                return
            try:
                def op(uow):
                    doc = c.ingestor_factory(uow).upload(user.ctx.user_id, e.name, e.content.read(), max_bytes=c.settings.max_upload_bytes, declared_mime=e.type)
                    job, _ = c.jobs.enqueue(uow, "document.ingest", {"document_id": doc.id}, f"ingest:{doc.id}")
                    return job

                c.jobs.dispatch([run_in_uow(c, op)])
            except CivicLensError as exc:
                ui.notify(exc.message, type="negative")
                return
            ui.notify(tr(c, "doc.uploaded"), type="positive")
            ui.navigate.reload()

        ui.upload(on_upload=on_upload, auto_upload=True, label=tr(c, "doc.dropzone")).props("flat").classes("cl-dropzone w-full max-w-xl")
        if c.ingestor_factory:
            docs = run_in_uow(c, lambda uow: uow.documents.list_for_owner(user.ctx.user_id))
            if docs:
                section_title(tr(c, "doc.mine"))
                data_table([("name", tr(c, "col.name")), ("status", tr(c, "lbl.status")), ("chunks", tr(c, "col.chunks")), ("err", tr(c, "col.error"))], [{"id": d.id, "name": d.name, "status": str(d.status), "chunks": d.chunk_count, "err": d.error or ""} for d in docs])
            failed = [d for d in docs if str(d.status) == "failed"]

            def _retry_ingest(i: str) -> None:
                run_in_uow(c, lambda uow: c.jobs.enqueue(uow, "document.ingest", {"document_id": i}, f"ingest-retry:{i}:{int(c.clock().timestamp())}"))
                ui.navigate.reload()

            for d in failed:
                ui.button(f"{tr(c, 'act.retry')} {d.name}", on_click=lambda i=d.id: _retry_ingest(i)).props("outline dense")
        section_title(tr(c, "doc.search"))
        with ui.row().classes("gap-2 w-full max-w-xl items-center"):
            q = ui.input(tr(c, "doc.search")).props("outlined dense").classes("flex-1")
            ui.button(icon="search", on_click=lambda: search()).props('round unelevated color=primary aria-label="Search"')
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

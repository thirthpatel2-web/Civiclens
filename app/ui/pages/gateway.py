"""Interoperability Gateway console (SIH26129's core) and the citizen's own data-sharing centre.

Everything here is a thin view over ``InteropGatewayService``: the service enforces permissions,
consent, identity rules and auditing; this module only renders state and forwards decisions.
Auditors see the same console read-only (no INTEROP_MANAGE), so every action is gated on that.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from nicegui import run, ui

from app.container import AppContainer
from app.core.authorization import Permission
from app.core.exceptions import CivicLensError
from app.ui.base import UiUser, data_table, error_banner, info_banner, page, tr
from app.ui.components import (
    chip,
    confirm_dialog,
    page_header,
    section_title,
    stat_tile,
    state_panel,
    surface,
)
from app.ui.navigation import CIT, GATEWAY

# The nine governed steps of the no-reupload workflow, in order (matches the registered
# ``residence_certificate_verification`` workflow definition).
PIPELINE: list[tuple[str, str, str]] = [
    ("resolve_identity", "Resolve identity", "fingerprint"),
    ("request_consent", "Citizen consent", "how_to_reg"),
    ("fetch_document", "Fetch from Revenue", "cloud_download"),
    ("validate_document", "Quality check", "fact_check"),
    ("transform_data", "Transform (canonical)", "sync_alt"),
    ("deliver_document", "Deliver to Seva Setu", "send"),
    ("publish_event", "Publish event", "podcasts"),
    ("update_tracker", "Update tracker", "timeline"),
    ("notify", "Notify citizen", "notifications_active"),
]
SYSTEM_NAMES = {"dept_a": "Revenue Records (Dept A)", "dept_b": "Seva Setu (Dept B)", "dept_c": "Nagrik Grievance (Dept C)", "civiclens": "CivicLens gateway"}
FIELD_LABELS = {"reference": "Certificate reference", "status": "Verification status", "issued_on": "Issue date", "document_reference": "Certificate reference",
                "document_status": "Verification status", "full_name": "Full name", "document_type": "Document type", "reference_no": "Reference no."}


def _fields(names: Any) -> str:
    return ", ".join(FIELD_LABELS.get(f, str(f).replace("_", " ")) for f in (names or []))
HEALTH_TONE = {"healthy": "success", "degraded": "warning", "down": "danger", "unknown": "muted"}
STATUS_TONE = {"success": "success", "granted": "success", "completed": "success", "processing": "info", "pending": "warning", "pending_document": "warning",
               "running": "info", "waiting_approval": "warning", "failed": "danger", "denied": "danger", "revoked": "muted", "dead": "danger", "open": "warning", "resolved": "success"}  # fmt: skip


def _when(v: Any) -> str:
    if isinstance(v, datetime):
        return v.strftime("%d %b %Y, %H:%M")
    return str(v)[:16].replace("T", " ") if v else "—"


def _pretty(step: str) -> str:
    return step.replace("_", " ").capitalize().replace("dept a", "Dept A").replace("dept b", "Dept B").replace("cross system", "across systems")


def _states_for(result: dict[str, Any] | None) -> tuple[list[str], str, str]:
    """Map an exchange result onto the nine pipeline steps: (per-step state, headline, tone)."""
    n = len(PIPELINE)
    if result is None:
        return ["upcoming"] * n, "Pick an application and run the exchange.", "muted"
    status = result.get("status")
    if status in ("success", "already_completed"):
        return ["done"] * n, "Verified certificate delivered - the citizen uploaded nothing.", "success"
    if status == "consent_required":
        return ["done", "current"] + ["upcoming"] * (n - 2), "Waiting for the citizen's consent.", "warning"
    if status in ("identity_ambiguous", "identity_conflict", "source_record_not_found"):
        return ["failed"] + ["upcoming"] * (n - 1), {"identity_ambiguous": "Identity match needs an officer's review.", "identity_conflict": "The two systems disagree on who this is - manual review needed.",
                                                      "source_record_not_found": "No matching resident in Revenue Records."}[str(status)], "danger"  # fmt: skip
    reason = result.get("reason")
    fail_at = {"data_field_not_consented": 1, "document_not_found": 2, "data_quality_failed": 3}.get(str(reason), 2)
    return ["done"] * fail_at + ["failed"] + ["upcoming"] * (n - fail_at - 1), f"Stopped safely: {str(reason).replace('_', ' ')}.", "danger"


def register(c: AppContainer) -> None:
    @page(c, "/gateway", "nav.interop_gateway", roles=GATEWAY)
    async def gateway(c: AppContainer, user: UiUser) -> None:
        g = c.interop_gateway
        can_manage = user.ctx.has(Permission.INTEROP_MANAGE)
        state: dict[str, Any] = {"app": None, "result": None}

        def refresh_all() -> None:
            header.refresh()
            live.refresh()
            connectors_view.refresh()
            consents_view.refresh()
            identity_view.refresh()
            exceptions_view.refresh()
            trace_list.refresh()

        def header_actions() -> None:
            ui.button("Refresh", icon="refresh", on_click=refresh_all).props("flat no-caps")

        page_header("Interoperability Gateway", "One consent click instead of five manual steps: departments reuse each other's verified data, with the citizen in control and every hop traced.",
                    icon="hub", actions=header_actions)  # fmt: skip
        if not can_manage:
            info_banner("Read-only view: your role can inspect every exchange, consent and trace, but cannot change anything.", "blue")

        @ui.refreshable
        def header() -> None:
            conns = g.list_connectors(user.ctx)
            txns = g.list_transactions(user.ctx, limit=200)
            pending = g.list_consents(user.ctx, status="pending")
            open_exc = g.list_exceptions(user.ctx, resolution_state="open", limit=200)
            alerts = g.list_alerts(user.ctx, acknowledged=False, limit=200)
            ok = sum(1 for t in txns if t["status"] == "success")
            with ui.row().classes("w-full gap-3 flex-wrap"):
                stat_tile("Connected systems", f"{sum(1 for x in conns if x['enabled'])}/{len(conns)}", icon="lan", color="info", hint="Revenue · Seva Setu · Nagrik (demo)")
                stat_tile("Successful exchanges", f"{ok}/{len(txns)}", icon="verified", color="success", hint="Zero documents re-uploaded")
                stat_tile("Awaiting consent", len(pending), icon="how_to_reg", color="warning", hint="Citizens decide, per field")
                stat_tile("Open exceptions", len(open_exc), icon="report_problem", color="danger" if open_exc else "success", hint=f"{len(alerts)} SLA alert(s) unacknowledged")

        header()

        with ui.tabs().classes("w-full").props("align=left inline-label no-caps active-color=primary indicator-color=primary") as tabs:
            t_live = ui.tab("live", "Live exchange", icon="bolt")
            t_conn = ui.tab("conn", "Connectors", icon="lan")
            t_cons = ui.tab("cons", "Consents", icon="how_to_reg")
            t_id = ui.tab("id", "Identity review", icon="fingerprint")
            t_exc = ui.tab("exc", "Exceptions", icon="report_problem")
            t_trace = ui.tab("trace", "Trace", icon="travel_explore")
            t_cat = ui.tab("cat", "Catalog", icon="menu_book")

        with ui.tab_panels(tabs, value=t_live).classes("w-full").style("background: transparent;").props("animated"):
            # ------------------------------------------------------------------ live exchange
            with ui.tab_panel(t_live).classes("!p-0 q-pt-md"):

                @ui.refreshable
                def live() -> None:
                    apps = g.list_demo_applications(user.ctx)
                    if state["app"] is None and apps:
                        state["app"] = apps[0]["application_no"]
                    with ui.row().classes("w-full gap-4 items-stretch flex-wrap"):
                        # --- the scenario
                        with ui.column().classes("gap-3").style("flex: 1 1 320px;"):
                            with surface():
                                section_title("The scenario", "Seva Setu (Dept B) needs a residence certificate that Revenue Records (Dept A) has already verified.")
                                with ui.row().classes("items-center gap-2 w-full no-wrap q-mt-sm"):
                                    for sys_id, label, icon in [("dept_a", "Revenue\n(holds certificate)", "account_balance"), ("gw", "CivicLens\ngateway", "hub"), ("dept_b", "Seva Setu\n(needs it)", "storefront")]:
                                        with ui.column().classes("items-center gap-1 flex-1"):
                                            with ui.element("div").classes("cl-orb" if sys_id == "gw" else "cl-stat-icon").style("" if sys_id == "gw" else "width: 46px; height: 46px; background: var(--cl-primary-soft); color: var(--cl-primary);"):
                                                ui.icon(icon).classes("text-[22px]")
                                            ui.label(label).classes("text-[11px] text-center").style("white-space: pre-line; color: var(--cl-fg-muted);")
                                        if sys_id != "dept_b":
                                            ui.icon("east").style("color: var(--cl-ai);")
                            section_title("Applications waiting for a document")
                            if not apps:
                                state_panel(icon="inbox", title="No demo applications", body="Department B has no applications to process.")
                            for a in apps:
                                selected = a["application_no"] == state["app"]
                                with ui.column().classes("cl-card cl-card-hover w-full gap-1 cursor-pointer").style(f"border: 1.5px solid {'var(--cl-ai)' if selected else 'var(--cl-border)'};") as card:
                                    with ui.row().classes("items-center justify-between w-full"):
                                        ui.label(a["application_no"]).classes("text-sm font-semibold")
                                        chip(a["status"].replace("_", " "), color=STATUS_TONE.get(a["status"], "muted"))
                                    ui.label(f"{a['applicant']} · {a['service_type']}").classes("text-xs").style("color: var(--cl-fg-muted);")
                                    ui.label(f"Document: {a['document_status']}" + (f" · {a['document_reference']}" if a.get("document_reference") else "")).classes("text-xs").style("color: var(--cl-fg-subtle);")
                                card.on("click", lambda _e, n=a["application_no"]: pick(n))
                            if can_manage:
                                with ui.row().classes("gap-2 w-full"):
                                    ui.button("Request certificate", icon="bolt", on_click=lambda: run_exchange()).props("unelevated color=primary no-caps").classes("flex-1")
                                    ui.button("Reset demo", icon="restart_alt", on_click=lambda: reset_dialog()).props("flat no-caps")
                        # --- the pipeline
                        with ui.column().classes("gap-3").style("flex: 2 1 420px;"):
                            result = state["result"]
                            states, headline, tone = _states_for(result)
                            with surface():
                                with ui.row().classes("items-center justify-between w-full"):
                                    section_title("9-step governed workflow", state["app"] or "")
                                    chip(headline, color=tone)
                                with ui.element("div").classes("w-full q-mt-sm").style("display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px;"):
                                    for (_step_id, label, icon), st in zip(PIPELINE, states, strict=True):
                                        colour = {"done": "success", "current": "warning", "failed": "danger"}.get(st, "muted")
                                        with ui.row().classes("items-center gap-2 no-wrap").style(f"padding: 8px 10px; border-radius: 10px; border: 1px solid var(--cl-border); background: var(--cl-{colour}-soft, var(--cl-surface-alt));"):
                                            ui.icon({"done": "check_circle", "current": "pending", "failed": "cancel"}.get(st, icon)).style(f"color: var(--cl-{colour});")
                                            ui.label(label).classes("text-xs font-medium")
                                if result:
                                    ui.separator().classes("q-my-sm")
                                    render_result(result)
                            timeline_card()

                def render_result(r: dict[str, Any]) -> None:
                    status = r.get("status")
                    if status == "consent_required":
                        who = "the citizen's own CivicLens app (linked by verified mobile) - they have been notified" if r.get("citizen_linked") else "the consent queue (no citizen account is linked to this record yet)"
                        ui.label(f"A consent request was sent to {who}. Only 3 fields will be shared: certificate reference, verification status and issue date.").classes("text-sm")
                        with ui.row().classes("gap-2 q-mt-xs"):
                            ui.button("Check again", icon="refresh", on_click=lambda: run_exchange()).props("outline no-caps")
                            if can_manage and not r.get("citizen_linked"):
                                ui.button("Record consent on the citizen's behalf", icon="how_to_reg", on_click=lambda: grant(r["consent_id"])).props("flat no-caps color=warning")
                    elif status in ("success", "already_completed"):
                        with ui.row().classes("gap-2 flex-wrap"):
                            chip(f"Document {r.get('document_reference', '')}", color="success", icon="verified")
                            if r.get("quality_score") is not None:
                                chip(f"Quality {round(float(r['quality_score']) * 100)}%", color="info", icon="fact_check")
                            for f in r.get("fields_exchanged") or []:
                                chip(str(f).replace("_", " "), color="muted", outline=True)
                        if r.get("correlation_id"):
                            ui.button("View full trace", icon="travel_explore", on_click=lambda: open_trace(r["correlation_id"])).props("flat no-caps").classes("q-mt-xs")
                    else:
                        issues = r.get("issues") or r.get("denied_fields") or []
                        ui.label(r.get("detail") or f"The gateway stopped before any data moved: {str(r.get('reason') or status).replace('_', ' ')}.").classes("text-sm")
                        for i in issues:
                            ui.label(f"• {i}").classes("text-xs").style("color: var(--cl-danger);")
                        if status == "identity_ambiguous":
                            ui.button("Open identity review", icon="fingerprint", on_click=lambda: tabs.set_value(t_id)).props("flat no-caps")

                def timeline_card() -> None:
                    if not state["app"]:
                        return
                    try:
                        tl = g.get_timeline(user.ctx, application_no=state["app"])
                    except CivicLensError:
                        return
                    events = tl.get("events") or []
                    runs = list(dict.fromkeys(ev["correlation_id"] for ev in events))  # oldest -> newest
                    latest = [ev for ev in events if runs and ev["correlation_id"] == runs[-1]]
                    with surface():
                        section_title("Cross-department timeline", "Every step of the latest run, from every system, in one place.")
                        if not events:
                            ui.label("No exchange has run for this application yet.").classes("text-sm").style("color: var(--cl-fg-muted);")
                        elif len(runs) > 1:
                            ui.label(f"Latest of {len(runs)} runs - earlier runs are kept in the audit trail.").classes("text-xs").style("color: var(--cl-fg-subtle);")
                        with ui.column().classes("cl-timeline w-full gap-0"):
                            for ev in latest:
                                with ui.column().classes("cl-timeline-step gap-0"):
                                    with ui.element("div").classes("cl-timeline-dot " + ("cl-done" if ev["status"] == "success" else "cl-rejected")):
                                        ui.icon("check" if ev["status"] == "success" else "close")
                                    ui.label(_pretty(ev["step"])).classes("text-sm font-medium")
                                    ui.label(f"{SYSTEM_NAMES.get(ev['source_system'], ev['source_system'])} · {_when(ev['occurred_at'])}").classes("text-xs").style("color: var(--cl-fg-subtle);")

                live()

            # ------------------------------------------------------------------ connectors
            with ui.tab_panel(t_conn).classes("!p-0 q-pt-md"):

                @ui.refreshable
                def connectors_view() -> None:
                    conns = g.list_connectors(user.ctx)
                    with ui.row().classes("w-full gap-3 flex-wrap"):
                        for x in conns:
                            with ui.column().classes("cl-card gap-2").style("flex: 1 1 280px;"):
                                with ui.row().classes("items-center justify-between w-full"):
                                    ui.label(x["name"]).classes("text-sm font-semibold")
                                    chip(x["health_state"], color=HEALTH_TONE.get(x["health_state"], "muted"))
                                ui.label(f"{x['department']} · v{x['version']}").classes("text-xs").style("color: var(--cl-fg-muted);")
                                with ui.row().classes("gap-1 flex-wrap"):
                                    for op in x["supported_operations"]:
                                        chip(op, outline=True)
                                with ui.row().classes("w-full gap-4 q-mt-xs"):
                                    for label, val in [("Calls", x["total_calls"]), ("Failures", x["total_failures"]), ("Avg ms", x["avg_response_ms"] if x["avg_response_ms"] is not None else "—"), ("SLA", x.get("sla_status", "unknown"))]:
                                        with ui.column().classes("gap-0"):
                                            ui.label(str(val)).classes("text-base font-bold")
                                            ui.label(label).classes("text-[11px]").style("color: var(--cl-fg-subtle);")
                                ui.label(f"Last health check: {_when(x['last_health_check'])}").classes("text-[11px]").style("color: var(--cl-fg-subtle);")
                                if can_manage:
                                    with ui.row().classes("gap-2"):
                                        ui.button("Health check", icon="monitor_heart", on_click=lambda _e, cid=x["connector_id"]: act(g.connector_health, "Health check complete.", connector_id=cid)).props("outline dense no-caps")
                                        ui.button("Disable" if x["enabled"] else "Enable", icon="power_settings_new",
                                                  on_click=lambda _e, cid=x["connector_id"], en=not x["enabled"]: act(g.set_connector_enabled, "Connector updated.", connector_id=cid, enabled=en)).props("flat dense no-caps")  # fmt: skip
                    info_banner("Each connector authenticates to the gateway with an OAuth2 client-credentials token from the (demo) federated identity provider. A real department API replaces a demo system by swapping only the connector's query functions.", "blue")

                connectors_view()

            # ------------------------------------------------------------------ consents
            with ui.tab_panel(t_cons).classes("!p-0 q-pt-md"):

                @ui.refreshable
                def consents_view() -> None:
                    rows = g.list_consents(user.ctx)
                    section_title("Consent ledger", "Purpose-bound, field-level, 30-day expiry, revocable by the citizen at any time.")
                    data_table([("purpose", "Purpose"), ("status", "Status"), ("fields", "Fields"), ("created", "Requested"), ("expires", "Expires")],
                               [{"id": r["consent_id"], "purpose": r["purpose"], "status": r["status"], "fields": _fields(r["fields"]), "created": _when(r["created_at"]), "expires": _when(r["expires_at"])} for r in rows],
                               empty="No consent requests yet.")  # fmt: skip

                consents_view()

            # ------------------------------------------------------------------ identity review
            with ui.tab_panel(t_id).classes("!p-0 q-pt-md"):

                @ui.refreshable
                def identity_view() -> None:
                    cands = g.list_identity_candidates(user.ctx)
                    section_title("Identity review queue", "Records are linked automatically only at 90%+ confidence. Between 55% and 90% a person decides - two citizens are never silently merged.")
                    if not cands:
                        state_panel(icon="verified_user", title="Nothing to review", body="Every identity match so far was confident enough to link automatically, or clearly different.", tone="success")
                    for cd in cands:
                        with surface():
                            conf = float(cd.get("score") or 0)
                            with ui.row().classes("items-center justify-between w-full"):
                                ui.label(f"{SYSTEM_NAMES.get(cd.get('system', ''), cd.get('system', ''))} · {str(cd.get('identifier_type', '')).replace('_', ' ')} {cd.get('identifier_value', '')}").classes("text-sm font-semibold")
                                chip(f"{round(conf * 100)}% match", color="warning")
                            ui.linear_progress(value=conf, show_value=False).props("rounded color=warning").classes("q-my-xs")
                            ui.label(f"Why: {cd.get('explanation')}").classes("text-xs").style("color: var(--cl-fg-muted);")
                            try:
                                ev = g.identity_candidate_evidence(user.ctx, candidate_id=cd["id"])
                            except CivicLensError:
                                ev = None
                            if ev and ev["existing"]:
                                # side by side, with the fields that disagree flagged, so the reviewer
                                # decides on evidence rather than on a percentage
                                other = ev["existing"][0]
                                with ui.element("div").classes("cl-id-compare w-full q-my-sm"):
                                    ui.label("").classes("cl-id-h")
                                    for side in (other, ev["incoming"]):
                                        with ui.column().classes("cl-id-h gap-0"):
                                            ui.label(SYSTEM_NAMES.get(side["system"], side["system"])).classes("text-xs font-semibold")
                                            ui.label(side["id"]).classes("text-[11px] cl-mono").style("color: var(--cl-fg-subtle);")
                                    for label, key in (("Name", "name"), ("Mobile", "mobile"), ("City", "city")):
                                        same_key = "mobile_last4" if key == "mobile" else key
                                        differs = other[same_key] != ev["incoming"][same_key] and "—" not in (other[key], ev["incoming"][key])
                                        ui.label(label).classes("text-xs").style("color: var(--cl-fg-subtle);")
                                        for side in (other, ev["incoming"]):
                                            with ui.row().classes("items-center gap-1 no-wrap"):
                                                ui.label(side[key]).classes("text-sm" + (" cl-mono" if key == "mobile" else "")).style(f"color: var(--cl-{'danger' if differs else 'fg'});")
                                                if differs:
                                                    ui.icon("error_outline").classes("text-[15px]").style("color: var(--cl-danger);")
                                ui.label("Linking tells every department these two records are the same citizen. If unsure, keep them separate - it can be linked later, but a wrong link leaks one person's documents to another.").classes("text-[11px]").style("color: var(--cl-fg-subtle);")
                            if can_manage:
                                with ui.row().classes("gap-2"):
                                    ui.button("Same person - link", icon="link", on_click=lambda _e, i=cd["id"]: act(g.resolve_identity_candidate, "Identities linked.", candidate_id=i, approve=True)).props("unelevated dense no-caps color=positive")
                                    ui.button("Different people", icon="link_off", on_click=lambda _e, i=cd["id"]: act(g.resolve_identity_candidate, "Kept as separate identities.", candidate_id=i, approve=False)).props("outline dense no-caps")

                identity_view()

            # ------------------------------------------------------------------ exceptions & alerts
            with ui.tab_panel(t_exc).classes("!p-0 q-pt-md"):

                @ui.refreshable
                def exceptions_view() -> None:
                    excs = g.list_exceptions(user.ctx, limit=100)
                    alerts = g.list_alerts(user.ctx, limit=50)
                    section_title("Exceptions", "Classified into a 20-code taxonomy, retried automatically where safe, parked in a dead-letter queue otherwise.")
                    if not excs:
                        state_panel(icon="task_alt", title="No exceptions", body="Every exchange so far completed or stopped cleanly.", tone="success")
                    for x in excs:
                        with ui.row().classes("cl-card w-full items-center justify-between gap-2 flex-wrap"):
                            with ui.column().classes("gap-0").style("flex: 1 1 260px;"):
                                with ui.row().classes("items-center gap-2"):
                                    chip(x.get("error_code", ""), color="danger")
                                    chip(x.get("resolution_state", ""), color=STATUS_TONE.get(x.get("resolution_state", ""), "muted"), outline=True)
                                ui.label(x.get("message", "")).classes("text-sm")
                                ui.label(f"{_when(x.get('created_at'))} · correlation {str(x.get('correlation_id') or '')[:8]}").classes("text-[11px]").style("color: var(--cl-fg-subtle);")
                            if can_manage and x.get("resolution_state") == "open":
                                with ui.row().classes("gap-1"):
                                    ui.button("Retry", on_click=lambda _e, i=x["exception_id"]: act(g.retry_exception, "Retry recorded.", exception_id=i)).props("outline dense no-caps")
                                    ui.button("Resolve", on_click=lambda _e, i=x["exception_id"]: act(g.resolve_exception, "Marked resolved.", exception_id=i)).props("flat dense no-caps")
                                    ui.button("Dead-letter", on_click=lambda _e, i=x["exception_id"]: act(g.mark_exception_dead, "Moved to dead-letter queue.", exception_id=i)).props("flat dense no-caps color=negative")
                    section_title("SLA alerts", "Raised when a connector's average response time or success rate crosses its threshold (default 1000 ms / 95%).")
                    if not alerts:
                        state_panel(icon="notifications_off", title="No SLA alerts", body="All connectors are within their service levels.", tone="success")
                    for a in alerts:
                        with ui.row().classes("cl-card w-full items-center justify-between gap-2"):
                            ui.label(f"{a.get('connector_id')}: {a.get('message') or a.get('alert_type')}").classes("text-sm")
                            if can_manage and not a.get("acknowledged"):
                                ui.button("Acknowledge", on_click=lambda _e, i=a["alert_id"]: act(g.acknowledge_alert, "Alert acknowledged.", alert_id=i)).props("flat dense no-caps")

                exceptions_view()

            # ------------------------------------------------------------------ trace explorer
            with ui.tab_panel(t_trace).classes("!p-0 q-pt-md"):
                section_title("Distributed tracing", "Every transaction, event and audit row from one exchange shares a single correlation ID.")
                with ui.row().classes("w-full gap-2 items-center"):
                    trace_input = ui.input("Correlation ID").props("outlined dense").classes("flex-1")
                    ui.button("Trace", icon="travel_explore", on_click=lambda: open_trace(trace_input.value or "")).props("unelevated no-caps color=primary")
                trace_box = ui.column().classes("w-full gap-2")

                @ui.refreshable
                def trace_list() -> None:
                    txns = g.list_transactions(user.ctx, limit=12)
                    section_title("Recent exchanges")
                    data_table([("when", "When"), ("route", "Route"), ("status", "Status"), ("fields", "Fields exchanged"), ("cid", "Correlation")],
                               [{"id": t["transaction_id"], "when": _when(t["created_at"]), "route": f"{SYSTEM_NAMES.get(t['source_system'], t['source_system'])} → {SYSTEM_NAMES.get(t['target_system'], t['target_system'])}",
                                 "status": t["status"], "fields": _fields(t.get("fields_exchanged")) or "—", "cid": t["correlation_id"]} for t in txns],
                               on_row=lambda row: trace_later(row["cid"]), empty="No exchanges yet.")  # fmt: skip

                trace_list()

            # ------------------------------------------------------------------ catalog & workflows
            with ui.tab_panel(t_cat).classes("!p-0 q-pt-md"):
                for svc in g.list_service_catalog(user.ctx):
                    with surface():
                        with ui.row().classes("items-center justify-between w-full"):
                            ui.label(svc["name"]).classes("text-base font-semibold")
                            chip("active" if svc.get("active") else "inactive", color="success" if svc.get("active") else "muted")
                        ui.label(svc["description"]).classes("text-sm").style("color: var(--cl-fg-muted);")
                        ui.label(f"{SYSTEM_NAMES.get(svc['source_system'], svc['source_system'])} → {SYSTEM_NAMES.get(svc['target_system'], svc['target_system'])} · data category: {svc['data_category']}").classes("text-xs").style("color: var(--cl-fg-subtle);")
                section_title("Field mappings", "Department fields ↔ canonical model, one row per field - how a new department is onboarded without gateway code changes.")
                data_table([("system", "System"), ("direction", "Direction"), ("source", "From"), ("target", "To"), ("note", "Transform")],
                           [{"id": m["mapping_id"], "system": SYSTEM_NAMES.get(m["system_id"], m["system_id"]), "direction": m["direction"].replace("_", " "), "source": m["source_field"], "target": m["target_field"], "note": m.get("transform_note") or "—"} for m in g.list_field_mappings(user.ctx)],
                           empty="No mappings.")  # fmt: skip
                for wf in g.list_workflow_definitions(user.ctx):
                    section_title(f"Workflow: {wf['name']}", f"Version {wf['version']} · stored as data, so steps can change without redeploying.")
                    with ui.row().classes("gap-2 flex-wrap items-center"):
                        for i, st in enumerate(wf["steps"]):
                            chip(f"{i + 1}. {st['step_id'].replace('_', ' ')}", color="info", outline=True)
                execs = g.list_workflow_executions(user.ctx, limit=10)
                section_title("Recent workflow runs")
                data_table([("started", "Started"), ("status", "Status"), ("step", "Step reached"), ("cid", "Correlation")],
                           [{"id": e["execution_id"], "started": _when(e["started_at"]), "status": e["status"], "step": e["current_step_index"], "cid": e["correlation_id"]} for e in execs], empty="No runs yet.")  # fmt: skip

        # ---------------------------------------------------------------------- actions
        def pick(app_no: str) -> None:
            state["app"], state["result"] = app_no, None
            live.refresh()

        async def run_exchange() -> None:
            if not state["app"]:
                return
            try:
                state["result"] = await run.io_bound(g.request_document_exchange, user.ctx, application_no=state["app"])
            except CivicLensError as exc:
                ui.notify(exc.message, type="negative")
                return
            refresh_all()

        async def grant(consent_id: str) -> None:
            try:
                await run.io_bound(g.grant_consent, user.ctx, consent_id=consent_id)
            except CivicLensError as exc:
                ui.notify(exc.message, type="negative")
                return
            ui.notify("Consent recorded - running the exchange.", type="positive")
            await run_exchange()

        async def act(fn: Any, ok_msg: str, **kwargs: Any) -> None:
            try:
                await run.io_bound(fn, user.ctx, **kwargs)
            except CivicLensError as exc:
                ui.notify(exc.message, type="negative")
                return
            ui.notify(ok_msg, type="positive")
            refresh_all()

        def do_reset() -> None:  # sync: confirm_dialog calls on_confirm() without awaiting it
            try:
                r = g.reset_demo_scenario(user.ctx)
            except CivicLensError as exc:
                ui.notify(exc.message, type="negative")
                return
            state["result"] = None
            ui.notify(f"Demo reset: {r['applications_reopened']} application(s) reopened, {r['consents_withdrawn']} consent(s) withdrawn (kept in the audit log).", type="positive")
            refresh_all()

        reset_dialog = confirm_dialog("Reset the demo scenario?", "Reopens the demo Seva Setu applications and withdraws their consents so the full flow can be shown again. Nothing is deleted: history and audit rows stay.",
                                      confirm_label="Reset", on_confirm=lambda: do_reset())  # fmt: skip

        def trace_later(cid: str) -> None:
            ui.timer(0, lambda: open_trace(cid), once=True)  # table row clicks are sync; the trace lookup is async

        async def open_trace(cid: str) -> None:
            cid = (cid or "").strip()
            if not cid:
                return
            tabs.set_value(t_trace)
            trace_input.value = cid
            trace_box.clear()
            try:
                t = await run.io_bound(g.get_trace, user.ctx, correlation_id=cid)
            except CivicLensError as exc:
                with trace_box:
                    error_banner(exc.message)
                return
            with trace_box:
                with surface():
                    section_title(f"Trace {cid}")
                    for tx in t.get("transactions", []):
                        with ui.row().classes("gap-2 flex-wrap items-center"):
                            chip(tx["status"], color=STATUS_TONE.get(tx["status"], "muted"))
                            ui.label(f"{SYSTEM_NAMES.get(tx['source_system'], tx['source_system'])} → {SYSTEM_NAMES.get(tx['target_system'], tx['target_system'])} · {_when(tx['created_at'])}").classes("text-sm")
                        ui.label("Fields exchanged: " + (_fields(tx.get("fields_exchanged")) or "none")).classes("text-xs").style("color: var(--cl-fg-muted);")
                    with ui.column().classes("cl-timeline w-full gap-0 q-mt-sm"):
                        for ev in t.get("events", []):
                            with ui.column().classes("cl-timeline-step gap-0"):
                                with ui.element("div").classes("cl-timeline-dot " + ("cl-done" if ev["status"] == "success" else "cl-rejected")):
                                    ui.icon("check" if ev["status"] == "success" else "close")
                                ui.label(_pretty(ev["step"])).classes("text-sm font-medium")
                                ui.label(f"{SYSTEM_NAMES.get(ev['source_system'], ev['source_system'])} · {_when(ev['occurred_at'])}").classes("text-xs").style("color: var(--cl-fg-subtle);")
                    if not t.get("transactions") and not t.get("events"):
                        ui.label("Nothing recorded under this correlation ID.").classes("text-sm")

    # ========================================================================== citizen: my data sharing
    @page(c, "/my-data", "nav.my_data", roles=CIT)
    async def my_data(c: AppContainer, user: UiUser) -> None:
        g = c.interop_gateway
        page_header(tr(c, "mydata.title"), tr(c, "mydata.subtitle"), icon="how_to_reg")

        @ui.refreshable
        def view() -> None:
            rows = g.list_my_consents(user.ctx)
            pending = [r for r in rows if r["status"] == "pending"]
            active = [r for r in rows if r["status"] == "granted"]
            past = [r for r in rows if r["status"] not in ("pending", "granted")]
            section_title(tr(c, "mydata.requests"))
            if not pending:
                state_panel(icon="mark_email_read", title=tr(c, "mydata.no_requests"), body=tr(c, "mydata.no_requests_body"), tone="success")
            for r in pending:
                with ui.column().classes("cl-card w-full gap-2").style("border: 1.5px solid var(--cl-warning);"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("mark_email_unread").style("color: var(--cl-warning);")
                        ui.label(f"{SYSTEM_NAMES.get(r['providing_system'], r['providing_system'])} → {SYSTEM_NAMES.get(r['requesting_system'], r['requesting_system'])}").classes("text-sm font-semibold")
                    ui.label(r["purpose"]).classes("text-sm")
                    ui.label(tr(c, "mydata.only_fields")).classes("text-xs").style("color: var(--cl-fg-muted);")
                    with ui.row().classes("gap-1 flex-wrap"):
                        for f in r["fields"]:
                            chip(tr(c, f"field.{f}") if f in ("reference", "status", "issued_on") else FIELD_LABELS.get(f, f), color="info", icon="check")
                    ui.label(tr(c, "mydata.expiry_note")).classes("text-[11px]").style("color: var(--cl-fg-subtle);")
                    with ui.row().classes("gap-2"):
                        ui.button(tr(c, "mydata.allow"), icon="check", on_click=lambda _e, i=r["consent_id"]: decide(g.grant_consent, i)).props("unelevated color=positive no-caps")
                        ui.button(tr(c, "mydata.deny"), icon="close", on_click=lambda _e, i=r["consent_id"]: decide(g.deny_consent, i)).props("outline no-caps")
            section_title(tr(c, "mydata.active"))
            if not active:
                ui.label(tr(c, "mydata.none_active")).classes("text-sm").style("color: var(--cl-fg-muted);")
            for r in active:
                with ui.row().classes("cl-card w-full items-center justify-between gap-2 flex-wrap"):
                    with ui.column().classes("gap-0").style("flex: 1 1 260px;"):
                        ui.label(r["purpose"]).classes("text-sm font-medium")
                        ui.label(f"{tr(c, 'mydata.valid_until')} {_when(r['expires_at'])} · " + ", ".join(tr(c, f"field.{f}") if f in ("reference", "status", "issued_on") else FIELD_LABELS.get(f, f) for f in r["fields"])).classes("text-xs").style("color: var(--cl-fg-muted);")
                    ui.button(tr(c, "mydata.revoke"), icon="block", on_click=lambda _e, i=r["consent_id"]: revoke(i)).props("outline dense no-caps color=negative")
            used = g.my_data_access_log(user.ctx)
            section_title(tr(c, "mydata.used_title"), tr(c, "mydata.used_sub"))
            if not used:
                ui.label(tr(c, "mydata.used_none")).classes("text-sm").style("color: var(--cl-fg-muted);")
            for u in used:
                with ui.row().classes("cl-card w-full items-center gap-3 flex-wrap"):
                    ui.icon("swap_horiz").classes("text-[22px]").style("color: var(--cl-success);")
                    with ui.column().classes("gap-0").style("flex: 1 1 260px;"):
                        ui.label(f"{SYSTEM_NAMES.get(u['from_system'], u['from_system'])} → {SYSTEM_NAMES.get(u['to_system'], u['to_system'])}").classes("text-sm font-semibold")
                        ui.label(u["purpose"]).classes("text-xs").style("color: var(--cl-fg-muted);")
                        with ui.row().classes("gap-1 flex-wrap q-mt-xs"):
                            for f in u["fields"]:
                                chip(tr(c, f"field.{f}") if f in ("reference", "status", "issued_on") else FIELD_LABELS.get(f, f), color="muted", outline=True)
                    ui.label(_when(u["at"])).classes("text-xs cl-mono").style("color: var(--cl-fg-subtle);")
            if past:
                section_title(tr(c, "mydata.history"))
                data_table([("purpose", tr(c, "mydata.col_purpose")), ("status", tr(c, "lbl.status")), ("when", tr(c, "lbl.created"))],
                           [{"id": r["consent_id"], "purpose": r["purpose"], "status": r["status"], "when": _when(r["created_at"])} for r in past])  # fmt: skip

        async def decide(fn: Any, consent_id: str) -> None:
            try:
                await run.io_bound(fn, user.ctx, consent_id=consent_id)
            except CivicLensError as exc:
                ui.notify(exc.message, type="negative")
                return
            ui.notify(tr(c, "msg.saved"), type="positive")
            view.refresh()

        async def revoke(consent_id: str) -> None:
            try:
                await run.io_bound(g.revoke_consent, user.ctx, consent_id=consent_id, reason="Revoked by citizen")
            except CivicLensError as exc:
                ui.notify(exc.message, type="negative")
                return
            ui.notify(tr(c, "msg.saved"), type="positive")
            view.refresh()

        view()

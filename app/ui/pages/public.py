"""Landing, login, registration, password reset, onboarding and two-factor pages.

None of these render inside the authenticated app shell (``shell_on=False``); ``page()`` in
``app.ui.base`` applies ``public_topbar`` for them instead - otherwise they would render
completely unstyled, which is what happened before this module was redesigned.
"""

from __future__ import annotations

import base64
import logging

from nicegui import app, ui

from app.container import AppContainer
from app.core.authorization import Role
from app.core.exceptions import AuthenticationFailed, CivicLensError, MfaRequired
from app.core.transactions import run_in_uow
from app.services.profile_service import CONSENT_PURPOSES
from app.ui import navigation
from app.ui.base import UiUser, info_banner, page, sign_in, tr
from app.ui.components import (
    divider,
    field_hint,
    page_header,
    run_with_loading,
    section_title,
    state_panel,
)

logger = logging.getLogger("civiclens.ui")
PRIV = (Role.ADMIN, Role.SUPER_ADMIN, Role.INTEGRATION_ADMIN, Role.AUDITOR)  # every privileged staff role signs in through the administration door
DESK = (Role.OFFICER, Role.ADMIN, Role.SUPER_ADMIN)


def _login_form(c: AppContainer, *, privileged: bool, allowed: tuple[Role, ...] | None = None, accent: str | None = None, icon: str | None = None, heading: str | None = None, subheading: str | None = None, cta: str | None = None, note: str | None = None, links: bool = True) -> None:
    """One sign-in card. ``allowed`` restricts which roles may enter through *this* door: the
    officer/admin portals reject a citizen account (and log the session straight back out) so the
    two desks are genuinely separate entrances, not cosmetic tabs over one form. ``allowed=None``
    (the citizen door) lets the server decide the role and where the account lands.
    """
    allowed = allowed if allowed is not None else (PRIV if privileged else None)
    with ui.column().classes("cl-glass w-full max-w-md q-mx-auto gap-1").style(f"padding: 28px;{f' border-color: {accent};' if accent else ''}"):
        with ui.column().classes("items-center w-full gap-1 q-mb-sm"):
            chip_style = "width:52px; height:52px;" + (f" background: {accent};" if accent else "")
            with ui.element("div").classes("cl-brand-chip").style(chip_style):
                ui.icon(icon or ("admin_panel_settings" if privileged else "account_balance")).classes("text-[26px]")
            # An accented door (the officer/admin desks) paints its heading in that accent; painting
            # it with the citizen brand ramp would make the two portals read as the same desk.
            head = ui.label(heading or tr(c, "brand")).classes("text-lg font-bold q-mt-sm cl-title")
            head.classes("cl-gradient-text") if not accent else head.style("background: " + accent + "; -webkit-background-clip: text; background-clip: text; color: transparent;")
            ui.label(subheading or (tr(c, "nav.administration") if privileged else tr(c, "appTagline"))).classes("text-xs text-center").style("color: var(--cl-fg-muted); max-width: 34ch;")
        divider()
        with ui.column().classes("w-full gap-3 q-mt-md"):
            email = ui.input(tr(c, "lbl.email")).props("outlined dense").classes("w-full")
            pw = ui.input(tr(c, "lbl.password"), password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
            otp_box = ui.column().classes("w-full gap-1")
            with otp_box:
                otp = ui.input(tr(c, "lbl.otp")).props("outlined dense inputmode=numeric maxlength=12 autofocus").classes("w-full")
                field_hint(tr(c, "auth.otp_hint"))
            otp_box.set_visibility(False)
            err = ui.row().classes("cl-card w-full items-start gap-2 hidden").style("background: var(--cl-danger-soft); border-color: transparent; padding: 10px 12px;")
            with err:
                ui.icon("error").classes("text-[16px]").style("color: var(--cl-danger);")
                err_label = ui.label("").classes("text-xs").style("color: var(--cl-danger);")

            def show_error(message: str) -> None:
                err_label.set_text(message)
                err.classes(remove="hidden")

            async def submit() -> None:
                err.classes(add="hidden")
                client_key = str(ui.context.client.id)  # must be read on the UI event loop, before run_with_loading moves work to a thread

                def op(uow):
                    auth = c.auth_for(uow)
                    res = auth.login(email.value or "", pw.value or "", otp=(otp.value or None), client_key=client_key)
                    if allowed is not None and res.context.role not in allowed:
                        auth.logout(res.session_token)
                        uow.commit()
                        raise AuthenticationFailed("Invalid e-mail, password or verification code.")
                    return res

                try:
                    res = await run_with_loading(submit_btn, run_in_uow, c, op, commit_on_error=True)
                except MfaRequired as exc:
                    otp_box.set_visibility(True)
                    show_error(exc.message)
                    return
                except CivicLensError as exc:
                    show_error(exc.message)
                    return
                try:
                    saved = c.profiles.get(res.context).language
                except CivicLensError:
                    saved = None
                sign_in(res.session_token, saved)
                ui.navigate.to(navigation.home_for(res.context.role))

            pw.on("keydown.enter", submit)
            otp.on("keydown.enter", submit)
            submit_btn = ui.button(cta or tr(c, "act.sign_in"), icon="login", on_click=submit).props("unelevated").classes("w-full q-mt-sm cl-btn-glow")
            if accent:
                submit_btn.style(f"background: {accent} !important;")
        if note:
            ui.label(note).classes("text-xs q-mt-sm").style("color: var(--cl-fg-subtle); line-height: 1.5;")
        if links:
            with ui.row().classes("justify-between w-full q-mt-md text-sm"):
                ui.link(tr(c, "act.register"), "/register")
                ui.link(tr(c, "page.forgot"), "/reset-password")


OFFICER_ACCENT = "linear-gradient(135deg, #8A5A16 0%, #C22A1B 100%)"


def _portal_switcher(c: AppContainer, current: str) -> None:
    """Citizen / Officer segmented control. Each side is a distinct route, so the chosen desk
    survives a refresh, a bookmark and a shared link - not just a tab state in one form."""
    with ui.element("div").classes("cl-segment w-full max-w-md q-mx-auto q-mb-md"):
        for key, route, icon in (("portal.citizen", "/login", "person"), ("portal.official", "/officer/login", "account_balance")):
            on = " cl-on cl-" + ("citizen" if key.endswith("citizen") else "official") if key.split(".")[1] == current else ""
            el = ui.element("div").classes("cl-segment-item cl-focusable" + on).props('role=tab tabindex=0')
            with el:
                ui.icon(icon).classes("text-[17px]")
                ui.label(tr(c, key))
            if key.split(".")[1] != current:
                el.on("click", lambda r=route: ui.navigate.to(r))


def _landing_heading(title: str, subtitle: str | None = None) -> None:
    """Centred section heading for the landing page. ``section_title`` renders a small left-aligned
    uppercase label, which reads as a stray micro-label next to centred content on a wide hero page."""
    with ui.column().classes("items-center gap-1 w-full"):
        ui.label(title).classes("cl-title text-center").style("font-size: clamp(1.4rem, 3vw, 1.9rem); color: var(--cl-fg);")
        if subtitle:
            ui.label(subtitle).classes("text-sm text-center").style("color: var(--cl-fg-muted); max-width: 52ch;")


def _tile(icon: str, title: str, body: str, *, route: str | None = None) -> None:
    col = ui.column().classes("cl-glass cl-tile" + (" cl-card-hover" if route else ""))
    with col:
        with ui.element("div").classes("cl-brand-chip").style("width:38px; height:38px;"):
            ui.icon(icon).classes("text-[19px]")
        ui.label(title).classes("cl-tile-title")
        ui.label(body).classes("cl-tile-body")
    if route:
        col.on("click", lambda r=route: ui.navigate.to(r))


def register(c: AppContainer) -> None:
    @page(c, "/", "brand", public=True, shell_on=False)
    def landing(c: AppContainer, user: UiUser | None) -> None:
        from app.services.classification_service import CATEGORIES

        with ui.column().classes("items-center w-full cl-hero gap-4").style("max-width: 920px; margin: 0 auto;"):
            with ui.element("div").classes("cl-eyebrow"):
                ui.icon("auto_awesome").classes("text-[15px]")
                ui.label(tr(c, "hero.eyebrow"))
            ui.label(tr(c, "brand")).classes("cl-hero-title text-center cl-gradient-text").style("padding-bottom: 6px;")
            ui.label(tr(c, "appTagline")).classes("cl-hero-sub text-center")
            with ui.row().classes("gap-3 q-mt-md justify-center flex-wrap"):
                ui.button(tr(c, "portal.citizen"), icon="person", on_click=lambda: ui.navigate.to("/login")).props("unelevated size=lg").classes("cl-btn-glow")
                ui.button(tr(c, "portal.official"), icon="account_balance", on_click=lambda: ui.navigate.to("/officer/login")).props("outline size=lg").style("color: var(--cl-warning);")
                ui.button(tr(c, "nav.emergency"), icon="emergency", on_click=lambda: ui.navigate.to("/emergency-public")).props("flat size=lg").style("color: var(--cl-emergency);")

            # Every number here is read from this server's live configuration, never hard-coded copy.
            with ui.element("div").classes("cl-hero-strip q-mt-lg"):
                for value, label_key in ((str(len(c.ui_text.languages)), "hero.stat_languages"), (str(len(CATEGORIES)), "hero.stat_categories"), (str(c.settings.rti_response_days), "hero.stat_rti_days")):
                    with ui.column().classes("items-center gap-0"):
                        ui.label(value).classes("cl-hero-stat-n")
                        ui.label(tr(c, label_key)).classes("cl-hero-stat-l")

        with ui.column().classes("cl-page q-py-lg gap-4 items-center"):
            _landing_heading(tr(c, "land.how"))
            with ui.row().classes("gap-3 w-full flex-wrap justify-center items-stretch"):
                steps = [("edit_note", "land.step_report"), ("smart_toy", "land.step_analyse"), ("alt_route", "land.step_route"), ("task_alt", "land.step_resolve")]
                for i, (icon, key) in enumerate(steps):
                    with ui.row().classes("items-center gap-3"):
                        with ui.column().classes("cl-glass items-center justify-center gap-2").style("width: 172px; min-height: 130px; padding: 18px;"):
                            with ui.element("div").classes("cl-brand-chip").style("width:40px; height:40px;"):
                                ui.icon(icon).classes("text-[20px]")
                            ui.label(tr(c, key)).classes("text-sm font-medium text-center").style("color: var(--cl-fg);")
                        if i < len(steps) - 1:
                            ui.icon("arrow_forward").classes("gt-xs").style("color: var(--cl-fg-subtle);")

        # The tile rows are width-capped so they break 3-per-row instead of leaving a single
        # orphaned tile centred on a second line.
        with ui.column().classes("cl-page q-py-lg gap-4 items-center"):
            _landing_heading(tr(c, "land.everything"))
            with ui.row().classes("gap-4 justify-center flex-wrap items-stretch").style("max-width: 720px;"):
                _tile("record_voice_over", tr(c, "nav.assistant"), tr(c, "land.t_assistant"), route="/login")
                _tile("add_circle", tr(c, "nav.report"), tr(c, "land.t_report"), route="/login")
                _tile("gavel", tr(c, "nav.rti"), tr(c, "land.t_rti"), route="/login")
                _tile("balance", tr(c, "nav.legal"), tr(c, "land.t_legal"), route="/login")
                _tile("map", tr(c, "nav.gis"), tr(c, "land.t_gis"), route="/login")
                _tile("hub", tr(c, "nav.interop"), tr(c, "land.t_interop"), route="/login")

        with ui.column().classes("cl-page q-py-lg gap-4 items-center q-mb-lg"):
            _landing_heading(tr(c, "land.for_officials"), tr(c, "land.for_officials_sub"))
            with ui.row().classes("gap-4 justify-center flex-wrap items-stretch").style("max-width: 720px;"):
                _tile("inbox", tr(c, "nav.officer_queue"), tr(c, "land.t_queue"))
                _tile("timer", tr(c, "nav.sla"), tr(c, "land.t_sla"))
                _tile("search", tr(c, "nav.investigations"), tr(c, "land.t_investigations"))
            ui.button(tr(c, "portal.official_cta"), icon="account_balance", on_click=lambda: ui.navigate.to("/officer/login")).props("outline size=lg").classes("q-mt-sm").style("color: var(--cl-warning);")

    @page(c, "/login", "act.sign_in", public=True, shell_on=False)
    def login(c: AppContainer, user: UiUser | None) -> None:
        _portal_switcher(c, "citizen")
        _login_form(c, privileged=False, icon="person", heading=tr(c, "portal.citizen_title"), subheading=tr(c, "portal.citizen_sub"))

    @page(c, "/officer/login", "portal.official_title", public=True, shell_on=False)
    def officer_login(c: AppContainer, user: UiUser | None) -> None:
        _portal_switcher(c, "official")
        _login_form(
            c, privileged=False, allowed=DESK, accent=OFFICER_ACCENT, icon="account_balance",
            heading=tr(c, "portal.official_title"), subheading=tr(c, "portal.official_sub"),
            cta=tr(c, "portal.official_cta"), note=tr(c, "portal.official_note"), links=False,
        )
        with ui.row().classes("justify-center w-full q-mt-sm text-sm"):
            ui.link(tr(c, "portal.admin_link"), "/admin/login").classes("text-xs")

    @page(c, "/admin/login", "act.sign_in", public=True, shell_on=False)
    def admin_login(c: AppContainer, user: UiUser | None) -> None:
        with ui.column().classes("items-center w-full max-w-md q-mx-auto q-mb-sm"):
            ui.label(tr(c, "nav.administration")).classes("text-xs font-semibold uppercase").style("color: var(--cl-fg-subtle); letter-spacing: .08em;")
        _login_form(c, privileged=True, icon="admin_panel_settings", links=False)

    @page(c, "/register", "act.register", public=True, shell_on=False)
    def registration(c: AppContainer, user: UiUser | None) -> None:
        with ui.column().classes("cl-glass w-full max-w-md q-mx-auto gap-3").style("padding: 28px;"):
            ui.label(tr(c, "act.register")).classes("text-lg font-bold cl-gradient-text")
            name = ui.input(tr(c, "fullName")).props("outlined dense").classes("w-full")
            email = ui.input(tr(c, "lbl.email")).props("outlined dense type=email").classes("w-full")
            pw = ui.input(tr(c, "lbl.password"), password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
            confirm = ui.input(tr(c, "auth.confirm_password"), password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
            field_hint(tr(c, "auth.password_rule"))
            err = ui.row().classes("cl-card w-full items-start gap-2 hidden").style("background: var(--cl-danger-soft); border-color: transparent; padding: 10px 12px;")
            with err:
                ui.icon("error").classes("text-[16px]").style("color: var(--cl-danger);")
                err_label = ui.label("").classes("text-xs").style("color: var(--cl-danger);")

            async def submit() -> None:
                err.classes(add="hidden")
                if (pw.value or "") != (confirm.value or ""):
                    err_label.set_text("Passwords do not match.")
                    err.classes(remove="hidden")
                    return
                try:
                    await run_with_loading(submit_btn, run_in_uow, c, lambda uow: c.auth_for(uow).register(email.value or "", pw.value or "", name.value or ""))
                except CivicLensError as exc:
                    err_label.set_text(exc.message + (" " + ", ".join(f"{k}: {v}" for k, v in exc.details.items()) if isinstance(exc.details, dict) else ""))
                    err.classes(remove="hidden")
                    return
                ui.notify(tr(c, "msg.saved"), type="positive")
                ui.navigate.to("/login")

            submit_btn = ui.button(tr(c, "act.register"), icon="person_add", on_click=submit).props("unelevated").classes("w-full q-mt-sm cl-btn-glow")
            with ui.row().classes("justify-center w-full text-sm"):
                ui.label(tr(c, "auth.have_account")).style("color: var(--cl-fg-muted);")
                ui.link(tr(c, "act.sign_in"), "/login")

    @page(c, "/reset-password", "page.forgot", public=True, shell_on=False)
    def reset(c: AppContainer, user: UiUser | None) -> None:
        token = ui.context.client.request.query_params.get("token") if ui.context.client.request else None
        with ui.column().classes("cl-glass w-full max-w-md q-mx-auto gap-3").style("padding: 28px;"):
            if token:
                ui.label(tr(c, "auth.choose_new_password")).classes("text-lg font-bold cl-gradient-text")
                pw = ui.input(tr(c, "auth.new_password"), password=True, password_toggle_button=True).props("outlined dense").classes("w-full")

                async def do_reset() -> None:
                    try:
                        await run_with_loading(submit_btn, run_in_uow, c, lambda uow: c.auth_for(uow).reset_password(token, pw.value or ""), commit_on_error=True)
                    except CivicLensError as exc:
                        ui.notify(exc.message, type="negative")
                        return
                    ui.notify(tr(c, "msg.saved"), type="positive")
                    ui.navigate.to("/login")

                submit_btn = ui.button(tr(c, "act.save"), icon="lock_reset", on_click=do_reset).props("unelevated").classes("w-full cl-btn-glow")
            else:
                ui.label(tr(c, "auth.reset_title")).classes("text-lg font-bold cl-gradient-text")
                ui.label(tr(c, "auth.reset_sub")).classes("text-sm").style("color: var(--cl-fg-muted);")
                email = ui.input(tr(c, "lbl.email")).props("outlined dense type=email").classes("w-full")

                async def ask() -> None:
                    from app.api.v1.auth import forgot
                    from app.schemas.api import ForgotBody

                    r = await run_with_loading(submit_btn, forgot, ForgotBody(email=email.value or ""), c)
                    ui.notify(r["message"] + ("" if r["email_delivery"] == "configured" else " (This server cannot send e-mail: ask an administrator for a reset link.)"), type="info")

                submit_btn = ui.button(tr(c, "act.submit"), icon="send", on_click=ask).props("unelevated").classes("w-full cl-btn-glow")
                if c.mailer is None:
                    info_banner(tr(c, "auth.reset_no_email"), "orange")
            with ui.row().classes("justify-center w-full text-sm q-mt-sm"):
                ui.link(tr(c, "act.sign_in"), "/login")

    @page(c, "/admin/setup", "page.setup_admin", public=True, shell_on=False)
    def admin_setup(c: AppContainer, user: UiUser | None) -> None:
        if not c.admin_setup_token:
            with ui.column().classes("w-full max-w-md q-mx-auto q-mt-xl"):
                state_panel(icon="lock", title=tr(c, "auth.setup_disabled_title"), body=tr(c, "auth.setup_disabled_body"))
            return
        with ui.column().classes("cl-glass w-full max-w-md q-mx-auto gap-3").style("padding: 28px;"):
            ui.label(tr(c, "page.setup_admin")).classes("text-lg font-bold cl-gradient-text")
            name = ui.input(tr(c, "fullName")).props("outlined dense").classes("w-full")
            email = ui.input(tr(c, "lbl.email")).props("outlined dense").classes("w-full")
            pw = ui.input(tr(c, "lbl.password"), password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
            tok = ui.input(tr(c, "auth.setup_token"), password=True).props("outlined dense").classes("w-full")

            async def go() -> None:
                try:
                    await run_with_loading(submit_btn, run_in_uow, c, lambda uow: c.auth_for(uow).bootstrap_first_admin(email.value or "", pw.value or "", name.value or "", provided_token=tok.value or "", expected_token=c.admin_setup_token), commit_on_error=True)
                except CivicLensError as exc:
                    ui.notify(exc.message, type="negative")
                    return
                ui.notify(tr(c, "auth.admin_created"), type="positive")
                ui.navigate.to("/admin/login")

            submit_btn = ui.button(tr(c, "act.submit"), icon="admin_panel_settings", on_click=go).props("unelevated").classes("w-full cl-btn-glow")

    @page(c, "/emergency-public", "nav.emergency", public=True, shell_on=False)
    def emergency_public(c: AppContainer, user: UiUser | None) -> None:
        from app.ui.pages.citizen import helpline_cards

        with ui.column().classes("cl-page q-pa-md gap-4"):
            helpline_cards(c)

    @page(c, "/onboarding", "page.onboarding")
    def onboarding(c: AppContainer, user: UiUser) -> None:
        prof = c.profiles.get(user.ctx)
        page_header(tr(c, "page.onboarding"), tr(c, "onb.help"), icon="waving_hand")
        with ui.column().classes("cl-card w-full max-w-2xl gap-5 q-mt-md"):
            section_title(tr(c, "onb.your_details"))
            with ui.row().classes("gap-3 w-full flex-wrap"):
                name = ui.input(tr(c, "fullName"), value=prof.full_name).props("outlined dense").classes("w-full sm:flex-1")
                phone = ui.input(tr(c, "phoneNumber"), value=prof.phone or "").props("outlined dense").classes("w-full sm:flex-1")
            divider()
            section_title(tr(c, "lbl.location"), tr(c, "onb.ward_hint"))
            with ui.row().classes("gap-3 w-full flex-wrap"):
                city = ui.input(tr(c, "selectCity"), value=prof.city or "").props("outlined dense").classes("w-full sm:flex-1")
                ward = ui.input(tr(c, "lbl.ward"), value=prof.ward or "").props("outlined dense").classes("w-full sm:flex-1")
            divider()
            section_title(tr(c, "lbl.language"))
            language = ui.select({code: code.upper() for code in c.ui_text.languages}, value=prof.language, label=tr(c, "lbl.language")).props("outlined dense").classes("w-48")
            divider()
            section_title(tr(c, "onb.ai_consent"), tr(c, "onb.ai_consent_sub"))
            boxes = {p: ui.checkbox(p.replace("_", " ").capitalize(), value=c.profiles.consents(user.ctx)[p]["granted"]) for p in CONSENT_PURPOSES}
            field_hint(tr(c, "onb.ai_hint"))

            def save() -> None:
                c.profiles.update(user.ctx, full_name=name.value, phone=phone.value or None, city=city.value, ward=ward.value, language=language.value, complete_onboarding=True)
                for purpose, box in boxes.items():
                    c.profiles.set_consent(user.ctx, purpose, bool(box.value))
                app.storage.user["lang"] = language.value
                ui.navigate.to(navigation.home_for(user.ctx.role))

            ui.button(tr(c, "act.save"), icon="check", on_click=save).props("color=primary unelevated").classes("q-mt-sm")

    @page(c, "/security", "nav.security")
    def security(c: AppContainer, user: UiUser) -> None:
        enabled = run_in_uow(c, lambda uow: c.mfa_for(uow).is_enabled(user.ctx.user_id))
        page_header(tr(c, "nav.security"), tr(c, "mfa.help"), icon="lock")
        if enabled:
            with ui.column().classes("cl-card w-full max-w-md gap-3 q-mt-md"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("verified").style("color: var(--cl-success);")
                    ui.label(tr(c, "mfa.is_on")).classes("text-sm font-semibold").style("color: var(--cl-success);")
                divider()
                ui.label(tr(c, "mfa.disable_it")).classes("text-sm font-medium")
                pw = ui.input(tr(c, "lbl.password"), password=True).props("outlined dense").classes("w-full")
                code = ui.input(tr(c, "lbl.otp")).props("outlined dense").classes("w-full")

                def disable() -> None:
                    def op(uow):
                        ok = c.auth_for(uow).verify_password(user.ctx.user_id, pw.value or "")
                        c.mfa_for(uow).disable(user.ctx.user_id, code.value or "", reauthenticated=ok)

                    try:
                        run_in_uow(c, op, commit_on_error=True)
                    except CivicLensError as exc:
                        ui.notify(exc.message, type="negative")
                        return
                    ui.navigate.reload()

                ui.button(tr(c, "act.disable"), on_click=disable).props("color=negative outline")
            return

        with ui.column().classes("cl-card w-full max-w-md gap-3 q-mt-md"):
            area = ui.column().classes("gap-3 w-full")

            def start() -> None:
                try:
                    e = run_in_uow(c, lambda uow: c.mfa_for(uow).begin_enrollment(user.ctx.user_id, user.email))
                except CivicLensError as exc:
                    ui.notify(exc.message, type="negative")
                    return
                qr_png: bytes | None = None
                if c.qr_renderer:
                    try:
                        qr_png = c.qr_renderer(e.provisioning_uri)
                    except Exception:
                        logger.exception("QR rendering failed for MFA enrollment")
                area.clear()
                with area:
                    ui.label(tr(c, "mfa.scan")).classes("text-sm")
                    if qr_png is not None:
                        ui.image("data:image/png;base64," + base64.b64encode(qr_png).decode()).classes("w-56 self-center").style("border-radius: var(--cl-radius-md);")
                    else:
                        state_panel(icon="qr_code_2", title=tr(c, "mfa.qr_unavailable"), body=tr(c, "mfa.qr_unavailable_body"))
                    with ui.row().classes("items-center gap-2 w-full"):
                        ui.label(tr(c, "mfa.manual_key")).classes("text-xs").style("color: var(--cl-fg-muted);")
                        ui.label(e.manual_entry_secret).classes("cl-mono text-xs")
                    code = ui.input(tr(c, "lbl.otp")).props("outlined dense").classes("w-full")

                    def confirm() -> None:
                        def op(uow):
                            codes = c.mfa_for(uow).confirm_enrollment(user.ctx.user_id, code.value or "")
                            c.auth_for(uow).mark_session_mfa_verified(user.token)
                            return codes

                        try:
                            codes = run_in_uow(c, op, commit_on_error=True)
                        except CivicLensError as exc:
                            ui.notify(exc.message, type="negative")
                            return
                        area.clear()
                        with area:
                            with ui.row().classes("cl-card items-start gap-2 w-full").style("background: var(--cl-success-soft); border-color: transparent;"):
                                ui.icon("verified").style("color: var(--cl-success);")
                                with ui.column().classes("gap-1"):
                                    ui.label(tr(c, "mfa.enabled")).classes("text-sm font-semibold").style("color: var(--cl-success);")
                                    ui.label(tr(c, "mfa.save_codes")).classes("text-xs").style("color: var(--cl-success);")
                            with ui.column().classes("cl-surface-alt q-pa-md gap-1 w-full"):
                                for bc in codes:
                                    ui.label(bc).classes("cl-mono text-sm")

                    ui.button(tr(c, "act.confirm"), icon="check", on_click=confirm).props("color=primary unelevated")

            with area:
                ui.button(tr(c, "act.enable"), icon="add_moderator", on_click=start).props("color=primary unelevated")

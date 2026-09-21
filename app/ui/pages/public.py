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
PRIV = (Role.ADMIN, Role.SUPER_ADMIN)


def _login_form(c: AppContainer, *, privileged: bool) -> None:
    with ui.column().classes("cl-glass w-full max-w-md q-mx-auto gap-1").style("padding: 28px;"):
        with ui.column().classes("items-center w-full gap-1 q-mb-sm"):
            with ui.element("div").classes("cl-brand-chip").style("width:52px; height:52px;"):
                ui.icon("admin_panel_settings" if privileged else "account_balance").classes("text-[26px]")
            ui.label(tr(c, "brand")).classes("text-lg font-bold q-mt-sm cl-gradient-text")
            ui.label(tr(c, "nav.administration") if privileged else tr(c, "appTagline")).classes("text-xs text-center").style("color: var(--cl-fg-muted); max-width: 30ch;")
        divider()
        with ui.column().classes("w-full gap-3 q-mt-md"):
            email = ui.input(tr(c, "lbl.email")).props("outlined dense").classes("w-full")
            pw = ui.input(tr(c, "lbl.password"), password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
            otp_box = ui.column().classes("w-full gap-1")
            with otp_box:
                otp = ui.input(tr(c, "lbl.otp")).props("outlined dense inputmode=numeric maxlength=12 autofocus").classes("w-full")
                field_hint("Enter the 6-digit code from your authenticator app.")
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

                def op(uow):  # type: ignore[no-untyped-def]
                    auth = c.auth_for(uow)
                    res = auth.login(email.value or "", pw.value or "", otp=(otp.value or None), client_key=client_key)
                    if privileged and res.context.role not in PRIV:
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
            submit_btn = ui.button(tr(c, "act.sign_in"), icon="login", on_click=submit).props("unelevated").classes("w-full q-mt-sm cl-btn-glow")
        if not privileged:
            with ui.row().classes("justify-between w-full q-mt-md text-sm"):
                ui.link(tr(c, "act.register"), "/register")
                ui.link(tr(c, "page.forgot"), "/reset-password")


def register(c: AppContainer) -> None:
    @page(c, "/", "brand", public=True, shell_on=False)
    def landing(c: AppContainer, user: UiUser | None) -> None:
        with ui.column().classes("items-center w-full q-pa-xl gap-3").style("max-width: 880px; margin: 0 auto;"):
            with ui.row().classes("cl-badge cl-badge-ai q-mb-sm"):
                ui.icon("auto_awesome")
                ui.label("AI-assisted civic grievance platform")
            ui.label(tr(c, "brand")).classes("text-5xl font-extrabold text-center cl-gradient-text").style("letter-spacing: -.03em; padding-bottom: 4px;")
            ui.label(tr(c, "appTagline")).classes("text-base text-center").style("color: var(--cl-fg-muted); max-width: 56ch;")
            with ui.row().classes("gap-3 q-mt-md justify-center flex-wrap"):
                ui.button(tr(c, "act.sign_in"), icon="login", on_click=lambda: ui.navigate.to("/login")).props("unelevated size=lg").classes("cl-btn-glow")
                ui.button(tr(c, "act.register"), on_click=lambda: ui.navigate.to("/register")).props("outline color=primary size=lg")
                ui.button(tr(c, "nav.emergency"), icon="emergency", on_click=lambda: ui.navigate.to("/emergency-public")).props("flat size=lg").style("color: var(--cl-emergency);")

        with ui.column().classes("w-full items-center q-mt-xl"):
            with ui.column().classes("cl-page q-py-xl gap-4"):
                section_title("How it works")
                with ui.row().classes("gap-3 w-full flex-wrap justify-center q-mt-sm"):
                    steps = [("edit_note", "Citizen reports"), ("smart_toy", "AI analyses"), ("alt_route", "Smart routing"), ("task_alt", "Tracked to resolution")]
                    for i, (icon, label) in enumerate(steps):
                        with ui.row().classes("items-center gap-3"):
                            with ui.column().classes("cl-glass cl-card-hover items-center gap-2").style("width: 168px; padding: 18px;"):
                                with ui.element("div").classes("cl-brand-chip").style("width:40px; height:40px;"):
                                    ui.icon(icon).classes("text-[20px]")
                                ui.label(label).classes("text-sm font-medium text-center").style("color: var(--cl-fg);")
                            if i < len(steps) - 1:
                                ui.icon("arrow_forward").classes("gt-xs").style("color: var(--cl-fg-subtle);")

        with ui.column().classes("cl-page q-py-xl gap-4 items-center"):
            section_title("Everything a citizen needs")
            with ui.row().classes("gap-4 justify-center flex-wrap q-mt-sm"):
                for key, icon, route in (("nav.report", "add_circle", "/login"), ("nav.rti", "gavel", "/login"), ("nav.copilot", "smart_toy", "/login"), ("nav.gis", "map", "/login")):
                    with ui.column().classes("cl-glass cl-card-hover items-center gap-2").style("width: 168px; padding: 18px;").on("click", lambda r=route: ui.navigate.to(r)):
                        with ui.element("div").classes("cl-brand-chip").style("width:40px; height:40px;"):
                            ui.icon(icon).classes("text-[20px]")
                        ui.label(tr(c, key)).classes("text-sm font-medium text-center").style("color: var(--cl-fg);")

    @page(c, "/login", "act.sign_in", public=True, shell_on=False)
    def login(c: AppContainer, user: UiUser | None) -> None:
        _login_form(c, privileged=False)

    @page(c, "/admin/login", "act.sign_in", public=True, shell_on=False)
    def admin_login(c: AppContainer, user: UiUser | None) -> None:
        with ui.column().classes("items-center w-full max-w-md q-mx-auto q-mb-sm"):
            ui.label(tr(c, "nav.administration")).classes("text-xs font-semibold uppercase").style("color: var(--cl-fg-subtle); letter-spacing: .08em;")
        _login_form(c, privileged=True)

    @page(c, "/register", "act.register", public=True, shell_on=False)
    def registration(c: AppContainer, user: UiUser | None) -> None:
        with ui.column().classes("cl-glass w-full max-w-md q-mx-auto gap-3").style("padding: 28px;"):
            ui.label(tr(c, "act.register")).classes("text-lg font-bold cl-gradient-text")
            name = ui.input(tr(c, "fullName")).props("outlined dense").classes("w-full")
            email = ui.input(tr(c, "lbl.email")).props("outlined dense type=email").classes("w-full")
            pw = ui.input(tr(c, "lbl.password"), password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
            confirm = ui.input("Confirm password", password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
            field_hint("At least 10 characters.")
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
                ui.label("Already have an account?").style("color: var(--cl-fg-muted);")
                ui.link(tr(c, "act.sign_in"), "/login")

    @page(c, "/reset-password", "page.forgot", public=True, shell_on=False)
    def reset(c: AppContainer, user: UiUser | None) -> None:
        token = ui.context.client.request.query_params.get("token") if ui.context.client.request else None  # type: ignore[union-attr]
        with ui.column().classes("cl-glass w-full max-w-md q-mx-auto gap-3").style("padding: 28px;"):
            if token:
                ui.label("Choose a new password").classes("text-lg font-bold cl-gradient-text")
                pw = ui.input("New password", password=True, password_toggle_button=True).props("outlined dense").classes("w-full")

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
                ui.label("Reset your password").classes("text-lg font-bold cl-gradient-text")
                ui.label("Enter the e-mail on your account and we'll send a reset link if it exists.").classes("text-sm").style("color: var(--cl-fg-muted);")
                email = ui.input(tr(c, "lbl.email")).props("outlined dense type=email").classes("w-full")

                async def ask() -> None:
                    from app.api.v1.auth import forgot
                    from app.schemas.api import ForgotBody

                    r = await run_with_loading(submit_btn, forgot, ForgotBody(email=email.value or ""), c)
                    ui.notify(r["message"] + ("" if r["email_delivery"] == "configured" else " (This server cannot send e-mail: ask an administrator for a reset link.)"), type="info")

                submit_btn = ui.button(tr(c, "act.submit"), icon="send", on_click=ask).props("unelevated").classes("w-full cl-btn-glow")
                if c.mailer is None:
                    info_banner("E-mail delivery is not configured on this server, so reset links cannot be sent. Ask an administrator for help.", "orange")
            with ui.row().classes("justify-center w-full text-sm q-mt-sm"):
                ui.link(tr(c, "act.sign_in"), "/login")

    @page(c, "/admin/setup", "page.setup_admin", public=True, shell_on=False)
    def admin_setup(c: AppContainer, user: UiUser | None) -> None:
        if not c.admin_setup_token:
            with ui.column().classes("w-full max-w-md q-mx-auto q-mt-xl"):
                state_panel(icon="lock", title="Administrator setup is disabled", body="ADMIN_SETUP_TOKEN is not set on this server.")
            return
        with ui.column().classes("cl-glass w-full max-w-md q-mx-auto gap-3").style("padding: 28px;"):
            ui.label(tr(c, "page.setup_admin")).classes("text-lg font-bold cl-gradient-text")
            name = ui.input(tr(c, "fullName")).props("outlined dense").classes("w-full")
            email = ui.input(tr(c, "lbl.email")).props("outlined dense").classes("w-full")
            pw = ui.input(tr(c, "lbl.password"), password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
            tok = ui.input("Setup token", password=True).props("outlined dense").classes("w-full")

            async def go() -> None:
                try:
                    await run_with_loading(submit_btn, run_in_uow, c, lambda uow: c.auth_for(uow).bootstrap_first_admin(email.value or "", pw.value or "", name.value or "", provided_token=tok.value or "", expected_token=c.admin_setup_token), commit_on_error=True)
                except CivicLensError as exc:
                    ui.notify(exc.message, type="negative")
                    return
                ui.notify("Administrator created. Sign in and enrol two-factor authentication.", type="positive")
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
        page_header(tr(c, "page.onboarding"), "A minute of setup so CivicLens can route your reports correctly.", icon="waving_hand")
        with ui.column().classes("cl-card w-full max-w-2xl gap-5 q-mt-md"):
            section_title("Your details")
            with ui.row().classes("gap-3 w-full flex-wrap"):
                name = ui.input(tr(c, "fullName"), value=prof.full_name).props("outlined dense").classes("w-full sm:flex-1")
                phone = ui.input(tr(c, "phoneNumber"), value=prof.phone or "").props("outlined dense").classes("w-full sm:flex-1")
            divider()
            section_title("Location", "Helps route reports to the right ward office.")
            with ui.row().classes("gap-3 w-full flex-wrap"):
                city = ui.input(tr(c, "selectCity"), value=prof.city or "").props("outlined dense").classes("w-full sm:flex-1")
                ward = ui.input(tr(c, "lbl.ward"), value=prof.ward or "").props("outlined dense").classes("w-full sm:flex-1")
            divider()
            section_title("Language")
            language = ui.select({code: code.upper() for code in c.ui_text.languages}, value=prof.language, label=tr(c, "lbl.language")).props("outlined dense").classes("w-48")
            divider()
            section_title("AI & data consent", "Optional. You can change any of this later in Settings.")
            boxes = {p: ui.checkbox(p.replace("_", " ").capitalize(), value=c.profiles.consents(user.ctx)[p]["granted"]) for p in CONSENT_PURPOSES}
            field_hint("AI processing lets a model help classify your complaints; it never decides outcomes on its own.")

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
        page_header(tr(c, "nav.security"), "Two-factor authentication adds a one-time code to every sign-in.", icon="lock")
        if enabled:
            with ui.column().classes("cl-card w-full max-w-md gap-3 q-mt-md"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("verified").style("color: var(--cl-success);")
                    ui.label("Two-factor authentication is ON").classes("text-sm font-semibold").style("color: var(--cl-success);")
                divider()
                ui.label("Disable it").classes("text-sm font-medium")
                pw = ui.input(tr(c, "lbl.password"), password=True).props("outlined dense").classes("w-full")
                code = ui.input(tr(c, "lbl.otp")).props("outlined dense").classes("w-full")

                def disable() -> None:
                    def op(uow):  # type: ignore[no-untyped-def]
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
                    ui.label("Scan with Google Authenticator (or any TOTP app):").classes("text-sm")
                    if qr_png is not None:
                        ui.image("data:image/png;base64," + base64.b64encode(qr_png).decode()).classes("w-56 self-center").style("border-radius: var(--cl-radius-md);")
                    else:
                        state_panel(icon="qr_code_2", title="QR rendering unavailable", body="Enter the key manually below.")
                    with ui.row().classes("items-center gap-2 w-full"):
                        ui.label("Manual key:").classes("text-xs").style("color: var(--cl-fg-muted);")
                        ui.label(e.manual_entry_secret).classes("cl-mono text-xs")
                    code = ui.input(tr(c, "lbl.otp")).props("outlined dense").classes("w-full")

                    def confirm() -> None:
                        def op(uow):  # type: ignore[no-untyped-def]
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
                                    ui.label("Two-factor authentication is enabled").classes("text-sm font-semibold").style("color: var(--cl-success);")
                                    ui.label("Save these backup codes now - they are shown once.").classes("text-xs").style("color: var(--cl-success);")
                            with ui.column().classes("cl-surface-alt q-pa-md gap-1 w-full"):
                                for bc in codes:
                                    ui.label(bc).classes("cl-mono text-sm")

                    ui.button(tr(c, "act.confirm"), icon="check", on_click=confirm).props("color=primary unelevated")

            with area:
                ui.button(tr(c, "act.enable"), icon="add_moderator", on_click=start).props("color=primary unelevated")

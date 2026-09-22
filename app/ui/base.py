"""Shared UI plumbing: session lookup, translation, page decorator, application shell, small widgets.

Pages call the same service objects the REST API calls (in-process); authorization is therefore
identical and always derived from the server-side session, never from anything the browser holds.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from nicegui import app, ui

from app.container import AppContainer
from app.core.authorization import AuthContext, Role
from app.core.exceptions import AuthenticationFailed, CivicLensError
from app.core.security import hash_token
from app.core.transactions import run_in_uow
from app.ui import navigation, theme

logger = logging.getLogger("civiclens.ui")


@dataclass
class UiUser:
    ctx: AuthContext
    token: str
    lang: str
    email: str = ""
    full_name: str = ""


def lang() -> str:
    return str(app.storage.user.get("lang", "en"))


def current_user(c: AppContainer) -> UiUser | None:
    """Resolve the server-side session token kept in NiceGUI's per-browser *server* storage."""
    token = app.storage.user.get("session_token")
    if not token:
        return None
    try:
        with c.uow_factory() as uow:
            ctx = c.auth_for(uow).authenticate(token)
            u = uow.users.get_by_id(ctx.user_id)
            uow.commit()
    except AuthenticationFailed:
        app.storage.user.pop("session_token", None)
        return None
    return UiUser(ctx, token, lang(), u.email if u else "", u.full_name if u else "")


def sign_in(token: str, language: str | None = None) -> None:
    app.storage.user["session_token"] = token
    if language:  # the account's saved language wins after sign-in, and survives navigation (server-side storage)
        app.storage.user["lang"] = language


def set_language(c: AppContainer, user: UiUser, code: str) -> None:
    """Switch the interface language now, and persist it on the account."""
    app.storage.user["lang"] = code
    try:
        c.profiles.update(user.ctx, language=code)
    except CivicLensError:
        pass  # e.g. a language the profile does not accept; the session choice still applies


def sign_out(c: AppContainer) -> None:
    token = app.storage.user.pop("session_token", None)
    if token:
        run_in_uow(c, lambda uow: c.auth_for(uow).logout(token))
        c.ws.drop_session_threadsafe(hash_token(token))


def tr(c: AppContainer, key: str, **kw: Any) -> str:
    return c.ui_text.t(key, lang(), **kw)


_TONE_ICON = {"red": ("danger", "error"), "orange": ("warning", "warning"), "blue": ("info", "info"), "green": ("success", "task_alt"), "grey": ("muted", "info")}


def error_banner(message: str) -> None:
    with ui.row().classes("cl-card w-full items-start gap-3").style("background: var(--cl-danger-soft); border-color: transparent;"):
        ui.icon("error").style("color: var(--cl-danger);")
        ui.label(message).classes("text-sm").style("color: var(--cl-danger);")


def info_banner(message: str, color: str = "blue") -> None:
    tone, icon = _TONE_ICON.get(color, ("info", "info"))
    with ui.row().classes("cl-card w-full items-start gap-3").style(f"background: var(--cl-{tone}-soft); border-color: transparent;"):
        ui.icon(icon).style(f"color: var(--cl-{tone});")
        ui.label(message).classes("text-sm").style(f"color: var(--cl-{tone});")


def empty_state(message: str, *, icon: str = "inbox") -> None:
    with ui.column().classes("cl-state"):
        ui.icon(icon)
        ui.label(message).classes("cl-state-body")


def badge(text: str, color: str) -> None:
    known = {"grey": "muted", "green": "success", "green-9": "success", "orange": "warning", "deep-orange": "warning", "red": "danger", "blue": "info", "blue-grey": "muted", "indigo": "primary"}
    tone = known.get(color, color)
    with ui.row().classes(f"cl-badge cl-badge-{tone}"):
        ui.label(text)


def stat_card(label: str, value: Any, color: str = "primary", hint: str | None = None) -> None:
    tone = {"primary": "primary", "green": "success", "orange": "warning", "red": "danger", "deep-orange": "warning", "indigo": "ai", "grey": "muted"}.get(color, color)
    with ui.column().classes("cl-card cl-stat gap-1"):
        ui.label(str(label)).classes("text-xs font-medium").style("color: var(--cl-fg-muted);")
        ui.label(str(value)).classes("text-2xl font-bold").style(f"color: var(--cl-{tone}); letter-spacing: -.02em;")
        if hint:
            ui.label(hint).classes("text-xs").style("color: var(--cl-fg-subtle);")


def data_table(columns: list[tuple[str, str]], rows: list[dict[str, Any]], *, on_row: Callable[[dict[str, Any]], None] | None = None, empty: str = "No data yet.", key: str = "id") -> None:
    if not rows:
        empty_state(empty)
        return
    t = ui.table(columns=[{"name": n, "label": label, "field": n, "align": "left", "sortable": True} for n, label in columns], rows=rows, row_key=key, pagination=15).classes("w-full cl-card !p-0")
    t.props("flat")
    if on_row:
        t.on("rowClick", lambda e: on_row(e.args[1]))


class _UiSocket:
    """Adapts a NiceGUI client to the WebSocketManager's ``send_json`` (real-time push into the page)."""

    def __init__(self, client: Any, on_event: Callable[[dict[str, Any]], None]) -> None:
        self._client, self._on_event = client, on_event

    async def send_json(self, data: Any) -> None:
        with self._client:
            self._on_event(data)


def _toast(c: AppContainer, data: dict[str, Any]) -> None:
    kind = data.get("type", "")
    d = data.get("data", {})
    if kind == "notification.created":
        ui.notify(d.get("title", "Notification"), type="info", position="top-right")
    elif kind.startswith("complaint."):
        ui.notify(f"{d.get('reference', '')}: {kind.split('.', 1)[1].replace('_', ' ')}", type="info", position="top-right")
    elif kind == "integration.status_changed":
        ui.notify(f"{d.get('platform')}: {d.get('to')}", type="warning", position="top-right")


def public_topbar(c: AppContainer, *, home: bool = False) -> None:
    """Animated gradient-mesh backdrop + a floating glass header for pages outside the app shell
    (auth, landing) - previously these pages had zero background treatment beyond a flat colour.

    Must run *before* the page-content column opens: ``ui.header`` is a top-level layout element
    and NiceGUI refuses to nest it inside a regular container.
    """
    ui.add_css(theme.CSS)
    ui.colors(**theme.QUASAR_COLOR_KWARGS)
    dm = ui.dark_mode(value=app.storage.user.get("dark"))

    with ui.element("div").classes("cl-aurora"):
        ui.element("div").classes("cl-blob cl-blob-1")
        ui.element("div").classes("cl-blob cl-blob-2")
        ui.element("div").classes("cl-blob cl-blob-3")

    with ui.header(elevated=False).classes("cl-glass items-center q-px-md").style("height: 64px; border-radius: 0; border-left: none; border-right: none; border-top: none;"):
        brand = ui.row().classes("items-center gap-2") if home else ui.link(target="/")
        with brand:
            if not home:
                brand.style("display: flex; align-items: center; gap: 10px; color: inherit; text-decoration: none;")
            with ui.element("div").classes("cl-brand-chip").style("width: 34px; height: 34px;"):
                ui.icon("account_balance").classes("text-[18px]")
            ui.label(tr(c, "brand")).classes("text-base font-bold").style("color: var(--cl-fg);")
        ui.space()

        def flip() -> None:
            new_value = not (dm.value if dm.value is not None else False)
            dm.value = new_value
            app.storage.user["dark"] = new_value
            theme_btn.props(f"icon={'light_mode' if new_value else 'dark_mode'}")

        theme_btn = ui.button(icon="light_mode" if dm.value else "dark_mode", on_click=flip).props("flat round dense").style("color: var(--cl-fg);")
        theme_btn.tooltip(tr(c, "theme.toggle"))

        from app.i18n.languages import LANGUAGES as _LANGS

        opts = {code: (_LANGS[code].native if code in _LANGS else code.upper()) for code in c.ui_text.languages}

        def set_lang(e: Any) -> None:
            app.storage.user["lang"] = e.value
            ui.navigate.reload()

        lsel = ui.select(opts, value=app.storage.user.get("lang", "en"), on_change=set_lang).props("dense outlined options-dense behavior=menu").classes("w-24")
        lsel.tooltip(tr(c, "lang.select"))


def _role_label(c: AppContainer, role: Role) -> str:
    key = {Role.CITIZEN: "role.citizen", Role.OFFICER: "role.officer", Role.ADMIN: "role.admin", Role.SUPER_ADMIN: "role.super_admin"}.get(role)
    return tr(c, key) if key else role.value.title()


def shell(c: AppContainer, user: UiUser, route: str, title_key: str) -> None:
    ui.add_css(theme.CSS)
    ui.colors(**theme.QUASAR_COLOR_KWARGS)
    dark_pref = app.storage.user.get("dark")
    dm = ui.dark_mode(value=dark_pref)
    ui.link(tr(c, "a11y.skip_content"), "#cl-main").classes("cl-skip-link cl-focusable")

    # A drawer with value=None lets Quasar decide, per-viewport, whether it is a pushed sidebar
    # (wide screens) or a closed overlay (narrow screens) - a value of True forced it open as an
    # *overlay on top of the page* on any viewport under the breakpoint, which is what used to make
    # the drawer cover the Report an Issue form. Never force this drawer open.
    drawer = ui.left_drawer(value=None, bordered=False).props("breakpoint=1024 width=264").classes("cl-sidebar")

    with drawer:
        with ui.row().classes("cl-brand-mark items-center"):
            with ui.element("div").classes("cl-brand-chip").style("width: 32px; height: 32px;"):
                ui.icon("account_balance").classes("text-[17px]")
            ui.label(tr(c, "brand")).classes("text-base font-bold text-white")
        with ui.column().classes("w-full gap-0 q-pb-md").style("overflow-y: auto;"):
            for group in navigation.visible(user.ctx.role):
                if group.key:
                    ui.label(tr(c, group.key)).classes("cl-nav-group")
                for item in group.items:
                    active = route == item.route or (item.route != "/" and route.startswith(item.route + "/") and not any(o.route.startswith(item.route + "/") and route.startswith(o.route) for g in navigation.NAVIGATION for o in g.items if o is not item))
                    with ui.link(target=item.route).classes("cl-nav-item cl-focusable" + (" cl-active" if active else "")):
                        ui.icon(item.icon)
                        ui.label(tr(c, item.key))

    with ui.header(elevated=False).classes("cl-shell-header items-center q-px-md").style("height: 64px;"):
        ui.button(icon="menu", on_click=drawer.toggle).props("flat round dense").tooltip(tr(c, "nav.open_menu")).style("color: var(--cl-fg);")
        with ui.column().classes("gap-0 gt-xs q-ml-sm"):
            ui.label(tr(c, title_key)).classes("text-sm font-semibold").style("color: var(--cl-fg); line-height: 1.1;")
            ui.label(_role_label(c, user.ctx.role) + (f" · {user.ctx.department_id}" if user.ctx.department_id else "")).classes("text-xs").style("color: var(--cl-fg-muted);")
        ui.space()
        with ui.row().classes("items-center gt-sm").style("max-width: 320px;"):
            q = ui.input(placeholder=tr(c, "act.search")).props("dense outlined rounded clearable").classes("w-56")
            q.on("keydown.enter", lambda: ui.navigate.to(f"/copilot?q={q.value}" if user.ctx.role is Role.CITIZEN else f"/officer/queue?q={q.value}"))
        live = ui.element("div").classes("cl-badge cl-badge-muted gt-xs")
        with live:
            ui.element("span").classes("cl-dot cl-dot-muted")
            live_label = ui.label(tr(c, "conn.offline"))
        pending = ui.element("div").classes("cl-badge cl-badge-warning")
        with pending:
            pending_label = ui.label("")
        pending.tooltip(tr(c, "msg.pending_sync"))
        pending.set_visibility(False)

        def flip_theme() -> None:
            new_value = not (dm.value if dm.value is not None else False)
            dm.value = new_value
            app.storage.user["dark"] = new_value
            theme_btn.props(f"icon={'light_mode' if new_value else 'dark_mode'}")
            theme_btn.tooltip(tr(c, "theme.dark") if not new_value else tr(c, "theme.light"))

        theme_btn = ui.button(icon="light_mode" if dm.value else "dark_mode", on_click=flip_theme).props("flat round dense").style("color: var(--cl-fg);")
        theme_btn.tooltip(tr(c, "theme.toggle"))

        bell = ui.button(icon="notifications", on_click=lambda: ui.navigate.to("/notifications")).props("flat round dense").style("color: var(--cl-fg);")
        bell.tooltip(tr(c, "nav.notifications"))
        with bell:
            count = ui.badge("0", color="danger").props("floating")

        langs = c.ui_text.languages
        from app.i18n.languages import LANGUAGES as _LANGS

        lang_options = {code: _LANGS[code].native if code in _LANGS else code.upper() for code in langs}
        lang_sel = ui.select(lang_options, value=lang(), on_change=lambda e: (set_language(c, user, e.value), ui.navigate.reload())).props("dense outlined options-dense behavior=menu").classes("w-24 gt-xs")
        lang_sel.tooltip(tr(c, "lang.select"))

        with ui.button(icon="account_circle").props("flat round dense").style("color: var(--cl-fg);"):
            with ui.menu().props("anchor='bottom right' self='top right'"):
                with ui.column().classes("q-pa-sm gap-0").style("min-width: 200px;"):
                    ui.label(user.full_name or user.email).classes("text-sm font-semibold q-px-sm")
                    ui.label(user.email).classes("text-xs q-px-sm q-pb-xs").style("color: var(--cl-fg-muted);")
                ui.separator()
                ui.menu_item(tr(c, "nav.profile"), lambda: ui.navigate.to("/profile"))
                ui.menu_item(tr(c, "nav.settings"), lambda: ui.navigate.to("/settings"))
                with ui.row().classes("items-center justify-between w-full q-px-sm q-py-xs"):
                    ui.label(tr(c, "lbl.appearance")).classes("text-sm")
                    ui.button(icon="light_mode" if dm.value else "dark_mode", on_click=flip_theme).props("flat round dense size=sm")
                ui.separator()
                ui.menu_item(tr(c, "act.sign_out"), lambda: (sign_out(c), ui.navigate.to("/login")))

    def refresh() -> None:
        try:
            with c.uow_factory() as uow:
                n = uow.notifications.unread_count(user.ctx.user_id)
                drafts = uow.drafts.list_for_user(user.ctx.user_id, "complaint") if user.ctx.role is Role.CITIZEN else []
            count.set_text(str(n))
            count.set_visibility(n > 0)
            waiting = sum(1 for d in drafts if d.status in ("pending_sync", "failed"))
            pending_label.set_text(str(waiting))
            pending.set_visibility(waiting > 0)
        except Exception:
            logger.warning("header refresh failed")

    async def connect() -> None:
        await ui.context.client.connected()
        live_label.set_text(tr(c, "conn.live"))
        live.classes(remove="cl-badge-muted", add="cl-badge-success")
        cid = await c.ws.connect(_UiSocket(ui.context.client, lambda d: (_toast(c, d), refresh())), user.ctx)  # type: ignore[arg-type]
        ui.context.client.on_disconnect(lambda: c.ws.disconnect(cid))

    ui.timer(0.1, connect, once=True)
    ui.timer(30.0, refresh)
    refresh()


def page(c: AppContainer, path: str, title_key: str, *, roles: frozenset[Role] | None = None, public: bool = False, shell_on: bool = True) -> Callable[..., Any]:
    """Register a page: authentication, role check, shell, and uniform error display."""

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        @ui.page(path)
        async def wrapper(request: Request) -> None:
            kw = dict(request.path_params)
            user = current_user(c)
            if not public and user is None:
                ui.navigate.to("/login" if not path.startswith("/admin") else "/admin/login")
                return
            if user is not None and roles is not None and user.ctx.role not in roles:
                ui.navigate.to(navigation.home_for(user.ctx.role))
                return
            if user is not None and shell_on:
                shell(c, user, path if "{" not in path else path.split("/{")[0], title_key)
            elif not shell_on:
                public_topbar(c, home=path == "/")
            with ui.column().classes("cl-page q-pa-md gap-4").props('id="cl-main" role="main"'):
                try:
                    res = fn(c, user, **kw)
                    if hasattr(res, "__await__"):
                        await res
                except CivicLensError as exc:
                    error_banner(exc.message + (f" ({', '.join(f'{k}: {v}' for k, v in exc.details.items())})" if isinstance(exc.details, dict) else ""))
                except Exception:
                    logger.exception("ui page %s failed", path)
                    error_banner(tr(c, "msg.error_generic"))

        return wrapper

    return deco


def hash_of(token: str) -> str:
    return hash_token(token)

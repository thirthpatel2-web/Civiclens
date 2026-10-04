"""NiceGUI application: pages are registered on import of ``mount_ui`` and served by the same FastAPI app."""

from __future__ import annotations

from typing import Any


def mount_ui(fastapi_app: Any, container: Any, settings: Any) -> None:
    from nicegui import ui

    from app.ui.pages import admin, citizen, gateway, public, staff

    for module in (public, citizen, staff, admin, gateway):
        module.register(container)
    secret = settings.session_secret or settings.app_secret_key
    if settings.is_production and not secret:
        raise RuntimeError("SESSION_SECRET is required in production")
    # The browser session cookie maps to the signed-in user, so on an https:// deployment it is marked Secure
    # (never sent over plain http). NiceGUI reuses a SessionMiddleware that is already registered.
    import os

    from nicegui import app as nicegui_app
    from starlette.middleware.sessions import SessionMiddleware

    https = os.environ.get("PUBLIC_BASE_URL", "").strip().lower().startswith("https://")
    nicegui_app.add_middleware(SessionMiddleware, secret_key=secret or "dev-only-storage-secret", https_only=https, same_site="lax")
    ui.run_with(fastapi_app, storage_secret=secret or "dev-only-storage-secret", title="CivicLens", favicon="🏛️", mount_path="/")

"""NiceGUI application: pages are registered on import of ``mount_ui`` and served by the same FastAPI app."""

from __future__ import annotations

from typing import Any


def mount_ui(fastapi_app: Any, container: Any, settings: Any) -> None:
    from nicegui import ui

    from app.ui.pages import admin, citizen, public, staff

    for module in (public, citizen, staff, admin):
        module.register(container)
    secret = settings.session_secret or settings.app_secret_key
    if settings.is_production and not secret:
        raise RuntimeError("SESSION_SECRET is required in production")
    ui.run_with(fastapi_app, storage_secret=secret or "dev-only-storage-secret", title="CivicLens", favicon="🏛️", mount_path="/")

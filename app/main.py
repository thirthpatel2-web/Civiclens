"""FastAPI application factory: REST API + WebSocket + NiceGUI UI in one Python process."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.api.v1.router import api_router
from app.container import AppContainer, build_container
from app.core import middleware
from app.core.config import Settings
from app.core.dependencies import SESSION_COOKIE
from app.core.exceptions import AuthenticationFailed
from app.core.logging import configure_logging
from app.realtime.websocket_manager import LocalEventBus

logger = logging.getLogger("civiclens.main")


def _load_precedents(container: AppContainer) -> int:
    """Populate the verified precedent index from PostgreSQL (rows come from scripts/ingest_legal_metadata.py --db)."""
    try:
        from app.db.repositories.content import SqlLegalRepository

        with container.uow_factory() as uow:
            records = SqlLegalRepository(uow.session).load_all()  # type: ignore[attr-defined]
        for r in records:
            container.precedents.add(r)
        return len(records)
    except Exception:
        logger.warning("precedent index could not be loaded")
        return 0


def create_app(container: AppContainer | None = None, *, with_ui: bool = True) -> FastAPI:
    settings = container.settings if container else Settings.load()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        c = container or build_container(settings)
        app.state.container = c
        loop = asyncio.get_running_loop()
        c.ws.bind_loop(loop)
        if isinstance(c.bus, LocalEventBus):
            c.bus.bind_loop(loop)
        stop = threading.Event()

        async def sweeper() -> None:  # drop sockets whose session expired/was revoked (idle expiry, password or role change)
            def valid(h: str) -> bool:
                with c.uow_factory() as uow:
                    return c.auth_for(uow).is_session_active(h)

            async def is_valid(h: str) -> bool:
                return await run_in_threadpool(valid, h)

            while not stop.is_set():
                await asyncio.sleep(30)
                try:
                    await c.ws.sweep(is_valid)
                except Exception:
                    logger.warning("websocket sweep failed")

        sweep_task = asyncio.create_task(sweeper())
        if hasattr(c.bus, "listen"):  # Redis pub/sub bridge: every web process pushes to its own sockets
            threading.Thread(target=c.bus.listen, args=(lambda ev: asyncio.run_coroutine_threadsafe(c.ws.deliver(ev), loop), stop), daemon=True).start()
        n = await run_in_threadpool(_load_precedents, c) if container is None else 0
        if c.index_sync is not None:
            await run_in_threadpool(c.index_sync.refresh)
        logger.info("CivicLens started: %s precedents loaded", n)
        try:
            yield
        finally:
            stop.set()
            sweep_task.cancel()

    app = FastAPI(title="CivicLens", version="0.2.0", lifespan=lifespan, docs_url=None if settings.is_production else "/api/docs", redoc_url=None, openapi_url=None if settings.is_production else "/api/openapi.json")
    middleware.install(app, settings)
    app.include_router(api_router)
    if container is not None:
        app.state.container = container  # available before lifespan for TestClient-less introspection

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        c: AppContainer = websocket.app.state.container
        auth = websocket.headers.get("authorization", "")
        token = auth[7:].strip() if auth[:7].lower() == "bearer " else websocket.cookies.get(SESSION_COOKIE)  # mobile sends a Bearer header

        def authenticate():  # type: ignore[no-untyped-def]
            with c.uow_factory() as uow:
                ctx = c.auth_for(uow).authenticate(token)
                uow.commit()
            return ctx

        origin = websocket.headers.get("origin")
        if origin and origin.split("://", 1)[-1] != websocket.headers.get("host", ""):
            await websocket.close(code=4403)
            return
        try:
            ctx = await run_in_threadpool(authenticate)
        except AuthenticationFailed:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        from app.core.security import hash_token

        conn_id = await c.ws.connect(websocket, ctx, hash_token(token or ""))
        try:
            while True:
                msg = await websocket.receive_text()
                if msg == "ping":  # heartbeat doubles as session re-validation (logout/expiry closes the socket)
                    try:
                        await run_in_threadpool(authenticate)
                    except AuthenticationFailed:
                        await websocket.close(code=4401)
                        return
                    await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            pass
        finally:
            c.ws.disconnect(conn_id)

    if with_ui:
        from app.ui import mount_ui

        mount_ui(app, container if container is not None else _LazyContainer(app), settings)
    return app


class _LazyContainer:
    """UI pages are registered before the lifespan builds the container; resolve attributes on first use."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        c = getattr(self._app.state, "container", None)
        if c is None:
            raise RuntimeError("application container is not ready")
        return getattr(c, name)

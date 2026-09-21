"""Connection registry + authorised fan-out for WebSocket clients."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.authorization import AuthContext
from app.realtime.events import DomainEvent, may_receive, view_for

logger = logging.getLogger("civiclens.realtime")


class Socket(Protocol):
    async def send_json(self, data: Any) -> None: ...


@dataclass
class Connection:
    id: str
    socket: Socket
    ctx: AuthContext
    session_hash: str | None = None


class WebSocketManager:
    """Holds live connections. The auth context is fixed at connect time from the *server-side*
    session; nothing the client later sends can widen its audience."""

    def __init__(self, send_timeout: float = 5.0) -> None:
        self._conns: dict[str, Connection] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._timeout = send_timeout
        self.delivered_total = 0
        self.dropped_total = 0

    def connection_count(self) -> int:
        return len(self._conns)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, socket: Socket, ctx: AuthContext, session_hash: str | None = None) -> str:
        cid = uuid.uuid4().hex
        self._conns[cid] = Connection(cid, socket, ctx, session_hash)
        return cid

    async def _close(self, conn: Connection) -> None:
        self.disconnect(conn.id)
        closer = getattr(conn.socket, "close", None)
        if closer is not None:
            try:
                await asyncio.wait_for(closer(code=4401), timeout=self._timeout)
            except Exception:  # the peer may already be gone
                pass

    async def drop_session(self, session_hash: str) -> int:
        """Close every socket that belongs to a session that has just ended (logout, revocation)."""
        victims = [c for c in list(self._conns.values()) if c.session_hash == session_hash]
        for c in victims:
            await self._close(c)
        return len(victims)

    def drop_session_threadsafe(self, session_hash: str) -> None:
        """For synchronous request handlers (which run in worker threads)."""
        loop = getattr(self, "_loop", None)
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.drop_session(session_hash), loop)

    async def sweep(self, is_valid: Callable[[str], Awaitable[bool]]) -> int:
        """Periodic: drop sockets whose session expired or was revoked (idle expiry, password change, role change...)."""
        dropped = 0
        for conn in list(self._conns.values()):
            if conn.session_hash and not await is_valid(conn.session_hash):
                await self._close(conn)
                dropped += 1
        return dropped

    def disconnect(self, connection_id: str) -> None:
        self._conns.pop(connection_id, None)

    async def deliver(self, event: DomainEvent) -> int:
        """Send to every authorised connection; drop connections that fail. Returns sent count."""
        targets = [c for c in list(self._conns.values()) if may_receive(c.ctx, event)]
        results = await asyncio.gather(*(self._send(c, view_for(c.ctx, event)) for c in targets), return_exceptions=True)
        sent = 0
        for conn, res in zip(targets, results, strict=True):
            if isinstance(res, BaseException):
                self.dropped_total += 1
                self.disconnect(conn.id)
                logger.info("websocket dropped: %s", type(res).__name__)
            else:
                sent += 1
        self.delivered_total += sent
        return sent

    async def _send(self, conn: Connection, body: dict[str, Any]) -> None:
        await asyncio.wait_for(conn.socket.send_json(body), timeout=self._timeout)


class EventBus(Protocol):
    def publish(self, event: DomainEvent) -> None: ...


class LocalEventBus:
    """In-process bus: sync ``publish`` schedules delivery on the running loop.

    Single-process deployments use this directly; multi-process deployments use
    ``RedisEventBus`` (app/workers/redis_backend.py) whose subscriber calls the same manager.
    """

    def __init__(self, manager: WebSocketManager) -> None:
        self._manager = manager
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, event: DomainEvent) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return  # no live UI loop: events are still persisted (notifications/timeline), just not pushed
        asyncio.run_coroutine_threadsafe(self._manager.deliver(event), loop)

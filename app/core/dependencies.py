"""FastAPI dependencies: container access, session authentication, CSRF, permission guards, rate limits."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request

from app.container import AppContainer
from app.core.authorization import (
    AuthContext,
    Permission,
    Role,
    require,
    require_mfa_for_privileged,
)
from app.core.exceptions import PermissionDenied
from app.core.security import hash_token, verify_csrf
from app.core.transactions import run_in_uow  # noqa: F401  (re-exported for routers)

SESSION_COOKIE = "civiclens_session"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def session_token(request: Request) -> tuple[str | None, bool]:
    """(token, via_bearer). Mobile clients send ``Authorization: Bearer <session token>``; browsers use the HttpOnly cookie."""
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip() or None, True
    return request.cookies.get(SESSION_COOKIE), False


def get_ctx(request: Request, container: AppContainer = Depends(get_container)) -> AuthContext:
    """Authenticate the session (cookie or Bearer). Role/department come from the database row.

    CSRF protection applies only to cookie-authenticated state changes: a Bearer token is never attached
    automatically by a browser, so it is not CSRF-able.
    """
    token, via_bearer = session_token(request)
    with container.uow_factory() as uow:
        ctx = container.auth_for(uow).authenticate(token)  # raises AuthenticationFailed
        uow.commit()
    session_hash = hash_token(token or "")
    request.state.session_hash = session_hash
    if request.method in UNSAFE and not via_bearer and not verify_csrf(request.headers.get("x-csrf-token"), session_hash, container.settings.session_secret or container.settings.app_secret_key or "dev-csrf"):
        raise PermissionDenied("Missing or invalid CSRF token.")
    return ctx


def csrf_secret(container: AppContainer) -> str:
    return container.settings.session_secret or container.settings.app_secret_key or "dev-csrf"


def guard(permission: Permission, *, mfa_for_privileged: bool = True) -> Callable[..., AuthContext]:
    """Dependency factory: authenticated + holds ``permission`` (+ second factor for admin roles)."""

    def dep(ctx: AuthContext = Depends(get_ctx)) -> AuthContext:
        require(ctx, permission)
        if mfa_for_privileged:
            require_mfa_for_privileged(ctx)
        return ctx

    return dep


def staff_only(ctx: AuthContext = Depends(get_ctx)) -> AuthContext:
    if ctx.role is Role.CITIZEN:
        raise PermissionDenied("Staff access only.")
    return ctx


def limited(bucket: str) -> Callable[..., None]:
    def dep(request: Request, container: AppContainer = Depends(get_container)) -> None:
        container.limiters[bucket].hit(f"{bucket}:{client_ip(request)}")

    return dep

"""HTTP middleware and exception handlers: correlation ids, security headers, origin check, safe errors."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import Settings
from app.core.exceptions import CivicLensError
from app.core.logging import correlation_id_var

logger = logging.getLogger("civiclens.http")
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Any:
        cid = request.headers.get("x-request-id", "")
        cid = cid if 8 <= len(cid) <= 64 and cid.replace("-", "").isalnum() else uuid.uuid4().hex
        token = correlation_id_var.set(cid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        response.headers["X-Request-ID"] = cid
        logger.info("%s %s -> %s", request.method, request.url.path, response.status_code, extra={"extra_fields": {"duration_ms": round((time.perf_counter() - start) * 1000, 1)}})
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, production: bool) -> None:
        super().__init__(app)
        self._prod = production

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(self), geolocation=(self)")
        if request.url.path.startswith("/api/"):
            h.setdefault("Cache-Control", "no-store")
        if self._prod:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Cookie-authenticated state changes must come from this site: reject cross-origin ``Origin``."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if request.method in UNSAFE and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/").split("://", 1)[-1] != request.headers.get("host", ""):
                return JSONResponse({"error": {"code": "cross_origin", "message": "Cross-origin requests are not allowed."}}, status_code=403)
        return await call_next(request)


def install(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(OriginCheckMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, production=settings.is_production)
    app.add_middleware(CorrelationIdMiddleware)

    @app.exception_handler(CivicLensError)
    async def civiclens_error(request: Request, exc: CivicLensError) -> JSONResponse:
        headers = {"Retry-After": str(getattr(exc, "retry_after_seconds", 0))} if exc.status_code == 429 else None
        return JSONResponse(exc.to_response(correlation_id_var.get()), status_code=exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = {".".join(str(p) for p in e["loc"][1:]) or "body": e["msg"] for e in exc.errors()}
        return JSONResponse({"error": {"code": "validation_failed", "message": "The request is invalid.", "details": fields, "correlation_id": correlation_id_var.get()}}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"error": {"code": "internal_error", "message": "Something went wrong. Please try again.", "correlation_id": correlation_id_var.get()}}, status_code=500)

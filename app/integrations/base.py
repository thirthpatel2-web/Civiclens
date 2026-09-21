"""Government-platform adapter framework with honest runtime states.

Vocabulary (kept strictly separate, never conflated):

* **implemented**  – a class exists (this module);
* ``NOT_CONFIGURED`` – no base URL / credentials / endpoint paths were supplied; the
  adapter makes **no network call** and every operation reports ``NOT_CONFIGURED``;
* ``UNAVAILABLE``    – configured, but the last health check/call failed;
* ``CONNECTED``      – configured and the last health check succeeded;
* operation ``SUCCESS`` – a real call returned a 2xx and a valid body.

No public, documented API contract for CPGRAMS/UMANG/Swachhata/BBMP Sahaaya/MyGov was
supplied, so **no endpoint path or payload shape is assumed**: paths come from
configuration and responses are normalised through a configurable field map.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import urlparse

_EXTERNAL_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
REQUIRED_ENDPOINTS = ("health", "submit", "status")
OPTIONAL_ENDPOINTS = ("update", "reference", "sync")


class IntegrationState(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"
    CONNECTED = "CONNECTED"


class OperationStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


@dataclass(frozen=True)
class AdapterConfig:
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    endpoints: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: float = 10.0
    max_retries: int = 2
    backoff_seconds: float = 0.5
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"
    field_map: Mapping[str, str] = field(default_factory=lambda: {"reference": "reference", "status": "status", "remarks": "remarks", "updated_at": "updated_at"})
    allow_private_hosts: bool = False
    allow_insecure_http: bool = False

    def missing(self) -> list[str]:
        gaps = []
        if not self.base_url:
            gaps.append("base_url")
        if not self.api_key:
            gaps.append("api_key")
        gaps += [f"endpoint:{e}" for e in REQUIRED_ENDPOINTS if not self.endpoints.get(e)]
        return gaps

    @classmethod
    def from_env(cls, prefix: str, env: Mapping[str, str], *, timeout: float = 10.0, retries: int = 2) -> AdapterConfig:
        endpoints = {e: env.get(f"{prefix}_ENDPOINT_{e.upper()}", "").strip() for e in REQUIRED_ENDPOINTS + OPTIONAL_ENDPOINTS}
        return cls(env.get(f"{prefix}_BASE_URL", "").strip().rstrip("/"), env.get(f"{prefix}_API_KEY", "").strip(),
                   {k: v for k, v in endpoints.items() if v}, timeout, retries)  # fmt: skip


@dataclass(frozen=True)
class TransportResponse:
    status: int
    body: Any  # parsed JSON or None
    elapsed_ms: float


class TransportError(Exception):
    """Network-level failure (DNS, refused, timeout, redirect refused, bad body)."""


class Transport(Protocol):
    def request(self, method: str, url: str, headers: Mapping[str, str], body: Any | None, timeout: float) -> TransportResponse: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a: Any, **k: Any) -> None:  # type: ignore[override]
        return None  # a redirect could bounce the request to an internal address (SSRF)


class UrllibTransport:
    """Standard-library HTTP transport: no redirects, JSON only, hard timeout."""

    def request(self, method: str, url: str, headers: Mapping[str, str], body: Any | None, timeout: float) -> TransportResponse:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", "Accept": "application/json", **headers})  # noqa: S310
        opener = urllib.request.build_opener(_NoRedirect)
        start = time.monotonic()
        try:
            with opener.open(req, timeout=timeout) as resp:  # noqa: S310
                raw, status = resp.read(2_000_000), resp.status
        except urllib.error.HTTPError as exc:
            raw, status = exc.read(2_000_000), exc.code
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TransportError(type(exc).__name__) from exc
        elapsed = (time.monotonic() - start) * 1000
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = None
        return TransportResponse(status, parsed, elapsed)


def assert_safe_url(url: str, *, allow_private: bool, allow_http: bool) -> None:
    """SSRF guard: https only (unless allowed), and the host must not resolve to a non-public address."""
    p = urlparse(url)
    if p.scheme not in (("https", "http") if allow_http else ("https",)) or not p.hostname or p.username or p.password:
        raise TransportError("url_not_allowed")
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise TransportError("dns_failure") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise TransportError("non_public_address")


@dataclass(frozen=True)
class NormalizedGrievance:
    external_reference: str | None
    status: str | None
    remarks: str | None
    updated_at: str | None
    raw_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationResult:
    status: OperationStatus
    operation: str
    platform: str
    data: NormalizedGrievance | None = None
    error: str | None = None
    http_status: int | None = None
    attempts: int = 0
    duration_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status is OperationStatus.SUCCESS


@dataclass(frozen=True)
class HealthReport:
    platform: str
    state: IntegrationState
    detail: str
    checked_at: datetime
    last_success_at: datetime | None
    last_error: str | None
    avg_response_ms: float | None
    total_calls: int
    total_failures: int


class GovernmentAdapter(ABC):
    """Base class. Subclasses only declare identity (and may refine payloads/normalisation)."""

    platform: str = ""
    display_name: str = ""

    def __init__(self, config: AdapterConfig, *, transport: Transport | None = None, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], datetime] | None = None, audit: Callable[[str, dict[str, Any]], None] | None = None) -> None:  # fmt: skip
        self.config = config
        self._transport = transport or UrllibTransport()
        self._sleep, self._audit = sleep, audit
        self._clock = clock or (lambda: datetime.now(UTC))
        self._last_success: datetime | None = None
        self._last_error: str | None = None
        self._calls = self._failures = 0
        self._total_ms = 0.0
        self._state = IntegrationState.NOT_CONFIGURED if config.missing() else IntegrationState.UNAVAILABLE

    # ------------------------------------------------------------------ state
    def is_configured(self) -> bool:
        return not self.config.missing()

    @property
    def state(self) -> IntegrationState:
        return self._state

    def health_snapshot(self, detail: str = "") -> HealthReport:
        return HealthReport(self.platform, self._state, detail, self._clock(), self._last_success, self._last_error,
                            (self._total_ms / self._calls) if self._calls else None, self._calls, self._failures)  # fmt: skip

    # ------------------------------------------------------------- operations
    def health_check(self) -> HealthReport:
        if not self.is_configured():
            self._state = IntegrationState.NOT_CONFIGURED
            return self.health_snapshot("Missing configuration: " + ", ".join(self.config.missing()))
        res = self._call("health_check", "GET", "health", None)
        self._state = IntegrationState.CONNECTED if res.ok else IntegrationState.UNAVAILABLE
        return self.health_snapshot("reachable" if res.ok else (res.error or "failed"))

    def submit_grievance(self, payload: Mapping[str, Any], *, idempotency_key: str) -> OperationResult:
        return self._call("submit_grievance", "POST", "submit", self.build_submission(payload), idempotency_key=idempotency_key)

    def get_status(self, external_reference: str) -> OperationResult:
        if not _EXTERNAL_REF.match(external_reference or "") or ".." in external_reference:
            return self._finish(OperationResult(OperationStatus.FAILED, "get_status", self.platform, error="invalid external reference; no request was made."))
        return self._call("get_status", "GET", "status", None, path_suffix=external_reference)

    def update_status(self, external_reference: str, status: str, remarks: str | None = None, *, idempotency_key: str) -> OperationResult:
        return self._call("update_status", "POST", "update", {"reference": external_reference, "status": status, "remarks": remarks}, idempotency_key=idempotency_key)

    def add_reference(self, external_reference: str, our_reference: str, *, idempotency_key: str) -> OperationResult:
        return self._call("add_reference", "POST", "reference", {"reference": external_reference, "civiclens_reference": our_reference}, idempotency_key=idempotency_key)

    def synchronize(self, since: datetime | None = None) -> OperationResult:
        return self._call("synchronize", "GET", "sync", None, query={"since": since.isoformat()} if since else None)

    # -------------------------------------------------------------- overridable
    def build_submission(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """CivicLens canonical grievance -> outbound body. Override once a platform contract is known."""
        return dict(payload)

    def normalize_response(self, raw: Any) -> NormalizedGrievance:
        m = self.config.field_map
        data = raw if isinstance(raw, dict) else {}

        def pick(k: str) -> str | None:
            v = data.get(m.get(k, k))
            return None if v is None else str(v)

        return NormalizedGrievance(pick("reference"), pick("status"), pick("remarks"), pick("updated_at"), tuple(sorted(data)))

    # ---------------------------------------------------------------- internals
    def _call(self, operation: str, method: str, endpoint: str, body: Any | None, *, idempotency_key: str | None = None,
              path_suffix: str | None = None, query: Mapping[str, str] | None = None) -> OperationResult:  # fmt: skip
        if not self.is_configured():
            self._state = IntegrationState.NOT_CONFIGURED
            return self._finish(OperationResult(OperationStatus.NOT_CONFIGURED, operation, self.platform, error="Integration is not configured; no request was made."))
        path = self.config.endpoints.get(endpoint)
        if not path:
            return self._finish(OperationResult(OperationStatus.NOT_CONFIGURED, operation, self.platform, error=f"Endpoint '{endpoint}' is not configured; no request was made."))
        url = self.config.base_url + path + (f"/{urllib.request.quote(path_suffix, safe='')}" if path_suffix else "")
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {self.config.auth_header: f"{self.config.auth_scheme} {self.config.api_key}".strip()}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        attempts, last_err, http_status, total_ms = 0, "", None, 0.0
        for attempt in range(self.config.max_retries + 1):
            attempts = attempt + 1
            try:
                assert_safe_url(url, allow_private=self.config.allow_private_hosts, allow_http=self.config.allow_insecure_http)
                resp = self._transport.request(method, url, headers, body, self.config.timeout_seconds)
            except TransportError as exc:
                last_err, http_status = f"network error: {exc}", None
                if str(exc) in ("url_not_allowed", "non_public_address"):
                    break  # never retry a policy refusal
            else:
                total_ms += resp.elapsed_ms
                http_status = resp.status
                if 200 <= resp.status < 300:
                    if resp.body is None and operation != "health_check":
                        last_err = "invalid or empty response body"
                        break
                    return self._finish(OperationResult(OperationStatus.SUCCESS, operation, self.platform, self.normalize_response(resp.body), None, resp.status, attempts, total_ms), success=True)
                last_err = f"HTTP {resp.status}"
                if not (resp.status == 429 or resp.status >= 500):
                    break  # 4xx (other than 429) will not improve on retry
            if attempt < self.config.max_retries:
                self._sleep(self.config.backoff_seconds * (2**attempt))
        return self._finish(OperationResult(OperationStatus.FAILED, operation, self.platform, None, last_err, http_status, attempts, total_ms))

    def _finish(self, result: OperationResult, *, success: bool = False) -> OperationResult:
        if result.status is not OperationStatus.NOT_CONFIGURED:
            self._calls += 1
            self._total_ms += result.duration_ms
            if success:
                self._last_success, self._last_error = self._clock(), None
            else:
                self._failures += 1
                self._last_error = result.error
        if self._audit:  # never includes payloads, headers or keys
            self._audit("integration.request", {"platform": self.platform, "operation": result.operation, "status": str(result.status), "http_status": result.http_status, "attempts": result.attempts, "duration_ms": round(result.duration_ms, 1)})
        return result


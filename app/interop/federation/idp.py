"""Mock Government Identity Provider - **DEMO / MOCK IDENTITY PROVIDER**, not connected to any
real government identity federation. An OAuth2 client_credentials-style authorization server
(RFC 6749 s4.4) every connector (app.interop.connectors) authenticates against before it's used,
and that a real department's system could authenticate against the same way once one exists.

Opaque bearer tokens, hashed at rest - the same discipline app.core.security.hash_token already
uses for session tokens, so this needs no new crypto dependency (no JWT signing/verification).
``introspect`` deliberately never explains *why* a token is invalid (expired vs revoked vs unknown)
to the caller - that is the actual OAuth2 introspection (RFC 7662) privacy rule, not a shortcut.

issuer / client registration / authorization flow / token issuance / token validation / claims /
role+department mapping (via FederationClient.system) / token expiry / revocation ("logout") /
invalid-token and revoked-token handling are all here and all real - see
tests/unit/test_federation_idp.py and tests/integration/test_connectors.py's federation tests.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import Argon2Hasher, hash_token, new_token
from app.db.models.interop_platform import FederationClient, FederationToken

ISSUER = "CivicLens Government Identity Federation (demo)"
TOKEN_TTL = timedelta(hours=1)

# One registered client per mock connector, seeded on startup (seed_if_empty). Real credentials
# never look like this - a demo secret exists only so the demo connectors can authenticate.
_DEMO_CLIENTS: tuple[tuple[str, str, str], ...] = (
    ("dept_a", "Maharashtra Revenue Records System (demo)", "dept_a-demo-secret-not-for-production"),
    ("dept_b", "Seva Setu Service Application System (demo)", "dept_b-demo-secret-not-for-production"),
    ("dept_c", "Nagrik Grievance Cell (demo)", "dept_c-demo-secret-not-for-production"),
)
DEFAULT_SCOPES = ("interop:read", "interop:write")


def demo_client_secret(connector_id: str) -> str:
    """The seeded demo secret for a connector's federation client - real connectors will not
    have a discoverable secret like this; used by the demo connectors and by tests only."""
    return f"{connector_id}-demo-secret-not-for-production"


@dataclass(frozen=True)
class FederationClaims:
    client_id: str
    system: str
    scope: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime


class InvalidClient(Exception):
    """Unknown client_id, disabled client, or wrong client_secret."""


class InvalidToken(Exception):
    """Unknown, expired, revoked token, or a token whose issuing client is no longer enabled."""


def register_client(session: Session, *, client_id: str, name: str, system: str, client_secret: str, scopes: list[str], clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> FederationClient:
    client = FederationClient(client_id=client_id, name=name, client_secret_hash=Argon2Hasher().hash(client_secret), system=system, allowed_scopes=list(scopes), enabled=True, created_at=clock())
    session.add(client)
    return client


def seed_if_empty(session: Session) -> bool:
    if session.execute(select(FederationClient).limit(1)).first() is not None:
        return False
    for connector_id, name, secret in _DEMO_CLIENTS:
        register_client(session, client_id=connector_id, name=name, system=connector_id, client_secret=secret, scopes=list(DEFAULT_SCOPES))
    return True


def issue_token(session: Session, *, client_id: str, client_secret: str, scope: list[str] | None = None, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> tuple[str, FederationClaims]:
    """The client_credentials grant. Returns (raw_token, claims) - the raw token is shown ONCE,
    same discipline as every other bearer credential in this codebase; only its hash is stored."""
    client = session.get(FederationClient, client_id)
    if client is None or not client.enabled or not Argon2Hasher().verify(client.client_secret_hash, client_secret):
        raise InvalidClient("Unknown client, disabled client, or wrong secret.")
    requested = scope if scope is not None else client.allowed_scopes
    granted = [s for s in requested if s in client.allowed_scopes]
    now = clock()
    raw = new_token()
    expires_at = now + TOKEN_TTL
    session.add(FederationToken(token_id=str(uuid.uuid4()), token_hash=hash_token(raw), client_id=client_id, scope=granted, issued_at=now, expires_at=expires_at))
    return raw, FederationClaims(client_id=client_id, system=client.system, scope=tuple(granted), issued_at=now, expires_at=expires_at)


def validate_token(session: Session, raw_token: str, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> FederationClaims:
    row = session.execute(select(FederationToken).where(FederationToken.token_hash == hash_token(raw_token))).scalars().first()
    if row is None:
        raise InvalidToken("Token not recognized.")
    if row.revoked_at is not None:
        raise InvalidToken("Token has been revoked.")
    if row.expires_at <= clock():
        raise InvalidToken("Token has expired.")
    client = session.get(FederationClient, row.client_id)
    if client is None or not client.enabled:
        raise InvalidToken("Issuing client is no longer enabled.")
    return FederationClaims(client_id=row.client_id, system=client.system, scope=tuple(row.scope), issued_at=row.issued_at, expires_at=row.expires_at)


def introspect(session: Session, raw_token: str, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> dict:
    """RFC 7662-shaped: {"active": false} for anything invalid - the standard's own rule is to
    never tell the caller *why* a token failed (expired vs revoked vs unknown are indistinguishable
    from the outside), so this never lets an InvalidToken's message leak through."""
    try:
        claims = validate_token(session, raw_token, clock=clock)
    except InvalidToken:
        return {"active": False}
    return {"active": True, "client_id": claims.client_id, "system": claims.system, "scope": list(claims.scope), "iss": ISSUER, "exp": int(claims.expires_at.timestamp())}


def revoke_token(session: Session, raw_token: str, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> bool:
    """"Logout" for a federated client - once revoked, validate_token/introspect never accept this
    token again, even if it hasn't expired yet."""
    row = session.execute(select(FederationToken).where(FederationToken.token_hash == hash_token(raw_token))).scalars().first()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = clock()
    session.add(row)
    return True

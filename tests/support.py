"""Test doubles. EVERYTHING in this module exists only for automated tests.

* ``ScryptTestHasher``  – stand-in for Argon2 so auth logic is testable where
  ``argon2-cffi`` is not installed. NOT used by the application.
* ``ReferenceTotp``     – an RFC 6238 implementation from the standard library,
  itself verified against the RFC's published vectors in test_mfa.py.
* ``Memory*`` classes   – in-memory repositories implementing the service Protocols.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from app.core.authorization import Role
from app.core.security import SessionRecord
from app.services.audit_service import AuditEvent
from app.services.auth_service import ResetTokenRecord, UserRecord
from app.services.mfa_service import MfaRecord


class ScryptTestHasher:
    """TEST DOUBLE for Argon2 (same interface)."""

    def __init__(self) -> None:
        self.rehash_calls = 0
        self.force_rehash = False

    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=2**10, r=8, p=1)
        return "scrypt-test$" + salt.hex() + "$" + digest.hex()

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            _, salt_hex, digest_hex = password_hash.split("$")
        except ValueError:
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**10, r=8, p=1)
        return hmac.compare_digest(digest.hex(), digest_hex)

    def needs_rehash(self, password_hash: str) -> bool:
        if self.force_rehash:
            self.rehash_calls += 1
        return self.force_rehash


def hotp(secret: bytes, counter: int, digits: int = 6) -> str:
    mac = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


class ReferenceTotp:
    """RFC 6238 (SHA-1, 30 s, 6 digits) — implements the TotpEngine protocol."""

    def random_secret(self) -> str:
        return base64.b32encode(secrets.token_bytes(20)).decode()

    def provisioning_uri(self, secret: str, account_name: str, issuer: str) -> str:
        label = quote(f"{issuer}:{account_name}")
        return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"

    @staticmethod
    def code_at(secret: str, at: float, digits: int = 6) -> str:
        return hotp(base64.b32decode(secret), int(at // 30), digits)

    def match(self, secret: str, code: str, *, at: float | None = None, window: int = 1) -> int | None:
        assert at is not None
        step = int(at // 30)
        for off in range(-window, window + 1):
            if hmac.compare_digest(hotp(base64.b32decode(secret), step + off), code):
                return step + off
        return None


class MemoryAuditRepo:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def add(self, event: AuditEvent) -> None:
        self.events.append(event)

    def actions(self) -> list[str]:
        return [e.action for e in self.events]


class MemoryMfaRepo:
    def __init__(self) -> None:
        self.rows: dict[str, MfaRecord] = {}

    def get(self, user_id: str) -> MfaRecord | None:
        return self.rows.get(user_id)

    def save(self, record: MfaRecord) -> None:
        self.rows[record.user_id] = record

    def delete(self, user_id: str) -> None:
        self.rows.pop(user_id, None)


class MemoryUserRepo:
    def __init__(self) -> None:
        self.rows: dict[str, UserRecord] = {}

    def get_by_id(self, user_id: str) -> UserRecord | None:
        return self.rows.get(user_id)

    def get_by_email(self, email: str) -> UserRecord | None:
        return next((u for u in self.rows.values() if u.email == email), None)

    def add(self, user: UserRecord) -> None:
        self.rows[user.id] = user

    def update(self, user: UserRecord) -> None:
        self.rows[user.id] = user

    def count_with_role(self, role: Role) -> int:
        return sum(1 for u in self.rows.values() if u.role is role)


class MemorySessionRepo:
    def __init__(self) -> None:
        self.rows: dict[str, SessionRecord] = {}

    def add(self, session: SessionRecord) -> None:
        self.rows[session.token_hash] = session

    def get_by_token_hash(self, token_hash: str) -> SessionRecord | None:
        return self.rows.get(token_hash)

    def update(self, session: SessionRecord) -> None:
        self.rows[session.token_hash] = session

    def revoke_all_for_user(self, user_id: str, at: datetime) -> None:
        for s in self.rows.values():
            if s.user_id == user_id and s.revoked_at is None:
                s.revoked_at = at


class MemoryResetRepo:
    def __init__(self) -> None:
        self.rows: dict[str, ResetTokenRecord] = {}

    def add(self, record: ResetTokenRecord) -> None:
        self.rows[record.token_hash] = record

    def get(self, token_hash: str) -> ResetTokenRecord | None:
        return self.rows.get(token_hash)

    def mark_used(self, token_hash: str, at: datetime) -> None:
        r = self.rows[token_hash]
        self.rows[token_hash] = ResetTokenRecord(r.token_hash, r.user_id, r.expires_at, at)


class FakeClock:
    """Controllable clock usable as both datetime and epoch-seconds source."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def epoch(self) -> float:
        return self.now.timestamp()

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)

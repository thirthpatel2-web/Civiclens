"""Security primitives: password hashing, secret encryption, session tokens, CSRF.

Nothing here touches a database or web framework, so each piece is unit-testable.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.exceptions import ValidationFailed

# --------------------------------------------------------------------------- passwords

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128
_COMMON_PASSWORDS = frozenset(
    {
        "password", "password1", "password123", "1234567890", "qwertyuiop", "iloveyou12",
        "letmein123", "admin12345", "welcome123", "civiclens123",
    }
)  # fmt: skip


def validate_password_policy(password: str, *, email: str | None = None) -> None:
    """Length-based policy (NIST 800-63B style): no arbitrary composition rules."""
    problems: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        problems.append(f"must be at most {MAX_PASSWORD_LENGTH} characters")
    if password.lower() in _COMMON_PASSWORDS:
        problems.append("is too common")
    if email and password.lower() == email.strip().lower():
        problems.append("must not equal the e-mail address")
    if password.strip() != password or not password.strip():
        problems.append("must not start/end with whitespace or be blank")
    if problems:
        raise ValidationFailed("Password " + ", ".join(problems) + ".", details={"field": "password"})


class PasswordHasher(Protocol):
    """Contract used by AuthService; ``Argon2Hasher`` is the production implementation."""

    def hash(self, password: str) -> str: ...
    def verify(self, password_hash: str, password: str) -> bool: ...
    def needs_rehash(self, password_hash: str) -> bool: ...


class Argon2Hasher:
    """Argon2id via ``argon2-cffi`` (imported lazily so the package imports without it)."""

    def __init__(self) -> None:
        from argon2 import PasswordHasher as _Argon2

        self._ph = _Argon2()

    def hash(self, password: str) -> str:
        return self._ph.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

        try:
            return bool(self._ph.verify(password_hash, password))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return bool(self._ph.check_needs_rehash(password_hash))


# --------------------------------------------------------------------------- encryption


class SecretBox:
    """Authenticated encryption for values stored at rest (e.g. TOTP secrets).

    The Fernet key is derived from the application secret with HKDF-SHA256, so
    the raw application secret is never used directly as a cipher key.
    Passing previous secrets enables key rotation (decrypt old, encrypt new).
    """

    _INFO = b"civiclens/secretbox/v1"

    def __init__(self, secret: str, *previous_secrets: str) -> None:
        if len(secret) < 16:
            raise ValueError("SecretBox secret must be at least 16 characters")
        keys = [self._derive(s) for s in (secret, *previous_secrets)]
        self._fernet = MultiFernet([Fernet(k) for k in keys])

    @classmethod
    def _derive(cls, secret: str) -> bytes:
        raw = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=cls._INFO).derive(
            secret.encode("utf-8")
        )
        return base64.urlsafe_b64encode(raw)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("stored secret could not be decrypted (wrong key or tampered)") from exc


# --------------------------------------------------------------------------- sessions


def new_token(nbytes: int = 32) -> str:
    """Cryptographically random URL-safe token (256 bits by default)."""
    return secrets.token_urlsafe(nbytes)


def hash_token(raw_token: str) -> str:
    """SHA-256 of a high-entropy token. Only the hash is persisted server-side."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@dataclass(frozen=True)
class SessionPolicy:
    """Idle and absolute lifetime limits."""

    idle: timedelta = timedelta(minutes=30)
    absolute: timedelta = timedelta(hours=12)


MOBILE_SESSION_POLICY = SessionPolicy(idle=timedelta(days=14), absolute=timedelta(days=60))  # phones stay signed in; still revocable server-side


@dataclass
class SessionRecord:
    """Server-side session row. Role is NOT stored here: it is read from the user row."""

    id: str
    user_id: str
    token_hash: str
    created_at: datetime
    last_seen_at: datetime
    mfa_verified: bool = False
    revoked_at: datetime | None = None
    kind: str = "web"  # web | mobile

    def is_active(self, now: datetime, policy: SessionPolicy) -> bool:
        if self.revoked_at is not None:
            return False
        if now - self.created_at > policy.absolute:
            return False
        return now - self.last_seen_at <= policy.idle


# --------------------------------------------------------------------------- CSRF


def csrf_token_for(session_token_hash: str, secret: str) -> str:
    """Per-session CSRF token: HMAC(secret, session-hash). Stateless to verify."""
    return hmac.new(secret.encode("utf-8"), session_token_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_csrf(candidate: str | None, session_token_hash: str, secret: str) -> bool:
    if not candidate:
        return False
    return constant_time_equals(candidate, csrf_token_for(session_token_hash, secret))

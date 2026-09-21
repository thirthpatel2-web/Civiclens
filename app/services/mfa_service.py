"""TOTP two-factor authentication (RFC 6238, Google Authenticator compatible).

Fixes over the original scripts this replaces:
* secrets are persisted **encrypted at rest**, not held in process memory;
* codes cannot be replayed (the last accepted time-step is stored);
* ``valid_window`` is an int (the reference script passed ``0.5``, which raises);
* single-use hashed backup codes exist for lost devices;
* disabling 2FA requires a valid code *and* fresh password re-authentication.
"""

from __future__ import annotations

import hmac
import io
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from app.core.exceptions import AuthenticationFailed, Conflict, NotFound, ValidationFailed
from app.core.rate_limit import FailureThrottle
from app.core.security import SecretBox, hash_token
from app.services.audit_service import AuditService

TOTP_INTERVAL = 30
BACKUP_CODE_COUNT = 8
_CODE_RE = re.compile(r"^\d{6}$")
_BACKUP_RE = re.compile(r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")
_BACKUP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class TotpEngine(Protocol):
    def random_secret(self) -> str: ...
    def provisioning_uri(self, secret: str, account_name: str, issuer: str) -> str: ...
    def match(self, secret: str, code: str, *, at: float | None = None, window: int = 1) -> int | None:
        """Return the matching time-step counter, or ``None`` if the code is invalid."""
        ...


class PyOtpEngine:
    """Production engine backed by ``pyotp`` (imported lazily)."""

    def __init__(self) -> None:
        import pyotp

        self._pyotp = pyotp

    def random_secret(self) -> str:
        return str(self._pyotp.random_base32())

    def provisioning_uri(self, secret: str, account_name: str, issuer: str) -> str:
        return str(self._pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=issuer))

    def match(self, secret: str, code: str, *, at: float | None = None, window: int = 1) -> int | None:
        now = time.time() if at is None else at
        totp = self._pyotp.TOTP(secret, interval=TOTP_INTERVAL)
        for offset in range(-window, window + 1):
            if hmac.compare_digest(str(totp.at(now, offset)), code):
                return int(now // TOTP_INTERVAL) + offset
        return None


def render_qr_png(uri: str) -> bytes:
    """Render a provisioning URI as PNG bytes (requires ``qrcode[pil]``)."""
    import qrcode

    buffer = io.BytesIO()
    qrcode.make(uri).save(buffer, format="PNG")
    return buffer.getvalue()


@dataclass
class MfaRecord:
    user_id: str
    secret_encrypted: str
    enabled: bool = False
    last_used_step: int = -1
    backup_code_hashes: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    confirmed_at: datetime | None = None


class MfaRepository(Protocol):
    def get(self, user_id: str) -> MfaRecord | None: ...
    def save(self, record: MfaRecord) -> None: ...
    def delete(self, user_id: str) -> None: ...


@dataclass(frozen=True)
class Enrollment:
    provisioning_uri: str
    manual_entry_secret: str  # shown once for manual entry; never logged


class MFAService:
    def __init__(
        self,
        repo: MfaRepository,
        box: SecretBox,
        engine: TotpEngine,
        audit: AuditService,
        *,
        issuer: str = "CivicLens",
        throttle: FailureThrottle | None = None,
        clock: Callable[[], float] = time.time,
        window: int = 1,
    ) -> None:
        if not isinstance(window, int) or window < 0:
            raise ValueError("window must be a non-negative int")
        self._repo, self._box, self._engine, self._audit = repo, box, engine, audit
        self._issuer, self._throttle, self._clock, self._window = issuer, throttle, clock, window

    # ------------------------------------------------------------------ queries
    def is_enabled(self, user_id: str) -> bool:
        record = self._repo.get(user_id)
        return bool(record and record.enabled)

    # --------------------------------------------------------------- enrollment
    def begin_enrollment(self, user_id: str, account_name: str) -> Enrollment:
        existing = self._repo.get(user_id)
        if existing and existing.enabled:
            raise Conflict("Two-factor authentication is already enabled.")
        secret = self._engine.random_secret()
        self._repo.save(MfaRecord(user_id=user_id, secret_encrypted=self._box.encrypt(secret)))
        self._audit.record("mfa.enrollment_started", actor_id=user_id, resource_type="user", resource_id=user_id)
        return Enrollment(self._engine.provisioning_uri(secret, account_name, self._issuer), secret)

    def confirm_enrollment(self, user_id: str, code: str) -> list[str]:
        """Verify the first code from the authenticator app; returns backup codes (shown once)."""
        record = self._repo.get(user_id)
        if record is None:
            raise NotFound("No pending two-factor enrollment.")
        if record.enabled:
            raise Conflict("Two-factor authentication is already enabled.")
        step = self._match(record, code)
        if step is None:
            self._audit.record("mfa.enrollment_failed", actor_id=user_id)
            raise AuthenticationFailed("The verification code is incorrect or expired.")
        backup = self._new_backup_codes()
        record.enabled = True
        record.last_used_step = step
        record.confirmed_at = datetime.fromtimestamp(self._clock(), UTC)
        record.backup_code_hashes = [hash_token(c) for c in backup]
        self._repo.save(record)
        self._audit.record("mfa.enabled", actor_id=user_id, resource_type="user", resource_id=user_id)
        return backup

    # ------------------------------------------------------------- verification
    def verify_login(self, user_id: str, code: str) -> bool:
        """Verify a TOTP code (or a single-use backup code). Replays are rejected."""
        record = self._repo.get(user_id)
        if record is None or not record.enabled:
            return False
        key = f"mfa:{user_id}"
        if self._throttle:
            self._throttle.check(key)
        code = (code or "").strip()
        if "-" in code:
            code = code.upper()  # backup codes are case-insensitive
        ok = False
        if _CODE_RE.match(code):
            step = self._match(record, code)
            if step is not None and step > record.last_used_step:
                record.last_used_step = step
                self._repo.save(record)
                ok = True
        elif _BACKUP_RE.match(code):
            digest = hash_token(code)
            if digest in record.backup_code_hashes:
                record.backup_code_hashes.remove(digest)
                self._repo.save(record)
                ok = True
                self._audit.record("mfa.backup_code_used", actor_id=user_id)
        if self._throttle:
            (self._throttle.record_success if ok else self._throttle.record_failure)(key)
        self._audit.record("mfa.verified" if ok else "mfa.verification_failed", actor_id=user_id)
        return ok

    def disable(self, user_id: str, code: str, *, reauthenticated: bool) -> None:
        """Turn 2FA off. Caller must have just re-verified the password."""
        if not reauthenticated:
            raise AuthenticationFailed("Password re-authentication is required.")
        if not self.verify_login(user_id, code):
            raise AuthenticationFailed("The verification code is incorrect or expired.")
        self._repo.delete(user_id)
        self._audit.record("mfa.disabled", actor_id=user_id, resource_type="user", resource_id=user_id)

    # ------------------------------------------------------------------ helpers
    def _match(self, record: MfaRecord, code: str) -> int | None:
        if not _CODE_RE.match((code or "").strip()):
            raise ValidationFailed("Enter the 6-digit code.", details={"field": "otp"})
        secret = self._box.decrypt(record.secret_encrypted)
        return self._engine.match(secret, code.strip(), at=self._clock(), window=self._window)

    @staticmethod
    def _new_backup_codes() -> list[str]:
        def one() -> str:
            raw = "".join(secrets.choice(_BACKUP_ALPHABET) for _ in range(8))
            return f"{raw[:4]}-{raw[4:]}"

        return [one() for _ in range(BACKUP_CODE_COUNT)]

"""Authentication, sessions, password reset and first-admin bootstrap.

Design rules enforced here (each has a test):
* self-registration can only ever create a CITIZEN — there is no role parameter;
* the role used for authorization always comes from the stored user row;
* login failures are throttled and use one generic message (no user enumeration);
* an MFA-enabled account cannot obtain a session without a valid OTP;
* logout, password change and password reset revoke server-side sessions;
* the first admin can only be created once, with an out-of-band setup token.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.core.authorization import AuthContext, Role, can_assign_role, is_privileged_role
from app.core.exceptions import (
    AuthenticationFailed,
    Conflict,
    MfaRequired,
    NotFound,
    PermissionDenied,
    ValidationFailed,
)
from app.core.rate_limit import FailureThrottle
from app.core.security import (
    MOBILE_SESSION_POLICY,
    PasswordHasher,
    SessionPolicy,
    SessionRecord,
    constant_time_equals,
    hash_token,
    new_token,
    validate_password_policy,
)
from app.services.audit_service import AuditService
from app.services.mfa_service import MFAService

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
RESET_TOKEN_TTL = timedelta(hours=1)
_GENERIC_LOGIN_ERROR = "Invalid e-mail, password or verification code."


@dataclass(frozen=True)
class UserRecord:
    id: str
    email: str
    password_hash: str
    full_name: str
    role: Role = Role.CITIZEN
    department_id: str | None = None
    is_active: bool = True


@dataclass(frozen=True)
class ResetTokenRecord:
    token_hash: str
    user_id: str
    expires_at: datetime
    used_at: datetime | None = None


class UserRepository(Protocol):
    def get_by_id(self, user_id: str) -> UserRecord | None: ...
    def get_by_email(self, email: str) -> UserRecord | None: ...
    def add(self, user: UserRecord) -> None: ...
    def update(self, user: UserRecord) -> None: ...
    def count_with_role(self, role: Role) -> int: ...
    def list(self, *, role: Role | None = None, limit: int = 100, offset: int = 0) -> list[UserRecord]: ...


class SessionRepository(Protocol):
    def add(self, session: SessionRecord) -> None: ...
    def get_by_token_hash(self, token_hash: str) -> SessionRecord | None: ...
    def update(self, session: SessionRecord) -> None: ...
    def revoke_all_for_user(self, user_id: str, at: datetime) -> None: ...


class ResetTokenRepository(Protocol):
    def add(self, record: ResetTokenRecord) -> None: ...
    def get(self, token_hash: str) -> ResetTokenRecord | None: ...
    def mark_used(self, token_hash: str, at: datetime) -> None: ...


@dataclass(frozen=True)
class LoginResult:
    session_token: str  # raw token: set as an HttpOnly cookie, never stored or logged
    context: AuthContext


def normalize_email(email: str) -> str:
    value = (email or "").strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValidationFailed("Enter a valid e-mail address.", details={"field": "email"})
    return value


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        sessions: SessionRepository,
        resets: ResetTokenRepository,
        hasher: PasswordHasher,
        mfa: MFAService,
        audit: AuditService,
        *,
        throttle: FailureThrottle | None = None,
        policy: SessionPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._users, self._sessions, self._resets = users, sessions, resets
        self._hasher, self._mfa, self._audit = hasher, mfa, audit
        self._throttle = throttle or FailureThrottle()
        self._policy = policy or SessionPolicy()
        self._clock = clock or (lambda: datetime.now(UTC))
        # Verified against when the account does not exist, to equalise timing.
        self._timing_hash = hasher.hash("civiclens-timing-equaliser")

    # ------------------------------------------------------------- registration
    def register(self, email: str, password: str, full_name: str) -> UserRecord:
        """Create a CITIZEN account. Deliberately has no role argument."""
        email = normalize_email(email)
        full_name = (full_name or "").strip()
        if not 2 <= len(full_name) <= 120:
            raise ValidationFailed("Enter your full name.", details={"field": "full_name"})
        validate_password_policy(password, email=email)
        if self._users.get_by_email(email):
            raise Conflict("An account with this e-mail already exists.")
        user = UserRecord(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=self._hasher.hash(password),
            full_name=full_name,
        )
        self._users.add(user)
        self._audit.record("auth.registered", actor_id=user.id, resource_type="user", resource_id=user.id)
        return user

    def bootstrap_first_admin(
        self, email: str, password: str, full_name: str, *, provided_token: str, expected_token: str
    ) -> UserRecord:
        """One-time creation of the first SUPER_ADMIN, guarded by an out-of-band token."""
        if not expected_token or not constant_time_equals(provided_token or "", expected_token):
            self._audit.record("admin.bootstrap_denied", actor_id=None)
            raise PermissionDenied("Invalid setup token.")
        if self._users.count_with_role(Role.SUPER_ADMIN) > 0:
            raise Conflict("Initial administrator setup has already been completed.")
        email = normalize_email(email)
        validate_password_policy(password, email=email)
        if self._users.get_by_email(email):
            raise Conflict("An account with this e-mail already exists.")
        user = UserRecord(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=self._hasher.hash(password),
            full_name=full_name.strip(),
            role=Role.SUPER_ADMIN,
        )
        self._users.add(user)
        self._audit.record("admin.bootstrapped", actor_id=user.id, resource_type="user", resource_id=user.id)
        return user

    def is_session_active(self, token_hash: str) -> bool:
        """Read-only validity check (used to drop WebSocket connections whose session ended). Does not touch last_seen."""
        session = self._sessions.get_by_token_hash(token_hash)
        if session is None or session.revoked_at is not None:
            return False
        user = self._users.get_by_id(session.user_id)
        policy = MOBILE_SESSION_POLICY if session.kind == "mobile" else self._policy
        return bool(user and user.is_active and session.is_active(self._clock(), policy))

    def issue_reset_for_user(self, user_id: str) -> str:
        """Admin-assisted reset: mint a one-time token for a user (delivered out-of-band by the admin). Returned once, never stored raw."""
        user = self._users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise NotFound("User not found.")
        return self._new_reset_token(user, by_admin=True)

    def verify_password(self, user_id: str, password: str) -> bool:
        """Re-authentication check (e.g. before disabling 2FA)."""
        user = self._users.get_by_id(user_id)
        return bool(user and user.is_active and self._hasher.verify(user.password_hash, password or ""))

    def mark_session_mfa_verified(self, raw_token: str | None) -> None:
        """After a successful enrolment/step-up the *current* session counts as second-factor verified."""
        session = self._sessions.get_by_token_hash(hash_token(raw_token or ""))
        if session and session.revoked_at is None:
            session.mfa_verified = True
            self._sessions.update(session)

    # --------------------------------------------------------------- staff admin
    def create_staff(self, actor: AuthContext, email: str, password: str, full_name: str, role: Role, department_id: str | None) -> UserRecord:
        """Create an officer/admin. Only via an authorised actor; never through self-registration."""
        if role is Role.CITIZEN or not can_assign_role(actor, target_user_id="(new)", new_role=role):
            self._audit.record("admin.create_staff_denied", actor_id=actor.user_id, metadata={"role": str(role)})
            raise PermissionDenied("You may not create an account with this role.")
        if role is Role.OFFICER and not department_id:
            raise ValidationFailed("Officers must belong to a department.", details={"field": "department_id"})
        email = normalize_email(email)
        validate_password_policy(password, email=email)
        if self._users.get_by_email(email):
            raise Conflict("An account with this e-mail already exists.")
        user = UserRecord(str(uuid.uuid4()), email, self._hasher.hash(password), (full_name or "").strip(), role, department_id if role is not Role.SUPER_ADMIN else None)
        self._users.add(user)
        self._audit.record("admin.staff_created", actor_id=actor.user_id, resource_type="user", resource_id=user.id, metadata={"role": str(role), "department": department_id})
        return user

    def change_role(self, actor: AuthContext, user_id: str, role: Role, department_id: str | None) -> UserRecord:
        if not can_assign_role(actor, target_user_id=user_id, new_role=role):
            self._audit.record("admin.role_change_denied", actor_id=actor.user_id, resource_id=user_id, metadata={"role": str(role)})
            raise PermissionDenied("You may not assign this role.")
        user = self._users.get_by_id(user_id)
        if user is None:
            raise ValidationFailed("Unknown user.")
        if is_privileged_role(user.role) and actor.role is not Role.SUPER_ADMIN:
            raise PermissionDenied("Only a super-admin may change a privileged account.")
        if role is Role.OFFICER and not department_id:
            raise ValidationFailed("Officers must belong to a department.", details={"field": "department_id"})
        updated = replace(user, role=role, department_id=department_id if role in (Role.OFFICER, Role.ADMIN) else None)
        self._users.update(updated)
        self._sessions.revoke_all_for_user(user_id, self._clock())  # new privileges require a fresh sign-in
        self._audit.record("admin.role_changed", actor_id=actor.user_id, resource_type="user", resource_id=user_id, metadata={"from": str(user.role), "to": str(role)})
        return updated

    def set_active(self, actor: AuthContext, user_id: str, active: bool) -> UserRecord:
        user = self._users.get_by_id(user_id)
        if user is None or user_id == actor.user_id:
            raise ValidationFailed("Cannot change this account.")
        if is_privileged_role(user.role) and actor.role is not Role.SUPER_ADMIN:
            raise PermissionDenied("Only a super-admin may change a privileged account.")
        updated = replace(user, is_active=active)
        self._users.update(updated)
        if not active:
            self._sessions.revoke_all_for_user(user_id, self._clock())
        self._audit.record("admin.user_active_changed", actor_id=actor.user_id, resource_type="user", resource_id=user_id, metadata={"active": active})
        return updated

    # -------------------------------------------------------------------- login
    def login(self, email: str, password: str, *, otp: str | None = None, client_key: str = "", client: str = "web") -> LoginResult:
        try:
            email_n = normalize_email(email)
        except ValidationFailed:
            raise AuthenticationFailed(_GENERIC_LOGIN_ERROR) from None
        keys = [f"login:{email_n}"] + ([f"ip:{client_key}"] if client_key else [])
        for k in keys:
            self._throttle.check(k)

        user = self._users.get_by_email(email_n)
        stored = user.password_hash if user else self._timing_hash
        password_ok = self._hasher.verify(stored, password or "")
        if not (user and user.is_active and password_ok):
            self._fail(keys, email_n, "bad_credentials")
            raise AuthenticationFailed(_GENERIC_LOGIN_ERROR)

        mfa_verified = False
        if self._mfa.is_enabled(user.id):
            if not otp:
                raise MfaRequired("Enter the 6-digit code from your authenticator app.")
            if not self._mfa.verify_login(user.id, otp):
                self._fail(keys, email_n, "bad_otp")
                raise AuthenticationFailed(_GENERIC_LOGIN_ERROR)
            mfa_verified = True

        for k in keys:
            self._throttle.record_success(k)
        if self._hasher.needs_rehash(user.password_hash):
            user = replace(user, password_hash=self._hasher.hash(password))
            self._users.update(user)

        raw = new_token()
        now = self._clock()
        self._sessions.add(
            SessionRecord(
                id=str(uuid.uuid4()),
                user_id=user.id,
                token_hash=hash_token(raw),
                created_at=now,
                last_seen_at=now,
                mfa_verified=mfa_verified,
                kind="mobile" if client == "mobile" else "web",
            )
        )
        self._audit.record("auth.login", actor_id=user.id, metadata={"mfa": mfa_verified, "client": client})
        return LoginResult(raw, AuthContext(user.id, user.role, user.department_id, mfa_verified))

    def _fail(self, keys: list[str], email: str, reason: str) -> None:
        for k in keys:
            self._throttle.record_failure(k)
        self._audit.record("auth.login_failed", actor_id=None, metadata={"email": email, "reason": reason})

    # ------------------------------------------------------------------ session
    def authenticate(self, raw_token: str | None) -> AuthContext:
        """Resolve a session cookie to an AuthContext; role comes from the DB row."""
        if not raw_token:
            raise AuthenticationFailed("Not signed in.")
        session = self._sessions.get_by_token_hash(hash_token(raw_token))
        now = self._clock()
        policy = MOBILE_SESSION_POLICY if session is not None and session.kind == "mobile" else self._policy
        if session is None or not session.is_active(now, policy):
            raise AuthenticationFailed("Your session has expired. Please sign in again.")
        user = self._users.get_by_id(session.user_id)
        if user is None or not user.is_active:
            raise AuthenticationFailed("Your session has expired. Please sign in again.")
        session.last_seen_at = now
        self._sessions.update(session)
        return AuthContext(user.id, user.role, user.department_id, session.mfa_verified)

    def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        session = self._sessions.get_by_token_hash(hash_token(raw_token))
        if session and session.revoked_at is None:
            session.revoked_at = self._clock()
            self._sessions.update(session)
            self._audit.record("auth.logout", actor_id=session.user_id)

    # ---------------------------------------------------------------- passwords
    def change_password(self, ctx: AuthContext, current_password: str, new_password: str) -> None:
        user = self._users.get_by_id(ctx.user_id)
        if user is None or not self._hasher.verify(user.password_hash, current_password or ""):
            self._audit.record("auth.password_change_failed", actor_id=ctx.user_id)
            raise AuthenticationFailed("Current password is incorrect.")
        validate_password_policy(new_password, email=user.email)
        self._users.update(replace(user, password_hash=self._hasher.hash(new_password)))
        self._sessions.revoke_all_for_user(user.id, self._clock())
        self._audit.record("auth.password_changed", actor_id=user.id)

    def request_password_reset(self, email: str) -> str | None:
        """Returns a raw reset token for the mail sender, or ``None``.

        Callers must show the same neutral message either way (no enumeration).
        """
        try:
            user = self._users.get_by_email(normalize_email(email))
        except ValidationFailed:
            return None
        if user is None or not user.is_active:
            return None
        return self._new_reset_token(user)

    def _new_reset_token(self, user: UserRecord, *, by_admin: bool = False) -> str:
        raw = new_token()
        self._resets.add(ResetTokenRecord(hash_token(raw), user.id, self._clock() + RESET_TOKEN_TTL))
        self._audit.record("auth.password_reset_issued" if by_admin else "auth.password_reset_requested", actor_id=None if by_admin else user.id, resource_type="user", resource_id=user.id)
        return raw

    def reset_password(self, raw_token: str, new_password: str) -> None:
        record = self._resets.get(hash_token(raw_token or ""))
        now = self._clock()
        if record is None or record.used_at is not None or record.expires_at < now:
            raise AuthenticationFailed("This reset link is invalid or has expired.")
        user = self._users.get_by_id(record.user_id)
        if user is None:
            raise AuthenticationFailed("This reset link is invalid or has expired.")
        validate_password_policy(new_password, email=user.email)
        self._users.update(replace(user, password_hash=self._hasher.hash(new_password)))
        self._resets.mark_used(record.token_hash, now)
        self._sessions.revoke_all_for_user(user.id, now)
        self._audit.record("auth.password_reset", actor_id=user.id)

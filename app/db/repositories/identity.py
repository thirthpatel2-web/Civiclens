from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.authorization import Role
from app.core.security import SessionRecord
from app.db.models.identity import (
    ConsentModel,
    MfaConfigModel,
    NotificationPreferenceModel,
    PasswordResetTokenModel,
    ProfileModel,
    SessionModel,
    UserModel,
)
from app.services.auth_service import ResetTokenRecord, UserRecord
from app.services.mfa_service import MfaRecord
from app.services.ports import ConsentRecord, NotificationPreference, ProfileRecord


def _user(m: UserModel) -> UserRecord:
    return UserRecord(m.id, m.email, m.password_hash, m.full_name, Role(m.role), m.department_code, m.is_active)


class SqlUserRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    def get_by_id(self, user_id: str) -> UserRecord | None:
        m = self.s.get(UserModel, user_id)
        return _user(m) if m else None

    def get_by_email(self, email: str) -> UserRecord | None:
        m = self.s.scalars(select(UserModel).where(UserModel.email == email)).first()
        return _user(m) if m else None

    def add(self, u: UserRecord) -> None:
        self.s.add(UserModel(id=u.id, email=u.email, password_hash=u.password_hash, full_name=u.full_name, role=str(u.role), department_code=u.department_id, is_active=u.is_active))
        self.s.flush()

    def update(self, u: UserRecord) -> None:
        m = self.s.get(UserModel, u.id)
        if m is None:
            raise LookupError("user not found")
        m.email, m.password_hash, m.full_name, m.role, m.department_code, m.is_active = u.email, u.password_hash, u.full_name, str(u.role), u.department_id, u.is_active
        self.s.flush()

    def count_with_role(self, role: Role) -> int:
        from sqlalchemy import func

        return int(self.s.scalar(select(func.count()).select_from(UserModel).where(UserModel.role == str(role))) or 0)

    def list(self, *, role: Role | None = None, limit: int = 100, offset: int = 0) -> list[UserRecord]:
        q = select(UserModel).order_by(UserModel.created_at).limit(limit).offset(offset)
        if role is not None:
            q = q.where(UserModel.role == str(role))
        return [_user(m) for m in self.s.scalars(q)]


class SqlSessionRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: SessionModel) -> SessionRecord:
        return SessionRecord(m.id, m.user_id, m.token_hash, m.created_at, m.last_seen_at, m.mfa_verified, m.revoked_at, m.kind)

    def add(self, r: SessionRecord) -> None:
        self.s.add(SessionModel(id=r.id, user_id=r.user_id, token_hash=r.token_hash, created_at=r.created_at, last_seen_at=r.last_seen_at, mfa_verified=r.mfa_verified, revoked_at=r.revoked_at, kind=r.kind))
        self.s.flush()

    def get_by_token_hash(self, token_hash: str) -> SessionRecord | None:
        m = self.s.scalars(select(SessionModel).where(SessionModel.token_hash == token_hash)).first()
        return self._rec(m) if m else None

    def update(self, r: SessionRecord) -> None:
        m = self.s.get(SessionModel, r.id)
        if m is not None:
            m.last_seen_at, m.revoked_at, m.mfa_verified = r.last_seen_at, r.revoked_at, r.mfa_verified
            self.s.flush()

    def revoke_all_for_user(self, user_id: str, at: datetime) -> None:
        self.s.execute(update(SessionModel).where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None)).values(revoked_at=at))


class SqlResetTokenRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    def add(self, r: ResetTokenRecord) -> None:
        self.s.add(PasswordResetTokenModel(token_hash=r.token_hash, user_id=r.user_id, expires_at=r.expires_at, used_at=r.used_at))
        self.s.flush()

    def get(self, token_hash: str) -> ResetTokenRecord | None:
        m = self.s.get(PasswordResetTokenModel, token_hash)
        return ResetTokenRecord(m.token_hash, m.user_id, m.expires_at, m.used_at) if m else None

    def mark_used(self, token_hash: str, at: datetime) -> None:
        m = self.s.get(PasswordResetTokenModel, token_hash)
        if m is not None:
            m.used_at = at
            self.s.flush()


class SqlMfaRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    def get(self, user_id: str) -> MfaRecord | None:
        m = self.s.get(MfaConfigModel, user_id)
        return MfaRecord(m.user_id, m.secret_encrypted, m.enabled, m.last_used_step, list(m.backup_code_hashes), m.created_at, m.confirmed_at) if m else None

    def save(self, r: MfaRecord) -> None:
        m = self.s.get(MfaConfigModel, r.user_id) or MfaConfigModel(user_id=r.user_id)
        m.secret_encrypted, m.enabled, m.last_used_step, m.backup_code_hashes, m.confirmed_at = r.secret_encrypted, r.enabled, r.last_used_step, list(r.backup_code_hashes), r.confirmed_at
        self.s.add(m)
        self.s.flush()

    def delete(self, user_id: str) -> None:
        m = self.s.get(MfaConfigModel, user_id)
        if m is not None:
            self.s.delete(m)
            self.s.flush()


class SqlProfileRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    def get(self, user_id: str) -> ProfileRecord | None:
        m = self.s.get(ProfileModel, user_id)
        return ProfileRecord(m.user_id, m.full_name, m.phone, m.city, m.ward, m.language, m.onboarding_complete, m.designation, m.updated_at) if m else None

    def save(self, p: ProfileRecord) -> None:
        m = self.s.get(ProfileModel, p.user_id) or ProfileModel(user_id=p.user_id)
        m.full_name, m.phone, m.city, m.ward, m.language, m.onboarding_complete, m.designation, m.updated_at = p.full_name, p.phone, p.city, p.ward, p.language, p.onboarding_complete, p.designation, p.updated_at
        self.s.add(m)
        self.s.flush()


class SqlConsentRepository:
    def __init__(self, s: Session) -> None:
        self.s = s

    @staticmethod
    def _rec(m: ConsentModel) -> ConsentRecord:
        return ConsentRecord(m.user_id, m.purpose, m.granted, m.policy_version, m.at)

    def add(self, c: ConsentRecord) -> None:
        self.s.add(ConsentModel(user_id=c.user_id, purpose=c.purpose, granted=c.granted, policy_version=c.policy_version, at=c.at))
        self.s.flush()

    def history(self, user_id: str) -> list[ConsentRecord]:
        return [self._rec(m) for m in self.s.scalars(select(ConsentModel).where(ConsentModel.user_id == user_id).order_by(ConsentModel.at))]

    def latest_by_purpose(self, user_id: str) -> dict[str, ConsentRecord]:
        out: dict[str, ConsentRecord] = {}
        for rec in self.history(user_id):  # ordered by time: later rows overwrite earlier ones
            out[rec.purpose] = rec
        return out


class SqlNotificationPrefs:
    def __init__(self, s: Session) -> None:
        self.s = s

    def get(self, user_id: str) -> NotificationPreference | None:
        m = self.s.get(NotificationPreferenceModel, user_id)
        return NotificationPreference(m.user_id, m.in_app, m.email, tuple(m.muted_kinds)) if m else None

    def save(self, p: NotificationPreference) -> None:
        m = self.s.get(NotificationPreferenceModel, p.user_id) or NotificationPreferenceModel(user_id=p.user_id)
        m.in_app, m.email, m.muted_kinds = p.in_app, p.email, list(p.muted_kinds)
        self.s.add(m)
        self.s.flush()

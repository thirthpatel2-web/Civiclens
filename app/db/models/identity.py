from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at, jsonb, tstz, uuid_pk


class UserModel(Base):
    __tablename__ = "users"
    id: Mapped[str] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="citizen")
    department_code: Mapped[str | None] = mapped_column(ForeignKey("departments.code"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"), Index("ix_users_role", "role"), Index("ix_users_department_code", "department_code"))


class SessionModel(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = created_at()
    last_seen_at: Mapped[datetime] = tstz(False)
    mfa_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_at: Mapped[datetime | None] = tstz()
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="web", server_default="web")  # web | mobile (mobile sessions live longer)
    __table_args__ = (UniqueConstraint("token_hash", name="uq_sessions_token_hash"), Index("ix_sessions_user_id", "user_id"))


class MfaConfigModel(Base):
    __tablename__ = "mfa_configs"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_used_step: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    backup_code_hashes: Mapped[Any] = jsonb(list)
    created_at: Mapped[datetime] = created_at()
    confirmed_at: Mapped[datetime | None] = tstz()


class PasswordResetTokenModel(Base):
    __tablename__ = "password_reset_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = tstz(False)
    used_at: Mapped[datetime | None] = tstz()
    __table_args__ = (Index("ix_password_reset_tokens_user_id", "user_id"),)


class ProfileModel(Base):
    """Citizen and officer profile (officers use ``designation``)."""

    __tablename__ = "profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(100))
    ward: Mapped[str | None] = mapped_column(String(40))
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    designation: Mapped[str | None] = mapped_column(String(120))
    updated_at: Mapped[datetime] = tstz(False)


class ConsentModel(Base):
    __tablename__ = "consent_records"
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(20), nullable=False)
    at: Mapped[datetime] = tstz(False)
    __table_args__ = (Index("ix_consent_records_user_purpose_at", "user_id", "purpose", "at"),)


class NotificationPreferenceModel(Base):
    __tablename__ = "notification_preferences"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    in_app: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    muted_kinds: Mapped[Any] = jsonb(list)

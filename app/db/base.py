"""SQLAlchemy 2.x declarative base, naming convention and shared column helpers."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, overload

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {"ix": "ix_%(column_0_label)s", "uq": "uq_%(table_name)s_%(column_0_name)s", "ck": "ck_%(table_name)s_%(constraint_name)s",
          "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s", "pk": "pk_%(table_name)s"}  # fmt: skip


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def uuid_pk() -> Mapped[str]:
    return mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


@overload
def tstz(nullable: Literal[False]) -> Mapped[datetime]: ...


@overload
def tstz(nullable: Literal[True] = ...) -> Mapped[datetime | None]: ...


def tstz(nullable: bool = True) -> Any:
    """A timezone-aware timestamp column whose declared type follows its nullability.

    The single signature this replaced always returned ``Mapped[datetime | None]``, so every
    ``x: Mapped[datetime] = tstz(False)`` - the NOT NULL case, which is most of them - looked like
    an Optional being assigned to a non-Optional. The overloads make ``tstz(False)`` non-optional,
    which is what the column actually is.
    """
    return mapped_column(DateTime(timezone=True), nullable=nullable)


def jsonb(default: Any = dict) -> Mapped[Any]:
    return mapped_column(JSONB, nullable=False, default=default)

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, jsonb, tstz


class DepartmentModel(Base):
    __tablename__ = "departments"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CityModel(Base):
    __tablename__ = "cities"
    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str | None] = mapped_column(String(100))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)


class WardModel(Base):
    __tablename__ = "wards"
    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    city_code: Mapped[str | None] = mapped_column(ForeignKey("cities.code"))
    __table_args__ = (Index("ix_wards_city_code", "city_code"),)


class CivicServiceModel(Base):
    __tablename__ = "civic_services"
    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    department_code: Mapped[str] = mapped_column(ForeignKey("departments.code"), nullable=False)
    __table_args__ = (Index("ix_civic_services_department_code", "department_code"),)


class GovernmentOfficeModel(Base):
    __tablename__ = "government_offices"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    department_code: Mapped[str | None] = mapped_column(ForeignKey("departments.code"))
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    address: Mapped[str | None] = mapped_column(String(300))
    city_code: Mapped[str | None] = mapped_column(ForeignKey("cities.code"))


class RoutingRuleModel(Base):
    __tablename__ = "routing_rules"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    department_code: Mapped[str] = mapped_column(ForeignKey("departments.code"), nullable=False)
    service_code: Mapped[str | None] = mapped_column(String(60))
    categories: Mapped[Any] = jsonb(list)
    keywords_any: Mapped[Any] = jsonb(list)
    wards: Mapped[Any] = jsonb(list)
    min_severity: Mapped[str | None] = mapped_column(String(10))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (Index("ix_routing_rules_priority", "priority"),)


class SlaPolicyModel(Base):
    __tablename__ = "sla_policies"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    department_code: Mapped[str | None] = mapped_column(ForeignKey("departments.code"))
    resolution_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    approaching_fraction: Mapped[float] = mapped_column(Float, nullable=False, default=0.25)
    escalation_gap_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=48)
    max_level: Mapped[int] = mapped_column(Integer, nullable=False, default=3)


class GovernmentPlatformModel(Base):
    """One row per external platform; runtime state is persisted so the admin UI is truthful across restarts."""

    __tablename__ = "government_platforms"
    platform: Mapped[str] = mapped_column(String(40), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class IntegrationHealthModel(Base):
    __tablename__ = "integration_health"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(ForeignKey("government_platforms.platform"), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    checked_at: Mapped[Any] = tstz(False)
    last_success_at: Mapped[Any] = tstz()
    last_error: Mapped[str | None] = mapped_column(String(500))
    avg_response_ms: Mapped[float | None] = mapped_column(Float)
    total_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (Index("ix_integration_health_platform_checked_at", "platform", "checked_at"),)

"""Civic GIS Radar data. Only stored coordinates are ever returned; citizens get aggregated
hotspots (minimum group size, no complaint ids/exact home points), staff get scoped points."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.authorization import AuthContext, Permission, Role, require
from app.services.location_service import SEVERITY_WEIGHT, aggregate_hotspots
from app.services.uow import UowFactory

CITIZEN_MIN_GROUP = 3


class GisService:
    def __init__(self, uow_factory: UowFactory, clock: Callable[[], datetime] | None = None) -> None:
        self._uow, self._clock = uow_factory, clock or (lambda: datetime.now(UTC))

    def radar(self, ctx: AuthContext, *, category: str | None = None, ward: str | None = None, min_severity: str | None = None, days: int = 90, link_distance_m: float = 200.0) -> dict[str, Any]:
        require(ctx, Permission.GIS_VIEW)
        since = self._clock() - timedelta(days=max(1, min(days, 730)))
        staff = ctx.role is not Role.CITIZEN
        dept = ctx.department_id if staff else None
        with self._uow() as uow:
            rows = uow.complaints.rows(department_code=dept, since=since)
            offices = [o for o in uow.config.offices() if dept is None or o.department_code in (None, dept)]
            wards = uow.config.wards()
        floor = SEVERITY_WEIGHT.get(min_severity or "low", 1)
        recs = [{"id": r.id, "lat": r.lat, "lng": r.lng, "category": r.category, "ward": r.ward, "severity": r.severity} for r in rows if SEVERITY_WEIGHT.get(r.severity, 2) >= floor]
        mappable = [r for r in recs if r["lat"] is not None]
        hotspots = aggregate_hotspots(mappable, link_distance_m=link_distance_m, category=category, ward=ward, min_count=1 if staff else CITIZEN_MIN_GROUP)
        return {
            "total_complaints": len(recs), "mappable": len(mappable), "not_mappable": len(recs) - len(mappable),
            "hotspots": [{"lat": round(h.lat, 5), "lng": round(h.lng, 5), "count": h.count, "severity_score": h.severity_score, "categories": h.categories, "wards": h.wards, **({"complaint_ids": h.complaint_ids} if staff else {})} for h in hotspots],
            "points": [{"id": p["id"], "lat": p["lat"], "lng": p["lng"], "category": p["category"], "severity": p["severity"], "ward": p["ward"]} for p in mappable if staff and (not category or p["category"] == category) and (not ward or p["ward"] == ward)],
            "offices": [{"id": o.id, "name": o.name, "department_code": o.department_code, "lat": o.lat, "lng": o.lng, "address": o.address} for o in offices],
            "wards": [{"code": w.code, "name": w.name} for w in wards], "ward_boundaries": "not_available",
            "privacy": None if staff else f"Areas with fewer than {CITIZEN_MIN_GROUP} reports are hidden to protect reporters.",
        }  # fmt: skip

    def locator(self, ctx: AuthContext, *, city_code: str | None = None, department_code: str | None = None) -> dict[str, Any]:
        """Government offices a citizen can walk into, grouped by city.

        This is directory data (name, department, address, coordinates) that is already public on
        the departments' own sites - no complaint data is involved, so no aggregation floor applies
        here, unlike ``radar``. Only offices that were given real coordinates are returned as
        mappable; the rest are still listed so an office is never hidden just for lacking a pin.
        """
        require(ctx, Permission.GIS_VIEW)
        with self._uow() as uow:
            offices = uow.config.offices()
            cities = {x.code: x for x in uow.config.cities()}
            departments = {d.code: d.name for d in uow.config.departments()}
        picked = [
            o for o in offices
            if (not city_code or o.city_code == city_code) and (not department_code or o.department_code == department_code)
        ]  # fmt: skip
        return {
            "cities": [{"code": x.code, "name": x.name, "state": x.state, "lat": x.lat, "lng": x.lng} for x in cities.values()],
            "departments": [{"code": k, "name": v} for k, v in sorted(departments.items())],
            "offices": sorted(
                ({"id": o.id, "name": o.name, "department_code": o.department_code,
                  "department_name": departments.get(o.department_code or "", o.department_code or ""),
                  "lat": o.lat, "lng": o.lng, "address": o.address, "city_code": o.city_code,
                  "city_name": cities[o.city_code].name if o.city_code in cities else None} for o in picked),
                key=lambda d: (d["city_name"] or "", d["name"]),
            ),
            "total": len(offices), "shown": len(picked),
            "unlinked": sum(1 for o in offices if not o.city_code),
        }  # fmt: skip

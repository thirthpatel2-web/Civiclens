"""Location validation and GIS hotspot aggregation (no geocoding is fabricated).

If a coordinate is present it is validated and stored as given. Address/ward are only
recorded when supplied by the user or a configured geocoder; this module never
invents them.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import ValidationFailed

EARTH_RADIUS_M = 6_371_000.0
WARD_MAX_LENGTH = 40
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# Broad bounding box for India incl. islands; used to *warn*, not to reject.
INDIA_BOUNDS = (6.0, 37.5, 68.0, 97.5)  # lat_min, lat_max, lng_min, lng_max
SEVERITY_WEIGHT = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass(frozen=True)
class ValidatedLocation:
    lat: float | None
    lng: float | None
    ward: str | None
    address: str | None
    city: str | None
    warnings: tuple[str, ...] = ()


def haversine_m(lat1: float | None, lng1: float | None, lat2: float | None, lng2: float | None) -> float | None:
    if None in (lat1, lng1, lat2, lng2):
        return None
    p1, p2 = math.radians(lat1), math.radians(lat2)  # type: ignore[arg-type]
    dphi, dlmb = p2 - p1, math.radians(lng2 - lng1)  # type: ignore[operator]
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _clean_text(value: Any, maxlen: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationFailed("Location text must be a string.")
    cleaned = _CONTROL.sub("", value).strip()
    return cleaned[:maxlen] or None


def validate_location(lat: Any = None, lng: Any = None, ward: Any = None, address: Any = None, city: Any = None) -> ValidatedLocation:
    warnings: list[str] = []
    la = ln = None
    if lat not in (None, "") or lng not in (None, ""):
        try:
            la, ln = float(lat), float(lng)
        except (TypeError, ValueError):
            raise ValidationFailed("Latitude and longitude must both be numbers.", details={"field": "location"}) from None
        if not (math.isfinite(la) and math.isfinite(ln)):
            raise ValidationFailed("Coordinates must be finite numbers.", details={"field": "location"})
        if not -90 <= la <= 90 or not -180 <= ln <= 180:
            raise ValidationFailed("Coordinates are outside the valid range.", details={"field": "location"})
        if la == 0 and ln == 0:
            raise ValidationFailed("Coordinates (0, 0) are not a valid complaint location.", details={"field": "location"})
        lat_min, lat_max, lng_min, lng_max = INDIA_BOUNDS
        if not (lat_min <= la <= lat_max and lng_min <= ln <= lng_max):
            warnings.append("Coordinates are outside India; please confirm the location.")
    w = _clean_text(ward, 10_000)
    if w is not None and len(w) > WARD_MAX_LENGTH:
        raise ValidationFailed(f"Ward is too long (max {WARD_MAX_LENGTH} characters).", details={"field": "ward"})
    return ValidatedLocation(la, ln, w, _clean_text(address, 300), _clean_text(city, 100), tuple(warnings))


@dataclass
class Hotspot:
    key: str
    lat: float
    lng: float
    count: int = 0
    severity_score: int = 0
    categories: dict[str, int] = field(default_factory=dict)
    wards: dict[str, int] = field(default_factory=dict)
    complaint_ids: list[str] = field(default_factory=list)


def aggregate_hotspots(
    complaints: Iterable[dict[str, Any]], *, link_distance_m: float = 200.0, category: str | None = None,
    ward: str | None = None, min_count: int = 1,
) -> list[Hotspot]:  # fmt: skip
    """Cluster real complaint records (dicts with id/lat/lng/category/ward/severity).

    Single-linkage clustering: two complaints belong to the same hotspot if they are
    within ``link_distance_m`` of each other (directly or through a chain). This avoids
    the edge effect of fixed grid cells, which can split two complaints 20 m apart.
    Records without coordinates are skipped, never interpolated. A grid of
    ``link_distance_m`` buckets keeps neighbour search near-linear.
    """
    if link_distance_m <= 0:
        raise ValueError("link_distance_m must be positive")
    items = [
        c for c in complaints
        if c.get("lat") is not None and c.get("lng") is not None
        and (not category or c.get("category") == category) and (not ward or c.get("ward") == ward)
    ]  # fmt: skip
    deg_lat = link_distance_m / 111_320.0
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    keys: list[tuple[int, int]] = []
    for idx, c in enumerate(items):
        deg_lng = deg_lat / max(math.cos(math.radians(c["lat"])), 0.01)
        key = (math.floor(c["lat"] / deg_lat), math.floor(c["lng"] / deg_lng))
        keys.append(key)
        buckets[key].append(idx)

    parent = list(range(len(items)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for idx, c in enumerate(items):
        ki, kj = keys[idx]
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for other in buckets.get((ki + di, kj + dj), ()):
                    if other <= idx:
                        continue
                    o = items[other]
                    d = haversine_m(c["lat"], c["lng"], o["lat"], o["lng"])
                    if d is not None and d <= link_distance_m:
                        parent[find(other)] = find(idx)

    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for idx, c in enumerate(items):
        groups[find(idx)].append(c)
    out: list[Hotspot] = []
    for members in groups.values():
        if len(members) < min_count:
            continue
        hotspot_key = min(str(m.get("id")) for m in members)  # not `key`: that name is the (int, int) grid bucket above
        h = Hotspot(hotspot_key, sum(m["lat"] for m in members) / len(members), sum(m["lng"] for m in members) / len(members))
        for m in members:
            h.count += 1
            h.severity_score += SEVERITY_WEIGHT.get(str(m.get("severity", "medium")), 2)
            cat = m.get("category") or "unknown"
            h.categories[cat] = h.categories.get(cat, 0) + 1
            if m.get("ward"):
                h.wards[m["ward"]] = h.wards.get(m["ward"], 0) + 1
            h.complaint_ids.append(str(m.get("id")))
        out.append(h)
    out.sort(key=lambda h: (-h.severity_score, -h.count, h.key))
    return out

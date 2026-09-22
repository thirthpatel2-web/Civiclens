"""Reverse geocoding via OpenStreetMap Nominatim (free, no API key/credentials required).

Real results only: a failed or empty lookup returns None. Nothing here ever guesses an address -
this mirrors app.services.location_service's own stance ("address/ward are only recorded when
supplied by the user or a configured geocoder; this module never invents them").
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Any

from app.integrations.base import Transport, TransportError, UrllibTransport, assert_safe_url

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
# Nominatim's usage policy requires a real identifying User-Agent (no API key exists to authenticate
# with instead) and caps free use at ~1 request/second, which a citizen tapping "Use my location"
# once per complaint is nowhere near.
USER_AGENT = "CivicLens-CitizenApp/1.0 (+https://github.com/thirthpatel2-web/Civiclens)"


@dataclass(frozen=True)
class ReverseGeocodeResult:
    display_name: str | None
    area: str | None
    city: str | None
    state: str | None
    pincode: str | None
    country: str | None


class NominatimProvider:
    name = "nominatim"

    def __init__(self, transport: Transport | None = None, *, allow_private_hosts: bool = False) -> None:
        self._t = transport or UrllibTransport()
        self._allow_private = allow_private_hosts

    def reverse(self, lat: float, lng: float, *, timeout: float = 8.0) -> ReverseGeocodeResult | None:
        query = urllib.parse.urlencode({"format": "jsonv2", "lat": lat, "lon": lng, "zoom": 16, "addressdetails": 1})
        url = f"{NOMINATIM_URL}?{query}"
        try:
            assert_safe_url(url, allow_private=self._allow_private, allow_http=False)
            resp = self._t.request("GET", url, {"User-Agent": USER_AGENT, "Accept-Language": "en"}, None, timeout)
        except TransportError:
            return None
        if resp.status != 200 or not isinstance(resp.body, dict):
            return None
        addr: dict[str, Any] = resp.body.get("address") or {}
        area = addr.get("suburb") or addr.get("neighbourhood") or addr.get("road") or addr.get("residential")
        city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality") or addr.get("county")
        display_name = resp.body.get("display_name")
        if not (area or city or addr.get("state") or addr.get("postcode") or display_name):
            return None
        return ReverseGeocodeResult(
            display_name=str(display_name) if display_name else None,
            area=str(area) if area else None,
            city=str(city) if city else None,
            state=str(addr["state"]) if addr.get("state") else None,
            pincode=str(addr["postcode"]) if addr.get("postcode") else None,
            country=str(addr["country"]) if addr.get("country") else None,
        )

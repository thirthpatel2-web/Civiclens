"""Civic Emergency Hub: contacts are *configuration* stored in the database (admin-managed, seeded from the original app's list).

If nothing is configured the hub says so (``configured=False``) - it never falls back to an invented list.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.exceptions import ValidationFailed
from app.i18n.translator import Translator, load_json
from app.services.ports import EmergencyContactRecord
from app.services.uow import UowFactory

_NUMBER = re.compile(r"^[0-9*#+]{2,20}$")


def validate_contact(c: EmergencyContactRecord) -> EmergencyContactRecord:
    errors: dict[str, str] = {}
    if not re.fullmatch(r"[a-z0-9_-]{2,60}", c.id or ""):
        errors["id"] = "Use 2-60 lowercase letters, digits, '-' or '_'."
    if not _NUMBER.match(c.number or ""):
        errors["number"] = "A phone number/short code (digits, +, *, #)."
    if not 2 <= len((c.name or "").strip()) <= 120:
        errors["name"] = "Name is required."
    if c.scope not in ("national", "city") or (c.scope == "city" and not c.city_code):
        errors["scope"] = "Scope must be 'national', or 'city' with a city code."
    if errors:
        raise ValidationFailed("Invalid emergency contact.", details=errors)
    return c


def records_from_seed(items: list[dict[str, Any]]) -> list[EmergencyContactRecord]:
    return [EmergencyContactRecord(h["code"], h["number"], h["name"], h.get("description", ""), h.get("scope", "national"), None, h.get("translations", {}), True, 10 * (i + 1)) for i, h in enumerate(items)]


class EmergencyHubService:
    def __init__(self, translator: Translator, uow_factory: UowFactory) -> None:
        self._tr, self._uow = translator, uow_factory

    def list(self, lang: str | None = None, city_code: str | None = None) -> dict[str, Any]:
        code = self._tr.resolve_language(lang)
        with self._uow() as uow:
            contacts = uow.emergency.list(active_only=True, city_code=city_code)
        items = []
        for h in contacts:
            loc = h.translations.get(code)
            items.append({"code": h.id, "number": h.number, "tel_uri": f"tel:{h.number}", "name": loc["name"] if loc and loc.get("name") else h.name,
                          "description": loc.get("desc") if loc and loc.get("desc") else h.description, "language": code if loc else "en", "translated": bool(loc) or code == "en", "scope": h.scope})  # fmt: skip
        return {"configured": bool(items), "items": items, "notice": self._tr.t("emergencyHelplines", lang)}

    def seed_defaults(self) -> int:
        """Load the ported national helpline list into an EMPTY table (idempotent; never overwrites admin edits)."""
        with self._uow() as uow:
            if uow.emergency.list(active_only=False):
                return 0
            recs = records_from_seed(load_json("national_helplines.json"))
            for r in recs:
                uow.emergency.save(validate_contact(r))
            uow.commit()
        return len(recs)

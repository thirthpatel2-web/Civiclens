"""Expo push notifications (mobile). Delivery is reported truthfully: only a response the Expo push service marks ``ok`` counts as delivered."""

from __future__ import annotations

from typing import Any

from app.core.exceptions import DependencyUnavailable
from app.integrations.base import Transport, TransportError, UrllibTransport

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class ExpoPushSender:
    """POSTs messages to Expo's push API (documented public endpoint). Enabled only when ``EXPO_PUSH_ENABLED=true``."""

    def __init__(self, transport: Transport | None = None, url: str = EXPO_PUSH_URL, access_token: str = "") -> None:
        self._t, self._url, self._token = transport or UrllibTransport(), url, access_token

    def send(self, tokens: list[str], title: str, body: str, data: dict[str, Any] | None = None) -> None:
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        messages = [{"to": t, "title": title, "body": body, "data": data or {}, "sound": "default"} for t in tokens if t.startswith(("ExponentPushToken[", "ExpoPushToken["))]
        if not messages:
            raise DependencyUnavailable("No valid Expo push token is registered for this user (push service unavailable).")
        try:
            resp = self._t.request("POST", self._url, headers, messages, 15.0)
        except TransportError as exc:
            raise DependencyUnavailable(f"Expo push service is unreachable ({exc}).") from exc
        if not 200 <= resp.status < 300 or not isinstance(resp.body, dict):
            raise DependencyUnavailable(f"Expo push service returned HTTP {resp.status}.")
        tickets = resp.body.get("data")
        if not isinstance(tickets, list) or not tickets:
            raise DependencyUnavailable("Expo push service returned no tickets.")
        bad = [t for t in tickets if not isinstance(t, dict) or t.get("status") != "ok"]
        if len(bad) == len(tickets):  # every device refused: not delivered
            msg = bad[0].get("message", "rejected") if isinstance(bad[0], dict) else "rejected"
            raise DependencyUnavailable(f"Expo push service rejected the message: {msg}")

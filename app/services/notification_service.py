"""Notification persistence, preferences and honest delivery status.

* ``in_app``: written to the user's inbox inside the caller's transaction and marked
  ``delivered`` at that moment (it *is* in the inbox). A realtime push is best-effort extra.
* ``email``: only if the user opted in; a background job sends it through an ``EmailSender``.
  With no sender configured the record ends as ``not_configured`` with the reason - never ``delivered``.
* ``push`` (mobile): created ``queued`` when the user has a registered device; a worker sends it through Expo's push service if
  enabled (``sending`` -> ``delivered``/``failed``), else ``not_configured``. Push is best-effort *in addition to* the in-app record.
States: queued -> sending -> delivered | failed | not_configured.
"""

from __future__ import annotations

import smtplib
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any, Protocol

from app.core.authorization import AuthContext, Permission, require
from app.core.exceptions import CivicLensError, NotConfigured, NotFound
from app.realtime.events import NOTIFICATION_CREATED, DomainEvent
from app.services.ports import NotificationPreference, NotificationRecord, NotificationRepository

KINDS = ("complaint.created", "complaint.assigned", "complaint.status_changed", "complaint.escalated", "complaint.resolved", "rti.deadline", "sla.at_risk", "integration.error", "system")


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class SmtpEmailSender:
    """stdlib SMTP sender; only constructed when SMTP settings are present."""

    def __init__(self, host: str, port: int, sender: str, username: str = "", password: str = "", use_tls: bool = True) -> None:
        if not (host and sender):
            raise NotConfigured("SMTP host and sender are required.")
        self._cfg = (host, port, sender, username, password, use_tls)

    def send(self, to: str, subject: str, body: str) -> None:
        host, port, sender, user, pw, tls = self._cfg
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = sender, to, subject
        msg.set_content(body)
        with smtplib.SMTP(host, port, timeout=15) as s:
            if tls:
                s.starttls()
            if user:
                s.login(user, pw)
            s.send_message(msg)


class NotificationService:
    def __init__(self, clock: Callable[[], datetime] | None = None, email_sender: EmailSender | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._email = email_sender

    def notify(self, repo: NotificationRepository, user_id: str, kind: str, title: str, body: str, *, data: dict[str, Any] | None = None,
               dedupe_key: str | None = None, want_email_job: list[str] | None = None, push_devices: int = 0, want_push_job: list[str] | None = None) -> tuple[NotificationRecord | None, DomainEvent | None]:  # fmt: skip
        """Create an in-app notification inside the caller's transaction.

        Returns ``(record, event)``; the caller publishes ``event`` after commit. Returns
        ``(None, None)`` if the kind is muted or the ``dedupe_key`` was already used (idempotent).
        If the user opted into e-mail, the e-mail record id is appended to ``want_email_job``.
        """
        pref = repo.get_preferences(user_id) or NotificationPreference(user_id)
        if kind in pref.muted_kinds or not pref.in_app:
            return None, None
        now = self._clock()
        rec = NotificationRecord(str(uuid.uuid4()), user_id, kind, title[:200], body[:1000], data or {}, "in_app", "delivered", now, now, dedupe_key=dedupe_key)
        if not repo.add(rec):
            return None, None
        if pref.email and want_email_job is not None:
            em = NotificationRecord(str(uuid.uuid4()), user_id, kind, title[:200], body[:1000], data or {}, "email", "queued", now, dedupe_key=f"{dedupe_key}:email" if dedupe_key else None)
            if repo.add(em):
                want_email_job.append(em.id)
        if push_devices and want_push_job is not None:
            pn = NotificationRecord(str(uuid.uuid4()), user_id, kind, title[:200], body[:1000], data or {}, "push", "queued", now, dedupe_key=f"{dedupe_key}:push" if dedupe_key else None)
            if repo.add(pn):
                want_push_job.append(pn.id)
        return rec, DomainEvent(NOTIFICATION_CREATED, {"id": rec.id, "kind": kind, "title": rec.title, "body": rec.body}, owner_id=user_id)

    def begin_send(self, repo: NotificationRepository, notification_id: str, channel: str) -> NotificationRecord:
        """queued -> sending (persisted before the external call so a crash leaves a truthful state)."""
        n = repo.get(notification_id)
        if n is None or n.channel != channel:
            raise NotFound("Notification not found.")
        if n.status in ("queued", "sending", "failed"):
            n.status, n.error = "sending", None
            repo.update(n)
        return n

    def finish_email(self, repo: NotificationRepository, n: NotificationRecord, address: str | None) -> NotificationRecord:
        if n.status == "delivered":
            return n
        if self._email is None:
            n.status, n.error = "not_configured", "E-mail delivery is not configured (no SMTP settings)."
        elif not address:
            n.status, n.error = "failed", "The user has no e-mail address on file."
        else:
            try:
                self._email.send(address, n.title, n.body)
                n.status, n.delivered_at, n.error = "delivered", self._clock(), None
            except (OSError, smtplib.SMTPException) as exc:
                n.status, n.error = "failed", f"SMTP error: {type(exc).__name__}"
        repo.update(n)
        return n

    def deliver_email(self, repo: NotificationRepository, notification_id: str, address: str | None) -> NotificationRecord:
        return self.finish_email(repo, self.begin_send(repo, notification_id, "email"), address)

    def finish_push(self, repo: NotificationRepository, n: NotificationRecord, sender: Any | None, tokens: list[str]) -> NotificationRecord:
        if sender is None:
            n.status, n.error = "not_configured", "Push delivery is not enabled on this server (EXPO_PUSH_ENABLED)."
        elif not tokens:
            n.status, n.error = "failed", "The user has no registered device."
        else:
            try:
                sender.send(tokens, n.title, n.body, n.data)
                n.status, n.delivered_at, n.error = "delivered", self._clock(), None
            except CivicLensError as exc:
                n.status, n.error = "failed", exc.message[:300]
        repo.update(n)
        return n

    def register_device(self, ctx: AuthContext, uow: Any, token: str, platform: str) -> None:
        require(ctx, Permission.NOTIFICATION_READ_OWN)
        if platform not in ("android", "ios") or not 10 <= len(token) <= 200:
            from app.core.exceptions import ValidationFailed

            raise ValidationFailed("Invalid device registration.")
        from app.services.ports import PushDeviceRecord

        now = self._clock()
        uow.push.upsert(PushDeviceRecord(ctx.user_id, token, platform, now, now))  # a token belongs to ONE user: re-registering on a shared phone moves it

    # ---- user-facing operations (authorised by ownership)
    def list_for(self, ctx: AuthContext, repo: NotificationRepository, *, unread_only: bool = False, limit: int = 50) -> list[NotificationRecord]:
        require(ctx, Permission.NOTIFICATION_READ_OWN)
        return [n for n in repo.list_for_user(ctx.user_id, unread_only=unread_only, limit=limit) if n.channel == "in_app"]

    def mark_read(self, ctx: AuthContext, repo: NotificationRepository, notification_id: str) -> NotificationRecord:
        require(ctx, Permission.NOTIFICATION_READ_OWN)
        n = repo.get(notification_id)
        if n is None or n.user_id != ctx.user_id:
            raise NotFound("Notification not found.")
        if n.read_at is None:
            n.read_at = self._clock()
            repo.update(n)
        return n

    def mark_all_read(self, ctx: AuthContext, repo: NotificationRepository) -> int:
        require(ctx, Permission.NOTIFICATION_READ_OWN)
        count = 0
        for n in repo.list_for_user(ctx.user_id, unread_only=True, limit=500):
            n.read_at = self._clock()
            repo.update(n)
            count += 1
        return count

    def preferences(self, ctx: AuthContext, repo: NotificationRepository) -> NotificationPreference:
        require(ctx, Permission.NOTIFICATION_READ_OWN)
        return repo.get_preferences(ctx.user_id) or NotificationPreference(ctx.user_id)

    def save_preferences(self, ctx: AuthContext, repo: NotificationRepository, *, in_app: bool, email: bool, muted_kinds: list[str]) -> NotificationPreference:
        require(ctx, Permission.NOTIFICATION_READ_OWN)
        unknown = set(muted_kinds) - set(KINDS)
        if unknown:
            from app.core.exceptions import ValidationFailed

            raise ValidationFailed("Unknown notification kind(s).", details={"unknown": sorted(unknown)})
        pref = NotificationPreference(ctx.user_id, in_app, email, tuple(sorted(set(muted_kinds))))
        repo.save_preferences(pref)
        return pref




"""RTI (Right to Information Act, 2005) applications: draft, generate, file, track.

Deadlines are *configuration*: ``RtiRules`` defaults are the Act's Section 7(1) periods
(30 days; 48 hours where the information concerns life or liberty) and are overridable
from settings. The clock is counted from the ``received_at`` date the applicant records
(receipt by the PIO); if unknown, the filing time is used and the UI says it is an estimate.

This module produces a *draft* in statutory language. It does not file anything with
any authority; ``FILED`` only records that the citizen has submitted it.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from app.core.authorization import AuthContext, Permission, require
from app.core.exceptions import NotConfigured, NotFound, ValidationFailed
from app.services.reference import generate_reference

MAX_QUESTIONS = 20
MAX_QUESTION_LEN = 1000

# Statutory records worth demanding under RTI Section 2(j)/6(1), keyed by the same civic
# category taxonomy as complaint classification (app.services.classification_service.CATEGORIES).
# These are starting suggestions a citizen can pick from, edit, or ignore entirely - never
# submitted silently on their behalf.
RTI_CATEGORY_RECORDS: dict[str, tuple[str, ...]] = {
    "roads": (
        "Sanctioned Work Order / Tender copy for this stretch of road",
        "Technical sanction and detailed estimate",
        "Measurement Book (MB) entries recorded for this work",
        "Quality test / lab strength reports for the materials used",
        "Fund allocation versus actual utilisation ledger",
        "Name and contact of the engineer responsible for site inspection",
    ),
    "water": (
        "Sanctioned Work Order / Tender copy for this pipeline or supply line",
        "Maintenance and inspection log for this line",
        "Water quality test reports for this supply zone",
        "Fund allocation versus actual utilisation ledger",
        "Name and contact of the officer responsible for this ward",
    ),
    "electricity": (
        "Maintenance / inspection log for this transformer or line",
        "Complaint history and Action Taken Reports for this location",
        "Name and contact of the contractor or officer responsible for maintenance",
    ),
    "sanitation": (
        "Sanitation contract / tender covering this ward",
        "Collection schedule and compliance log for this area",
        "Name and contact of the officer responsible for this ward",
    ),
    "drainage": (
        "Sanctioned Work Order / Tender copy for this drain",
        "Desilting / maintenance schedule and log",
        "Fund allocation versus actual utilisation ledger",
    ),
    "encroachment": (
        "Survey / demarcation records for this site",
        "Notices issued and the enforcement action log",
        "Name and contact of the officer responsible for enforcement",
    ),
    "police": (
        "FIR / complaint register entry relating to this matter, if any",
        "Action Taken Report on file",
        "Name of the patrol / beat officer assigned to this area",
    ),
    "other": (
        "Relevant file notings and correspondence on this matter",
        "Name and contact of the officer responsible",
        "Action Taken Report on file, if any",
    ),
}


def default_records_for_category(category: str | None) -> tuple[str, ...]:
    return RTI_CATEGORY_RECORDS.get((category or "other").lower(), RTI_CATEGORY_RECORDS["other"])


def build_rti_questions(
    *,
    subject: str,
    location: str | None = None,
    records_requested: tuple[str, ...] = (),
    tender_reference: str | None = None,
    time_period: str | None = None,
    custom_questions: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Compose precise, numbered RTI particulars instead of leaving the citizen a blank box.

    Selecting records and optionally a tender/work-order reference and time period produces
    specific statutory questions; with nothing selected it falls back to the same general
    questions a well-drafted RTI on this subject would ask. ``custom_questions`` (freeform,
    citizen-authored) are always appended, never replaced.
    """
    where = f' at "{location}"' if location else ""
    qs: list[str] = [f'Certified copy of all sanctioned Work Orders, Technical Sanctions and Tender Estimates for the matter: "{subject.strip()}"{where}.']
    if tender_reference and tender_reference.strip():
        qs.append(f"Certified copy of the Contract Agreement, milestone schedule and penalty clauses under Tender / Work Order No: {tender_reference.strip()}.")
    period_suffix = f" for the period {time_period.strip()}" if time_period and time_period.strip() else ""
    if records_requested:
        qs += [f"Certified copy of {r.strip().rstrip('.')}{period_suffix}." for r in records_requested if r and r.strip()]
    else:
        qs.append(f"Certified copy of the relevant maintenance, inspection or fund-utilisation records for this matter{period_suffix}.")
    qs.append("Name, designation and official contact (e-mail/phone) of the officer responsible for this matter.")
    qs.append("Certified copy of any citizen grievances received regarding this matter and the Action Taken Report(s) recorded on file.")
    qs += [q.strip() for q in custom_questions if q and q.strip()]
    return tuple(qs)


class _ChatProvider(Protocol):
    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.0) -> str: ...


def enhance_questions_with_llm(subject: str, location: str | None, baseline: tuple[str, ...], llm: _ChatProvider | None) -> tuple[str, ...]:
    """Best-effort: ask the model for 1-3 questions specific to this exact situation, on top of the
    deterministic statutory baseline. Never replaces the baseline, never blocks on failure - an LLM
    outage or a bad response just means the citizen gets the same solid template as before, not an
    error. The model is asked to request information/records only, never to assert facts about the
    matter it wasn't given - it has no factual basis to add beyond what the citizen already wrote.
    """
    if llm is None or not subject.strip():
        return baseline
    import json
    import re

    where = f' The location given is: "{location}".' if location else ""
    prompt = (
        f'A citizen is filing an RTI application about this situation, in their own words: "{subject.strip()[:2000]}"{where}\n\n'
        f"These statutory questions are already included:\n" + "\n".join(f"- {q}" for q in baseline) + "\n\n"
        "Suggest up to 3 ADDITIONAL RTI questions - each requesting a specific document, record or "
        "piece of official information that would help this exact situation, and that is not already "
        "covered above. Do not restate the existing questions. Do not assert or assume any fact "
        "(date, name, amount, cause) that was not stated by the citizen - only request records. "
        'Reply with ONLY a JSON array of strings, e.g. ["question one", "question two"]. If nothing '
        "useful can be added beyond the list above, reply with an empty JSON array []."
    )  # fmt: skip
    try:
        raw = llm.chat([{"role": "user", "content": prompt}], temperature=0.2)
        fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        extra = json.loads(fenced)
        if not isinstance(extra, list):
            return baseline
        cleaned = tuple(q.strip() for q in extra if isinstance(q, str) and q.strip())[:3]
    except Exception:  # noqa: BLE001 - any failure (timeout, bad JSON, provider error) degrades to the deterministic baseline
        return baseline
    return baseline + cleaned


class RtiStatus(StrEnum):
    DRAFT = "draft"
    GENERATED = "generated"
    FILED = "filed"
    RESPONDED = "responded"
    CLOSED = "closed"


@dataclass(frozen=True)
class RtiRules:
    response_days: int = 30
    life_liberty_hours: int = 48
    reminder_days: tuple[int, ...] = (7, 3, 1, 0)

    def deadline(self, received_at: datetime, *, life_or_liberty: bool) -> datetime:
        if life_or_liberty:
            return received_at + timedelta(hours=self.life_liberty_hours)
        return received_at + timedelta(days=self.response_days)


@dataclass(frozen=True)
class RtiDraft:
    subject: str
    public_authority: str
    questions: tuple[str, ...]
    applicant_name: str
    applicant_address: str
    language: str = "en"
    purpose: str | None = None
    life_or_liberty: bool = False
    below_poverty_line: bool = False
    attachments: tuple[str, ...] = ()


@dataclass
class RtiApplication:
    id: str
    owner_id: str
    draft: RtiDraft
    status: RtiStatus = RtiStatus.DRAFT
    reference: str | None = None
    generated_text: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    filed_at: datetime | None = None
    received_at: datetime | None = None
    due_at: datetime | None = None
    deadline_is_estimate: bool = False
    reminders_sent: tuple[int, ...] = ()


@dataclass(frozen=True)
class Countdown:
    state: str  # "not_started" | "running" | "due_today" | "overdue" | "answered"
    days_remaining: int | None
    hours_remaining: float | None
    due_at: datetime | None
    is_estimate: bool


def validate_draft(d: RtiDraft) -> RtiDraft:
    errors: dict[str, str] = {}
    if not 5 <= len(d.subject.strip()) <= 200:
        errors["subject"] = "Subject must be 5-200 characters."
    if not 3 <= len(d.public_authority.strip()) <= 200:
        errors["public_authority"] = "Name the public authority (3-200 characters)."
    qs = tuple(q.strip() for q in d.questions if q and q.strip())
    if not qs:
        errors["questions"] = "Add at least one question."
    elif len(qs) > MAX_QUESTIONS or any(len(q) > MAX_QUESTION_LEN for q in qs):
        errors["questions"] = f"At most {MAX_QUESTIONS} questions of up to {MAX_QUESTION_LEN} characters."
    if not 2 <= len(d.applicant_name.strip()) <= 120:
        errors["applicant_name"] = "Enter the applicant's name."
    if not 10 <= len(d.applicant_address.strip()) <= 400:
        errors["applicant_address"] = "Enter a postal address (10-400 characters)."
    if errors:
        raise ValidationFailed("The RTI application has errors.", details=errors)
    return replace(d, subject=d.subject.strip(), public_authority=d.public_authority.strip(), questions=qs,
                   applicant_name=d.applicant_name.strip(), applicant_address=d.applicant_address.strip())  # fmt: skip


def generate_text(d: RtiDraft, reference: str, on: date, rules: RtiRules, *, fee_note: str | None = None) -> str:
    """Statutory-language draft. Wording follows the Act's Sections 6(1), 7(1), 7(5) and 8/9."""
    period = f"{rules.life_liberty_hours} hours (life or liberty, Section 7(1) proviso)" if d.life_or_liberty else f"{rules.response_days} days (Section 7(1))"
    fee = fee_note or (
        "I am below the poverty line and am exempt from the application fee under Section 7(5); a copy of my "
        "BPL certificate is enclosed." if d.below_poverty_line else "The prescribed application fee is being paid as per the applicable rules."
    )  # fmt: skip
    qs = "\n".join(f"{i}. {q}" for i, q in enumerate(d.questions, start=1))
    parts = [
        f"Reference: {reference}", f"Date: {on.strftime('%d %B %Y')}", "",
        "To,", "The Public Information Officer,", d.public_authority, "",
        f"Subject: Request for information under Section 6(1) of the Right to Information Act, 2005 - {d.subject}", "",
        "Sir/Madam,", "",
        "I, the undersigned, request the following information under Section 6(1) of the Right to Information Act, 2005:", "",
        qs, "",
    ]  # fmt: skip
    if d.purpose:
        parts += [f"Context (provided voluntarily; no reason is required under Section 6(2)): {d.purpose.strip()}", ""]
    parts += [
        f"Please provide the information within {period}.",
        fee,
        "To the best of my knowledge, the information sought does not fall within the exemptions of Sections 8 and 9 of the Act and relates to your office.",
    ]
    if d.attachments:
        parts += ["", "Enclosures: " + "; ".join(d.attachments)]
    parts += ["", "Yours faithfully,", d.applicant_name, d.applicant_address]
    return "\n".join(parts)


def render_pdf(text: str, *, title: str, font_path: str | None = None) -> bytes:
    """Render draft text to PDF with reportlab.

    Non-Latin text requires a Unicode TrueType font (``font_path``); without one this
    raises ``NotConfigured`` instead of emitting garbled glyphs.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font = "Helvetica"
    if not text.isascii() and not all(ord(c) < 256 for c in text):
        if not font_path:
            raise NotConfigured("This RTI contains non-Latin text; configure a Unicode font (RTI_PDF_FONT) to export it as PDF.")
        pdfmetrics.registerFont(TTFont("CivicLensUnicode", font_path))
        font = "CivicLensUnicode"
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, pageCompression=0)
    c.setTitle(title)
    width, height = A4
    margin, size, leading = 56, 11, 15
    y = height - margin
    c.setFont(font, size)
    for raw_line in text.split("\n"):
        line, words = "", raw_line.split(" ")
        wrapped: list[str] = []
        for w in words:
            trial = f"{line} {w}".strip()
            if pdfmetrics.stringWidth(trial, font, size) > width - 2 * margin and line:
                wrapped.append(line)
                line = w
            else:
                line = trial
        wrapped.append(line)
        for ln in wrapped:
            if y < margin:
                c.showPage()
                c.setFont(font, size)
                y = height - margin
            c.drawString(margin, y, ln)
            y -= leading
    c.save()
    return buf.getvalue()


def countdown(app: RtiApplication, now: datetime) -> Countdown:
    if app.status in (RtiStatus.RESPONDED, RtiStatus.CLOSED):
        return Countdown("answered", None, None, app.due_at, app.deadline_is_estimate)
    if app.due_at is None:
        return Countdown("not_started", None, None, None, False)
    delta = app.due_at - now
    hours = delta.total_seconds() / 3600
    if delta < timedelta(0):
        return Countdown("overdue", -((-delta).days), hours, app.due_at, app.deadline_is_estimate)
    days = delta.days
    state = "due_today" if days == 0 else "running"
    return Countdown(state, days, hours, app.due_at, app.deadline_is_estimate)


def due_reminders(app: RtiApplication, now: datetime, rules: RtiRules) -> list[int]:
    """Reminder thresholds (days-left) newly reached and not yet sent. Idempotent."""
    if app.status is not RtiStatus.FILED or app.due_at is None:
        return []
    days_left = (app.due_at - now).days if app.due_at >= now else -1
    return sorted((t for t in rules.reminder_days if 0 <= days_left <= t and t not in app.reminders_sent), reverse=True)[:1]


class RtiRepository(Protocol):
    def add(self, app: RtiApplication) -> None: ...
    def get(self, app_id: str) -> RtiApplication | None: ...
    def update(self, app: RtiApplication) -> None: ...
    def list_for_owner(self, owner_id: str) -> list[RtiApplication]: ...
    def list_filed(self) -> list[RtiApplication]: ...


class RtiService:
    def __init__(self, repo: RtiRepository, rules: RtiRules | None = None, clock: Callable[[], datetime] | None = None) -> None:
        self._repo, self.rules = repo, rules or RtiRules()
        self._clock = clock or (lambda: datetime.now(UTC))

    def _owned(self, ctx: AuthContext, app_id: str) -> RtiApplication:
        require(ctx, Permission.RTI_MANAGE_OWN)
        app = self._repo.get(app_id)
        if app is None or app.owner_id != ctx.user_id:
            raise NotFound("RTI application not found.")  # same answer for "not yours"
        return app

    def create(self, ctx: AuthContext, draft: RtiDraft) -> RtiApplication:
        require(ctx, Permission.RTI_MANAGE_OWN)
        app = RtiApplication(str(uuid.uuid4()), ctx.user_id, validate_draft(draft), created_at=self._clock())
        self._repo.add(app)
        return app

    def update_draft(self, ctx: AuthContext, app_id: str, draft: RtiDraft) -> RtiApplication:
        app = self._owned(ctx, app_id)
        if app.status not in (RtiStatus.DRAFT, RtiStatus.GENERATED):
            raise ValidationFailed("A filed RTI can no longer be edited.")
        app.draft, app.status, app.generated_text = validate_draft(draft), RtiStatus.DRAFT, None
        self._repo.update(app)
        return app

    def generate(self, ctx: AuthContext, app_id: str, *, fee_note: str | None = None) -> RtiApplication:
        app = self._owned(ctx, app_id)
        if app.status not in (RtiStatus.DRAFT, RtiStatus.GENERATED):
            raise ValidationFailed("This RTI has already been filed.")
        now = self._clock()
        app.reference = app.reference or generate_reference("RTI", now.date())
        app.generated_text = generate_text(app.draft, app.reference, now.date(), self.rules, fee_note=fee_note)
        app.status = RtiStatus.GENERATED
        self._repo.update(app)
        return app

    def mark_filed(self, ctx: AuthContext, app_id: str, *, received_at: datetime | None = None) -> RtiApplication:
        app = self._owned(ctx, app_id)
        if app.status is not RtiStatus.GENERATED:
            raise ValidationFailed("Generate the RTI before marking it as filed.")
        now = self._clock()
        if received_at and received_at > now:
            raise ValidationFailed("Receipt date cannot be in the future.", details={"field": "received_at"})
        app.filed_at, app.received_at = now, received_at or now
        app.deadline_is_estimate = received_at is None
        app.due_at = self.rules.deadline(app.received_at, life_or_liberty=app.draft.life_or_liberty)
        app.status = RtiStatus.FILED
        self._repo.update(app)
        return app

    def mark_responded(self, ctx: AuthContext, app_id: str) -> RtiApplication:
        app = self._owned(ctx, app_id)
        if app.status is not RtiStatus.FILED:
            raise ValidationFailed("Only a filed RTI can be marked as answered.")
        app.status = RtiStatus.RESPONDED
        self._repo.update(app)
        return app

    def track(self, ctx: AuthContext, app_id: str) -> tuple[RtiApplication, Countdown]:
        app = self._owned(ctx, app_id)
        return app, countdown(app, self._clock())

    def export_pdf(self, ctx: AuthContext, app_id: str, *, font_path: str | None = None) -> bytes:
        app = self._owned(ctx, app_id)
        if not app.generated_text or not app.reference:
            raise ValidationFailed("Generate the RTI before exporting it.")
        return render_pdf(app.generated_text, title=f"RTI {app.reference}", font_path=font_path)


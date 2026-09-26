"""Complaint intake orchestration and the citizen-side read/feedback operations.

``create`` is one transaction that really uses the tested services:
validation -> location -> classification -> duplicate detection -> routing rules ->
reference number -> assignment -> SLA -> persistence -> events -> notification -> audit,
and enqueues (outbox) the slow AI enrichment. Nothing that needs a model is required for
the complaint to be saved: without Ollama the rules result stands and ``ai_status`` says so.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.authorization import (
    AuthContext,
    Permission,
    Role,
    can_access_complaint,
    require,
    require_complaint_access,
)
from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.i18n.languages import LANGUAGES, detect_language
from app.realtime.events import COMPLAINT_ASSIGNED, COMPLAINT_CREATED
from app.services.classification_service import CATEGORIES, ClassificationService, compute_priority
from app.services.complaint_common import ComplaintEffects, Outbox, assign_least_loaded
from app.services.complaint_status import ComplaintStatus as S
from app.services.complaint_status import apply_transition, build_timeline, matches_filter
from app.services.document_service import Storage, validate_upload
from app.services.duplicate_service import ComplaintSnapshot, DuplicateDetector
from app.services.location_service import validate_location
from app.services.ports import ComplaintRecord, EvidenceRecord, FeedbackRecord
from app.services.reference import generate_reference
from app.services.routing_service import DepartmentRouter
from app.services.sla_service import SlaCalculator
from app.services.uow import UowFactory

SUPPORTED_LANGUAGES = frozenset(LANGUAGES)  # every language the product knows; UI strings fall back to English where untranslated
EVIDENCE_TYPES = (".png", ".jpg", ".jpeg", ".pdf", ".txt", ".docx")
MAX_EVIDENCE_PER_COMPLAINT = 8


@dataclass
class ComplaintInput:
    title: str
    description: str
    language: str = "en"
    category: str | None = None
    complaint_type: str = "municipal"
    ward: str | None = None
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    city: str | None = None
    client_request_id: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    voice_id: str | None = None  # id of a VoiceRecord this text came from (the STT output is kept separately, unedited)


@dataclass
class CreateResult:
    complaint: ComplaintRecord
    replayed: bool = False
    warnings: list[str] = field(default_factory=list)


class ComplaintService:
    def __init__(self, uow_factory: UowFactory, effects: ComplaintEffects, storage: Storage, *, ai_enrichment_enabled: bool = False,
                 detector: DuplicateDetector | None = None, max_upload_bytes: int = 10 * 1024 * 1024, vision_enabled: bool = False) -> None:  # fmt: skip
        # Intake classification is rules-only by design: a request never waits on (or sends data to) a model.
        # Model-based enrichment runs later in a worker, after a consent check.
        self._uow, self._classifier, self._fx, self._storage = uow_factory, ClassificationService(None), effects, storage
        self._ai_enabled = ai_enrichment_enabled
        self._detector = detector or DuplicateDetector()
        self._max_bytes, self._vision = max_upload_bytes, vision_enabled

    # ------------------------------------------------------------------ evidence
    def upload_evidence(self, ctx: AuthContext, filename: str, data: bytes, declared_mime: str | None = None) -> EvidenceRecord:
        require(ctx, Permission.EVIDENCE_UPLOAD)
        v = validate_upload(filename, data, max_bytes=self._max_bytes, declared_mime=declared_mime)
        if not v.storage_name.endswith(EVIDENCE_TYPES):
            raise ValidationFailed("This file type is not accepted as evidence.")
        self._storage.save(v.storage_name, data)
        is_image = v.mime.startswith("image/")
        status = ("PENDING" if self._vision else "IMAGE_ANALYSIS_UNAVAILABLE") if is_image else "NOT_APPLICABLE"
        ev = EvidenceRecord(str(uuid.uuid4()), None, ctx.user_id, v.display_name, v.mime, v.size, v.sha256, v.storage_name, self._fx.clock(), analysis_status=status)
        with self._uow() as uow:
            uow.complaints.add_evidence(ev)
            self._fx.audit(uow).record("evidence.uploaded", actor_id=ctx.user_id, resource_type="evidence", resource_id=ev.id, metadata={"mime": v.mime, "size": v.size})
            uow.commit()
        return ev

    # ------------------------------------------------------------------ evidence after creation, access, re-analysis
    def add_evidence(self, ctx: AuthContext, complaint_id: str, evidence_id: str) -> EvidenceRecord:
        """The owner attaches more evidence to an unfinished complaint; it shows on the timeline and the officer is told."""
        require(ctx, Permission.EVIDENCE_UPLOAD)
        out = Outbox()
        with self._uow() as uow:
            c = uow.complaints.get(complaint_id)
            if c is None or c.citizen_id != ctx.user_id:
                raise NotFound("Complaint not found.")
            if c.status in (S.CLOSED, S.REJECTED):
                raise Conflict("This complaint is closed; evidence can no longer be added.")
            ev = uow.complaints.get_evidence(evidence_id)
            if ev is None or ev.uploader_id != ctx.user_id or ev.complaint_id is not None:
                raise ValidationFailed("The attachment is invalid or already used.", details={"evidence_id": evidence_id})
            ev.complaint_id = c.id
            uow.complaints.update_evidence(ev)
            self._fx.event(uow, c, "evidence_added", ctx, remarks=f"Added evidence: {ev.name}", details={"evidence_id": ev.id, "mime": ev.mime})
            if c.assigned_officer_id:
                self._fx.notify(uow, out, c.assigned_officer_id, "complaint.updated", "New evidence added", f"{c.reference}: {ev.name}", c, dedupe_key=f"evidence:{ev.id}")
            if ev.analysis_status == "PENDING":
                job, created = self._fx.jobs.enqueue(uow, "evidence.analyze", {"evidence_id": ev.id}, f"evidence-analyze:{ev.id}:0")
                if created:
                    out.jobs.append(job)
            self._fx.audit(uow).record("evidence.attached", actor_id=ctx.user_id, resource_type="complaint", resource_id=c.id, metadata={"evidence_id": ev.id})
            uow.commit()
        self._fx.flush(out)
        return ev

    def _evidence_for(self, uow: Any, ctx: AuthContext, evidence_id: str, *, write: bool) -> tuple[EvidenceRecord, ComplaintRecord | None]:
        ev = uow.complaints.get_evidence(evidence_id)
        if ev is None:
            raise NotFound("Evidence not found.")
        c = uow.complaints.get(ev.complaint_id) if ev.complaint_id else None
        owner = ev.uploader_id == ctx.user_id
        staff_ok = c is not None and ctx.role is not Role.CITIZEN and can_access_complaint(ctx, owner_id=c.citizen_id, department_id=c.department_code, write=write)
        if not (owner or staff_ok):
            raise NotFound("Evidence not found.")  # identical for missing and not-yours
        return ev, c

    def read_evidence(self, ctx: AuthContext, evidence_id: str) -> tuple[EvidenceRecord, bytes]:
        """Preview/download: the uploader, or staff with access to the complaint. Every access is audited."""
        with self._uow() as uow:
            ev, c = self._evidence_for(uow, ctx, evidence_id, write=False)
            self._fx.audit(uow).record("evidence.accessed", actor_id=ctx.user_id, resource_type="evidence", resource_id=ev.id, metadata={"complaint_id": c.id if c else None})
            uow.commit()
        return ev, self._storage.read(ev.storage_name)

    def request_analysis(self, ctx: AuthContext, evidence_id: str) -> EvidenceRecord:
        """Re-run image analysis (e.g. after the vision model was configured or a previous attempt failed)."""
        out = Outbox()
        with self._uow() as uow:
            ev, _ = self._evidence_for(uow, ctx, evidence_id, write=True)
            if not ev.mime.startswith("image/"):
                raise ValidationFailed("Only images are analysed.")
            if self._vision is None:
                ev.analysis_status, ev.analysis_error = "IMAGE_ANALYSIS_UNAVAILABLE", "No vision provider is configured."
                uow.complaints.update_evidence(ev)
            else:
                ev.analysis_status, ev.analysis_error = "PENDING", None
                uow.complaints.update_evidence(ev)
                job, created = self._fx.jobs.enqueue(uow, "evidence.analyze", {"evidence_id": ev.id}, f"evidence-analyze:{ev.id}:{self._fx.clock().isoformat()}")
                if created:
                    out.jobs.append(job)
            uow.commit()
        self._fx.flush(out)
        return ev

    # ------------------------------------------------------------------ create
    def _validate(self, d: ComplaintInput) -> None:
        errors: dict[str, str] = {}
        if not 5 <= len((d.title or "").strip()) <= 200:
            errors["title"] = "Title must be 5-200 characters."
        if not 10 <= len((d.description or "").strip()) <= 5000:
            errors["description"] = "Description must be 10-5000 characters."
        if d.language not in SUPPORTED_LANGUAGES:
            errors["language"] = "Unsupported language."
        if d.category and d.category not in CATEGORIES:
            errors["category"] = "Unknown category."
        if d.complaint_type not in ("municipal", "utility", "legal"):
            errors["complaint_type"] = "Unknown complaint type."
        if len(d.evidence_ids) > MAX_EVIDENCE_PER_COMPLAINT:
            errors["evidence_ids"] = f"At most {MAX_EVIDENCE_PER_COMPLAINT} attachments."
        if d.client_request_id and not 8 <= len(d.client_request_id) <= 64:
            errors["client_request_id"] = "client_request_id must be 8-64 characters."
        if errors:
            raise ValidationFailed("The complaint has errors.", details=errors)

    def create(self, ctx: AuthContext, d: ComplaintInput) -> CreateResult:
        require(ctx, Permission.COMPLAINT_CREATE)
        self._validate(d)
        loc = validate_location(d.lat, d.lng, d.ward, d.address, d.city)
        out = Outbox()
        lang_warnings: list[str] = []
        with self._uow() as uow:
            if d.client_request_id:
                prior = uow.complaints.get_by_client_request(ctx.user_id, d.client_request_id)
                if prior:
                    return CreateResult(prior, replayed=True)  # offline-sync/double-submit protection
            now = self._fx.clock()
            title, desc = d.title.strip(), d.description.strip()
            cls = self._classifier.classify(title, desc)
            needs_ai = cls.ambiguous or cls.confidence < 0.6
            cls.ai_status = ("pending" if self._ai_enabled else "not_configured") if needs_ai else "not_needed"
            classification: dict[str, Any] = {"category": cls.category, "severity": cls.severity, "confidence": cls.confidence, "source": cls.source,
                                             "keywords": cls.matched_keywords, "explanation": cls.explanation, "ambiguous": cls.ambiguous}  # fmt: skip
            if d.category:
                classification["citizen_category"] = d.category
                if cls.ambiguous or cls.category == "other":
                    cls.category, cls.source, classification["category"], classification["source"] = d.category, "citizen_selected", d.category, "citizen_selected"

            snap = ComplaintSnapshot("new", "new", f"{title}. {desc}", cls.category, now, loc.lat, loc.lng)
            cands = uow.complaints.duplicate_candidates(cls.category, now - self._detector.window)
            matches = self._detector.find(snap, [ComplaintSnapshot(c.id, c.reference, f"{c.title}. {c.description}", c.category, c.created_at, c.lat, c.lng) for c in cands])
            prio = compute_priority(cls.severity, affects_safety=cls.affects_safety, near_sensitive_site=cls.near_sensitive_site, duplicate_count=len(matches))

            decision = self.decide_route(uow, cls, f"{title} {desc}", loc.ward)

            ref = generate_reference("CL", now.date())
            for _ in range(5):
                if not uow.complaints.reference_exists(ref):
                    break
                ref = generate_reference("CL", now.date())
            else:
                raise Conflict("Could not allocate a reference number; please retry.")

            c = ComplaintRecord(str(uuid.uuid4()), ref, ctx.user_id, title, desc, d.language, cls.category, cls.severity, prio["priority"], S.SUBMITTED, d.complaint_type,
                                department_code=decision.department_code, service_code=decision.service_code, ward=loc.ward, lat=loc.lat, lng=loc.lng, address=loc.address, city=loc.city,
                                created_at=now, updated_at=now, client_request_id=d.client_request_id, ai_status=cls.ai_status, classification=classification,
                                routing={"source": decision.source, "rule_id": decision.rule_id, "confidence": decision.confidence, "explanation": decision.explanation,
                                         "ai_disagreement": decision.ai_disagreement, "manual_triage": decision.needs_manual_triage},
                                duplicates=[{"reference": m.reference, "complaint_id": m.complaint_id, "score": m.score, "verdict": m.verdict, "explanation": m.explanation} for m in matches],
                                priority_factors=prio["factors"])  # fmt: skip
            detected, ambiguous = detect_language(desc)
            c.detected_language = detected
            if detected and detected != d.language and not (ambiguous and d.language in ("hi", "mr")):
                lang_warnings.append(f"The text looks like {LANGUAGES[detected].name}, but the complaint language is set to {LANGUAGES[d.language].name}. Your original text was kept as written.")
            if d.voice_id:
                v = uow.voice.get(d.voice_id)
                if v is None or v.user_id != ctx.user_id or v.status != "OK" or not v.transcript:
                    raise ValidationFailed("The voice recording is invalid or not yours.", details={"field": "voice_id"})
                c.input_method, c.voice_id = "voice", v.id
            uow.complaints.add(c)
            self._attach_evidence(uow, ctx, c, d.evidence_ids)
            self._fx.event(uow, c, "status_change", ctx, to_status=S.SUBMITTED, remarks=None, actor_label="Citizen")

            self.apply_routing(uow, c, decision)
            due = SlaCalculator(list(uow.config.sla_policies())).due_at(now, c.priority, c.department_code)
            c.sla_due_at = due
            if due is None:
                self._fx.event(uow, c, "sla", None, details={"state": "no_policy"}, internal=True, actor_label="System")
            uow.complaints.update(c)
            self._fx.run_workflow(uow, c, "complaint.created", out)

            self._fx.notify(uow, out, ctx.user_id, "complaint.created", "Complaint registered", f"Your complaint {c.reference} was registered.", c, dedupe_key=f"created:{c.id}")
            if c.assigned_officer_id:
                self._fx.notify(uow, out, c.assigned_officer_id, "complaint.assigned", "New complaint assigned", f"{c.reference}: {c.title}", c, dedupe_key=f"assigned:{c.id}:{c.assigned_officer_id}")
            job, created = self._fx.jobs.enqueue(uow, "complaint.enrich", {"complaint_id": c.id}, f"enrich:{c.id}")
            if created:
                out.jobs.append(job)
            out.events.append(self._fx.complaint_event(COMPLAINT_CREATED, c, internal={"priority": c.priority, "duplicates": len(matches)}))
            if c.assigned_officer_id:
                out.events.append(self._fx.complaint_event(COMPLAINT_ASSIGNED, c, internal={"officer_id": c.assigned_officer_id}))
            self._fx.audit(uow).record("complaint.created", actor_id=ctx.user_id, resource_type="complaint", resource_id=c.id,
                                       metadata={"reference": c.reference, "category": c.category, "department": c.department_code, "routing_source": decision.source, "duplicates": len(matches)})  # fmt: skip
            uow.commit()
        self._fx.flush(out)
        return CreateResult(c, warnings=[*loc.warnings, *lang_warnings])

    @staticmethod
    def decide_route(uow: Any, cls: Any, text: str, ward: str | None) -> Any:
        """Rules-first routing from the *current* admin-configured rules and active departments."""
        depts = frozenset(x.code for x in uow.config.departments() if x.active)
        return DepartmentRouter(list(uow.config.routing_rules()), depts).route(cls, text, ward)

    def preview_classification(self, ctx: AuthContext, title: str, description: str, ward: str | None = None) -> dict[str, Any]:
        """Same rules-only classifier and routing the real intake uses, run read-only for a live 'AI suggests...'
        preview while the citizen is still typing/speaking - nothing is saved, no complaint is created."""
        require(ctx, Permission.COMPLAINT_CREATE)
        title, description = title.strip(), description.strip()
        cls = self._classifier.classify(title, description)
        with self._uow() as uow:
            decision = self.decide_route(uow, cls, f"{title}. {description}", ward)
            dept_name = None
            if decision.department_code:
                dept = next((d for d in uow.config.departments() if d.code == decision.department_code), None)
                dept_name = dept.name if dept else None
        return {
            "category": cls.category, "severity": cls.severity, "confidence": cls.confidence, "source": cls.source,
            "matched_keywords": cls.matched_keywords, "explanation": cls.explanation, "ambiguous": cls.ambiguous,
            "department_code": decision.department_code, "department_name": dept_name,
            "routing_explanation": decision.explanation, "needs_manual_triage": decision.needs_manual_triage,
        }

    def apply_routing(self, uow: Any, c: ComplaintRecord, decision: Any) -> None:
        """Route (status AI_ROUTED) and assign the least-loaded officer, or record that manual triage is needed."""
        if decision.department_code:
            c.department_code, c.service_code = decision.department_code, decision.service_code
            self._advance(uow, c, S.AI_ROUTED, "routed", {"department": decision.department_code, "source": decision.source, "rule_id": decision.rule_id, "explanation": decision.explanation})
            officer_id = assign_least_loaded(uow, decision.department_code)
            if officer_id:
                c.assigned_officer_id = officer_id
                self._advance(uow, c, S.ASSIGNED, "assigned", {"officer_id": officer_id, "method": "least_open_workload"})
        else:
            self._fx.event(uow, c, "routed", None, details={"department": None, "explanation": decision.explanation}, internal=True, actor_label="System")

    def _advance(self, uow: Any, c: ComplaintRecord, target: S, kind: str, details: dict[str, Any]) -> None:
        ev = apply_transition(c.id, c.status, target, actor_id=None, actor_label="System", remarks=None, at=self._fx.clock())
        uow.complaints.add_event(_as_event(ev, c, kind, details))
        c.status, c.updated_at = target, ev.at

    def _attach_evidence(self, uow: Any, ctx: AuthContext, c: ComplaintRecord, ids: list[str]) -> None:
        for eid in dict.fromkeys(ids):
            ev = uow.complaints.get_evidence(eid)
            if ev is None or ev.uploader_id != ctx.user_id or ev.complaint_id is not None:
                raise ValidationFailed("An attachment is invalid or already used.", details={"evidence_id": eid})
            ev.complaint_id = c.id
            uow.complaints.update_evidence(ev)

    # ------------------------------------------------------------------ citizen reads
    def list_mine(self, ctx: AuthContext, *, filter_name: str = "all", limit: int = 50, offset: int = 0) -> list[ComplaintRecord]:
        require(ctx, Permission.COMPLAINT_READ_OWN)
        with self._uow() as uow:
            rows = uow.complaints.list_for_citizen(ctx.user_id, limit=limit, offset=offset)
        return [c for c in rows if matches_filter(filter_name, status=c.status, complaint_type=c.complaint_type)]

    def detail_for_citizen(self, ctx: AuthContext, complaint_id: str) -> dict[str, Any]:
        with self._uow() as uow:
            c = uow.complaints.get(complaint_id)
            if c is None or c.citizen_id != ctx.user_id:
                raise NotFound("Complaint not found.")  # identical for missing and not-yours
            require_complaint_access(ctx, owner_id=c.citizen_id, department_id=c.department_code)
            events = [e for e in uow.complaints.list_events(c.id) if not e.internal]
            evidence = uow.complaints.list_evidence(c.id)
            fb = uow.complaints.get_feedback(c.id)
        return {"complaint": c, "timeline": build_timeline(c.status, events), "events": events, "evidence": evidence, "feedback": fb}

    def add_feedback(self, ctx: AuthContext, complaint_id: str, rating: int, comment: str | None) -> FeedbackRecord:
        require(ctx, Permission.COMPLAINT_FEEDBACK)
        if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
            raise ValidationFailed("Rating must be a whole number from 1 to 5.", details={"field": "rating"})
        out = Outbox()
        with self._uow() as uow:
            c = uow.complaints.get(complaint_id)
            if c is None or c.citizen_id != ctx.user_id:
                raise NotFound("Complaint not found.")
            if c.status not in (S.RESOLVED, S.CLOSED):
                raise ValidationFailed("Feedback can be given once the complaint is resolved.")
            if uow.complaints.get_feedback(c.id):
                raise Conflict("Feedback has already been submitted for this complaint.")
            fb = FeedbackRecord(c.id, ctx.user_id, rating, (comment or "").strip()[:1000] or None, self._fx.clock())
            uow.complaints.add_feedback(fb)
            self._fx.event(uow, c, "feedback", ctx, details={"rating": rating}, remarks=fb.comment, actor_label="Citizen")
            if c.assigned_officer_id:
                self._fx.notify(uow, out, c.assigned_officer_id, "system", "Citizen feedback received", f"{c.reference}: {rating}/5", c, dedupe_key=f"feedback:{c.id}")
            self._fx.audit(uow).record("complaint.feedback", actor_id=ctx.user_id, resource_type="complaint", resource_id=c.id, metadata={"rating": rating})
            uow.commit()
        self._fx.flush(out)
        return fb

    def acknowledgement(self, ctx: AuthContext, complaint_id: str, *, public_base_url: str, qr_renderer: Any = None, font_path: str | None = None) -> bytes:
        """The citizen's proof-of-filing slip as PDF. Owner-only, like every other citizen read."""
        from app.services.receipt import acknowledgement_pdf

        require(ctx, Permission.COMPLAINT_READ_OWN)
        with self._uow() as uow:
            c = uow.complaints.get(complaint_id)
            if c is None or c.citizen_id != ctx.user_id:
                raise NotFound("Complaint not found.")
            dept = next((d.name for d in uow.config.departments() if d.code == c.department_code), None)
        url = f"{public_base_url.rstrip('/')}/grievances/{c.id}"
        qr = None
        if qr_renderer is not None:
            try:
                qr = qr_renderer(url)
            except Exception:  # a missing QR library must not block the slip itself
                qr = None
        return acknowledgement_pdf(c, department_name=dept, tracking_url=url, generated_at=self._fx.clock(), qr_png=qr, font_path=font_path)

    REOPEN_WINDOW_DAYS = 30

    def reopen_by_citizen(self, ctx: AuthContext, complaint_id: str, reason: str) -> ComplaintRecord:
        """Verified closure: a department marking a complaint "resolved" is not the last word. The
        citizen who filed it can say it was not actually fixed - within 30 days, with a reason - and
        it goes back to "in progress" with the assigned officer notified. A closed (confirmed)
        complaint, or one that has already been rated, cannot be reopened this way."""
        from datetime import timedelta

        require(ctx, Permission.COMPLAINT_FEEDBACK)
        if len((reason or "").strip()) < 5:
            raise ValidationFailed("Say briefly what is still wrong.", details={"field": "reason"})
        out = Outbox()
        with self._uow() as uow:
            c = uow.complaints.get(complaint_id)
            if c is None or c.citizen_id != ctx.user_id:
                raise NotFound("Complaint not found.")
            if c.status is not S.RESOLVED:
                raise ValidationFailed("Only a complaint marked resolved can be reopened.")
            if uow.complaints.get_feedback(c.id):
                raise Conflict("You have already rated this resolution.")
            now = self._fx.clock()
            if c.resolved_at is not None and now - c.resolved_at > timedelta(days=self.REOPEN_WINDOW_DAYS):
                raise ValidationFailed(f"Complaints can be reopened within {self.REOPEN_WINDOW_DAYS} days of being resolved. Please file a new complaint.")
            ev = apply_transition(c.id, c.status, S.IN_PROGRESS, actor_id=ctx.user_id, actor_label="Citizen", remarks=reason, at=now)
            self._fx.event(uow, c, "reopened", ctx, from_status=ev.from_status, to_status=ev.to_status, remarks=ev.remarks, actor_label="Citizen")
            c.status, c.resolved_at, c.updated_at = S.IN_PROGRESS, None, now
            uow.complaints.update(c)
            if c.assigned_officer_id:
                self._fx.notify(uow, out, c.assigned_officer_id, "complaint.reopened", "Citizen says it is not fixed", f"{c.reference}: {reason.strip()[:120]}", c, dedupe_key=f"reopen:{c.id}:{int(now.timestamp())}")
            self._fx.audit(uow).record("complaint.reopened_by_citizen", actor_id=ctx.user_id, resource_type="complaint", resource_id=c.id, metadata={"reference": c.reference})
            uow.commit()
        self._fx.flush(out)
        return c


def _as_event(ev: Any, c: ComplaintRecord, kind: str, details: dict[str, Any]) -> Any:
    from app.services.ports import ComplaintEvent

    return ComplaintEvent(str(uuid.uuid4()), c.id, "status_change", ev.from_status, ev.to_status, None, "System", None, {"step": kind, **details}, ev.at, False)


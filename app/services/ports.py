"""Domain records and repository ports (Protocols).

Services depend only on these. Production implementations live in ``app/db/repositories``
(SQLAlchemy/PostgreSQL); the in-memory implementations under ``tests/`` are test doubles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.services.complaint_status import ComplaintStatus


def _now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)


# ------------------------------------------------------------------ records
@dataclass
class ComplaintRecord:
    id: str
    reference: str
    citizen_id: str
    title: str
    description: str
    language: str
    category: str
    severity: str
    priority: str
    status: ComplaintStatus
    complaint_type: str = "municipal"  # municipal | utility | legal | rti
    subcategory: str | None = None
    department_code: str | None = None
    service_code: str | None = None
    ward: str | None = None
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    city: str | None = None
    assigned_officer_id: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    sla_due_at: datetime | None = None
    escalation_level: int = 0
    escalated_at: datetime | None = None
    resolved_at: datetime | None = None
    client_request_id: str | None = None
    ai_status: str = "not_needed"
    classification: dict[str, Any] = field(default_factory=dict)
    routing: dict[str, Any] = field(default_factory=dict)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    priority_factors: list[str] = field(default_factory=list)
    # Multilingual: ``description``/``language`` are the ORIGINAL citizen text/language (never rewritten); the rest is derived or provenance.
    detected_language: str | None = None
    translated_text: str | None = None
    translated_language: str | None = None
    translation_provider: str | None = None
    input_method: str = "typed"  # typed | voice
    voice_id: str | None = None


@dataclass(frozen=True)
class ComplaintEvent:
    id: str
    complaint_id: str
    kind: str  # status_change | routed | assigned | remark | field_visit | inspection | work_order | coordination | progress | escalated | ai_enriched | feedback | duplicate_review | sla
    from_status: ComplaintStatus | None
    to_status: ComplaintStatus | None
    actor_id: str | None
    actor_label: str | None
    remarks: str | None
    details: dict[str, Any]
    at: datetime
    internal: bool = False  # internal events are hidden from the citizen


@dataclass
class EvidenceRecord:
    id: str
    complaint_id: str | None
    uploader_id: str
    name: str
    mime: str
    size: int
    sha256: str
    storage_name: str
    created_at: datetime = field(default_factory=_now)
    analysis_status: str = "IMAGE_ANALYSIS_UNAVAILABLE"  # PENDING | OK | FAILED | IMAGE_ANALYSIS_UNAVAILABLE | NOT_APPLICABLE
    analysis_provider: str | None = None
    analysis_result: dict[str, Any] | None = None
    analysis_error: str | None = None


@dataclass(frozen=True)
class FeedbackRecord:
    complaint_id: str
    citizen_id: str
    rating: int
    comment: str | None
    created_at: datetime


@dataclass
class NotificationRecord:
    id: str
    user_id: str
    kind: str
    title: str
    body: str
    data: dict[str, Any]
    channel: str = "in_app"
    status: str = "queued"  # queued | sending | delivered | failed | not_configured   (in_app is delivered on creation)
    created_at: datetime = field(default_factory=_now)
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    error: str | None = None
    dedupe_key: str | None = None


@dataclass
class NotificationPreference:
    user_id: str
    in_app: bool = True
    email: bool = False
    muted_kinds: tuple[str, ...] = ()


@dataclass
class JobRecord:
    id: str
    kind: str
    payload: dict[str, Any]
    idempotency_key: str
    status: str = "pending"  # pending (not yet in Redis) | queued | running | retrying | succeeded | dead
    attempts: int = 0
    max_attempts: int = 3
    run_at: datetime = field(default_factory=_now)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    error: str | None = None
    result: dict[str, Any] | None = None
    worker_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class ProfileRecord:
    user_id: str
    full_name: str
    phone: str | None = None
    city: str | None = None
    ward: str | None = None
    language: str = "en"
    onboarding_complete: bool = False
    designation: str | None = None
    updated_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class ConsentRecord:
    user_id: str
    purpose: str  # ai_processing | data_sharing_government | document_storage | notifications_email
    granted: bool
    policy_version: str
    at: datetime


@dataclass
class DraftRecord:
    id: str
    user_id: str
    kind: str  # complaint | rti
    client_request_id: str
    payload: dict[str, Any]
    status: str = "draft"  # draft | pending_sync | synced | failed
    error: str | None = None
    result_ref: str | None = None
    updated_at: datetime = field(default_factory=_now)
    attempts: int = 0


@dataclass
class AnomalyRecord:
    id: str
    kind: str
    subject: str
    severity: str
    score: float
    explanation: str
    detected_at: datetime
    department_code: str | None = None
    status: str = "open"  # open | acknowledged | resolved
    details: dict[str, Any] = field(default_factory=dict)
    dedupe_key: str = ""


@dataclass
class InvestigationRecord:
    id: str
    subject_type: str  # complaint | anomaly | cluster
    subject_id: str
    opened_by: str
    department_code: str | None
    status: str = "open"  # open | closed
    created_at: datetime = field(default_factory=_now)
    closed_at: datetime | None = None
    notes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ConversationMessage:
    id: str
    conversation_id: str
    role: str  # user | assistant
    content: str
    at: datetime
    status: str | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    database_facts: Any = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ConversationRecord:
    id: str
    user_id: str
    title: str
    created_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class ComplaintRow:
    """Lightweight projection for dashboards, GIS and analytics (no free text)."""

    id: str
    reference: str
    status: ComplaintStatus
    category: str
    severity: str
    priority: str
    department_code: str | None
    ward: str | None
    complaint_type: str
    created_at: datetime
    resolved_at: datetime | None
    sla_due_at: datetime | None
    escalation_level: int
    lat: float | None
    lng: float | None
    assigned_officer_id: str | None
    citizen_id: str
    routing_source: str | None = None
    has_duplicates: bool = False


@dataclass(frozen=True)
class DepartmentRecord:
    code: str
    name: str
    active: bool = True


@dataclass(frozen=True)
class OfficerLoad:
    officer_id: str
    open_count: int


# ------------------------------------------------------------------ repository ports
class ComplaintRepository(Protocol):
    def add(self, c: ComplaintRecord) -> None: ...
    def get(self, complaint_id: str) -> ComplaintRecord | None: ...
    def get_by_reference(self, reference: str) -> ComplaintRecord | None: ...
    def get_by_client_request(self, citizen_id: str, client_request_id: str) -> ComplaintRecord | None: ...
    def reference_exists(self, reference: str) -> bool: ...
    def update(self, c: ComplaintRecord) -> None: ...
    def list_for_citizen(self, citizen_id: str, *, limit: int = 50, offset: int = 0) -> list[ComplaintRecord]: ...
    def list_for_department(self, department_code: str, *, statuses: list[ComplaintStatus] | None = None, officer_id: str | None = None, limit: int = 50, offset: int = 0) -> list[ComplaintRecord]: ...
    def list_unrouted(self, *, limit: int = 100) -> list[ComplaintRecord]: ...
    def list_open(self) -> list[ComplaintRecord]: ...
    def list_by_status(self, statuses: list[ComplaintStatus], *, limit: int = 1000) -> list[ComplaintRecord]: ...
    def duplicate_candidates(self, category: str, since: datetime, *, limit: int = 200) -> list[ComplaintRecord]: ...
    def rows(self, *, citizen_id: str | None = None, department_code: str | None = None, since: datetime | None = None) -> list[ComplaintRow]: ...
    def add_event(self, e: ComplaintEvent) -> None: ...
    def list_events(self, complaint_id: str) -> list[ComplaintEvent]: ...
    def add_evidence(self, e: EvidenceRecord) -> None: ...
    def get_evidence(self, evidence_id: str) -> EvidenceRecord | None: ...
    def update_evidence(self, e: EvidenceRecord) -> None: ...
    def list_evidence(self, complaint_id: str) -> list[EvidenceRecord]: ...
    def add_feedback(self, f: FeedbackRecord) -> None: ...
    def get_feedback(self, complaint_id: str) -> FeedbackRecord | None: ...
    def officer_loads(self, department_code: str, officer_ids: list[str]) -> list[OfficerLoad]: ...


class OfficerDirectory(Protocol):
    def officer_ids_for_department(self, department_code: str) -> list[str]: ...
    def user_label(self, user_id: str) -> str | None: ...
    def admin_ids(self) -> list[str]: ...


class NotificationRepository(Protocol):
    def add(self, n: NotificationRecord) -> bool:
        """Insert; returns False (no insert) if ``dedupe_key`` already exists for the user."""
        ...
    def get(self, notification_id: str) -> NotificationRecord | None: ...
    def update(self, n: NotificationRecord) -> None: ...
    def list_for_user(self, user_id: str, *, unread_only: bool = False, limit: int = 50) -> list[NotificationRecord]: ...
    def unread_count(self, user_id: str) -> int: ...
    def status_counts(self) -> dict[str, dict[str, int]]:
        """{channel: {status: n}} for the admin monitor."""
        ...
    def get_preferences(self, user_id: str) -> NotificationPreference | None: ...
    def save_preferences(self, p: NotificationPreference) -> None: ...


class JobRepository(Protocol):
    def add_if_absent(self, j: JobRecord) -> tuple[JobRecord, bool]: ...
    def get(self, job_id: str) -> JobRecord | None: ...
    def update(self, j: JobRecord) -> None: ...
    def list_orphans(self, older_than: datetime, limit: int = 100) -> list[JobRecord]: ...
    def counts_by_status(self) -> dict[str, int]: ...
    def list_recent(self, limit: int = 50, status: str | None = None) -> list[JobRecord]: ...


class ProfileRepository(Protocol):
    def get(self, user_id: str) -> ProfileRecord | None: ...
    def save(self, p: ProfileRecord) -> None: ...


class ConsentRepository(Protocol):
    def add(self, c: ConsentRecord) -> None: ...
    def latest_by_purpose(self, user_id: str) -> dict[str, ConsentRecord]: ...
    def history(self, user_id: str) -> list[ConsentRecord]: ...


class DraftRepository(Protocol):
    def get_by_client_request(self, user_id: str, client_request_id: str) -> DraftRecord | None: ...
    def get(self, draft_id: str) -> DraftRecord | None: ...
    def save(self, d: DraftRecord) -> None: ...
    def list_for_user(self, user_id: str, kind: str | None = None) -> list[DraftRecord]: ...
    def delete(self, draft_id: str) -> None: ...


class AnomalyRepository(Protocol):
    def add_if_new(self, a: AnomalyRecord) -> bool: ...
    def list(self, *, status: str | None = None, department_code: str | None = None, limit: int = 100) -> list[AnomalyRecord]: ...
    def get(self, anomaly_id: str) -> AnomalyRecord | None: ...
    def update(self, a: AnomalyRecord) -> None: ...


class InvestigationRepository(Protocol):
    def add(self, i: InvestigationRecord) -> None: ...
    def get(self, investigation_id: str) -> InvestigationRecord | None: ...
    def update(self, i: InvestigationRecord) -> None: ...
    def list(self, *, department_code: str | None = None, limit: int = 100) -> list[InvestigationRecord]: ...


class ConversationRepository(Protocol):
    def add_conversation(self, c: ConversationRecord) -> None: ...
    def get_conversation(self, conversation_id: str) -> ConversationRecord | None: ...
    def list_conversations(self, user_id: str, limit: int = 50) -> list[ConversationRecord]: ...
    def add_message(self, m: ConversationMessage) -> None: ...
    def list_messages(self, conversation_id: str) -> list[ConversationMessage]: ...


@dataclass(frozen=True)
class WardRecord:
    code: str
    name: str
    city_code: str | None = None


@dataclass(frozen=True)
class CityRecord:
    code: str
    name: str
    state: str | None = None
    lat: float | None = None
    lng: float | None = None


@dataclass(frozen=True)
class CivicServiceRecord:
    code: str
    name: str
    department_code: str


@dataclass(frozen=True)
class GovOfficeRecord:
    id: str
    name: str
    department_code: str | None
    lat: float
    lng: float
    address: str | None = None
    city_code: str | None = None


class ConfigRepository(Protocol):
    def departments(self) -> list[DepartmentRecord]: ...
    def routing_rules(self) -> list[Any]: ...
    def sla_policies(self) -> list[Any]: ...
    def wards(self) -> list[WardRecord]: ...
    def cities(self) -> list[CityRecord]: ...
    def services(self) -> list[CivicServiceRecord]: ...
    def offices(self) -> list[GovOfficeRecord]: ...
    def save_department(self, d: DepartmentRecord) -> None: ...
    def save_routing_rule(self, r: Any) -> None: ...
    def delete_routing_rule(self, rule_id: str) -> bool: ...
    def save_sla_policy(self, p: Any) -> None: ...
    def delete_sla_policy(self, policy_id: str) -> bool: ...
    def save_ward(self, w: WardRecord) -> None: ...
    def save_city(self, c: CityRecord) -> None: ...
    def save_service(self, s: CivicServiceRecord) -> None: ...
    def save_office(self, o: GovOfficeRecord) -> None: ...


class AnalyticsRepository(Protocol):
    def add_snapshot(self, scope: str, taken_at: datetime, metrics: dict[str, Any]) -> None: ...
    def latest_snapshot(self, scope: str) -> dict[str, Any] | None: ...
    def list_snapshots(self, scope: str, since: datetime, limit: int = 500) -> list[tuple[datetime, dict[str, Any]]]: ...


@dataclass(frozen=True)
class PushDeviceRecord:
    user_id: str
    token: str
    platform: str
    created_at: datetime
    last_seen_at: datetime


class PushDeviceRepository(Protocol):
    def upsert(self, d: PushDeviceRecord) -> None: ...
    def list_for_user(self, user_id: str) -> list[PushDeviceRecord]: ...
    def delete(self, token: str, user_id: str) -> bool: ...


@dataclass
class EmergencyContactRecord:
    id: str
    number: str
    name: str
    description: str = ""
    scope: str = "national"  # national | city
    city_code: str | None = None
    translations: dict[str, dict[str, str]] = field(default_factory=dict)  # {"hi": {"name": ..., "desc": ...}}
    active: bool = True
    sort_order: int = 100


class EmergencyRepository(Protocol):
    def list(self, *, active_only: bool = True, city_code: str | None = None) -> list[EmergencyContactRecord]: ...
    def save(self, c: EmergencyContactRecord) -> None: ...
    def delete(self, contact_id: str) -> bool: ...


class DuplicateReviewRepository(Protocol):
    def add(self, review: Any) -> None: ...
    def list_for_complaint(self, complaint_id: str) -> list[Any]: ...


@dataclass
class WorkflowRuleRecord:
    id: str
    name: str
    trigger: str  # complaint.created | complaint.status_changed | scheduled
    conditions: dict[str, Any]
    action: str  # notify_admins | escalate | auto_close | assign_least_loaded | add_internal_note
    params: dict[str, Any] = field(default_factory=dict)
    priority: int = 100
    active: bool = True
    created_by: str | None = None
    created_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class WorkflowExecutionRecord:
    rule_id: str
    complaint_id: str
    executed_at: datetime
    outcome: str


class WorkflowRepository(Protocol):
    def list_rules(self, *, active_only: bool = False) -> list[WorkflowRuleRecord]: ...
    def save_rule(self, r: WorkflowRuleRecord) -> None: ...
    def delete_rule(self, rule_id: str) -> bool: ...
    def try_record_execution(self, e: WorkflowExecutionRecord) -> bool:
        """Insert; False if this rule already ran for this complaint (idempotent)."""
        ...
    def list_executions(self, *, limit: int = 100) -> list[WorkflowExecutionRecord]: ...


@dataclass
class GovernmentSubmissionRecord:
    id: str
    complaint_id: str
    platform: str
    state: str  # consent_required | not_configured | queued | submitting | submitted | failed
    requested_by: str
    created_at: datetime
    updated_at: datetime
    external_reference: str | None = None
    attempts: int = 0
    last_error: str | None = None
    submitted_at: datetime | None = None


class GovernmentSubmissionRepository(Protocol):
    def get(self, complaint_id: str, platform: str) -> GovernmentSubmissionRecord | None: ...
    def save(self, r: GovernmentSubmissionRecord) -> None: ...
    def list_for_complaint(self, complaint_id: str) -> list[GovernmentSubmissionRecord]: ...
    def counts_by_state(self) -> dict[str, int]: ...


@dataclass(frozen=True)
class LegalAnalysisRecord:
    id: str
    user_id: str
    problem: str
    status: str
    result: dict[str, Any]
    created_at: datetime


class LegalAnalysisRepository(Protocol):
    def add(self, r: LegalAnalysisRecord) -> None: ...
    def get(self, analysis_id: str) -> LegalAnalysisRecord | None: ...
    def list_for_user(self, user_id: str, limit: int = 50) -> list[LegalAnalysisRecord]: ...


# -------------------------------------------------------------------------------------------
# Interoperability layer support: Golden Record links, integration exceptions, cross-portal
# tracking, classification-correction capture. See app/interop/ for the pure normalization layer.
# -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ExternalIdRecord:
    id: str
    user_id: str
    id_type: str  # aadhaar_ref | pan | voter_id | driving_license | ration_card
    id_hash: str  # salted SHA-256 of the normalized raw value - the raw value is never stored
    last4: str | None
    linked_at: datetime


class MasterDataRepository(Protocol):
    def add(self, r: ExternalIdRecord) -> bool:
        """Insert; False if this (id_type, id_hash) is already linked to *any* profile (conflict)."""
        ...
    def list_for_user(self, user_id: str) -> list[ExternalIdRecord]: ...
    def remove(self, record_id: str, user_id: str) -> bool: ...


@dataclass
class IntegrationExceptionRecord:
    id: str
    source_system: str
    reason: str
    payload: dict[str, Any]
    detected_at: datetime
    status: str = "open"  # open | resolved | ignored
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_note: str | None = None


class ExceptionRepository(Protocol):
    def add(self, r: IntegrationExceptionRecord) -> None: ...
    def list(self, *, status: str | None = None, limit: int = 100) -> list[IntegrationExceptionRecord]: ...
    def get(self, exception_id: str) -> IntegrationExceptionRecord | None: ...
    def update(self, r: IntegrationExceptionRecord) -> None: ...
    def counts_by_status(self) -> dict[str, int]: ...


@dataclass
class ExternalServiceLinkRecord:
    id: str
    user_id: str
    platform: str
    external_reference: str
    title: str
    created_at: datetime
    updated_at: datetime
    status_note: str = ""


class ExternalLinkRepository(Protocol):
    def add(self, r: ExternalServiceLinkRecord) -> None: ...
    def list_for_user(self, user_id: str) -> list[ExternalServiceLinkRecord]: ...
    def update(self, r: ExternalServiceLinkRecord) -> None: ...
    def remove(self, record_id: str, user_id: str) -> bool: ...


@dataclass(frozen=True)
class ClassificationCorrectionRecord:
    id: str
    complaint_id: str
    text_snapshot: str
    previous_category: str
    corrected_category: str
    corrected_by: str
    corrected_at: datetime


class ClassificationCorrectionRepository(Protocol):
    def add(self, r: ClassificationCorrectionRecord) -> None: ...
    def list_recent(self, limit: int = 100) -> list[ClassificationCorrectionRecord]: ...
    def find_similar(self, text: str, limit: int = 5) -> list[ClassificationCorrectionRecord]:
        """Best-effort keyword-overlap lookup - a transparent, inspectable suggestion source,
        never a black-box weight update."""
        ...

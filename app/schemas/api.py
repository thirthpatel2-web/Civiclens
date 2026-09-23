from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---- auth
class RegisterBody(Strict):
    email: str = Field(max_length=320)
    password: str = Field(max_length=128)
    full_name: str = Field(min_length=2, max_length=120)


class LoginBody(Strict):
    email: str = Field(max_length=320)
    password: str = Field(max_length=128)
    otp: str | None = Field(default=None, max_length=12)


class ForgotBody(Strict):
    email: str = Field(max_length=320)


class ResetBody(Strict):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(max_length=128)


class ChangePasswordBody(Strict):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class OtpBody(Strict):
    otp: str = Field(min_length=6, max_length=12)


class DisableMfaBody(Strict):
    password: str = Field(max_length=128)
    otp: str = Field(min_length=6, max_length=12)


class BootstrapBody(Strict):
    email: str
    password: str = Field(max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    setup_token: str = Field(max_length=200)


# ---- complaints
class ComplaintBody(Strict):
    title: str = Field(max_length=200)
    description: str = Field(max_length=5000)
    language: str = "en"
    category: str | None = None
    complaint_type: str = "municipal"
    ward: str | None = Field(default=None, max_length=40)
    lat: float | None = None
    lng: float | None = None
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=100)
    client_request_id: str | None = Field(default=None, max_length=64)
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)
    voice_id: str | None = Field(default=None, max_length=36)


class FeedbackBody(Strict):
    rating: int
    comment: str | None = Field(default=None, max_length=1000)


class ClassifyPreviewBody(Strict):
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=5000)
    ward: str | None = Field(default=None, max_length=40)


class DraftBody(Strict):
    kind: str = "complaint"
    client_request_id: str = Field(min_length=8, max_length=64)
    payload: dict[str, Any]


# ---- rti
class RtiBody(Strict):
    subject: str = Field(max_length=200)
    public_authority: str = Field(max_length=200)
    questions: list[str] = Field(max_length=20)
    applicant_name: str = Field(max_length=120)
    applicant_address: str = Field(max_length=400)
    language: str = "en"
    purpose: str | None = Field(default=None, max_length=1000)
    life_or_liberty: bool = False
    below_poverty_line: bool = False
    attachments: list[str] = Field(default_factory=list, max_length=10)


class RtiFileBody(Strict):
    received_at: datetime | None = None


class RtiQuestionsPreviewBody(Strict):
    # Unlike RtiBody.subject (a short document subject line), this carries the citizen's free-text
    # problem description for the AI to reason about - capped like LegalBody.problem, not like a
    # one-line subject. A tighter cap here silently 422'd any realistically detailed complaint.
    subject: str = Field(max_length=8000)
    category: str | None = None
    location: str | None = Field(default=None, max_length=200)
    records_requested: list[str] = Field(default_factory=list, max_length=20)
    tender_reference: str | None = Field(default=None, max_length=200)
    time_period: str | None = Field(default=None, max_length=100)
    custom_questions: list[str] = Field(default_factory=list, max_length=20)


# ---- ai / documents / legal / voice
class AskBody(Strict):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    language: str = "en"  # language code (e.g. "kn"); the answer is composed in that language where the model supports it


class RouteBody(Strict):
    text: str = Field(min_length=1, max_length=2000)
    ward: str | None = None


class SearchBody(Strict):
    query: str = Field(min_length=1, max_length=1000)


class LegalBody(Strict):
    problem: str = Field(min_length=5, max_length=8000)
    disposal: str | None = None
    year: int | None = None


class TranslateBody(Strict):
    text: str = Field(min_length=1, max_length=5000)
    source: str
    target: str


class LinkBody(Strict):
    linked_type: str
    linked_id: str


# ---- officer
class StatusBody(Strict):
    status: str
    remarks: str | None = Field(default=None, max_length=2000)


class AssignBody(Strict):
    officer_id: str


class TriageBody(Strict):
    department_code: str


class CorrectCategoryBody(Strict):
    category: str


class RemarkBody(Strict):
    text: str = Field(min_length=1, max_length=2000)
    internal: bool = True


class FieldVisitBody(Strict):
    scheduled_for: datetime
    notes: str | None = Field(default=None, max_length=2000)


class InspectionBody(Strict):
    findings: str = Field(min_length=1, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)


class WorkOrderBody(Strict):
    order_ref: str = Field(max_length=60)
    description: str = Field(min_length=1, max_length=2000)
    team: str | None = Field(default=None, max_length=80)


class CoordinationBody(Strict):
    with_team: str = Field(max_length=80)
    note: str = Field(min_length=1, max_length=2000)


class ProgressBody(Strict):
    percent: int
    notes: str | None = Field(default=None, max_length=2000)


class EscalateBody(Strict):
    reason: str = Field(min_length=1, max_length=1000)


class ResolveBody(Strict):
    resolution_notes: str = Field(min_length=1, max_length=2000)


class OpenInvestigationBody(Strict):
    subject_type: str
    subject_id: str


class NoteBody(Strict):
    text: str = Field(min_length=1, max_length=4000)


# ---- admin
class StaffBody(Strict):
    email: str
    password: str = Field(max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    role: str
    department_code: str | None = None


class RoleBody(Strict):
    role: str
    department_code: str | None = None


class ActiveBody(Strict):
    active: bool


class DepartmentBody(Strict):
    code: str
    name: str
    active: bool = True


class WardBody(Strict):
    code: str
    name: str
    city_code: str | None = None


class CityBody(Strict):
    code: str
    name: str
    state: str | None = None
    lat: float | None = None
    lng: float | None = None


class ServiceBody(Strict):
    code: str
    name: str
    department_code: str


class OfficeBody(Strict):
    id: str
    name: str
    department_code: str | None = None
    lat: float
    lng: float
    address: str | None = None
    city_code: str | None = None


class RuleBody(Strict):
    priority: int
    department_code: str
    categories: list[str] = Field(default_factory=list)
    keywords_any: list[str] = Field(default_factory=list)
    wards: list[str] = Field(default_factory=list)
    min_severity: str | None = None
    service_code: str | None = None
    active: bool = True


class SlaBody(Strict):
    priority: str
    resolution_hours: int
    department_code: str | None = None
    escalation_gap_hours: int = 48
    max_level: int = 3


class AnomalyStatusBody(Strict):
    status: str


# ---- profile / consent / notifications
class ProfileBody(Strict):
    full_name: str | None = None
    phone: str | None = None
    city: str | None = None
    ward: str | None = None
    language: str | None = None
    complete_onboarding: bool = False


class ConsentBody(Strict):
    granted: bool


class PrefsBody(Strict):
    in_app: bool = True
    email: bool = False
    muted_kinds: list[str] = Field(default_factory=list)


class DeviceBody(Strict):
    token: str = Field(min_length=10, max_length=200)
    platform: str = Field(pattern="^(android|ios)$")


class GovSubmitBody(Strict):
    platform: str = Field(max_length=40)


# ---- interoperability layer
class NormalizeDemoBody(Strict):
    system: str = Field(max_length=40)
    corrupt: bool = False


class LogExceptionBody(Strict):
    source_system: str = Field(max_length=60)
    reason: str = Field(max_length=300)
    payload: dict = Field(default_factory=dict)


class ResolveExceptionBody(Strict):
    note: str = Field(default="", max_length=500)
    ignore: bool = False


class LinkExternalIdBody(Strict):
    id_type: str = Field(max_length=30)
    raw_value: str = Field(max_length=40)


class AddExternalLinkBody(Strict):
    platform: str = Field(max_length=60)
    external_reference: str = Field(max_length=80)
    title: str = Field(max_length=200)
    status_note: str = Field(default="", max_length=300)


class UpdateExternalLinkStatusBody(Strict):
    status_note: str = Field(max_length=300)


class RequestDocumentExchangeBody(Strict):
    application_no: str = Field(max_length=40)
    document_type: str = Field(default="residence_certificate", max_length=60)


class RevokeConsentBody(Strict):
    reason: str = Field(default="", max_length=300)


class ResolveIdentityCandidateBody(Strict):
    approve: bool


class SetConnectorEnabledBody(Strict):
    enabled: bool


class FederationTokenBody(Strict):
    """OAuth2 client_credentials grant (RFC 6749 s4.4) against the mock Government IdP - see
    app/interop/federation/idp.py. grant_type is accepted (and validated) for shape-compatibility
    with real OAuth2 clients even though this demo IdP only implements the one grant type."""

    grant_type: str = Field(default="client_credentials", max_length=40)
    client_id: str = Field(max_length=60)
    client_secret: str = Field(max_length=200)
    scope: str | None = Field(default=None, max_length=200)  # space-separated, OAuth2-style


class FederationTokenActionBody(Strict):
    token: str = Field(max_length=200)


class DuplicateDecisionBody(Strict):
    other_complaint_id: str
    decision: str
    note: str | None = Field(default=None, max_length=1000)


class WorkflowRuleBody(Strict):
    name: str = Field(min_length=2, max_length=120)
    trigger: str
    action: str
    conditions: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    active: bool = True


class EmergencyBody(Strict):
    number: str = Field(max_length=20)
    name: str = Field(max_length=120)
    description: str = Field(default="", max_length=300)
    scope: str = "national"
    city_code: str | None = None
    translations: dict[str, dict[str, str]] = Field(default_factory=dict)
    active: bool = True
    sort_order: int = 100


class AttachEvidenceBody(Strict):
    evidence_id: str = Field(max_length=36)

"""Canonical interoperability schema, version 1.

External systems never communicate using CivicLens's internal SQLAlchemy models. Every connector
transforms its own system's shape into one of these frozen dataclasses on the way in
(``app.interop.canonical.v1.transform``), and back into that system's native shape on the way out.
Adding a new government system means writing two transform functions against this shape - it never
requires touching gateway orchestration logic (``app.services.interop_gateway_service``).

Not every entity here is wired into a live data flow yet - ``Document`` and ``Application`` are the
two the no-reupload demo actually transforms through today (see ``transform.py`` and
``docs/INTEROPERABILITY.md``'s "What's real, what's a demo" table for exactly which ones). The rest
are real, typed, and ready for the next connector that needs them, not placeholders - but a
dataclass existing here is not itself a claim that something is "done"; see
``docs/REQUIREMENT_TRACEABILITY.md``.

Schema versioning: this is v1. A backward-incompatible change to any of these dataclasses adds a
v2 package (``app.interop.canonical.v2``) alongside this one rather than editing v1 in place -
existing connectors keep transforming into v1 until they are explicitly migrated to v2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

SCHEMA_VERSION = "v1"

# Canonical cross-system application states (see docs/INTEROPERABILITY.md's "Canonical application
# state" section) - every connector's native status maps into exactly one of these; the citizen is
# never shown a raw, incompatible departmental status as the primary state.
CANONICAL_APPLICATION_STATES = (
    "DRAFT", "SUBMITTED", "IN_PROGRESS", "WAITING_FOR_CITIZEN", "WAITING_FOR_DEPARTMENT",
    "WAITING_FOR_EXTERNAL_SYSTEM", "APPROVED", "REJECTED", "COMPLETED", "FAILED", "CANCELLED",
)  # fmt: skip


@dataclass(frozen=True)
class Address:
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    pincode: str | None = None


@dataclass(frozen=True)
class Citizen:
    """A person as one source system described them - not yet resolved to a MasterIdentity."""

    name: str
    mobile: str | None = None
    email: str | None = None
    address: Address | None = None
    source_system: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MasterIdentity:
    """The resolved identity a Citizen record from any system links to. Mirrors
    ``app.db.models.interop_platform.MasterEntity`` + its ``MasterIdentifier`` rows - this is the
    canonical *view* of that resolution, not a replacement for it."""

    master_id: str
    display_name: str
    identifiers: tuple[tuple[str, str, str], ...] = ()  # (system, identifier_type, identifier_value)


@dataclass(frozen=True)
class Organization:
    org_id: str
    name: str
    org_type: str  # "department" | "office" | "external_system"


@dataclass(frozen=True)
class Department:
    code: str
    name: str
    state: str | None = None


@dataclass(frozen=True)
class Office:
    office_id: str
    name: str
    department_code: str


@dataclass(frozen=True)
class Service:
    service_id: str
    name: str
    department_code: str
    description: str | None = None


@dataclass(frozen=True)
class Document:
    """A document held by a source system - fetched by reference, never re-uploaded. This is what
    the no-reupload flow actually transforms (see ``transform.py``'s dept_a functions)."""

    document_id: str
    document_type: str
    reference: str
    status: str  # "verified" | "pending" | "rejected" | "unknown"
    source_system: str
    owner_master_id: str | None = None
    issued_on: date | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Application:
    """A citizen's application/service request as tracked across departments - the canonical view
    behind ``app.db.models.interop_platform.UnifiedApplication``."""

    application_id: str
    reference: str
    service_id: str | None
    master_id: str | None
    primary_system: str
    status: str  # one of CANONICAL_APPLICATION_STATES
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in CANONICAL_APPLICATION_STATES:
            raise ValueError(f"{self.status!r} is not a canonical application state")


@dataclass(frozen=True)
class Grievance:
    grievance_id: str
    subject: str
    status: str
    department_code: str | None = None


@dataclass(frozen=True)
class Approval:
    approval_id: str
    application_id: str
    approved_by: str | None
    status: str  # "pending" | "approved" | "rejected"
    decided_at: datetime | None = None


@dataclass(frozen=True)
class Beneficiary:
    beneficiary_id: str
    master_id: str | None
    name: str
    mobile: str | None = None


@dataclass(frozen=True)
class Consent:
    """Canonical view of ``app.db.models.interop_platform.InteropConsentGrant`` - the fields a
    connector or workflow step needs to check field-level authorization against."""

    consent_id: str
    master_id: str
    requesting_system: str
    providing_system: str
    purpose: str
    data_category: str
    fields: tuple[str, ...]
    status: str  # "pending" | "granted" | "denied" | "expired" | "revoked"


@dataclass(frozen=True)
class Event:
    event_id: str
    event_type: str
    source_system: str
    destination: str | None
    entity_id: str | None
    correlation_id: str
    occurred_at: datetime
    schema_version: str = SCHEMA_VERSION
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Workflow:
    workflow_id: str
    name: str
    status: str


@dataclass(frozen=True)
class Notification:
    notification_id: str
    recipient_master_id: str | None
    channel: str
    message: str

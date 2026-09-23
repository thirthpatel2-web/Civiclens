"""Interoperability middleware schema: three independent mock government systems (each with its
own identifier vocabulary, deliberately different from the others), master identity resolution,
a connector registry, fine-grained per-exchange consent grants, and a cross-system unified
application tracker. See docs/INTEROPERABILITY.md for the architecture this backs.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at, jsonb, tstz, uuid_pk

# ---------------------------------------------------------------------------------------------
# Mock Department A: Citizen/Resident Records System - identifier vocabulary: resident_id
# ---------------------------------------------------------------------------------------------


class MockDeptAResident(Base):
    __tablename__ = "mockgov_a_residents"
    resident_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    mobile: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[str] = mapped_column(String(400), nullable=False)
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = created_at()


class MockDeptADocument(Base):
    __tablename__ = "mockgov_a_documents"
    document_id: Mapped[str] = uuid_pk()
    resident_id: Mapped[str] = mapped_column(ForeignKey("mockgov_a_residents.resident_id", ondelete="CASCADE"), nullable=False)
    document_type: Mapped[str] = mapped_column(String(60), nullable=False)  # e.g. "residence_certificate"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="verified")  # verified | pending | rejected
    reference_no: Mapped[str] = mapped_column(String(60), nullable=False)
    issued_on: Mapped[datetime] = tstz(False)
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (Index("ix_mockgov_a_documents_resident_id", "resident_id"),)


# ---------------------------------------------------------------------------------------------
# Mock Department B: Certificate/Document Verification + Application System -
# identifier vocabulary: beneficiary_code, application_no (deliberately unrelated to Dept A's)
# ---------------------------------------------------------------------------------------------


class MockDeptBBeneficiary(Base):
    __tablename__ = "mockgov_b_beneficiaries"
    beneficiary_code: Mapped[str] = mapped_column(String(40), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    mobile_number: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = created_at()


class MockDeptBApplication(Base):
    __tablename__ = "mockgov_b_applications"
    application_no: Mapped[str] = mapped_column(String(40), primary_key=True)
    beneficiary_code: Mapped[str] = mapped_column(ForeignKey("mockgov_b_beneficiaries.beneficiary_code", ondelete="CASCADE"), nullable=False)
    service_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_document")  # pending_document | processing | approved | rejected
    required_document_type: Mapped[str] = mapped_column(String(60), nullable=False)
    document_status: Mapped[str] = mapped_column(String(30), nullable=False, default="missing")  # missing | requested | received | verified
    document_reference: Mapped[str | None] = mapped_column(String(60), nullable=True)  # Dept A's reference_no, once fetched - never re-uploaded
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = tstz(False)
    __table_args__ = (Index("ix_mockgov_b_applications_beneficiary_code", "beneficiary_code"),)


# ---------------------------------------------------------------------------------------------
# Mock Department C: Grievance/Service Application System - identifier vocabulary: grievance_ref
# (the third independent system - not used by the headline demo, but real and queryable, so the
# "at least 3 mock systems, each independent" requirement is a fact, not a claim)
# ---------------------------------------------------------------------------------------------


class MockDeptCGrievance(Base):
    __tablename__ = "mockgov_c_grievances"
    grievance_ref: Mapped[str] = mapped_column(String(40), primary_key=True)
    citizen_ref: Mapped[str] = mapped_column(String(40), nullable=False)  # Dept C's own name for "whoever filed this" - not resident_id or beneficiary_code
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    department: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = created_at()


# ---------------------------------------------------------------------------------------------
# Master Data Management: resolves the same real-world citizen across the systems above (and
# CivicLens's own users table) into one master entity, with a confidence score per link -
# never auto-merged below the confidence threshold; ambiguous links wait for officer review.
# ---------------------------------------------------------------------------------------------


class MasterEntity(Base):
    __tablename__ = "interop_master_entities"
    master_id: Mapped[str] = uuid_pk()
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = created_at()


class MasterIdentifier(Base):
    """One (system, identifier) pair linked to a master entity, with the confidence that link was made at."""

    __tablename__ = "interop_master_identifiers"
    id: Mapped[str] = uuid_pk()
    master_id: Mapped[str] = mapped_column(ForeignKey("interop_master_entities.master_id", ondelete="CASCADE"), nullable=False)
    system: Mapped[str] = mapped_column(String(40), nullable=False)  # "dept_a" | "dept_b" | "dept_c" | "civiclens"
    identifier_type: Mapped[str] = mapped_column(String(40), nullable=False)  # "resident_id" | "beneficiary_code" | "grievance_citizen_ref" | "user_id"
    identifier_value: Mapped[str] = mapped_column(String(80), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0-1.0; 1.0 = exact verified identifier
    matched_on: Mapped[str] = mapped_column(String(200), nullable=False)  # human-readable: what evidence produced this link
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (
        UniqueConstraint("system", "identifier_type", "identifier_value", name="uq_interop_master_identifiers_system_type_value"),
        Index("ix_interop_master_identifiers_master_id", "master_id"),
    )


class IdentityMatchCandidate(Base):
    """A link the resolver found but would not auto-confirm (below threshold, or conflicting) -
    queued for an officer to confirm or reject, never applied silently."""

    __tablename__ = "interop_identity_match_candidates"
    id: Mapped[str] = uuid_pk()
    master_id: Mapped[str] = mapped_column(ForeignKey("interop_master_entities.master_id", ondelete="CASCADE"), nullable=False)
    system: Mapped[str] = mapped_column(String(40), nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(40), nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(80), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending | confirmed | rejected
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = tstz()
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (Index("ix_interop_identity_match_candidates_status", "status"),)


# ---------------------------------------------------------------------------------------------
# Fine-grained, per-exchange consent (distinct from the broad profile-level consent purposes in
# app/services/profile_service.py - this is the "share exactly this data, with this department,
# for this long" artifact SIH26129's consent-management requirement actually describes).
# ---------------------------------------------------------------------------------------------


class InteropConsentGrant(Base):
    __tablename__ = "interop_consent_grants"
    consent_id: Mapped[str] = uuid_pk()
    master_id: Mapped[str] = mapped_column(ForeignKey("interop_master_entities.master_id", ondelete="CASCADE"), nullable=False)
    citizen_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    requesting_system: Mapped[str] = mapped_column(String(40), nullable=False)
    providing_system: Mapped[str] = mapped_column(String(40), nullable=False)
    purpose: Mapped[str] = mapped_column(String(200), nullable=False)
    data_category: Mapped[str] = mapped_column(String(80), nullable=False)
    fields: Mapped[list] = jsonb(list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending | granted | denied | expired | revoked
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime | None] = tstz()
    decided_at: Mapped[datetime | None] = tstz()
    revoked_at: Mapped[datetime | None] = tstz()
    revocation_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    __table_args__ = (Index("ix_interop_consent_grants_master_id", "master_id"), Index("ix_interop_consent_grants_status", "status"))


# ---------------------------------------------------------------------------------------------
# Connector Registry: metadata + live health for every connector (mock systems above, plus the
# existing app.integrations government adapters) - enable/disable without touching business logic.
# ---------------------------------------------------------------------------------------------


class ConnectorRegistration(Base):
    __tablename__ = "interop_connector_registry"
    connector_id: Mapped[str] = mapped_column(String(60), primary_key=True)  # "dept_a" | "dept_b" | "dept_c" | "cpgrams" | ...
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    department: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    supported_operations: Mapped[list] = jsonb(list)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    health_state: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")  # healthy | degraded | unavailable | not_configured | unknown
    last_health_check: Mapped[datetime | None] = tstz()
    last_success_at: Mapped[datetime | None] = tstz()
    last_failure_at: Mapped[datetime | None] = tstz()
    total_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_response_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = created_at()


# ---------------------------------------------------------------------------------------------
# Every interoperability exchange, end to end - the thing a judge/admin can click through.
# ---------------------------------------------------------------------------------------------


class InteropTransaction(Base):
    __tablename__ = "interop_transactions"
    transaction_id: Mapped[str] = uuid_pk()
    correlation_id: Mapped[str] = mapped_column(String(60), nullable=False)
    operation: Mapped[str] = mapped_column(String(60), nullable=False)  # e.g. "document_exchange"
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    target_system: Mapped[str] = mapped_column(String(40), nullable=False)
    master_id: Mapped[str | None] = mapped_column(ForeignKey("interop_master_entities.master_id"), nullable=True)
    consent_id: Mapped[str | None] = mapped_column(ForeignKey("interop_consent_grants.consent_id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # success | failed | pending_consent | rejected
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(400), nullable=True)
    fields_exchanged: Mapped[list] = jsonb(list)  # the destination system's own field names for what was actually written
    requested_fields: Mapped[list] = jsonb(list)  # canonical field names this operation needed to read from the source
    approved_fields: Mapped[list] = jsonb(list)  # consent.fields at the moment this transaction ran - the field-level authorization actually checked
    denied_fields: Mapped[list] = jsonb(list)  # requested_fields not in approved_fields - non-empty only when status="failed", error_code="data_field_not_consented"
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (Index("ix_interop_transactions_correlation_id", "correlation_id"), Index("ix_interop_transactions_master_id", "master_id"))


# ---------------------------------------------------------------------------------------------
# Unified Application Tracker: one timeline for a service that crosses department boundaries.
# ---------------------------------------------------------------------------------------------


class UnifiedApplication(Base):
    __tablename__ = "interop_unified_applications"
    application_id: Mapped[str] = uuid_pk()
    reference: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)  # e.g. CL-APP-1001
    master_id: Mapped[str] = mapped_column(ForeignKey("interop_master_entities.master_id", ondelete="CASCADE"), nullable=False)
    service_type: Mapped[str] = mapped_column(String(120), nullable=False)
    primary_system: Mapped[str] = mapped_column(String(40), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(60), nullable=True)  # the primary system's own application_no etc.
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="in_progress")  # in_progress | completed | rejected
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = tstz(False)


class UnifiedApplicationEvent(Base):
    __tablename__ = "interop_unified_application_events"
    id: Mapped[str] = uuid_pk()
    application_id: Mapped[str] = mapped_column(ForeignKey("interop_unified_applications.application_id", ondelete="CASCADE"), nullable=False)
    step: Mapped[str] = mapped_column(String(120), nullable=False)
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    detail: Mapped[dict] = jsonb(dict)
    occurred_at: Mapped[datetime] = created_at()
    __table_args__ = (Index("ix_interop_unified_application_events_application_id", "application_id"),)


# ---------------------------------------------------------------------------------------------
# Mock Government Identity Provider (federated identity / SSO, demo) - an OAuth2
# client_credentials-style authorization server every connector authenticates against before
# it's used. See app/interop/federation/idp.py. Every row here is DEMO data for the mock IdP -
# never a real government identity provider credential.
# ---------------------------------------------------------------------------------------------


class FederationClient(Base):
    __tablename__ = "interop_federation_clients"
    client_id: Mapped[str] = mapped_column(String(60), primary_key=True)  # e.g. "dept_a" - one per connector
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    client_secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    system: Mapped[str] = mapped_column(String(40), nullable=False)  # which connector/department this client represents
    allowed_scopes: Mapped[list] = jsonb(list)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = created_at()


class FederationToken(Base):
    __tablename__ = "interop_federation_tokens"
    token_id: Mapped[str] = uuid_pk()
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex of the raw bearer token - only the hash is ever stored
    client_id: Mapped[str] = mapped_column(ForeignKey("interop_federation_clients.client_id", ondelete="CASCADE"), nullable=False)
    scope: Mapped[list] = jsonb(list)
    issued_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = tstz(False)
    revoked_at: Mapped[datetime | None] = tstz()
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_interop_federation_tokens_token_hash"),
        Index("ix_interop_federation_tokens_client_id", "client_id"),
    )


# ---------------------------------------------------------------------------------------------
# Configurable interop workflows (Section 12) - a stored, ordered step sequence the workflow
# engine (app/interop/workflow/engine.py) executes, instead of a single hard-coded scenario in
# Python control flow. See docs/INTEROPERABILITY.md's "Configurable workflows" section.
# ---------------------------------------------------------------------------------------------


class WorkflowDefinition(Base):
    __tablename__ = "interop_workflow_definitions"
    workflow_id: Mapped[str] = mapped_column(String(80), primary_key=True)  # e.g. "residence_certificate_verification"
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1")
    steps: Mapped[list] = jsonb(list)  # ordered list of step dicts - see engine.py's StepSpec for the exact shape
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = created_at()


class WorkflowExecution(Base):
    __tablename__ = "interop_workflow_executions"
    execution_id: Mapped[str] = uuid_pk()
    workflow_id: Mapped[str] = mapped_column(ForeignKey("interop_workflow_definitions.workflow_id"), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")  # running | completed | failed | waiting_approval
    current_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    context: Mapped[dict] = jsonb(dict)  # accumulated step outputs, merged as each step completes
    started_at: Mapped[datetime] = created_at()
    finished_at: Mapped[datetime | None] = tstz()
    __table_args__ = (Index("ix_interop_workflow_executions_workflow_id", "workflow_id"), Index("ix_interop_workflow_executions_correlation_id", "correlation_id"))


class WorkflowStepExecution(Base):
    __tablename__ = "interop_workflow_step_executions"
    id: Mapped[str] = uuid_pk()
    execution_id: Mapped[str] = mapped_column(ForeignKey("interop_workflow_executions.execution_id", ondelete="CASCADE"), nullable=False)
    step_id: Mapped[str] = mapped_column(String(80), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # pending | running | completed | failed | skipped
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error_message: Mapped[str | None] = mapped_column(String(400), nullable=True)
    started_at: Mapped[datetime | None] = tstz()
    finished_at: Mapped[datetime | None] = tstz()
    __table_args__ = (Index("ix_interop_workflow_step_executions_execution_id", "execution_id"),)


# ---------------------------------------------------------------------------------------------
# Data quality rule configuration (Section 15) - a named, versioned rule set an authorized admin
# could edit (no UI to edit them yet - see docs/REQUIREMENT_TRACEABILITY.md); the storage and
# evaluation (app/interop/quality/engine.py) are real regardless.
# ---------------------------------------------------------------------------------------------


class QualityRuleSet(Base):
    __tablename__ = "interop_quality_rule_sets"
    ruleset_id: Mapped[str] = mapped_column(String(80), primary_key=True)  # e.g. "residence_certificate_v1"
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1")
    rules: Mapped[list] = jsonb(list)  # list of QualityRule dicts (engine.py's QualityRule.to_dict())
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = created_at()


# ---------------------------------------------------------------------------------------------
# Central exception management (Section 16-18): one consistent taxonomy across every layer of the
# interop platform, with retry/dead-letter state - distinct from the pre-existing
# IntegrationExceptionRecord/ExceptionService (app/services/interop_service.py), which is a
# simpler "log a malformed inbound payload for a human to review" queue with no taxonomy, no
# correlation_id, and no retry tracking. Both are real; neither replaces the other.
# ---------------------------------------------------------------------------------------------


class InteropException(Base):
    __tablename__ = "interop_exceptions"
    exception_id: Mapped[str] = uuid_pk()
    error_code: Mapped[str] = mapped_column(String(40), nullable=False)  # one of app.interop.exceptions.taxonomy.EXCEPTION_TYPES
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_system: Mapped[str | None] = mapped_column(String(40), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    retryable: Mapped[bool] = mapped_column(nullable=False, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_action: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolution_state: Mapped[str] = mapped_column(String(20), nullable=False, default="open")  # open | retrying | resolved | dead
    created_at: Mapped[datetime] = created_at()
    resolved_at: Mapped[datetime | None] = tstz()
    __table_args__ = (
        Index("ix_interop_exceptions_correlation_id", "correlation_id"),
        Index("ix_interop_exceptions_resolution_state", "resolution_state"),
    )

"""Initial schema (generated from app/db/models by scripts/generate_initial_migration.py).

Revision ID: 0001
Revises: 
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_snapshots",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("scope", sa.String(60), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_analytics_snapshots"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("resource_type", sa.String(40), nullable=True),
        sa.Column("resource_id", sa.String(80), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_audit_logs"),
    )
    op.create_table(
        "cities",
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('code', name="pk_cities"),
    )
    op.create_table(
        "departments",
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('code', name="pk_departments"),
    )
    op.create_table(
        "anomalies",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("department_code", sa.String(40), nullable=True),
        sa.Column("status", sa.String(14), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dedupe_key", sa.String(300), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_anomalies"),
        sa.ForeignKeyConstraint(["department_code"], ["departments.code"], name="fk_anomalies_department_code_departments"),
    )
    op.create_table(
        "civic_services",
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("department_code", sa.String(40), nullable=False),
        sa.PrimaryKeyConstraint('code', name="pk_civic_services"),
        sa.ForeignKeyConstraint(["department_code"], ["departments.code"], name="fk_civic_services_department_code_departments"),
    )
    op.create_table(
        "government_offices",
        sa.Column("id", sa.String(60), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("department_code", sa.String(40), nullable=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("address", sa.String(300), nullable=True),
        sa.Column("city_code", sa.String(60), nullable=True),
        sa.PrimaryKeyConstraint('id', name="pk_government_offices"),
        sa.ForeignKeyConstraint(["department_code"], ["departments.code"], name="fk_government_offices_department_code_departments"),
        sa.ForeignKeyConstraint(["city_code"], ["cities.code"], name="fk_government_offices_city_code_cities"),
    )
    op.create_table(
        "government_platforms",
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('platform', name="pk_government_platforms"),
    )
    op.create_table(
        "integration_health",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("avg_response_ms", sa.Float(), nullable=True),
        sa.Column("total_calls", sa.Integer(), nullable=False),
        sa.Column("total_failures", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_integration_health"),
        sa.ForeignKeyConstraint(["platform"], ["government_platforms.platform"], name="fk_integration_health_platform_government_platforms"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("worker_id", sa.String(80), nullable=True),
        sa.PrimaryKeyConstraint('id', name="pk_jobs"),
        sa.UniqueConstraint('idempotency_key', name='uq_jobs_idempotency_key'),
    )
    op.create_table(
        "legal_precedents",
        sa.Column("cnr", sa.String(40), nullable=False),
        sa.Column("neutral_citation", sa.String(30), nullable=False),
        sa.Column("reporter_citation", sa.String(40), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("petitioner", sa.Text(), nullable=True),
        sa.Column("respondent", sa.Text(), nullable=True),
        sa.Column("judges", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decision_date", sa.Date(), nullable=False),
        sa.Column("disposal", sa.String(80), nullable=True),
        sa.Column("court", sa.String(80), nullable=False),
        sa.Column("languages", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_path", sa.String(300), nullable=True),
        sa.Column("scraped_at", sa.String(40), nullable=True),
        sa.PrimaryKeyConstraint('cnr', name="pk_legal_precedents"),
        sa.UniqueConstraint('reporter_citation', name='uq_legal_precedents_reporter_citation'),
    )
    op.create_table(
        "routing_rules",
        sa.Column("id", sa.String(60), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("department_code", sa.String(40), nullable=False),
        sa.Column("service_code", sa.String(60), nullable=True),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("keywords_any", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("wards", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("min_severity", sa.String(10), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_routing_rules"),
        sa.ForeignKeyConstraint(["department_code"], ["departments.code"], name="fk_routing_rules_department_code_departments"),
    )
    op.create_table(
        "scheduler_state",
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('name', name="pk_scheduler_state"),
    )
    op.create_table(
        "sla_policies",
        sa.Column("id", sa.String(60), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("department_code", sa.String(40), nullable=True),
        sa.Column("resolution_hours", sa.Integer(), nullable=False),
        sa.Column("approaching_fraction", sa.Float(), nullable=False),
        sa.Column("escalation_gap_hours", sa.Integer(), nullable=False),
        sa.Column("max_level", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_sla_policies"),
        sa.ForeignKeyConstraint(["department_code"], ["departments.code"], name="fk_sla_policies_department_code_departments"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("department_code", sa.String(40), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint('id', name="pk_users"),
        sa.ForeignKeyConstraint(["department_code"], ["departments.code"], name="fk_users_department_code_departments"),
        sa.UniqueConstraint('email', name='uq_users_email'),
    )
    op.create_table(
        "ai_conversations",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_ai_conversations"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_ai_conversations_user_id_users", ondelete='CASCADE'),
    )
    op.create_table(
        "ai_messages",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("conversation_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=True),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("database_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_ai_messages"),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_conversations.id"], name="fk_ai_messages_conversation_id_ai_conversations", ondelete='CASCADE'),
    )
    op.create_table(
        "complaints",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("reference", sa.String(32), nullable=False),
        sa.Column("citizen_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("language", sa.String(5), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("subcategory", sa.String(60), nullable=True),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("complaint_type", sa.String(20), nullable=False),
        sa.Column("department_code", sa.String(40), nullable=True),
        sa.Column("service_code", sa.String(60), nullable=True),
        sa.Column("ward", sa.String(40), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("address", sa.String(300), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("assigned_officer_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalation_level", sa.Integer(), nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_request_id", sa.String(64), nullable=True),
        sa.Column("ai_status", sa.String(30), nullable=False),
        sa.Column("classification", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("routing", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("duplicates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("priority_factors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("has_duplicates", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_complaints"),
        sa.ForeignKeyConstraint(["citizen_id"], ["users.id"], name="fk_complaints_citizen_id_users"),
        sa.ForeignKeyConstraint(["department_code"], ["departments.code"], name="fk_complaints_department_code_departments"),
        sa.ForeignKeyConstraint(["assigned_officer_id"], ["users.id"], name="fk_complaints_assigned_officer_id_users"),
        sa.UniqueConstraint('reference', name='uq_complaints_reference'),
        sa.UniqueConstraint('citizen_id', 'client_request_id', name='uq_complaints_citizen_client_request'),
    )
    op.create_table(
        "complaint_events",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("complaint_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("from_status", sa.String(30), nullable=True),
        sa.Column("to_status", sa.String(30), nullable=True),
        sa.Column("actor_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("actor_label", sa.String(120), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("internal", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_complaint_events"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], name="fk_complaint_events_complaint_id_complaints", ondelete='CASCADE'),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_complaint_events_actor_id_users"),
    )
    op.create_table(
        "complaint_evidence",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("complaint_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("uploader_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("mime", sa.String(100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_name", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("analysis_status", sa.String(40), nullable=False),
        sa.Column("analysis_provider", sa.String(40), nullable=True),
        sa.Column("analysis_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("analysis_error", sa.String(300), nullable=True),
        sa.PrimaryKeyConstraint('id', name="pk_complaint_evidence"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], name="fk_complaint_evidence_complaint_id_complaints", ondelete='CASCADE'),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.id"], name="fk_complaint_evidence_uploader_id_users"),
        sa.UniqueConstraint('storage_name', name='uq_complaint_evidence_storage_name'),
    )
    op.create_table(
        "consent_records",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("policy_version", sa.String(20), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_consent_records"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_consent_records_user_id_users", ondelete='CASCADE'),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("owner_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("mime", sa.String(100), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_name", sa.String(64), nullable=False),
        sa.Column("visibility", sa.String(12), nullable=False),
        sa.Column("department_code", sa.String(40), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("semantic_indexed", sa.Boolean(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("linked_type", sa.String(20), nullable=True),
        sa.Column("linked_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_documents"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_documents_owner_id_users"),
        sa.ForeignKeyConstraint(["department_code"], ["departments.code"], name="fk_documents_department_code_departments"),
        sa.UniqueConstraint('storage_name', name='uq_documents_storage_name'),
    )
    op.create_table(
        "document_chunks",
        sa.Column("chunk_id", sa.String(80), nullable=False),
        sa.Column("document_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("document_name", sa.String(120), nullable=False),
        sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("heading", sa.String(200), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint('chunk_id', name="pk_document_chunks"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name="fk_document_chunks_document_id_documents", ondelete='CASCADE'),
    )
    op.create_table(
        "drafts",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("client_request_id", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("result_ref", sa.String(40), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_drafts"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_drafts_user_id_users", ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'client_request_id', name='uq_drafts_user_client_request'),
    )
    op.create_table(
        "duplicate_reviews",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("complaint_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("other_complaint_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_duplicate_reviews"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], name="fk_duplicate_reviews_complaint_id_complaints", ondelete='CASCADE'),
        sa.ForeignKeyConstraint(["other_complaint_id"], ["complaints.id"], name="fk_duplicate_reviews_other_complaint_id_complaints", ondelete='CASCADE'),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name="fk_duplicate_reviews_reviewer_id_users"),
    )
    op.create_table(
        "feedback",
        sa.Column("complaint_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("citizen_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('complaint_id', name="pk_feedback"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], name="fk_feedback_complaint_id_complaints", ondelete='CASCADE'),
        sa.ForeignKeyConstraint(["citizen_id"], ["users.id"], name="fk_feedback_citizen_id_users"),
    )
    op.create_table(
        "investigations",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("subject_type", sa.String(12), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("opened_by", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("department_code", sa.String(40), nullable=True),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_investigations"),
        sa.ForeignKeyConstraint(["opened_by"], ["users.id"], name="fk_investigations_opened_by_users"),
        sa.ForeignKeyConstraint(["department_code"], ["departments.code"], name="fk_investigations_department_code_departments"),
    )
    op.create_table(
        "legal_analyses",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint('id', name="pk_legal_analyses"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_legal_analyses_user_id_users"),
    )
    op.create_table(
        "mfa_configs",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_used_step", sa.Integer(), nullable=False),
        sa.Column("backup_code_hashes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('user_id', name="pk_mfa_configs"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_mfa_configs_user_id_users", ondelete='CASCADE'),
    )
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("in_app", sa.Boolean(), nullable=False),
        sa.Column("email", sa.Boolean(), nullable=False),
        sa.Column("muted_kinds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint('user_id', name="pk_notification_preferences"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_notification_preferences_user_id_users", ondelete='CASCADE'),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.String(1000), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("channel", sa.String(12), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("dedupe_key", sa.String(160), nullable=True),
        sa.PrimaryKeyConstraint('id', name="pk_notifications"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_notifications_user_id_users", ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'dedupe_key', name='uq_notifications_user_dedupe_key'),
    )
    op.create_table(
        "password_reset_tokens",
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('token_hash', name="pk_password_reset_tokens"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_password_reset_tokens_user_id_users", ondelete='CASCADE'),
    )
    op.create_table(
        "profiles",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("ward", sa.String(40), nullable=True),
        sa.Column("language", sa.String(5), nullable=False),
        sa.Column("onboarding_complete", sa.Boolean(), nullable=False),
        sa.Column("designation", sa.String(120), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('user_id', name="pk_profiles"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_profiles_user_id_users", ondelete='CASCADE'),
    )
    op.create_table(
        "rti_applications",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("owner_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("draft", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("reference", sa.String(32), nullable=True),
        sa.Column("generated_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_is_estimate", sa.Boolean(), nullable=False),
        sa.Column("reminders_sent", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_rti_applications"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_rti_applications_owner_id_users"),
        sa.UniqueConstraint('reference', name='uq_rti_applications_reference'),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mfa_verified", sa.Boolean(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name="pk_sessions"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete='CASCADE'),
        sa.UniqueConstraint('token_hash', name='uq_sessions_token_hash'),
    )
    op.create_table(
        "voice_transcripts",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("mime", sa.String(40), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("language_requested", sa.String(5), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("language_detected", sa.String(5), nullable=True),
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint('id', name="pk_voice_transcripts"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_voice_transcripts_user_id_users"),
    )
    op.create_table(
        "wards",
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("city_code", sa.String(60), nullable=True),
        sa.PrimaryKeyConstraint('code', name="pk_wards"),
        sa.ForeignKeyConstraint(["city_code"], ["cities.code"], name="fk_wards_city_code_cities"),
    )
    op.create_index('ix_analytics_snapshots_scope_taken', "analytics_snapshots", ['scope', 'taken_at'])
    op.create_index('ix_audit_logs_occurred_at', "audit_logs", ['occurred_at'])
    op.create_index('ix_audit_logs_actor_id', "audit_logs", ['actor_id'])
    op.create_index('ix_audit_logs_resource', "audit_logs", ['resource_type', 'resource_id'])
    op.create_index('ix_audit_logs_action', "audit_logs", ['action'])
    op.create_index('ix_anomalies_status_detected', "anomalies", ['status', 'detected_at'])
    op.create_index('ix_anomalies_dedupe_key', "anomalies", ['dedupe_key'])
    op.create_index('ix_civic_services_department_code', "civic_services", ['department_code'])
    op.create_index('ix_integration_health_platform_checked_at', "integration_health", ['platform', 'checked_at'])
    op.create_index('ix_jobs_status_updated', "jobs", ['status', 'updated_at'])
    op.create_index('ix_legal_precedents_neutral_citation', "legal_precedents", ['neutral_citation'])
    op.create_index('ix_legal_precedents_decision_date', "legal_precedents", ['decision_date'])
    op.create_index('ix_routing_rules_priority', "routing_rules", ['priority'])
    op.create_index('ix_users_role', "users", ['role'])
    op.create_index('ix_users_department_code', "users", ['department_code'])
    op.create_index('ix_ai_conversations_user_id', "ai_conversations", ['user_id'])
    op.create_index('ix_ai_messages_conversation_at', "ai_messages", ['conversation_id', 'at'])
    op.create_index('ix_complaints_citizen_created', "complaints", ['citizen_id', 'created_at'])
    op.create_index('ix_complaints_department_status', "complaints", ['department_code', 'status'])
    op.create_index('ix_complaints_assigned_officer_status', "complaints", ['assigned_officer_id', 'status'])
    op.create_index('ix_complaints_category_created', "complaints", ['category', 'created_at'])
    op.create_index('ix_complaints_ward', "complaints", ['ward'])
    op.create_index('ix_complaints_sla_due_at', "complaints", ['sla_due_at'])
    op.create_index('ix_complaint_events_complaint_at', "complaint_events", ['complaint_id', 'at'])
    op.create_index('ix_complaint_evidence_complaint_id', "complaint_evidence", ['complaint_id'])
    op.create_index('ix_consent_records_user_purpose_at', "consent_records", ['user_id', 'purpose', 'at'])
    op.create_index('ix_documents_owner_id', "documents", ['owner_id'])
    op.create_index('ix_documents_status', "documents", ['status'])
    op.create_index('ix_documents_linked', "documents", ['linked_type', 'linked_id'])
    op.create_index('ix_document_chunks_document_id', "document_chunks", ['document_id'])
    op.create_index('ix_duplicate_reviews_complaint_id', "duplicate_reviews", ['complaint_id'])
    op.create_index('ix_investigations_department_status', "investigations", ['department_code', 'status'])
    op.create_index('ix_investigations_subject', "investigations", ['subject_type', 'subject_id'])
    op.create_index('ix_legal_analyses_user_id', "legal_analyses", ['user_id'])
    op.create_index('ix_notifications_user_created', "notifications", ['user_id', 'created_at'])
    op.create_index('ix_notifications_user_unread', "notifications", ['user_id', 'read_at'])
    op.create_index('ix_password_reset_tokens_user_id', "password_reset_tokens", ['user_id'])
    op.create_index('ix_rti_applications_owner_id', "rti_applications", ['owner_id'])
    op.create_index('ix_rti_applications_status_due', "rti_applications", ['status', 'due_at'])
    op.create_index('ix_sessions_user_id', "sessions", ['user_id'])
    op.create_index('ix_voice_transcripts_user_id', "voice_transcripts", ['user_id'])
    op.create_index('ix_wards_city_code', "wards", ['city_code'])


def downgrade() -> None:
    op.drop_table("wards")
    op.drop_table("voice_transcripts")
    op.drop_table("sessions")
    op.drop_table("rti_applications")
    op.drop_table("profiles")
    op.drop_table("password_reset_tokens")
    op.drop_table("notifications")
    op.drop_table("notification_preferences")
    op.drop_table("mfa_configs")
    op.drop_table("legal_analyses")
    op.drop_table("investigations")
    op.drop_table("feedback")
    op.drop_table("duplicate_reviews")
    op.drop_table("drafts")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("consent_records")
    op.drop_table("complaint_evidence")
    op.drop_table("complaint_events")
    op.drop_table("complaints")
    op.drop_table("ai_messages")
    op.drop_table("ai_conversations")
    op.drop_table("users")
    op.drop_table("sla_policies")
    op.drop_table("scheduler_state")
    op.drop_table("routing_rules")
    op.drop_table("legal_precedents")
    op.drop_table("jobs")
    op.drop_table("integration_health")
    op.drop_table("government_platforms")
    op.drop_table("government_offices")
    op.drop_table("civic_services")
    op.drop_table("anomalies")
    op.drop_table("departments")
    op.drop_table("cities")
    op.drop_table("audit_logs")
    op.drop_table("analytics_snapshots")

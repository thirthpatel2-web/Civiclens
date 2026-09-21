"""Multilingual/voice fields, mobile sessions, job lifecycle timestamps, workflow rules, emergency contacts, government submissions, push devices.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emergency_contacts",
        sa.Column("id", sa.String(60), nullable=False),
        sa.Column("number", sa.String(20), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("city_code", sa.String(60), nullable=True),
        sa.Column("translations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_emergency_contacts"),
        sa.ForeignKeyConstraint(["city_code"], ["cities.code"], name="fk_emergency_contacts_city_code_cities"),
    )
    op.create_table(
        "government_submissions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("complaint_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("platform", sa.String(40), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("external_reference", sa.String(120), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("requested_by", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name="pk_government_submissions"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], name="fk_government_submissions_complaint_id_complaints", ondelete='CASCADE'),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], name="fk_government_submissions_requested_by_users"),
        sa.UniqueConstraint('complaint_id', 'platform', name='uq_government_submissions_complaint_platform'),
    )
    op.create_table(
        "push_devices",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("token", sa.String(200), nullable=False),
        sa.Column("platform", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_push_devices"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_push_devices_user_id_users", ondelete='CASCADE'),
        sa.UniqueConstraint('token', name='uq_push_devices_token'),
    )
    op.create_table(
        "workflow_rules",
        sa.Column("id", sa.String(60), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("trigger", sa.String(40), nullable=False),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_workflow_rules"),
    )
    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("rule_id", sa.String(60), nullable=False),
        sa.Column("complaint_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(200), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_workflow_executions"),
        sa.ForeignKeyConstraint(["rule_id"], ["workflow_rules.id"], name="fk_workflow_executions_rule_id_workflow_rules", ondelete='CASCADE'),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], name="fk_workflow_executions_complaint_id_complaints", ondelete='CASCADE'),
        sa.UniqueConstraint('rule_id', 'complaint_id', name='uq_workflow_executions_rule_complaint'),
    )
    op.add_column("complaints", sa.Column("detected_language", sa.String(5), nullable=True))
    op.add_column("complaints", sa.Column("translated_text", sa.Text(), nullable=True))
    op.add_column("complaints", sa.Column("translated_language", sa.String(5), nullable=True))
    op.add_column("complaints", sa.Column("translation_provider", sa.String(40), nullable=True))
    op.add_column("complaints", sa.Column("input_method", sa.String(10), nullable=False, server_default='typed'))
    op.add_column("complaints", sa.Column("voice_id", sa.String(36), nullable=True))
    op.add_column("voice_transcripts", sa.Column("detected_by", sa.String(10), nullable=True))
    op.add_column("voice_transcripts", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("voice_transcripts", sa.Column("script_ok", sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column("voice_transcripts", sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("sessions", sa.Column("kind", sa.String(10), nullable=False, server_default='web'))
    op.add_column("jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_emergency_contacts_scope_city', "emergency_contacts", ['scope', 'city_code'])
    op.create_index('ix_government_submissions_state', "government_submissions", ['state'])
    op.create_index('ix_push_devices_user_id', "push_devices", ['user_id'])
    op.create_index('ix_workflow_rules_trigger_active', "workflow_rules", ['trigger', 'active'])


def downgrade() -> None:
    op.drop_column("jobs", "finished_at")
    op.drop_column("jobs", "started_at")
    op.drop_column("sessions", "kind")
    op.drop_column("voice_transcripts", "warnings")
    op.drop_column("voice_transcripts", "script_ok")
    op.drop_column("voice_transcripts", "confidence")
    op.drop_column("voice_transcripts", "detected_by")
    op.drop_column("complaints", "voice_id")
    op.drop_column("complaints", "input_method")
    op.drop_column("complaints", "translation_provider")
    op.drop_column("complaints", "translated_language")
    op.drop_column("complaints", "translated_text")
    op.drop_column("complaints", "detected_language")
    op.drop_table("workflow_executions")
    op.drop_table("workflow_rules")
    op.drop_table("push_devices")
    op.drop_table("government_submissions")
    op.drop_table("emergency_contacts")

"""Interoperability layer support (Golden Record links, integration exception queue, cross-portal tracking) and classification-correction capture for the learning loop.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "citizen_external_ids",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("id_type", sa.String(30), nullable=False),
        sa.Column("id_hash", sa.String(128), nullable=False),
        sa.Column("last4", sa.String(8), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_citizen_external_ids"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_citizen_external_ids_user_id_users", ondelete='CASCADE'),
        sa.UniqueConstraint('id_type', 'id_hash', name='uq_citizen_external_ids_type_hash'),
    )
    op.create_table(
        "classification_corrections",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("complaint_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("text_snapshot", sa.String(2000), nullable=False),
        sa.Column("previous_category", sa.String(30), nullable=False),
        sa.Column("corrected_category", sa.String(30), nullable=False),
        sa.Column("corrected_by", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_classification_corrections"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], name="fk_classification_corrections_complaint_id_complaints", ondelete='CASCADE'),
        sa.ForeignKeyConstraint(["corrected_by"], ["users.id"], name="fk_classification_corrections_corrected_by_users"),
    )
    op.create_table(
        "external_service_links",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("platform", sa.String(60), nullable=False),
        sa.Column("external_reference", sa.String(120), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status_note", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_external_service_links"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_external_service_links_user_id_users", ondelete='CASCADE'),
    )
    op.create_table(
        "integration_exceptions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("source_system", sa.String(60), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("resolution_note", sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint('id', name="pk_integration_exceptions"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], name="fk_integration_exceptions_resolved_by_users"),
    )
    op.create_index('ix_citizen_external_ids_user', "citizen_external_ids", ['user_id'])
    op.create_index('ix_classification_corrections_category', "classification_corrections", ['corrected_category'])
    op.create_index('ix_external_service_links_user', "external_service_links", ['user_id'])
    op.create_index('ix_integration_exceptions_status_detected', "integration_exceptions", ['status', 'detected_at'])


def downgrade() -> None:
    op.drop_table("integration_exceptions")
    op.drop_table("external_service_links")
    op.drop_table("classification_corrections")
    op.drop_table("citizen_external_ids")

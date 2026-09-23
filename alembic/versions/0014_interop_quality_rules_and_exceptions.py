"""interop_quality_rules_and_exceptions

Revision ID: 0014
Revises: 0013

NOTE: autogenerate also proposed dropping classification_corrections, external_service_links,
citizen_external_ids, integration_exceptions and two unrelated HNSW indexes - the same
pre-existing gap noted in 0010-0013 (those tables just aren't imported into
app/db/models/__init__.py's autogenerate scan). Pruned; not something this migration should touch.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'interop_exceptions',
        sa.Column('exception_id', sa.UUID(), nullable=False),
        sa.Column('error_code', sa.String(length=40), nullable=False),
        sa.Column('message', sa.String(length=500), nullable=False),
        sa.Column('source_system', sa.String(length=40), nullable=True),
        sa.Column('target_system', sa.String(length=40), nullable=True),
        sa.Column('correlation_id', sa.String(length=60), nullable=True),
        sa.Column('retryable', sa.Boolean(), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('max_retries', sa.Integer(), nullable=False),
        sa.Column('next_action', sa.String(length=200), nullable=True),
        sa.Column('resolution_state', sa.String(length=20), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('resolved_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('exception_id', name=op.f('pk_interop_exceptions')),
    )
    op.create_index('ix_interop_exceptions_correlation_id', 'interop_exceptions', ['correlation_id'], unique=False)
    op.create_index('ix_interop_exceptions_resolution_state', 'interop_exceptions', ['resolution_state'], unique=False)
    op.create_table(
        'interop_quality_rule_sets',
        sa.Column('ruleset_id', sa.String(length=80), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False),
        sa.Column('rules', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('ruleset_id', name=op.f('pk_interop_quality_rule_sets')),
    )


def downgrade() -> None:
    op.drop_table('interop_quality_rule_sets')
    op.drop_index('ix_interop_exceptions_resolution_state', table_name='interop_exceptions')
    op.drop_index('ix_interop_exceptions_correlation_id', table_name='interop_exceptions')
    op.drop_table('interop_exceptions')

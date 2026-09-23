"""interop_workflow_engine_tables

Revision ID: 0013
Revises: 0012

NOTE: autogenerate also proposed dropping classification_corrections, external_service_links,
citizen_external_ids, integration_exceptions and two unrelated HNSW indexes - the same
pre-existing gap noted in 0010/0011/0012 (those tables just aren't imported into
app/db/models/__init__.py's autogenerate scan). Pruned; not something this migration should touch.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'interop_workflow_definitions',
        sa.Column('workflow_id', sa.String(length=80), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False),
        sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('workflow_id', name=op.f('pk_interop_workflow_definitions')),
    )
    op.create_table(
        'interop_workflow_executions',
        sa.Column('execution_id', sa.UUID(), nullable=False),
        sa.Column('workflow_id', sa.String(length=80), nullable=False),
        sa.Column('correlation_id', sa.String(length=60), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('current_step_index', sa.Integer(), nullable=False),
        sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('finished_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workflow_id'], ['interop_workflow_definitions.workflow_id'], name=op.f('fk_interop_workflow_executions_workflow_id_interop_workflow_definitions')),
        sa.PrimaryKeyConstraint('execution_id', name=op.f('pk_interop_workflow_executions')),
    )
    op.create_index('ix_interop_workflow_executions_correlation_id', 'interop_workflow_executions', ['correlation_id'], unique=False)
    op.create_index('ix_interop_workflow_executions_workflow_id', 'interop_workflow_executions', ['workflow_id'], unique=False)
    op.create_table(
        'interop_workflow_step_executions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('execution_id', sa.UUID(), nullable=False),
        sa.Column('step_id', sa.String(length=80), nullable=False),
        sa.Column('step_index', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.String(length=400), nullable=True),
        sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('finished_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['execution_id'], ['interop_workflow_executions.execution_id'], name=op.f('fk_interop_workflow_step_executions_execution_id_interop_workflow_executions'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_interop_workflow_step_executions')),
    )
    op.create_index('ix_interop_workflow_step_executions_execution_id', 'interop_workflow_step_executions', ['execution_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_interop_workflow_step_executions_execution_id', table_name='interop_workflow_step_executions')
    op.drop_table('interop_workflow_step_executions')
    op.drop_index('ix_interop_workflow_executions_workflow_id', table_name='interop_workflow_executions')
    op.drop_index('ix_interop_workflow_executions_correlation_id', table_name='interop_workflow_executions')
    op.drop_table('interop_workflow_executions')
    op.drop_table('interop_workflow_definitions')

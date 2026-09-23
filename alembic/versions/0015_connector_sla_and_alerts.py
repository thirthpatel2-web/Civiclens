"""connector_sla_and_alerts

Revision ID: 0015
Revises: 0014

NOTE: autogenerate also proposed dropping classification_corrections, external_service_links,
citizen_external_ids, integration_exceptions and two unrelated HNSW indexes - the same
pre-existing gap noted in 0010-0014 (those tables just aren't imported into
app/db/models/__init__.py's autogenerate scan). Pruned; not something this migration should touch.

sla_status gets a server_default of 'unknown' so it applies cleanly against the existing seeded
connector rows without a NOT NULL violation; new rows always pass a real value explicitly
(`app.interop.connector_registry.seed_if_empty` sets health_state the same way already).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('interop_connector_registry', sa.Column('sla_max_avg_response_ms', sa.Float(), nullable=True))
    op.add_column('interop_connector_registry', sa.Column('sla_min_success_rate', sa.Float(), nullable=True))
    op.add_column('interop_connector_registry', sa.Column('sla_status', sa.String(length=20), nullable=False, server_default='unknown'))
    op.create_table(
        'interop_connector_alerts',
        sa.Column('alert_id', sa.UUID(), nullable=False),
        sa.Column('connector_id', sa.String(length=60), nullable=False),
        sa.Column('alert_type', sa.String(length=40), nullable=False),
        sa.Column('severity', sa.String(length=10), nullable=False),
        sa.Column('message', sa.String(length=300), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('acknowledged', sa.Boolean(), nullable=False),
        sa.Column('acknowledged_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('acknowledged_by', sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(['connector_id'], ['interop_connector_registry.connector_id'], name=op.f('fk_interop_connector_alerts_connector_id_interop_connector_registry')),
        sa.PrimaryKeyConstraint('alert_id', name=op.f('pk_interop_connector_alerts')),
    )
    op.create_index('ix_interop_connector_alerts_connector_id', 'interop_connector_alerts', ['connector_id'], unique=False)
    op.create_index('ix_interop_connector_alerts_acknowledged', 'interop_connector_alerts', ['acknowledged'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_interop_connector_alerts_acknowledged', table_name='interop_connector_alerts')
    op.drop_index('ix_interop_connector_alerts_connector_id', table_name='interop_connector_alerts')
    op.drop_table('interop_connector_alerts')
    op.drop_column('interop_connector_registry', 'sla_status')
    op.drop_column('interop_connector_registry', 'sla_min_success_rate')
    op.drop_column('interop_connector_registry', 'sla_max_avg_response_ms')

"""service_catalog_and_field_mappings

Revision ID: 0016
Revises: 0015

NOTE: autogenerate also proposed dropping classification_corrections, external_service_links,
citizen_external_ids, integration_exceptions and two unrelated HNSW indexes - the same
pre-existing gap noted in 0010-0015 (those tables just aren't imported into
app/db/models/__init__.py's autogenerate scan). Pruned; not something this migration should touch.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'interop_service_catalog',
        sa.Column('service_id', sa.String(length=80), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=False),
        sa.Column('source_system', sa.String(length=60), nullable=False),
        sa.Column('target_system', sa.String(length=60), nullable=False),
        sa.Column('data_category', sa.String(length=80), nullable=False),
        sa.Column('workflow_id', sa.String(length=80), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['source_system'], ['interop_connector_registry.connector_id'], name=op.f('fk_interop_service_catalog_source_system_interop_connector_registry')),
        sa.ForeignKeyConstraint(['target_system'], ['interop_connector_registry.connector_id'], name=op.f('fk_interop_service_catalog_target_system_interop_connector_registry')),
        sa.ForeignKeyConstraint(['workflow_id'], ['interop_workflow_definitions.workflow_id'], name=op.f('fk_interop_service_catalog_workflow_id_interop_workflow_definitions')),
        sa.PrimaryKeyConstraint('service_id', name=op.f('pk_interop_service_catalog')),
    )
    op.create_table(
        'interop_field_mappings',
        sa.Column('mapping_id', sa.String(length=120), nullable=False),
        sa.Column('service_id', sa.String(length=80), nullable=True),
        sa.Column('direction', sa.String(length=30), nullable=False),
        sa.Column('system_id', sa.String(length=60), nullable=False),
        sa.Column('entity', sa.String(length=60), nullable=False),
        sa.Column('source_field', sa.String(length=80), nullable=False),
        sa.Column('target_field', sa.String(length=80), nullable=False),
        sa.Column('transform_note', sa.String(length=300), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['service_id'], ['interop_service_catalog.service_id'], name=op.f('fk_interop_field_mappings_service_id_interop_service_catalog')),
        sa.ForeignKeyConstraint(['system_id'], ['interop_connector_registry.connector_id'], name=op.f('fk_interop_field_mappings_system_id_interop_connector_registry')),
        sa.PrimaryKeyConstraint('mapping_id', name=op.f('pk_interop_field_mappings')),
    )
    op.create_index('ix_interop_field_mappings_service_id', 'interop_field_mappings', ['service_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_interop_field_mappings_service_id', table_name='interop_field_mappings')
    op.drop_table('interop_field_mappings')
    op.drop_table('interop_service_catalog')

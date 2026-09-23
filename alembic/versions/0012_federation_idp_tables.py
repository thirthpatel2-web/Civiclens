"""federation_idp_tables

Revision ID: 0012
Revises: 0011

NOTE: autogenerate also proposed dropping classification_corrections, external_service_links,
citizen_external_ids, integration_exceptions and two unrelated HNSW indexes - the same
pre-existing gap noted in 0010/0011 (those tables just aren't imported into
app/db/models/__init__.py's autogenerate scan). Pruned; not something this migration should touch.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'interop_federation_clients',
        sa.Column('client_id', sa.String(length=60), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('client_secret_hash', sa.String(length=255), nullable=False),
        sa.Column('system', sa.String(length=40), nullable=False),
        sa.Column('allowed_scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('client_id', name=op.f('pk_interop_federation_clients')),
    )
    op.create_table(
        'interop_federation_tokens',
        sa.Column('token_id', sa.UUID(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('client_id', sa.String(length=60), nullable=False),
        sa.Column('scope', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('issued_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('revoked_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['interop_federation_clients.client_id'], name=op.f('fk_interop_federation_tokens_client_id_interop_federation_clients'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('token_id', name=op.f('pk_interop_federation_tokens')),
        sa.UniqueConstraint('token_hash', name='uq_interop_federation_tokens_token_hash'),
    )
    op.create_index('ix_interop_federation_tokens_client_id', 'interop_federation_tokens', ['client_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_interop_federation_tokens_client_id', table_name='interop_federation_tokens')
    op.drop_table('interop_federation_tokens')
    op.drop_table('interop_federation_clients')

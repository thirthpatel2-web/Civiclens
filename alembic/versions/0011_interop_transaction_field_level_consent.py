"""interop_transaction_field_level_consent

Revision ID: 0011
Revises: 0010

NOTE: autogenerate also proposed dropping classification_corrections, external_service_links,
citizen_external_ids, integration_exceptions and two unrelated HNSW indexes - those tables are
real, in-use, and simply weren't imported into app/db/models/__init__.py's autogenerate scan (the
same pre-existing gap noted in 0010; still not something this migration should touch). Pruned.

The three new columns get a server_default of an empty JSON array so this applies cleanly against
existing interop_transactions rows (there are real ones from the no-reupload demo already) without
a NOT NULL violation; new rows always pass real values explicitly.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('interop_transactions', sa.Column('requested_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'))
    op.add_column('interop_transactions', sa.Column('approved_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'))
    op.add_column('interop_transactions', sa.Column('denied_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'))


def downgrade() -> None:
    op.drop_column('interop_transactions', 'denied_fields')
    op.drop_column('interop_transactions', 'approved_fields')
    op.drop_column('interop_transactions', 'requested_fields')

"""Widen legal_precedents.disposal from VARCHAR(80) to VARCHAR(300).

Revision ID: 0009
Revises: 0008

Discovered ingesting the real Supreme Court metadata Parquet for every year (1950-2026): some real
disposal_nature values exceed 80 characters (e.g. a 1987 row: "Permission to File SLP/Appeal-allowed
and matter dismissed(including all pending IAs)", 85 chars). 300 is generous headroom, not a guess
tied to the one longest value seen so far.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("legal_precedents", "disposal", type_=sa.String(300))


def downgrade() -> None:
    op.alter_column("legal_precedents", "disposal", type_=sa.String(80))

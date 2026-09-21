"""Add the embedding column to legal_judgment_chunks. Same split as migration 0002 for
document_chunks: the vector dimension is deployment configuration, read from EMBEDDING_DIMENSIONS
here rather than baked into the generated migration 0006.

Revision ID: 0007
Revises: 0006
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _dimension() -> int:
    raw = os.environ.get("EMBEDDING_DIMENSIONS", "").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 16000:
        raise RuntimeError("Set EMBEDDING_DIMENSIONS (1-16000, the embedding model's output size) before running this migration.")
    return int(raw)


def upgrade() -> None:
    op.execute(sa.text(f"ALTER TABLE legal_judgment_chunks ADD COLUMN embedding vector({_dimension()})"))


def downgrade() -> None:
    op.execute("ALTER TABLE legal_judgment_chunks DROP COLUMN IF EXISTS embedding")

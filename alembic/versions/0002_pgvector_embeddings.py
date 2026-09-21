"""Enable pgvector and add the embedding column to document_chunks.

Revision ID: 0002
Revises: 0001

The vector dimension is deployment configuration (it must equal the embedding model's output size),
so it is read from EMBEDDING_DIMENSIONS here rather than hard-coded. Changing the embedding model
later requires a new migration that re-creates the column and re-embeds the corpus.
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _dimension() -> int:
    raw = os.environ.get("EMBEDDING_DIMENSIONS", "").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 16000:
        raise RuntimeError("Set EMBEDDING_DIMENSIONS (1-16000, the embedding model's output size) before running this migration.")
    return int(raw)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(sa.text(f"ALTER TABLE document_chunks ADD COLUMN embedding vector({_dimension()})"))


def downgrade() -> None:
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")

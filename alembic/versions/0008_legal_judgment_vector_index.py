"""HNSW cosine index over legal_judgment_chunks.embedding. Same pattern as migration 0003.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_legal_judgment_chunks_embedding_hnsw ON legal_judgment_chunks USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_legal_judgment_chunks_embedding_hnsw")

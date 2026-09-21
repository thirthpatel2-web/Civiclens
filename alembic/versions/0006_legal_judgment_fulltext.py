"""Full-text legal judgment corpus: legal_judgments + legal_judgment_chunks (public case law).
The pgvector column/index live in migrations 0007/0008, same split as 0002/0003 for document_chunks.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legal_judgments",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("court", sa.String(80), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=True),
        sa.Column("neutral_citation", sa.String(30), nullable=True),
        sa.Column("reporter_citation", sa.String(40), nullable=True),
        sa.Column("source_pdf_url", sa.String(400), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name="pk_legal_judgments"),
    )
    op.create_table(
        "legal_judgment_chunks",
        sa.Column("chunk_id", sa.String(100), nullable=False),
        sa.Column("judgment_id", sa.String(80), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("heading", sa.String(200), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint('chunk_id', name="pk_legal_judgment_chunks"),
        sa.ForeignKeyConstraint(["judgment_id"], ["legal_judgments.id"], name="fk_legal_judgment_chunks_judgment_id_legal_judgments", ondelete='CASCADE'),
    )
    op.create_index('ix_legal_judgments_neutral_citation', "legal_judgments", ['neutral_citation'])
    op.create_index('ix_legal_judgments_decision_date', "legal_judgments", ['decision_date'])
    op.create_index('ix_legal_judgment_chunks_judgment_id', "legal_judgment_chunks", ['judgment_id'])


def downgrade() -> None:
    op.drop_table("legal_judgment_chunks")
    op.drop_table("legal_judgments")

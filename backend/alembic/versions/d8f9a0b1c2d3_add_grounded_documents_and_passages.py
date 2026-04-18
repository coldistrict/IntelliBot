"""add grounded documents and passages

Revision ID: d8f9a0b1c2d3
Revises: c7e8f9a0b1c2
Create Date: 2026-04-07 02:15:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d8f9a0b1c2d3"
down_revision: str | None = "c7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_run_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("canonical_url", sa.String(length=1000), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("extractor", sa.String(length=64), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=255), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_analysis_run_id"), "documents", ["analysis_run_id"], unique=False)
    op.create_index(op.f("ix_documents_source_id"), "documents", ["source_id"], unique=False)

    op.create_table(
        "passages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_run_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("passage_index", sa.Integer(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_passages_analysis_run_id"), "passages", ["analysis_run_id"], unique=False)
    op.create_index(op.f("ix_passages_document_id"), "passages", ["document_id"], unique=False)
    op.create_index(op.f("ix_passages_source_id"), "passages", ["source_id"], unique=False)

    op.add_column("fact_claims", sa.Column("passage_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_fact_claims_passage_id_passages",
        "fact_claims",
        "passages",
        ["passage_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_fact_claims_passage_id_passages", "fact_claims", type_="foreignkey")
    op.drop_column("fact_claims", "passage_id")

    op.drop_index(op.f("ix_passages_source_id"), table_name="passages")
    op.drop_index(op.f("ix_passages_document_id"), table_name="passages")
    op.drop_index(op.f("ix_passages_analysis_run_id"), table_name="passages")
    op.drop_table("passages")

    op.drop_index(op.f("ix_documents_source_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_analysis_run_id"), table_name="documents")
    op.drop_table("documents")

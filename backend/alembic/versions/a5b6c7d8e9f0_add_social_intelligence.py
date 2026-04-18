"""add_social_intelligence

Revision ID: a5b6c7d8e9f0
Revises: 9f535e60a1fb
Create Date: 2026-04-06 17:05:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a5b6c7d8e9f0"
down_revision: str | None = "9f535e60a1fb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


consensus_label_enum = sa.Enum(
    "bullish",
    "bearish",
    "mixed",
    "unclear",
    name="consensus_label_enum",
)
consensus_strength_enum = sa.Enum(
    "weak",
    "medium",
    "strong",
    name="consensus_strength_enum",
)
narrative_phase_enum = sa.Enum(
    "fresh",
    "emerging",
    "crowded",
    "priced_in",
    name="narrative_phase_enum",
)


postgres_consensus_label_enum = postgresql.ENUM(
    "bullish",
    "bearish",
    "mixed",
    "unclear",
    name="consensus_label_enum",
    create_type=False,
)
postgres_consensus_strength_enum = postgresql.ENUM(
    "weak",
    "medium",
    "strong",
    name="consensus_strength_enum",
    create_type=False,
)
postgres_narrative_phase_enum = postgresql.ENUM(
    "fresh",
    "emerging",
    "crowded",
    "priced_in",
    name="narrative_phase_enum",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    column_consensus_label_enum: sa.Enum = consensus_label_enum
    column_consensus_strength_enum: sa.Enum = consensus_strength_enum
    column_narrative_phase_enum: sa.Enum = narrative_phase_enum

    if dialect == "postgresql":
        op.execute("ALTER TYPE source_kind_enum ADD VALUE IF NOT EXISTS 'live_social'")
        op.execute("ALTER TYPE source_tier_enum ADD VALUE IF NOT EXISTS 'high_trust_social'")
        consensus_label_enum.create(bind, checkfirst=True)
        consensus_strength_enum.create(bind, checkfirst=True)
        narrative_phase_enum.create(bind, checkfirst=True)
        column_consensus_label_enum = postgres_consensus_label_enum
        column_consensus_strength_enum = postgres_consensus_strength_enum
        column_narrative_phase_enum = postgres_narrative_phase_enum

    op.create_table(
        "social_intel_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_run_id", sa.Integer(), nullable=False),
        sa.Column("consensus_label", column_consensus_label_enum, nullable=False),
        sa.Column("consensus_strength", column_consensus_strength_enum, nullable=False),
        sa.Column("narrative_phase", column_narrative_phase_enum, nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_themes", sa.JSON(), nullable=False),
        sa.Column("trusted_accounts_count", sa.Integer(), nullable=False),
        sa.Column("broad_posts_sampled", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["analysis_runs.id"],
            name=op.f("fk_social_intel_summaries_analysis_run_id_analysis_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_social_intel_summaries")),
    )
    op.create_index(
        op.f("ix_social_intel_summaries_analysis_run_id"),
        "social_intel_summaries",
        ["analysis_run_id"],
        unique=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_index(
        op.f("ix_social_intel_summaries_analysis_run_id"),
        table_name="social_intel_summaries",
    )
    op.drop_table("social_intel_summaries")

    if dialect == "postgresql":
        narrative_phase_enum.drop(bind, checkfirst=True)
        consensus_strength_enum.drop(bind, checkfirst=True)
        consensus_label_enum.drop(bind, checkfirst=True)
        # The appended values on source_kind_enum and source_tier_enum are intentionally retained.

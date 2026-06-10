"""add market resolution tracking

Revision ID: e9a0b1c2d3e4
Revises: d8f9a0b1c2d3
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e9a0b1c2d3e4"
down_revision: str | None = "d8f9a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("markets", sa.Column("resolved_outcome", sa.String(length=16), nullable=True))
    op.add_column(
        "markets",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("markets", "resolved_at")
    op.drop_column("markets", "resolved_outcome")

"""add_request_progress_json

Revision ID: b6d7e8f9a0b1
Revises: a5b6c7d8e9f0
Create Date: 2026-04-06 18:10:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b6d7e8f9a0b1"
down_revision: str | None = "a5b6c7d8e9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_requests",
        sa.Column("progress_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.alter_column("analysis_requests", "progress_json", server_default=None)


def downgrade() -> None:
    op.drop_column("analysis_requests", "progress_json")

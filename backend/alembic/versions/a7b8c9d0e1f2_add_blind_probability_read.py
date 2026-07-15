"""add blind probability read

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analysis_runs", sa.Column("blind_p_hat", sa.Float(), nullable=True))
    op.add_column("published_forecasts", sa.Column("blind_p_hat", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("published_forecasts", "blind_p_hat")
    op.drop_column("analysis_runs", "blind_p_hat")

"""add research integrity ledger

Revision ID: f1a2b3c4d5e6
Revises: e9a0b1c2d3e4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e9a0b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    run_quality = postgresql.ENUM("unknown", "clean", "warning", "invalid", name="run_quality_enum", create_type=False)
    attempt_reason = postgresql.ENUM("original", "intentional_rerun", "retry", "recovery", name="attempt_reason_enum", create_type=False)
    result_mode = postgresql.ENUM("model", "deterministic_fallback", "skipped", "failed", name="execution_result_mode_enum", create_type=False)
    forecast_quality = postgresql.ENUM("unknown", "clean", "warning", "invalid", name="published_forecast_quality_enum", create_type=False)
    forecast_attempt = postgresql.ENUM("original", "intentional_rerun", "retry", "recovery", name="published_forecast_attempt_reason_enum", create_type=False)
    journal_type = postgresql.ENUM("before", "after", name="journal_event_type_enum", create_type=False)
    bind = op.get_bind()
    for enum in (run_quality, attempt_reason, result_mode, forecast_quality, forecast_attempt, journal_type):
        enum.create(bind, checkfirst=True)

    op.add_column("rule_parses", sa.Column("deadline_provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.add_column("analysis_runs", sa.Column("quality_state", run_quality, nullable=False, server_default="unknown"))
    op.add_column("analysis_runs", sa.Column("quality_reasons", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.add_column("analysis_runs", sa.Column("attempt_reason", attempt_reason, nullable=False, server_default="original"))
    op.add_column("analysis_runs", sa.Column("market_match_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.add_column("analysis_runs", sa.Column("evidence_update", sa.Float(), nullable=True))
    op.add_column("sources", sa.Column("lane", sa.String(64), nullable=False, server_default="unknown"))
    op.add_column("sources", sa.Column("exclusion_reason", sa.Text(), nullable=True))
    op.add_column("markets", sa.Column("yes_token_id", sa.String(255), nullable=True))
    op.add_column("markets", sa.Column("no_token_id", sa.String(255), nullable=True))

    op.create_table(
        "market_price_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("market_id", sa.Integer(), sa.ForeignKey("markets.id"), nullable=False),
        sa.Column("token_id", sa.String(255), nullable=False),
        sa.Column("outcome", sa.String(8), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("market_id", "token_id", "observed_at"),
    )
    op.create_index("ix_market_price_points_market_id", "market_price_points", ["market_id"])

    op.create_table(
        "execution_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("analysis_requests.id"), nullable=False),
        sa.Column("analysis_run_id", sa.Integer(), sa.ForeignKey("analysis_runs.id"), nullable=True),
        sa.Column("stage_key", sa.String(64), nullable=False),
        sa.Column("event_kind", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64)),
        sa.Column("model", sa.String(255)),
        sa.Column("task_name", sa.String(128)),
        sa.Column("prompt_version", sa.String(128)),
        sa.Column("result_mode", result_mode, nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error_class", sa.String(255)),
        sa.Column("detail_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_execution_events_request_id", "execution_events", ["request_id"])
    op.create_index("ix_execution_events_analysis_run_id", "execution_events", ["analysis_run_id"])
    op.create_index("ix_execution_events_stage_key", "execution_events", ["stage_key"])

    op.create_table(
        "published_forecasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analysis_run_id", sa.Integer(), sa.ForeignKey("analysis_runs.id"), nullable=False, unique=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("analysis_requests.id"), nullable=False),
        sa.Column("market_id", sa.Integer(), sa.ForeignKey("markets.id")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(255), nullable=False),
        sa.Column("prompt_versions_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("market_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("quality_state", forecast_quality, nullable=False),
        sa.Column("attempt_reason", forecast_attempt, nullable=False),
        sa.Column("is_repeat", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("p_hat", sa.Float()),
        sa.Column("market_mid_prob", sa.Float()),
    )
    op.create_index("ix_published_forecasts_analysis_run_id", "published_forecasts", ["analysis_run_id"], unique=True)
    op.create_index("ix_published_forecasts_request_id", "published_forecasts", ["request_id"])
    op.create_index("ix_published_forecasts_market_id", "published_forecasts", ["market_id"])

    op.create_table(
        "journal_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analysis_run_id", sa.Integer(), sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("event_type", journal_type, nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("analysis_run_id", "event_type", "created_at", name="uq_journal_event_time"),
    )
    op.create_index("ix_journal_events_analysis_run_id", "journal_events", ["analysis_run_id"])


def downgrade() -> None:
    op.drop_index("ix_market_price_points_market_id", table_name="market_price_points")
    op.drop_table("market_price_points")
    op.drop_column("markets", "no_token_id")
    op.drop_column("markets", "yes_token_id")
    op.drop_index("ix_journal_events_analysis_run_id", table_name="journal_events")
    op.drop_table("journal_events")
    op.drop_index("ix_published_forecasts_market_id", table_name="published_forecasts")
    op.drop_index("ix_published_forecasts_request_id", table_name="published_forecasts")
    op.drop_index("ix_published_forecasts_analysis_run_id", table_name="published_forecasts")
    op.drop_table("published_forecasts")
    op.drop_index("ix_execution_events_stage_key", table_name="execution_events")
    op.drop_index("ix_execution_events_analysis_run_id", table_name="execution_events")
    op.drop_index("ix_execution_events_request_id", table_name="execution_events")
    op.drop_table("execution_events")
    for column in ("evidence_update", "market_match_json", "attempt_reason", "quality_reasons", "quality_state"):
        op.drop_column("analysis_runs", column)
    op.drop_column("sources", "exclusion_reason")
    op.drop_column("sources", "lane")
    op.drop_column("rule_parses", "deadline_provenance")
    bind = op.get_bind()
    for name in (
        "journal_event_type_enum", "published_forecast_attempt_reason_enum",
        "published_forecast_quality_enum", "execution_result_mode_enum",
        "attempt_reason_enum", "run_quality_enum",
    ):
        sa.Enum(name=name).drop(bind, checkfirst=True)

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ConfidenceLabelEnum, RecommendationLabelEnum, RunQualityEnum, TemplateKey


class ResolvedRunRow(BaseModel):
    analysis_request_id: int
    analysis_run_id: int
    title: str
    template: TemplateKey | None
    recommendation_label: RecommendationLabelEnum | None
    confidence_label: ConfidenceLabelEnum | None
    p_hat: float | None
    market_mid_prob: float | None
    outcome: str
    resolved_at: datetime | None
    model_brier: float | None
    market_brier: float | None
    direction_hit: bool | None
    trade_side: str | None
    trade_entry_price: float | None
    trade_pnl: float | None
    is_repeat: bool = False
    quality_state: RunQualityEnum = RunQualityEnum.UNKNOWN
    user_before_brier: float | None = None
    user_after_brier: float | None = None


class PendingRunRow(BaseModel):
    analysis_request_id: int
    analysis_run_id: int
    title: str
    p_hat: float | None
    recommendation_label: RecommendationLabelEnum | None
    market_expiry_at: datetime | None
    is_repeat: bool = False
    quality_state: RunQualityEnum = RunQualityEnum.UNKNOWN
    expired_unresolved: bool = False


class CalibrationBucket(BaseModel):
    label: str
    lower: float
    upper: float
    count: int
    avg_p_hat: float | None
    actual_yes_rate: float | None


class SliceStats(BaseModel):
    key: str
    resolved_runs: int
    avg_model_brier: float | None
    direction_hit_rate: float | None
    trades: int
    total_pnl: float


class ScoreboardSummary(BaseModel):
    resolved_runs: int
    pending_runs: int
    unlinked_runs: int
    scored_runs: int
    avg_model_brier: float | None
    avg_market_brier: float | None
    head_to_head_runs: int
    head_to_head_model_brier: float | None
    head_to_head_market_brier: float | None
    model_beats_market_rate: float | None
    direction_calls: int
    direction_hit_rate: float | None
    trade_count: int
    trade_wins: int
    total_pnl: float
    roi_per_trade: float | None
    distinct_markets: int = 0
    published_forecasts: int = 0
    repeated_forecasts: int = 0
    unknown_forecasts: int = 0
    user_before_runs: int = 0
    avg_user_before_brier: float | None = None
    user_after_runs: int = 0
    avg_user_after_brier: float | None = None


class CalibrationScoreboardResponse(BaseModel):
    summary: ScoreboardSummary
    buckets: list[CalibrationBucket]
    template_slices: list[SliceStats]
    confidence_slices: list[SliceStats]
    resolved: list[ResolvedRunRow]
    pending: list[PendingRunRow]


class OutcomeRefreshResponse(BaseModel):
    markets_checked: int
    newly_resolved: int
    still_open: int
    lookup_failures: int

from __future__ import annotations

from collections import defaultdict

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnalysisRun, Market, PublishedForecast
from app.models.enums import JournalEventTypeEnum, RecommendationLabelEnum, RunQualityEnum
from app.schemas.calibration import (
    CalibrationBucket,
    CalibrationScoreboardResponse,
    PendingRunRow,
    ResolvedRunRow,
    ScoreboardSummary,
    SliceStats,
)

VIRTUAL_STAKE = 100.0
MIN_EXECUTABLE_PRICE = 0.001
BUCKET_BOUNDS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]
MAX_TABLE_ROWS = 200


def build_scoreboard(session: Session) -> CalibrationScoreboardResponse:
    rows = session.execute(
        select(PublishedForecast, AnalysisRun, Market)
        .join(AnalysisRun, PublishedForecast.analysis_run_id == AnalysisRun.id)
        .outerjoin(Market, PublishedForecast.market_id == Market.id)
        .where(PublishedForecast.quality_state.in_([RunQualityEnum.CLEAN, RunQualityEnum.WARNING]))
        .order_by(PublishedForecast.id.desc())
    ).all()

    resolved_rows: list[ResolvedRunRow] = []
    pending_rows: list[PendingRunRow] = []
    unlinked_runs = 0

    for forecast, run, market in rows:
        if market is None:
            unlinked_runs += 1
            continue
        if market.resolved_outcome in {"yes", "no"}:
            resolved_rows.append(_resolved_row(forecast, run, market))
        else:
            pending_rows.append(
                PendingRunRow(
                    analysis_request_id=run.request_id,
                    analysis_run_id=run.id,
                    title=market.title,
                    p_hat=run.p_hat,
                    recommendation_label=run.recommendation_label,
                    market_expiry_at=market.expiry_at,
                    is_repeat=forecast.is_repeat,
                    quality_state=forecast.quality_state,
                    expired_unresolved=bool(
                        market.expiry_at and market.expiry_at < datetime.now(UTC)
                    ),
                )
            )

    published_count = session.scalar(select(func.count()).select_from(PublishedForecast)) or 0
    run_count = session.scalar(select(func.count()).select_from(AnalysisRun)) or 0
    unknown_count = (run_count - published_count) + (
        session.scalar(
            select(func.count()).select_from(PublishedForecast).where(
                PublishedForecast.quality_state.in_([RunQualityEnum.UNKNOWN, RunQualityEnum.INVALID])
            )
        ) or 0
    )
    summary = _summarize(
        resolved_rows,
        pending_runs=len(pending_rows),
        unlinked_runs=unlinked_runs,
        distinct_markets=len({forecast.market_id for forecast, _, _ in rows if forecast.market_id}),
        published_forecasts=len(rows),
        repeated_forecasts=sum(1 for forecast, _, _ in rows if forecast.is_repeat),
        unknown_forecasts=unknown_count,
    )
    return CalibrationScoreboardResponse(
        summary=summary,
        buckets=_calibration_buckets(resolved_rows),
        template_slices=_slices(resolved_rows, key=lambda row: row.template.value if row.template else "unknown"),
        confidence_slices=_slices(
            resolved_rows,
            key=lambda row: row.confidence_label.value if row.confidence_label else "unknown",
        ),
        resolved=resolved_rows[:MAX_TABLE_ROWS],
        pending=pending_rows[:MAX_TABLE_ROWS],
    )


def _resolved_row(
    forecast: PublishedForecast,
    run: AnalysisRun,
    market: Market,
) -> ResolvedRunRow:
    outcome_value = 1.0 if market.resolved_outcome == "yes" else 0.0

    model_brier = _round_score((forecast.p_hat - outcome_value) ** 2) if forecast.p_hat is not None else None
    market_brier = (
        _round_score((forecast.market_mid_prob - outcome_value) ** 2)
        if forecast.market_mid_prob is not None
        else None
    )

    direction_hit: bool | None = None
    if forecast.p_hat is not None and forecast.p_hat != 0.5:
        direction_hit = (forecast.p_hat > 0.5) == (outcome_value == 1.0)

    trade_side, trade_entry_price, trade_pnl = _virtual_trade(run, outcome_value)

    return ResolvedRunRow(
        analysis_request_id=run.request_id,
        analysis_run_id=run.id,
        title=market.title,
        template=run.template_selected,
        recommendation_label=run.recommendation_label,
        confidence_label=run.confidence_label,
        p_hat=forecast.p_hat,
        market_mid_prob=forecast.market_mid_prob,
        outcome=market.resolved_outcome or "unknown",
        resolved_at=market.resolved_at,
        model_brier=model_brier,
        market_brier=market_brier,
        direction_hit=direction_hit,
        trade_side=trade_side,
        trade_entry_price=trade_entry_price,
        trade_pnl=trade_pnl,
        is_repeat=forecast.is_repeat,
        quality_state=forecast.quality_state,
        user_before_brier=_journal_brier(run, JournalEventTypeEnum.BEFORE, outcome_value),
        user_after_brier=_journal_brier(run, JournalEventTypeEnum.AFTER, outcome_value),
    )


def _journal_brier(
    run: AnalysisRun,
    event_type: JournalEventTypeEnum,
    outcome_value: float,
) -> float | None:
    events = sorted(
        (event for event in run.journal_events if event.event_type == event_type),
        key=lambda event: event.created_at,
    )
    if not events:
        return None
    payload = events[-1].payload_json
    if event_type == JournalEventTypeEnum.BEFORE:
        probability = payload.get("prior_probability")
    else:
        decision = payload.get("decision")
        probability = {"yes": 1.0, "no": 0.0}.get(decision) if isinstance(decision, str) else None
    if not isinstance(probability, (int, float)):
        return None
    return _round_score((float(probability) - outcome_value) ** 2)


def _virtual_trade(
    run: AnalysisRun,
    outcome_value: float,
) -> tuple[str | None, float | None, float | None]:
    if run.recommendation_label == RecommendationLabelEnum.LEAN_YES:
        entry_price = run.yes_exec_price
        won = outcome_value == 1.0
        side = "yes"
    elif run.recommendation_label == RecommendationLabelEnum.LEAN_NO:
        entry_price = run.no_exec_price
        won = outcome_value == 0.0
        side = "no"
    else:
        return None, None, None

    if entry_price is None or not (MIN_EXECUTABLE_PRICE <= entry_price < 1.0):
        return None, None, None

    payout = VIRTUAL_STAKE / entry_price if won else 0.0
    pnl = round(payout - VIRTUAL_STAKE, 2)
    return side, entry_price, pnl


def _summarize(
    resolved_rows: list[ResolvedRunRow],
    *,
    pending_runs: int,
    unlinked_runs: int,
    distinct_markets: int = 0,
    published_forecasts: int = 0,
    repeated_forecasts: int = 0,
    unknown_forecasts: int = 0,
) -> ScoreboardSummary:
    model_briers = [row.model_brier for row in resolved_rows if row.model_brier is not None]
    market_briers = [row.market_brier for row in resolved_rows if row.market_brier is not None]
    head_to_head = [
        (row.model_brier, row.market_brier)
        for row in resolved_rows
        if row.model_brier is not None and row.market_brier is not None
    ]
    direction_calls = [row.direction_hit for row in resolved_rows if row.direction_hit is not None]
    trades = [row for row in resolved_rows if row.trade_pnl is not None]
    user_before_briers = [row.user_before_brier for row in resolved_rows if row.user_before_brier is not None]
    user_after_briers = [row.user_after_brier for row in resolved_rows if row.user_after_brier is not None]

    model_wins = sum(1 for model, market in head_to_head if model < market)
    total_pnl = round(sum(row.trade_pnl for row in trades if row.trade_pnl is not None), 2)

    return ScoreboardSummary(
        resolved_runs=len(resolved_rows),
        pending_runs=pending_runs,
        unlinked_runs=unlinked_runs,
        scored_runs=len(model_briers),
        avg_model_brier=_average(model_briers),
        avg_market_brier=_average(market_briers),
        head_to_head_runs=len(head_to_head),
        head_to_head_model_brier=_average([model for model, _ in head_to_head]),
        head_to_head_market_brier=_average([market for _, market in head_to_head]),
        model_beats_market_rate=_rate(model_wins, len(head_to_head)),
        direction_calls=len(direction_calls),
        direction_hit_rate=_rate(sum(1 for hit in direction_calls if hit), len(direction_calls)),
        trade_count=len(trades),
        trade_wins=sum(1 for row in trades if row.trade_pnl is not None and row.trade_pnl > 0),
        total_pnl=total_pnl,
        roi_per_trade=round(total_pnl / (VIRTUAL_STAKE * len(trades)), 4) if trades else None,
        distinct_markets=distinct_markets,
        published_forecasts=published_forecasts,
        repeated_forecasts=repeated_forecasts,
        unknown_forecasts=unknown_forecasts,
        user_before_runs=len(user_before_briers),
        avg_user_before_brier=_average(user_before_briers),
        user_after_runs=len(user_after_briers),
        avg_user_after_brier=_average(user_after_briers),
    )


def _calibration_buckets(resolved_rows: list[ResolvedRunRow]) -> list[CalibrationBucket]:
    buckets: list[CalibrationBucket] = []
    for lower, upper in BUCKET_BOUNDS:
        in_bucket = [
            row
            for row in resolved_rows
            if row.p_hat is not None
            and (lower <= row.p_hat < upper or (upper == 1.0 and row.p_hat == 1.0))
        ]
        p_hats = [row.p_hat for row in in_bucket if row.p_hat is not None]
        yes_count = sum(1 for row in in_bucket if row.outcome == "yes")
        buckets.append(
            CalibrationBucket(
                label=f"{int(lower * 100)}-{int(upper * 100)}%",
                lower=lower,
                upper=upper,
                count=len(in_bucket),
                avg_p_hat=_average(p_hats),
                actual_yes_rate=_rate(yes_count, len(in_bucket)),
            )
        )
    return buckets


def _slices(
    resolved_rows: list[ResolvedRunRow],
    *,
    key,
) -> list[SliceStats]:
    grouped: dict[str, list[ResolvedRunRow]] = defaultdict(list)
    for row in resolved_rows:
        grouped[key(row)].append(row)

    slices: list[SliceStats] = []
    for slice_key in sorted(grouped):
        rows = grouped[slice_key]
        briers = [row.model_brier for row in rows if row.model_brier is not None]
        calls = [row.direction_hit for row in rows if row.direction_hit is not None]
        trades = [row for row in rows if row.trade_pnl is not None]
        slices.append(
            SliceStats(
                key=slice_key,
                resolved_runs=len(rows),
                avg_model_brier=_average(briers),
                direction_hit_rate=_rate(sum(1 for hit in calls if hit), len(calls)),
                trades=len(trades),
                total_pnl=round(sum(row.trade_pnl for row in trades if row.trade_pnl is not None), 2),
            )
        )
    return slices


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return _round_score(sum(values) / len(values))


def _rate(hits: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(hits / total, 4)


def _round_score(value: float) -> float:
    if 0.0 < value < 0.001:
        return value
    return round(value, 4)

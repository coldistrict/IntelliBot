from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.clients.polymarket_client import ResolvedMarketRecord
from app.models import AnalysisRequest, AnalysisRun, Market
from app.models.enums import (
    ConfidenceLabelEnum,
    PricedInRiskLabelEnum,
    RecommendationLabelEnum,
    RequestStatusEnum,
)
from app.schemas.market import ResearchEdgeSignalResponse

FRICTION_BUFFER = 0.02
MAX_SIGNAL_AGE = timedelta(hours=24)


def _analysis_needed() -> ResearchEdgeSignalResponse:
    return ResearchEdgeSignalResponse(
        status="analysis_needed",
        reason="Run the research analysis to check whether the market price offers verified edge.",
    )


def _signal_for_run(
    run: AnalysisRun,
    record: ResolvedMarketRecord,
) -> ResearchEdgeSignalResponse:
    recommendation = run.recommendation
    side: Literal["yes", "no"] | None = {
        RecommendationLabelEnum.LEAN_YES: "yes",
        RecommendationLabelEnum.LEAN_NO: "no",
    }.get(run.recommendation_label)

    if side == "yes":
        win_probability = run.p_hat
        conservative_probability = run.p_low
        live_price = record.yes_ask
    elif side == "no":
        win_probability = 1 - run.p_hat if run.p_hat is not None else None
        conservative_probability = 1 - run.p_high if run.p_high is not None else None
        live_price = record.no_ask
    else:
        win_probability = None
        conservative_probability = None
        live_price = None

    live_edge = (
        round(conservative_probability - live_price - FRICTION_BUFFER, 4)
        if conservative_probability is not None and live_price is not None
        else None
    )
    analyzed_at = run.created_at
    if analyzed_at.tzinfo is None:
        analyzed_at = analyzed_at.replace(tzinfo=UTC)
    is_fresh = datetime.now(UTC) - analyzed_at <= MAX_SIGNAL_AGE
    is_favorable = (
        recommendation is not None
        and side is not None
        and conservative_probability is not None
        and conservative_probability > 0.5
        and live_edge is not None
        and live_edge > 0
        and run.confidence_label in {ConfidenceLabelEnum.MEDIUM, ConfidenceLabelEnum.HIGH}
        and run.priced_in_risk_label != PricedInRiskLabelEnum.HIGH
        and record.status == "active"
        and is_fresh
    )

    if is_favorable:
        reason = (
            f"{side.upper()} has verified conservative edge over the live price "
            "after a 2% execution buffer."
        )
        status: Literal["favorable", "no_favorable_setup"] = "favorable"
    elif recommendation is None:
        reason = "The latest analysis did not finish an executable edge check."
        status = "no_favorable_setup"
    elif record.status != "active":
        reason = "This market is not active, so there is no actionable setup."
        status = "no_favorable_setup"
    elif not is_fresh:
        reason = "The latest research is more than 24 hours old. Refresh it before acting."
        status = "no_favorable_setup"
    elif run.confidence_label == ConfidenceLabelEnum.LOW:
        reason = "The latest research confidence is too low to verify price edge."
        status = "no_favorable_setup"
    elif run.priced_in_risk_label == PricedInRiskLabelEnum.HIGH:
        reason = "The latest analysis flags high priced-in risk."
        status = "no_favorable_setup"
    elif conservative_probability is None or conservative_probability <= 0.5:
        reason = "No side has a conservative win chance above 50%."
        status = "no_favorable_setup"
    elif live_edge is None or live_edge <= 0:
        reason = "The current price no longer leaves positive edge after the 2% buffer."
        status = "no_favorable_setup"
    else:
        reason = "The latest analysis does not recommend an executable side."
        status = "no_favorable_setup"

    return ResearchEdgeSignalResponse(
        status=status,
        side=side,
        win_probability=win_probability,
        conservative_probability=conservative_probability,
        live_price=live_price,
        edge_after_buffer=live_edge,
        confidence=run.confidence_label.value,
        analysis_id=run.request_id,
        analyzed_at=analyzed_at,
        reason=reason,
    )


def research_edge_signals_for_records(
    session: Session,
    records: list[ResolvedMarketRecord],
) -> dict[str, ResearchEdgeSignalResponse]:
    polymarket_ids = [record.polymarket_id for record in records if record.polymarket_id]
    if not polymarket_ids:
        return {}

    markets = session.scalars(
        select(Market).where(Market.polymarket_id.in_(polymarket_ids))
    ).all()
    polymarket_id_by_market_id = {market.id: market.polymarket_id for market in markets}

    latest_runs: dict[str, AnalysisRun] = {}
    if polymarket_id_by_market_id:
        runs = session.scalars(
            select(AnalysisRun)
            .join(AnalysisRequest, AnalysisRequest.id == AnalysisRun.request_id)
            .options(selectinload(AnalysisRun.recommendation))
            .where(AnalysisRun.market_id.in_(polymarket_id_by_market_id))
            .where(AnalysisRequest.status == RequestStatusEnum.COMPLETE)
            .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        ).all()
        for run in runs:
            polymarket_id = polymarket_id_by_market_id.get(run.market_id)
            if polymarket_id and polymarket_id not in latest_runs:
                latest_runs[polymarket_id] = run

    return {
        record.polymarket_id: (
            _signal_for_run(latest_runs[record.polymarket_id], record)
            if record.polymarket_id in latest_runs
            else _analysis_needed()
        )
        for record in records
    }

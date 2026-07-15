from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.config.settings import get_settings
from app.models import (
    AnalysisRequest,
    AnalysisRun,
    ExecutionEvent,
    Market,
    PublishedForecast,
    Recommendation,
    RuleParse,
    Snapshot,
    Source,
)
from app.models.enums import RequestStatusEnum, RunQualityEnum, SnapshotTypeEnum, SourceKindEnum
from app.services.analysis_execution import derive_quality, finalize_stage_ledger
from app.services.analysis_progress import mark_stage_complete, mark_stage_running

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models import Factor
    from app.services.analysis_pipeline import AnalysisProcessor, RetrievalResult, ScoreOutcome


def run_briefing_stage(
    processor: "AnalysisProcessor",
    *,
    session: "Session",
    request: AnalysisRequest,
    market: Market | None,
    rule_parse: RuleParse,
    analysis_run: AnalysisRun,
    retrieval_result: "RetrievalResult",
    factors: list["Factor"],
    score_outcome: "ScoreOutcome",
) -> None:
    mark_stage_running(
        request,
        "brief_generation",
        "Writing the editorial brief, recommendation context, and caveats.",
    )
    session.add(request)
    session.commit()

    brief = processor._build_brief(
        session,
        request,
        market,
        rule_parse,
        score_outcome,
        retrieval_result.source_contexts,
        factors,
        score_outcome.priced_in_risk,
        retrieval_result.social_intel_summary,
    )

    mark_stage_complete(
        request,
        "brief_generation",
        "Summary, caveats, and recommendation language are ready to inspect.",
    )
    mark_stage_complete(
        request,
        "complete",
        "Analysis complete. The research brief and audit are ready.",
    )

    analysis_run.market_mid_prob = processor._market_prior(market)
    analysis_run.yes_exec_price = market.yes_ask if market else None
    analysis_run.no_exec_price = market.no_ask if market else None
    analysis_run.priced_in_risk_label = score_outcome.priced_in_risk
    analysis_run.numeric_estimate_available = score_outcome.numeric_estimate_available
    analysis_run.numeric_estimate_reason = score_outcome.numeric_estimate_reason
    analysis_run.qualitative_label = score_outcome.qualitative_label
    analysis_run.p_hat = score_outcome.p_hat
    analysis_run.p_low = score_outcome.p_low
    analysis_run.p_high = score_outcome.p_high
    analysis_run.confidence_label = score_outcome.recommendation.confidence_label
    analysis_run.recommendation_label = score_outcome.recommendation.recommendation_label
    analysis_run.final_summary = brief.final_summary
    analysis_run.why_wrong_summary = brief.why_wrong_summary
    analysis_run.evidence_update = (
        round(analysis_run.p_hat - analysis_run.market_mid_prob, 4)
        if analysis_run.p_hat is not None and analysis_run.market_mid_prob is not None
        else None
    )
    analysis_run.blind_p_hat = score_outcome.blind_p_hat
    analysis_run.market_match_json = {
        **(analysis_run.market_match_json or {}),
        "price_history_signal": score_outcome.price_history_signal,
    }

    recommendation = Recommendation(
        analysis_run_id=analysis_run.id,
        recommendation_label=score_outcome.recommendation.recommendation_label,
        confidence_label=score_outcome.recommendation.confidence_label,
        edge_yes=score_outcome.recommendation.edge_yes,
        edge_no=score_outcome.recommendation.edge_no,
        rationale_json=score_outcome.recommendation.rationale_json,
        created_at=datetime.now(UTC),
    )
    session.add(recommendation)

    if market is not None:
        session.add(
            Snapshot(
                market_id=market.id,
                analysis_run_id=analysis_run.id,
                snapshot_type=SnapshotTypeEnum.T0,
                yes_bid=market.yes_bid,
                yes_ask=market.yes_ask,
                no_bid=market.no_bid,
                no_ask=market.no_ask,
                midpoint_yes=processor._market_prior(market),
                created_at=datetime.now(UTC),
            )
        )

    request.template_selected = rule_parse.template_detected
    request.status = RequestStatusEnum.COMPLETE
    request.current_stage = "complete"
    request.error_message = None
    request.completed_at = datetime.now(UTC)
    session.add(request)
    session.flush()
    finalize_stage_ledger(session, request, analysis_run.id)
    events = list(
        session.scalars(
            select(ExecutionEvent).where(ExecutionEvent.analysis_run_id == analysis_run.id)
        ).all()
    )
    has_directional_evidence = any(
        factor.used_in_scoring and factor.stance.value in {"yes", "no"} for factor in factors
    )
    quality, reasons = derive_quality(events, has_directional_evidence=has_directional_evidence)
    run_sources = list(
        session.scalars(select(Source).where(Source.analysis_run_id == analysis_run.id)).all()
    )
    excluded_sources = [source for source in run_sources if source.exclusion_reason]
    if excluded_sources:
        reasons.append(
            {
                "code": "retrieval_contamination_rejected",
                "source_ids": [source.id for source in excluded_sources],
            }
        )
        if quality == RunQualityEnum.CLEAN:
            quality = RunQualityEnum.WARNING
    usable_research_sources = [
        source
        for source in run_sources
        if not source.exclusion_reason and source.source_kind != SourceKindEnum.MANUAL_INPUT
    ]
    if not usable_research_sources:
        reasons.append({"code": "no_usable_retrieval"})
        quality = RunQualityEnum.INVALID
    analysis_run.quality_state = quality
    analysis_run.quality_reasons = reasons
    session.add(analysis_run)

    prior_forecasts = session.scalar(
        select(func.count()).select_from(PublishedForecast).where(
            PublishedForecast.request_id == request.id
        )
    ) or 0
    settings = get_settings()
    session.add(
        PublishedForecast(
            analysis_run_id=analysis_run.id,
            request_id=request.id,
            market_id=market.id if market else None,
            published_at=request.completed_at,
            model_version=f"{settings.openai_model}+{settings.xai_social_model}",
            prompt_versions_json={
                event.task_name: event.prompt_version
                for event in events
                if event.task_name and event.prompt_version
            },
            market_snapshot_json={
                "yes_bid": market.yes_bid if market else None,
                "yes_ask": market.yes_ask if market else None,
                "no_bid": market.no_bid if market else None,
                "no_ask": market.no_ask if market else None,
                "midpoint_yes": analysis_run.market_mid_prob,
            },
            quality_state=quality,
            blind_p_hat=analysis_run.blind_p_hat,
            attempt_reason=analysis_run.attempt_reason,
            is_repeat=prior_forecasts > 0,
            p_hat=analysis_run.p_hat,
            market_mid_prob=analysis_run.market_mid_prob,
        )
    )
    session.commit()

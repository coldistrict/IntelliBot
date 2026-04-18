from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models import AnalysisRequest, AnalysisRun, Market, Recommendation, RuleParse, Snapshot
from app.models.enums import RequestStatusEnum, SnapshotTypeEnum
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
    session.commit()

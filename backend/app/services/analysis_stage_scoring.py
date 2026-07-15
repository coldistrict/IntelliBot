from __future__ import annotations

from typing import TYPE_CHECKING

from app.models import AnalysisRequest, Factor, Market, RuleParse, SocialIntelSummary
from app.services.analysis_progress import mark_stage_complete, mark_stage_running

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models import FactClaim
    from app.services.analysis_pipeline import AnalysisProcessor, ScoreOutcome, SourceContext


def run_scoring_stage(
    processor: "AnalysisProcessor",
    *,
    session: "Session",
    request: AnalysisRequest,
    market: Market | None,
    rule_parse: RuleParse,
    source_contexts: list["SourceContext"],
    social_intel_summary: SocialIntelSummary | None,
    facts: list["FactClaim"],
    factors: list[Factor],
) -> "ScoreOutcome":
    mark_stage_running(
        request,
        "probability_estimation",
        "Applying factor weights, uncertainty adjustments, and market context.",
    )
    session.add(request)
    session.commit()

    score_outcome = processor._score_analysis(
        request,
        market,
        rule_parse,
        source_contexts,
        social_intel_summary,
        facts,
        factors,
    )
    # Independent evidence-only read, produced without market context so the
    # scoreboard can compare the model against the market on resolved runs.
    score_outcome.blind_p_hat = processor.blind_probability_estimate(
        session,
        rule_parse,
        source_contexts,
        facts,
        factors,
    )

    mark_stage_complete(
        request,
        "probability_estimation",
        (
            f"Scored {sum(1 for factor in factors if factor.used_in_scoring)} factor(s) "
            + (
                f"into a YES {processor._format_probability(score_outcome.p_hat)} / "
                f"NO {processor._format_probability(1 - (score_outcome.p_hat or 0))} estimate."
                if score_outcome.p_hat is not None
                else f"and returned a qualitative-only assessment ({score_outcome.qualitative_label.value.replace('_', ' ') if score_outcome.qualitative_label else 'analysis only'})."
            )
        ),
    )
    session.add(request)
    session.commit()
    return score_outcome

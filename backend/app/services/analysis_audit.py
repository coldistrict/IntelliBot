from __future__ import annotations

import math
from typing import Any

from app.models import (
    AnalysisRequest,
    AnalysisRun,
    FactClaim,
    Factor,
    Recommendation,
    RuleParse,
    SocialIntelSummary,
    Source,
)
from app.models.enums import (
    ConsensusLabelEnum,
    NarrativePhaseEnum,
    PricedInRiskLabelEnum,
    RecommendationLabelEnum,
    SourceKindEnum,
    StanceEnum,
)
from app.services.analysis_progress import build_progress_snapshot
from app.services.analysis_scoring import (
    BASE_UNCERTAINTY,
    MAX_SOCIAL_EVIDENCE,
    crowd_signal_modifier,
    social_uncertainty_adjustment,
)


def _humanize(value: str | None) -> str | None:
    if value is None:
        return None
    return value.replace("_", " ")


def _format_probability(value: float | None) -> str:
    if value is None:
        return "Pending"
    percentage = value * 100
    rounded = round(percentage)
    if abs(percentage - rounded) >= 0.05:
        return f"{percentage:.1f}%"
    return f"{rounded}%"


def _factor_is_scored(factor: Factor) -> bool:
    used_in_scoring = getattr(factor, "used_in_scoring", None)
    if used_in_scoring is not None:
        return bool(used_in_scoring)
    return factor.stance in {StanceEnum.YES, StanceEnum.NO} and (factor.final_weight or 0.0) > 0


def build_display_summary(
    request: AnalysisRequest,
    *,
    rule_parse: RuleParse | None = None,
    analysis_run: AnalysisRun | None = None,
    recommendation: Recommendation | None = None,
    factors: list[Factor] | None = None,
) -> str:
    progress = build_progress_snapshot(request)
    if request.status.value == "failed":
        if progress["current_label"]:
            return (
                f"Analysis stopped during {progress['current_label'].lower()}. "
                f"{request.error_message or 'Review the failure details and rerun when ready.'}"
            )
        return request.error_message or "The analysis failed before it could finish."

    if request.status.value == "queued":
        return "The analysis is queued and will start building the research brief shortly."

    if request.status.value == "running" and progress["current_note"]:
        return f"Analysis in progress. {progress['current_note']}"

    if analysis_run and analysis_run.final_summary and analysis_run.final_summary.strip():
        return analysis_run.final_summary.strip()

    scored_yes_factors = [
        factor
        for factor in (factors or [])
        if _factor_is_scored(factor) and factor.stance == StanceEnum.YES
    ][:1]
    scored_no_factors = [
        factor
        for factor in (factors or [])
        if _factor_is_scored(factor) and factor.stance == StanceEnum.NO
    ][:1]

    if analysis_run and recommendation is not None and analysis_run.p_hat is not None:
        question = rule_parse.question_text if rule_parse else request.input_text
        label = _humanize(recommendation.recommendation_label.value) or "analysis"
        confidence = _humanize(recommendation.confidence_label.value) or "unknown"
        if analysis_run.p_hat > 0.5:
            decision = "YES is more likely"
        elif analysis_run.p_hat < 0.5:
            decision = "NO is more likely"
        else:
            decision = "the market is close to a coin flip"
        summary = (
            f"{question}: {decision}. Current model read is YES {_format_probability(analysis_run.p_hat)} / "
            f"NO {_format_probability(1 - analysis_run.p_hat)}. "
            f"The current posture is {label} with {confidence} confidence."
        )

        if scored_yes_factors:
            summary += f" Best YES case: {scored_yes_factors[0].rationale or 'supportive evidence was found.'}"
        if scored_no_factors:
            summary += f" Main NO case: {scored_no_factors[0].rationale or 'contrary evidence remains visible.'}"
        return summary

    return "The analysis is still assembling the research brief."


def build_analysis_audit(
    *,
    request: AnalysisRequest,
    rule_parse: RuleParse | None,
    analysis_run: AnalysisRun | None,
    recommendation: Recommendation | None,
    sources: list[Source],
    facts: list[FactClaim],
    factors: list[Factor],
    social_intel_summary: SocialIntelSummary | None,
) -> dict[str, Any] | None:
    if rule_parse is None or analysis_run is None:
        return None

    fact_lookup = {fact.id: fact for fact in facts}
    source_lookup = {source.id: source for source in sources}
    contributing_factor_ids = {
        factor.fact_claim_id
        for factor in factors
        if _factor_is_scored(factor) and factor.stance in {StanceEnum.YES, StanceEnum.NO}
    }
    contributing_source_ids = {
        fact.source_id for fact in facts if fact.id in contributing_factor_ids
    }

    factor_rows: list[dict[str, Any]] = []
    non_social_evidence = 0.0
    raw_social_evidence = 0.0
    directional_factor_count = 0
    has_yes = False
    has_no = False

    for factor in factors:
        fact = fact_lookup.get(factor.fact_claim_id)
        source = source_lookup.get(fact.source_id) if fact else None
        direction = 1.0 if factor.stance == StanceEnum.YES else -1.0 if factor.stance == StanceEnum.NO else 0.0
        scored = _factor_is_scored(factor)
        signed_contribution = round(direction * factor.final_weight, 4) if scored else 0.0
        if scored and factor.stance == StanceEnum.YES:
            has_yes = True
            directional_factor_count += 1
        elif scored and factor.stance == StanceEnum.NO:
            has_no = True
            directional_factor_count += 1

        if scored and source and source.source_kind in {SourceKindEnum.MANUAL_SOCIAL, SourceKindEnum.LIVE_SOCIAL}:
            raw_social_evidence += signed_contribution
        elif scored:
            non_social_evidence += signed_contribution

        factor_rows.append(
            {
                "factor_id": factor.id,
                "fact_claim_id": factor.fact_claim_id,
                "source_title": source.title if source else None,
                "source_kind": source.source_kind if source else None,
                "source_tier": source.source_tier if source else None,
                "stance": factor.stance,
                "strength": factor.strength,
                "evidence_role": factor.evidence_role,
                "used_in_scoring": scored,
                "exclusion_reason": factor.exclusion_reason,
                "directness": fact.directness if fact else None,
                "verifier_status": fact.verifier_status if fact else None,
                "source_weight": factor.source_weight,
                "freshness_multiplier": factor.freshness_multiplier,
                "uniqueness_multiplier": factor.uniqueness_multiplier,
                "template_multiplier": factor.template_multiplier,
                "final_weight": factor.final_weight,
                "signed_contribution": signed_contribution,
                "rationale": factor.rationale,
            }
        )

    factor_rows.sort(
        key=lambda item: (not item["used_in_scoring"], -abs(item["signed_contribution"])),
    )
    capped_social_evidence = max(min(raw_social_evidence, MAX_SOCIAL_EVIDENCE), -MAX_SOCIAL_EVIDENCE)
    crowd_signal = crowd_signal_modifier(social_intel_summary)
    total_evidence = max(
        min(non_social_evidence + capped_social_evidence + crowd_signal.evidence_delta, 2.5),
        -2.5,
    )

    prior_probability = analysis_run.market_mid_prob
    prior_logit = None
    if prior_probability is not None:
        bounded_prior = min(max(prior_probability, 0.01), 0.99)
        prior_logit = round(math.log(bounded_prior / (1 - bounded_prior)), 4)

    uncertainty_adjustments: list[dict[str, Any]] = []
    base_uncertainty = BASE_UNCERTAINTY[rule_parse.template_detected]

    low_clarity = max(0.0, 0.9 - rule_parse.clarity_score) * 0.12
    if low_clarity:
        uncertainty_adjustments.append(
            {
                "key": "clarity_gap",
                "label": "Clarity gap",
                "amount": round(low_clarity, 4),
                "note": "Lower rule clarity widens the range.",
            }
        )

    resolution_risk = rule_parse.resolution_risk * 0.15
    if resolution_risk:
        uncertainty_adjustments.append(
            {
                "key": "resolution_risk",
                "label": "Resolution risk",
                "amount": round(resolution_risk, 4),
                "note": "Higher resolution risk adds uncertainty to the final range.",
            }
        )

    if analysis_run.priced_in_risk_label == PricedInRiskLabelEnum.MEDIUM:
        uncertainty_adjustments.append(
            {
                "key": "priced_in_medium",
                "label": "Priced-in risk",
                "amount": 0.05,
                "note": "The visible evidence may already be partially reflected in the market.",
            }
        )
    elif analysis_run.priced_in_risk_label == PricedInRiskLabelEnum.HIGH:
        uncertainty_adjustments.append(
            {
                "key": "priced_in_high",
                "label": "Priced-in risk",
                "amount": 0.10,
                "note": "The market likely reacted to the same information already.",
            }
        )

    has_official_sources = any(
        source.source_tier.value in {"official_primary", "official_statement"}
        for source in sources
    )
    if not has_official_sources:
        uncertainty_adjustments.append(
            {
                "key": "no_official_sources",
                "label": "No official sources",
                "amount": 0.07,
                "note": "The run lacks direct official evidence.",
            }
        )

    if any(source.source_kind == SourceKindEnum.MANUAL_SOCIAL for source in sources):
        uncertainty_adjustments.append(
            {
                "key": "manual_social",
                "label": "Manual social reliance",
                "amount": 0.03,
                "note": "User-provided social context widens the range slightly.",
            }
        )

    if (
        analysis_run.yes_exec_price is None
        or analysis_run.no_exec_price is None
        or not analysis_run.numeric_estimate_available
    ):
        uncertainty_adjustments.append(
            {
                "key": "missing_market_prior",
                "label": "Missing executable market prior",
                "amount": 0.04,
                "note": "No executable bid/ask pair was available for a cleaner anchor.",
            }
        )

    if analysis_run.market and analysis_run.market.spread is not None and analysis_run.market.spread > 0.05:
        uncertainty_adjustments.append(
            {
                "key": "wide_spread",
                "label": "Wide spread",
                "amount": 0.04,
                "note": "A wider spread weakens the market prior.",
            }
        )

    if has_yes and has_no:
        uncertainty_adjustments.append(
            {
                "key": "contradictory_factors",
                "label": "Contradictory factors",
                "amount": 0.05,
                "note": "Both YES and NO evidence remain live in the factor set.",
            }
        )

    social_uncertainty = social_uncertainty_adjustment(social_intel_summary)
    if social_uncertainty:
        uncertainty_adjustments.append(
            {
                "key": "social_narrative",
                "label": "Social narrative modifier",
                "amount": round(social_uncertainty, 4),
                "note": crowd_signal.reason,
            }
        )

    total_uncertainty = min(
        max(base_uncertainty + sum(item["amount"] for item in uncertainty_adjustments), 0.05),
        0.40,
    )

    friction_buffer = None
    recommendation_note = "Recommendation math will appear after scoring finishes."
    if recommendation is not None:
        friction_buffer = recommendation.rationale_json.get("friction_buffer")
        if recommendation.recommendation_label == RecommendationLabelEnum.ANALYSIS_ONLY:
            recommendation_note = str(
                recommendation.rationale_json.get(
                    "reason",
                    "No executable market was available, so the output remains analysis-only.",
                )
            )
        elif not analysis_run.numeric_estimate_available:
            recommendation_note = (
                "Model probability is shown for transparency, but the numeric estimate remained unapproved because "
                + (
                    analysis_run.numeric_estimate_reason
                    or "the directional evidence did not clear the numeric threshold"
                )
                + "."
            )
        else:
            recommendation_note = (
                f"YES edge compares p_low to yes ask, and NO edge compares 1 - p_high to no ask. "
                f"The chosen label is {_humanize(recommendation.recommendation_label.value)}."
            )

    confidence_reason_parts = []
    if analysis_run.p_high is not None and analysis_run.p_low is not None:
        width = analysis_run.p_high - analysis_run.p_low
        confidence_reason_parts.append(
            f"Range width is {round(width * 100)} points with {directional_factor_count} directional factor(s)."
        )
    else:
        confidence_reason_parts.append(
            f"The run stayed qualitative-only with {directional_factor_count} scored directional factor(s)."
        )
    if social_intel_summary and (
        social_intel_summary.consensus_label in {ConsensusLabelEnum.MIXED, ConsensusLabelEnum.UNCLEAR}
        or social_intel_summary.narrative_phase in {NarrativePhaseEnum.CROWDED, NarrativePhaseEnum.PRICED_IN}
    ):
        confidence_reason_parts.append("Live X narrative reduced confidence relative to the base range.")

    return {
        "rule_interpretation": {
            "template": rule_parse.template_detected,
            "claim_family": rule_parse.claim_family,
            "action": rule_parse.action,
            "yes_condition": rule_parse.yes_condition,
            "no_condition": rule_parse.no_condition,
            "deadline_text": rule_parse.deadline_text,
            "resolution_definition": rule_parse.resolution_definition,
            "clarity_score": rule_parse.clarity_score,
            "resolution_risk": rule_parse.resolution_risk,
        },
        "source_lanes": {
            "official": sum(1 for source in sources if source.source_kind == SourceKindEnum.OFFICIAL),
            "news": sum(1 for source in sources if source.source_kind == SourceKindEnum.NEWS),
            "premium": sum(1 for source in sources if source.source_kind == SourceKindEnum.PREMIUM_NEWS),
            "live_social": sum(1 for source in sources if source.source_kind == SourceKindEnum.LIVE_SOCIAL),
            "manual_social": sum(1 for source in sources if source.source_kind == SourceKindEnum.MANUAL_SOCIAL),
            "manual_input": sum(1 for source in sources if source.source_kind == SourceKindEnum.MANUAL_INPUT),
            "total": len(sources),
            "contributing_sources": len(contributing_source_ids),
        },
        "social_modifier": (
            {
                "consensus_label": social_intel_summary.consensus_label,
                "consensus_strength": social_intel_summary.consensus_strength,
                "narrative_phase": social_intel_summary.narrative_phase,
                "summary": social_intel_summary.summary,
                "broad_posts_sampled": social_intel_summary.broad_posts_sampled,
                "trusted_accounts_count": social_intel_summary.trusted_accounts_count,
                "crowd_signal_direction": crowd_signal.direction,
                "crowd_signal_evidence": crowd_signal.evidence_delta,
                "crowd_signal_uncertainty": crowd_signal.uncertainty_delta,
                "crowd_signal_reason": crowd_signal.reason,
            }
            if social_intel_summary
            else None
        ),
        "probability": {
            "numeric_estimate_available": analysis_run.numeric_estimate_available,
            "numeric_estimate_reason": analysis_run.numeric_estimate_reason,
            "prior_probability": prior_probability,
            "prior_logit": prior_logit,
            "non_social_evidence": round(non_social_evidence, 4),
            "raw_social_evidence": round(raw_social_evidence, 4),
            "capped_social_evidence": round(capped_social_evidence, 4),
            "crowd_signal_evidence": crowd_signal.evidence_delta,
            "total_evidence": round(total_evidence, 4),
            "p_hat": analysis_run.p_hat,
        },
        "uncertainty": {
            "base_uncertainty": round(base_uncertainty, 4),
            "adjustments": uncertainty_adjustments,
            "total_uncertainty": round(total_uncertainty, 4),
            "p_low": analysis_run.p_low,
            "p_high": analysis_run.p_high,
        },
        "recommendation_math": {
            "yes_exec_price": analysis_run.yes_exec_price,
            "no_exec_price": analysis_run.no_exec_price,
            "friction_buffer": friction_buffer,
            "edge_yes": recommendation.edge_yes if recommendation else None,
            "edge_no": recommendation.edge_no if recommendation else None,
            "chosen_label": recommendation.recommendation_label if recommendation else None,
            "note": recommendation_note,
        },
        "confidence": {
            "final_label": analysis_run.confidence_label,
            "reason": " ".join(confidence_reason_parts),
        },
        "factor_contributions": factor_rows,
    }

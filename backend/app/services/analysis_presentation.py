from __future__ import annotations

from typing import Any

from app.models import AnalysisRequest, AnalysisRun, FactClaim, Factor, Recommendation, RuleParse, Source
from app.models.enums import StanceEnum
from app.services.analysis_artifacts import build_artifact_statuses
from app.services.analysis_audit import build_display_summary
from app.services.analysis_progress import build_progress_snapshot


def _humanize(value: str | None) -> str:
    if not value:
        return "Unavailable"
    return value.replace("_", " ")


def _format_probability(value: float | None) -> str:
    if value is None:
        return "Pending"
    percentage = value * 100
    rounded = round(percentage)
    if abs(percentage - rounded) >= 0.05:
        return f"{percentage:.1f}%"
    return f"{rounded}%"


def _signed_weight(factor: Factor) -> float | None:
    if not factor.used_in_scoring:
        return None
    direction = 1 if factor.stance == StanceEnum.YES else -1 if factor.stance == StanceEnum.NO else 0
    return round(direction * factor.final_weight, 4)


def _evidence_item(*, factor: Factor, fact: FactClaim | None, source: Source | None) -> dict[str, Any]:
    note_parts: list[str] = []
    if source:
        source_label = source.title or source.domain
        if source_label:
            note_parts.append(source_label)
    if factor.evidence_role:
        note_parts.append(_humanize(factor.evidence_role.value))
    if factor.used_in_scoring:
        note_parts.append(f"signed weight {_signed_weight(factor):+.4f}")
    elif factor.exclusion_reason:
        note_parts.append(factor.exclusion_reason)

    return {
        "factor_id": factor.id,
        "source_id": source.id if source else None,
        "passage_id": fact.passage_id if fact else None,
        "title": factor.rationale or (fact.normalized_fact if fact else "Evidence item"),
        "note": " · ".join(note_parts) if note_parts else None,
        "evidence_role": factor.evidence_role,
        "source_title": source.title if source else None,
        "signed_weight": _signed_weight(factor),
    }


def _source_for_factor(
    factor: Factor,
    fact_lookup: dict[int, FactClaim],
    source_lookup: dict[int, Source],
) -> Source | None:
    fact = fact_lookup.get(factor.fact_claim_id)
    if fact is None:
        return None
    return source_lookup.get(fact.source_id)


def build_analysis_presentation(
    *,
    request: AnalysisRequest,
    rule_parse: RuleParse | None,
    analysis_run: AnalysisRun | None,
    recommendation: Recommendation | None,
    sources: list[Source],
    facts: list[FactClaim],
    factors: list[Factor],
) -> dict[str, Any]:
    progress = build_progress_snapshot(request)
    display_summary = build_display_summary(
        request,
        rule_parse=rule_parse,
        analysis_run=analysis_run,
        recommendation=recommendation,
        factors=factors,
    )
    fact_lookup = {fact.id: fact for fact in facts}
    source_lookup = {source.id: source for source in sources}

    why_yes = [
        _evidence_item(
            factor=factor,
            fact=fact_lookup.get(factor.fact_claim_id),
            source=_source_for_factor(factor, fact_lookup, source_lookup),
        )
        for factor in factors
        if factor.used_in_scoring and factor.stance == StanceEnum.YES
    ][:4]
    why_no = [
        _evidence_item(
            factor=factor,
            fact=fact_lookup.get(factor.fact_claim_id),
            source=_source_for_factor(factor, fact_lookup, source_lookup),
        )
        for factor in factors
        if factor.used_in_scoring and factor.stance == StanceEnum.NO
    ][:4]
    context = [
        _evidence_item(
            factor=factor,
            fact=fact_lookup.get(factor.fact_claim_id),
            source=_source_for_factor(factor, fact_lookup, source_lookup),
        )
        for factor in factors
        if not factor.used_in_scoring
    ][:6]

    if request.status.value == "failed":
        thesis = (
            f"Analysis stopped during {progress['current_label'].lower()}."
            if progress["current_label"]
            else "Analysis stopped before the memo could finish."
        )
    elif request.status.value in {"queued", "running"}:
        thesis = "The memo is still assembling. Partial artifacts will unlock as each stage finishes."
    elif analysis_run and analysis_run.p_hat is not None:
        confidence = _humanize(analysis_run.confidence_label.value)
        thesis = (
            f"Current read: YES {_format_probability(analysis_run.p_hat)} / "
            f"NO {_format_probability(1 - analysis_run.p_hat)} with {confidence.lower()} confidence."
        )
    elif analysis_run and analysis_run.qualitative_label is not None:
        confidence = _humanize(analysis_run.confidence_label.value)
        thesis = f"Current read: {_humanize(analysis_run.qualitative_label.value)} with {confidence.lower()} confidence."
    else:
        thesis = display_summary

    if request.error_message:
        status_note = request.error_message
    elif progress["current_note"]:
        status_note = progress["current_note"]
    elif analysis_run and analysis_run.numeric_estimate_reason:
        status_note = analysis_run.numeric_estimate_reason
    else:
        status_note = None

    caveats = (
        analysis_run.why_wrong_summary
        if analysis_run and analysis_run.why_wrong_summary
        else "The read can still change as new official information, clearer resolution language, or stronger contradictory evidence arrives."
    )

    what_it_means = display_summary
    if analysis_run and analysis_run.final_summary:
        what_it_means = analysis_run.final_summary

    return {
        "headline": request.input_text,
        "thesis": thesis,
        "status_note": status_note,
        "brief_sections": {
            "what_it_means": what_it_means,
            "why_yes": why_yes,
            "why_no": why_no,
            "context": context,
            "caveats": caveats,
        },
        "artifact_statuses": build_artifact_statuses(
            progress=progress,
            has_rule_parse=rule_parse is not None,
            has_sources=bool(sources),
            has_social_sources=bool(analysis_run and analysis_run.social_intel_summary),
            has_factors=bool(factors),
            has_analysis_run=analysis_run is not None,
            has_final_summary=bool(analysis_run and analysis_run.final_summary),
        ),
    }

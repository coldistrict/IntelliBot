from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from app.models import FactClaim, Factor, SocialIntelSummary, Source
from app.models.enums import (
    ConsensusLabelEnum,
    ConsensusStrengthEnum,
    DirectnessEnum,
    NarrativePhaseEnum,
    SourceKindEnum,
    SourceTierEnum,
    StanceEnum,
    StrengthEnum,
    TemplateKey,
    VerifierStatusEnum,
)
from app.services.analysis_social_trust import social_metadata_is_trusted

SOURCE_WEIGHTS = {
    SourceTierEnum.OFFICIAL_PRIMARY: 0.45,
    SourceTierEnum.OFFICIAL_STATEMENT: 0.30,
    SourceTierEnum.EXPERT_ANALYSIS: 0.24,
    SourceTierEnum.PREMIUM_NEWS: 0.25,
    SourceTierEnum.REPUTABLE_NEWS: 0.20,
    SourceTierEnum.OFFICIAL_SOCIAL: 0.12,
    SourceTierEnum.HIGH_TRUST_SOCIAL: 0.10,
    SourceTierEnum.REPORTER_SOCIAL: 0.06,
    SourceTierEnum.GENERIC_SOCIAL: 0.02,
}

STRENGTH_MULTIPLIERS = {
    StrengthEnum.STRONG: 1.0,
    StrengthEnum.MEDIUM: 0.65,
    StrengthEnum.WEAK: 0.35,
}

DIRECTNESS_MULTIPLIERS = {
    DirectnessEnum.DIRECT: 1.0,
    DirectnessEnum.INDIRECT: 0.7,
    DirectnessEnum.BACKGROUND: 0.3,
}

VERIFICATION_MULTIPLIERS = {
    VerifierStatusEnum.SUPPORTED: 1.0,
    VerifierStatusEnum.AMBIGUOUS: 0.5,
    VerifierStatusEnum.REJECTED: 0.0,
}

TEMPLATE_MULTIPLIERS = {
    TemplateKey.OFFICIAL_EVENT: 1.0,
    TemplateKey.MACRO_POLICY: 0.7,
    TemplateKey.LEGAL_CASE: 0.75,
    TemplateKey.NARRATIVE_MANUAL: 0.55,
    TemplateKey.GENERIC_MANUAL: 0.6,
}

BASE_UNCERTAINTY = {
    TemplateKey.OFFICIAL_EVENT: 0.08,
    TemplateKey.MACRO_POLICY: 0.15,
    TemplateKey.LEGAL_CASE: 0.14,
    TemplateKey.NARRATIVE_MANUAL: 0.22,
    TemplateKey.GENERIC_MANUAL: 0.20,
}

MAX_SOCIAL_EVIDENCE = 0.18
MAX_CROWD_SIGNAL_EVIDENCE = 0.30
CROWD_SIGNAL_STRENGTH_EVIDENCE = {
    ConsensusStrengthEnum.WEAK: 0.045,
    ConsensusStrengthEnum.MEDIUM: 0.14,
    ConsensusStrengthEnum.STRONG: 0.26,
}
CROWD_SIGNAL_STRENGTH_UNCERTAINTY = {
    ConsensusStrengthEnum.WEAK: 0.025,
    ConsensusStrengthEnum.MEDIUM: 0.04,
    ConsensusStrengthEnum.STRONG: 0.055,
}
CROWD_SIGNAL_PHASE_MULTIPLIER = {
    NarrativePhaseEnum.FRESH: 1.0,
    NarrativePhaseEnum.EMERGING: 1.0,
    NarrativePhaseEnum.CROWDED: 0.75,
    NarrativePhaseEnum.PRICED_IN: 0.55,
}


@dataclass(frozen=True)
class CrowdSignalModifier:
    direction: ConsensusLabelEnum | None
    evidence_delta: float
    uncertainty_delta: float
    reason: str
    volume_multiplier: float
    phase_multiplier: float


def sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-value))


def logit(probability: float | None) -> float:
    safe_probability = min(max(probability or 0.5, 1e-6), 1 - 1e-6)
    return math.log(safe_probability / (1 - safe_probability))


def factor_used_in_scoring(factor: Factor | Any) -> bool:
    return bool(factor.used_in_scoring) and factor.stance in {StanceEnum.YES, StanceEnum.NO}


def source_is_factor_eligible(source: Source) -> bool:
    if source.source_kind == SourceKindEnum.LIVE_SOCIAL:
        return social_metadata_is_trusted(
            source_tier=source.source_tier,
            metadata=source.metadata_json,
        )
    return source.source_kind != SourceKindEnum.MANUAL_SOCIAL


def capped_evidence_score(
    factors: list[Factor | Any],
    fact_lookup: dict[int, FactClaim],
    source_lookup: dict[int, Source],
) -> float:
    non_social_evidence = 0.0
    social_evidence = 0.0

    for factor in factors:
        if not factor_used_in_scoring(factor) or factor.stance == StanceEnum.NEUTRAL:
            continue
        fact = fact_lookup.get(factor.fact_claim_id)
        source = source_lookup.get(fact.source_id) if fact else None
        direction = 1.0 if factor.stance == StanceEnum.YES else -1.0
        contribution = direction * factor.final_weight
        if source and source.source_kind in {SourceKindEnum.MANUAL_SOCIAL, SourceKindEnum.LIVE_SOCIAL}:
            social_evidence += contribution
        else:
            non_social_evidence += contribution

    social_evidence = max(min(social_evidence, MAX_SOCIAL_EVIDENCE), -MAX_SOCIAL_EVIDENCE)
    return non_social_evidence + social_evidence


def has_contradictory_factors(factors: list[Factor]) -> bool:
    has_yes = any(factor_used_in_scoring(factor) and factor.stance == StanceEnum.YES for factor in factors)
    has_no = any(factor_used_in_scoring(factor) and factor.stance == StanceEnum.NO for factor in factors)
    return has_yes and has_no


def _crowd_volume_multiplier(posts_sampled: int) -> float:
    if posts_sampled <= 0:
        return 0.0
    if posts_sampled < 8:
        return 0.35
    if posts_sampled < 15:
        return 0.70
    return 1.0


def crowd_signal_modifier(
    social_intel_summary: SocialIntelSummary | None,
) -> CrowdSignalModifier:
    if social_intel_summary is None:
        return CrowdSignalModifier(
            direction=None,
            evidence_delta=0.0,
            uncertainty_delta=0.0,
            reason="No live X crowd signal was collected.",
            volume_multiplier=0.0,
            phase_multiplier=0.0,
        )

    volume_multiplier = _crowd_volume_multiplier(social_intel_summary.broad_posts_sampled)
    phase_multiplier = CROWD_SIGNAL_PHASE_MULTIPLIER[social_intel_summary.narrative_phase]
    direction_multiplier = {
        ConsensusLabelEnum.BULLISH: 1.0,
        ConsensusLabelEnum.BEARISH: -1.0,
    }.get(social_intel_summary.consensus_label, 0.0)

    if direction_multiplier == 0.0 or volume_multiplier == 0.0:
        reason = (
            "Broad X flow is modifier-only because it is not directionally clear."
            if volume_multiplier
            else "Broad X flow is modifier-only because no broad posts were sampled."
        )
        return CrowdSignalModifier(
            direction=None,
            evidence_delta=0.0,
            uncertainty_delta=0.0,
            reason=reason,
            volume_multiplier=volume_multiplier,
            phase_multiplier=phase_multiplier,
        )

    raw_evidence = (
        CROWD_SIGNAL_STRENGTH_EVIDENCE[social_intel_summary.consensus_strength]
        * volume_multiplier
        * phase_multiplier
    )
    evidence_delta = round(
        max(min(raw_evidence, MAX_CROWD_SIGNAL_EVIDENCE), -MAX_CROWD_SIGNAL_EVIDENCE)
        * direction_multiplier,
        4,
    )
    trust_multiplier = 1.0 if social_intel_summary.trusted_accounts_count == 0 else 0.70
    uncertainty_delta = round(
        CROWD_SIGNAL_STRENGTH_UNCERTAINTY[social_intel_summary.consensus_strength]
        * volume_multiplier
        * trust_multiplier,
        4,
    )
    phase_label = social_intel_summary.narrative_phase.value.replace("_", " ")
    reason = (
        f"{social_intel_summary.consensus_strength.value} "
        f"{social_intel_summary.consensus_label.value} broad X flow from "
        f"{social_intel_summary.broad_posts_sampled} sampled post(s), discounted for a "
        f"{phase_label} narrative phase."
    )
    if social_intel_summary.trusted_accounts_count == 0:
        reason += " No trusted account posts were retained, so this stays capped and widens uncertainty."
    else:
        reason += " Trusted account evidence remains separate from this crowd-flow modifier."

    return CrowdSignalModifier(
        direction=social_intel_summary.consensus_label,
        evidence_delta=evidence_delta,
        uncertainty_delta=uncertainty_delta,
        reason=reason,
        volume_multiplier=volume_multiplier,
        phase_multiplier=phase_multiplier,
    )


def social_uncertainty_adjustment(social_intel_summary: SocialIntelSummary | None) -> float:
    if social_intel_summary is None:
        return 0.0
    crowd_signal = crowd_signal_modifier(social_intel_summary)
    if crowd_signal.evidence_delta:
        return crowd_signal.uncertainty_delta
    if social_intel_summary.consensus_label == ConsensusLabelEnum.MIXED:
        return 0.03
    if social_intel_summary.consensus_label == ConsensusLabelEnum.UNCLEAR:
        return 0.02
    if social_intel_summary.consensus_strength == ConsensusStrengthEnum.WEAK:
        return 0.02
    return 0.0

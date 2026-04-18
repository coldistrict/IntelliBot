from __future__ import annotations

import math
from typing import Any

from app.models import FactClaim, Factor, SocialIntelSummary, Source
from app.models.enums import (
    ConsensusStrengthEnum,
    DirectnessEnum,
    SourceKindEnum,
    SourceTierEnum,
    StanceEnum,
    StrengthEnum,
    TemplateKey,
    VerifierStatusEnum,
)

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


def sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-value))


def logit(probability: float | None) -> float:
    safe_probability = min(max(probability or 0.5, 1e-6), 1 - 1e-6)
    return math.log(safe_probability / (1 - safe_probability))


def factor_used_in_scoring(factor: Factor | Any) -> bool:
    return bool(factor.used_in_scoring) and factor.stance in {StanceEnum.YES, StanceEnum.NO}


def source_is_factor_eligible(source: Source) -> bool:
    if source.source_kind == SourceKindEnum.LIVE_SOCIAL:
        return source.source_tier in {SourceTierEnum.OFFICIAL_SOCIAL, SourceTierEnum.HIGH_TRUST_SOCIAL}
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


def social_uncertainty_adjustment(social_intel_summary: SocialIntelSummary | None) -> float:
    if social_intel_summary is None:
        return 0.0
    if social_intel_summary.consensus_strength == ConsensusStrengthEnum.STRONG:
        return -0.01
    if social_intel_summary.consensus_strength == ConsensusStrengthEnum.WEAK:
        return 0.02
    return 0.0


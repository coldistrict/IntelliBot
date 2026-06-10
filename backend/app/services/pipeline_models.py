from __future__ import annotations

from datetime import datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, Field

from app.models.enums import (
    ClaimTypeEnum,
    ClaimFamilyEnum,
    ConfidenceLabelEnum,
    ConsensusLabelEnum,
    ConsensusStrengthEnum,
    DirectnessEnum,
    EvidenceRoleEnum,
    NarrativePhaseEnum,
    QualitativeLabelEnum,
    RecommendationLabelEnum,
    SourceTierEnum,
    StanceEnum,
    StrengthEnum,
    TemplateKey,
    VerifierStatusEnum,
)


class DirectionalScoringPolicyDraft(TypedDict):
    allowed_roles: list[EvidenceRoleEnum]
    commentary_mode: Literal["none", "expert_only", "bounded"]
    procedural_mode: Literal["uncertainty_only"]


class RuleParseDraft(BaseModel):
    question_text: str
    event: str
    entity_names: list[str] = Field(default_factory=list)
    action: str
    claim_family: ClaimFamilyEnum
    yes_condition: str
    no_condition: str
    deadline_text: str | None = None
    deadline_utc: datetime | None = None
    timezone_text: str | None = None
    resolution_definition: str | None = None
    directional_scoring_policy: DirectionalScoringPolicyDraft
    official_resolution_source: str | None = None
    fallback_sources: list[str] = Field(default_factory=list)
    official_domains: list[str] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    clarity_score: float
    resolution_risk: float
    suitable_for_auto: bool
    template_detected: TemplateKey


class ExtractedFactDraft(BaseModel):
    normalized_fact: str
    exact_quote: str
    claim_type: ClaimTypeEnum
    directness: DirectnessEnum
    extracted_timestamp: datetime | None = None


class VerifiedFactDraft(BaseModel):
    verifier_status: VerifierStatusEnum
    verifier_notes: str | None = None


class EvidenceRoleDraft(BaseModel):
    evidence_role: EvidenceRoleEnum


class FactorMappingDraft(BaseModel):
    stance: StanceEnum
    strength: StrengthEnum
    evidence_role: EvidenceRoleEnum
    used_in_scoring: bool
    exclusion_reason: str | None = None
    rationale: str | None = None


class EvidenceAdjudicationDraft(BaseModel):
    stance: StanceEnum
    strength: StrengthEnum
    evidence_role: EvidenceRoleEnum
    used_in_scoring: bool
    relevance_score: float = Field(ge=0.0, le=1.0)
    reliability_score: float = Field(ge=0.0, le=1.0)
    directional_score: float = Field(ge=-1.0, le=1.0)
    rationale: str


class BriefDraft(BaseModel):
    final_summary: str
    why_wrong_summary: str


class TrustedSocialPostDraft(BaseModel):
    handle: str
    display_name: str
    post_url: str
    post_timestamp: datetime
    account_category: str
    trust_tier: SourceTierEnum
    trust_confidence: float
    relevance_reason: str
    trust_reason: str
    post_summary: str
    possible_facts: list[str] = Field(default_factory=list)
    citation_urls: list[str] = Field(default_factory=list)


class SocialIntelDraft(BaseModel):
    consensus_label: ConsensusLabelEnum
    consensus_strength: ConsensusStrengthEnum
    narrative_phase: NarrativePhaseEnum
    summary: str
    key_themes: list[str] = Field(default_factory=list)
    trusted_accounts_count: int
    broad_posts_sampled: int
    trusted_posts: list[TrustedSocialPostDraft] = Field(default_factory=list)


class SearchSourceDraft(BaseModel):
    url: str
    title: str | None = None
    excerpt: str
    domain: str | None = None
    published_at: datetime | None = None
    source_tier: SourceTierEnum
    is_paywalled: bool = False
    metadata_json: dict = Field(default_factory=dict)


class RecommendationDraft(BaseModel):
    recommendation_label: RecommendationLabelEnum
    confidence_label: ConfidenceLabelEnum
    qualitative_label: QualitativeLabelEnum | None = None
    edge_yes: float | None = None
    edge_no: float | None = None
    rationale_json: dict = Field(default_factory=dict)

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, model_validator

from app.models.enums import (
    ConfidenceLabelEnum,
    ClaimTypeEnum,
    ClaimFamilyEnum,
    ConsensusLabelEnum,
    ConsensusStrengthEnum,
    DirectnessEnum,
    EvidenceRoleEnum,
    InputTypeEnum,
    ModeEnum,
    NarrativePhaseEnum,
    PricedInRiskLabelEnum,
    QualitativeLabelEnum,
    RecommendationLabelEnum,
    RequestStatusEnum,
    ReviewDecisionEnum,
    SourceKindEnum,
    SourceTierEnum,
    StanceEnum,
    StrengthEnum,
    TemplateKey,
    VerifierStatusEnum,
)
from app.schemas.common import ORMModel
from app.schemas.market import MarketResponse


class ManualAnalysisCreateRequest(BaseModel):
    polymarket_url: HttpUrl | None = None
    polymarket_market_id: str | None = None
    custom_claim: str | None = None
    deadline_text: str | None = None
    template_requested: TemplateKey | None = None
    include_premium: bool = False
    include_live_x_intelligence: bool | None = None

    @model_validator(mode="after")
    def validate_exactly_one_primary_input(self) -> "ManualAnalysisCreateRequest":
        provided = [
            bool(self.polymarket_url),
            bool(self.polymarket_market_id),
            bool(self.custom_claim),
        ]
        if sum(provided) != 1:
            raise ValueError(
                "Provide exactly one of polymarket_url, polymarket_market_id, or custom_claim."
            )
        return self

    @property
    def resolved_input_type(self) -> InputTypeEnum:
        if self.polymarket_url:
            return InputTypeEnum.MARKET_URL
        if self.polymarket_market_id:
            return InputTypeEnum.MARKET_ID
        return InputTypeEnum.CUSTOM_CLAIM

    @property
    def resolved_input_text(self) -> str:
        return str(self.polymarket_url or self.polymarket_market_id or self.custom_claim)


class AutoScanRunRequest(BaseModel):
    note: str | None = None


class RuleParseResponse(ORMModel):
    id: int
    analysis_request_id: int
    market_id: int | None
    question_text: str
    event: str
    entity_names: list[str]
    action: str
    claim_family: ClaimFamilyEnum
    yes_condition: str
    no_condition: str
    deadline_text: str | None
    deadline_utc: datetime | None
    timezone_text: str | None
    resolution_definition: str | None
    directional_scoring_policy: dict[str, Any]
    official_resolution_source: str | None
    fallback_sources: list[str]
    official_domains: list[str]
    ambiguity_flags: list[str]
    clarity_score: float
    resolution_risk: float
    suitable_for_auto: bool
    template_detected: TemplateKey
    created_at: datetime


class RecommendationResponse(ORMModel):
    id: int
    analysis_run_id: int
    recommendation_label: RecommendationLabelEnum
    confidence_label: ConfidenceLabelEnum
    edge_yes: float | None
    edge_no: float | None
    rationale_json: dict[str, Any]
    created_at: datetime


class AnalysisRunResponse(ORMModel):
    id: int
    request_id: int
    market_id: int | None
    rule_parse_id: int
    template_selected: TemplateKey
    market_mid_prob: float | None
    yes_exec_price: float | None
    no_exec_price: float | None
    priced_in_risk_label: PricedInRiskLabelEnum | None
    numeric_estimate_available: bool
    numeric_estimate_reason: str | None
    qualitative_label: QualitativeLabelEnum | None
    p_hat: float | None
    p_low: float | None
    p_high: float | None
    confidence_label: ConfidenceLabelEnum
    recommendation_label: RecommendationLabelEnum
    why_wrong_summary: str | None
    final_summary: str | None
    created_at: datetime
    recommendation: RecommendationResponse | None = None


class ReviewCreateRequest(BaseModel):
    decision: ReviewDecisionEnum
    note: str | None = None


class ReviewResponse(ORMModel):
    id: int
    analysis_run_id: int
    decision: ReviewDecisionEnum
    note: str | None
    created_at: datetime


class SocialIntelSummaryResponse(ORMModel):
    id: int
    analysis_run_id: int
    consensus_label: ConsensusLabelEnum
    consensus_strength: ConsensusStrengthEnum
    narrative_phase: NarrativePhaseEnum
    summary: str
    key_themes: list[str]
    trusted_accounts_count: int
    broad_posts_sampled: int
    created_at: datetime


class SourceResponse(ORMModel):
    id: int
    analysis_run_id: int
    url: str | None
    domain: str | None
    title: str | None
    source_kind: SourceKindEnum
    source_tier: SourceTierEnum
    published_at: datetime | None
    fetched_at: datetime
    excerpt: str
    canonical_url: str | None
    is_paywalled: bool
    metadata_json: dict[str, Any]
    created_at: datetime


class DocumentResponse(ORMModel):
    id: int
    analysis_run_id: int
    source_id: int
    canonical_url: str | None
    title: str | None
    domain: str | None
    extractor: str | None
    word_count: int
    fetched_at: datetime
    created_at: datetime


class PassageResponse(ORMModel):
    id: int
    analysis_run_id: int
    source_id: int
    document_id: int
    passage_index: int
    relevance_score: float
    text: str
    created_at: datetime


class FactClaimResponse(ORMModel):
    id: int
    analysis_run_id: int
    source_id: int
    passage_id: int | None
    normalized_fact: str
    exact_quote: str
    claim_type: ClaimTypeEnum
    directness: DirectnessEnum
    event_date: datetime | None
    extracted_timestamp: datetime | None
    verifier_status: VerifierStatusEnum
    verifier_notes: str | None
    evidence_role: EvidenceRoleEnum
    uniqueness_group: str | None
    created_at: datetime


class FactorResponse(ORMModel):
    id: int
    analysis_run_id: int
    fact_claim_id: int
    stance: StanceEnum
    strength: StrengthEnum
    evidence_role: EvidenceRoleEnum
    used_in_scoring: bool
    exclusion_reason: str | None
    source_weight: float
    freshness_multiplier: float
    uniqueness_multiplier: float
    template_multiplier: float
    final_weight: float
    rationale: str | None
    created_at: datetime


class PresentationEvidenceItemResponse(BaseModel):
    factor_id: int | None = None
    source_id: int | None = None
    passage_id: int | None = None
    title: str
    note: str | None = None
    evidence_role: EvidenceRoleEnum | None = None
    source_title: str | None = None
    signed_weight: float | None = None


class PresentationBriefSectionsResponse(BaseModel):
    what_it_means: str
    why_yes: list[PresentationEvidenceItemResponse] = Field(default_factory=list)
    why_no: list[PresentationEvidenceItemResponse] = Field(default_factory=list)
    context: list[PresentationEvidenceItemResponse] = Field(default_factory=list)
    caveats: str


class PresentationArtifactStatusResponse(BaseModel):
    key: str
    label: str
    status: str
    note: str | None = None
    available: bool


class AnalysisPresentationResponse(BaseModel):
    headline: str
    thesis: str
    status_note: str | None = None
    brief_sections: PresentationBriefSectionsResponse
    artifact_statuses: list[PresentationArtifactStatusResponse] = Field(default_factory=list)


class AnalysisProgressPresentationResponse(BaseModel):
    artifact_statuses: list[PresentationArtifactStatusResponse] = Field(default_factory=list)


class AnalysisStageResponse(BaseModel):
    key: str
    label: str
    description: str
    optional: bool
    status: str
    note: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AnalysisProgressResponse(BaseModel):
    current_stage: str | None = None
    current_label: str | None = None
    current_note: str | None = None
    completed_count: int
    total_count: int
    percent_complete: int
    stages: list[AnalysisStageResponse] = Field(default_factory=list)
    last_updated_at: datetime | None = None


class AuditRuleInterpretationResponse(BaseModel):
    template: TemplateKey | None = None
    claim_family: ClaimFamilyEnum | None = None
    action: str | None = None
    yes_condition: str | None = None
    no_condition: str | None = None
    deadline_text: str | None = None
    resolution_definition: str | None = None
    clarity_score: float | None = None
    resolution_risk: float | None = None


class SourceLaneBreakdownResponse(BaseModel):
    official: int = 0
    news: int = 0
    premium: int = 0
    live_social: int = 0
    manual_social: int = 0
    manual_input: int = 0
    total: int = 0
    contributing_sources: int = 0


class SocialModifierResponse(BaseModel):
    consensus_label: ConsensusLabelEnum | None = None
    consensus_strength: ConsensusStrengthEnum | None = None
    narrative_phase: NarrativePhaseEnum | None = None
    summary: str | None = None
    broad_posts_sampled: int | None = None
    trusted_accounts_count: int | None = None
    crowd_signal_direction: ConsensusLabelEnum | None = None
    crowd_signal_evidence: float = 0.0
    crowd_signal_uncertainty: float = 0.0
    crowd_signal_reason: str | None = None


class FactorContributionResponse(BaseModel):
    factor_id: int
    fact_claim_id: int
    source_title: str | None = None
    source_kind: SourceKindEnum | None = None
    source_tier: SourceTierEnum | None = None
    stance: StanceEnum
    strength: StrengthEnum
    evidence_role: EvidenceRoleEnum
    used_in_scoring: bool
    exclusion_reason: str | None = None
    directness: DirectnessEnum | None = None
    verifier_status: VerifierStatusEnum | None = None
    source_weight: float
    freshness_multiplier: float
    uniqueness_multiplier: float
    template_multiplier: float
    final_weight: float
    signed_contribution: float
    rationale: str | None = None


class ProbabilityMathResponse(BaseModel):
    numeric_estimate_available: bool
    numeric_estimate_reason: str | None = None
    prior_probability: float | None = None
    prior_logit: float | None = None
    non_social_evidence: float
    raw_social_evidence: float
    capped_social_evidence: float
    crowd_signal_evidence: float = 0.0
    total_evidence: float
    p_hat: float | None = None


class UncertaintyAdjustmentResponse(BaseModel):
    key: str
    label: str
    amount: float
    note: str


class UncertaintyMathResponse(BaseModel):
    base_uncertainty: float | None = None
    adjustments: list[UncertaintyAdjustmentResponse] = Field(default_factory=list)
    total_uncertainty: float | None = None
    p_low: float | None = None
    p_high: float | None = None


class RecommendationComparisonResponse(BaseModel):
    yes_exec_price: float | None = None
    no_exec_price: float | None = None
    friction_buffer: float | None = None
    edge_yes: float | None = None
    edge_no: float | None = None
    chosen_label: RecommendationLabelEnum | None = None
    note: str


class ConfidenceAuditResponse(BaseModel):
    final_label: ConfidenceLabelEnum | None = None
    reason: str


class AnalysisAuditResponse(BaseModel):
    rule_interpretation: AuditRuleInterpretationResponse
    source_lanes: SourceLaneBreakdownResponse
    social_modifier: SocialModifierResponse | None = None
    probability: ProbabilityMathResponse | None = None
    uncertainty: UncertaintyMathResponse | None = None
    recommendation_math: RecommendationComparisonResponse | None = None
    confidence: ConfidenceAuditResponse | None = None
    factor_contributions: list[FactorContributionResponse] = Field(default_factory=list)


class AnalysisRequestSummary(ORMModel):
    id: int
    mode: ModeEnum
    input_type: InputTypeEnum
    input_text: str
    market_id: int | None
    market_title: str | None = None
    template_requested: TemplateKey | None
    template_selected: TemplateKey | None
    status: RequestStatusEnum
    current_stage: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    latest_recommendation_label: RecommendationLabelEnum | None = None
    latest_confidence_label: ConfidenceLabelEnum | None = None
    review_count: int = 0
    progress_percent: int | None = None
    current_stage_label: str | None = None
    current_stage_note: str | None = None
    display_summary: str | None = None
    qualitative_label: QualitativeLabelEnum | None = None


class AnalysisListResponse(BaseModel):
    items: list[AnalysisRequestSummary]
    total: int


class AnalysisQueuedResponse(BaseModel):
    request: AnalysisRequestSummary


class AnalysisProgressPollResponse(BaseModel):
    request: AnalysisRequestSummary
    progress: AnalysisProgressResponse
    presentation: AnalysisProgressPresentationResponse
    last_updated_at: datetime | None = None


class AnalysisDetailResponse(BaseModel):
    request: AnalysisRequestSummary
    market: MarketResponse | None = None
    latest_rule_parse: RuleParseResponse | None = None
    latest_run: AnalysisRunResponse | None = None
    recommendation: RecommendationResponse | None = None
    progress: AnalysisProgressResponse
    audit: AnalysisAuditResponse | None = None
    presentation: AnalysisPresentationResponse
    display_summary: str
    last_updated_at: datetime | None = None
    social_intel_summary: SocialIntelSummaryResponse | None = None
    sources: list[SourceResponse] = Field(default_factory=list)
    documents: list[DocumentResponse] = Field(default_factory=list)
    passages: list[PassageResponse] = Field(default_factory=list)
    trusted_social_sources: list[SourceResponse] = Field(default_factory=list)
    fact_claims: list[FactClaimResponse] = Field(default_factory=list)
    factors: list[FactorResponse] = Field(default_factory=list)
    reviews: list[ReviewResponse] = Field(default_factory=list)

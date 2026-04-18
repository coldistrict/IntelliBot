from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin
from app.models.enums import (
    ClaimTypeEnum,
    ClaimFamilyEnum,
    ConfidenceLabelEnum,
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
    SnapshotTypeEnum,
    SourceKindEnum,
    SourceTierEnum,
    StanceEnum,
    StrengthEnum,
    TemplateKey,
    VerifierStatusEnum,
    enum_column,
)

if TYPE_CHECKING:
    from app.models.market import Market


class AnalysisRequest(TimestampMixin, Base):
    __tablename__ = "analysis_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[ModeEnum] = mapped_column(enum_column(ModeEnum, "mode_enum"), nullable=False)
    input_type: Mapped[InputTypeEnum] = mapped_column(
        enum_column(InputTypeEnum, "input_type_enum"), nullable=False
    )
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    progress_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"))
    template_requested: Mapped[TemplateKey | None] = mapped_column(
        enum_column(TemplateKey, "template_key_enum")
    )
    template_selected: Mapped[TemplateKey | None] = mapped_column(
        enum_column(TemplateKey, "template_key_enum")
    )
    status: Mapped[RequestStatusEnum] = mapped_column(
        enum_column(RequestStatusEnum, "request_status_enum"),
        default=RequestStatusEnum.QUEUED,
        nullable=False,
    )
    current_stage: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    market: Mapped["Market | None"] = relationship(back_populates="analysis_requests")
    rule_parses: Mapped[list["RuleParse"]] = relationship(
        back_populates="analysis_request", cascade="all, delete-orphan"
    )
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class RuleParse(Base):
    __tablename__ = "rule_parses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_request_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_requests.id"), nullable=False, index=True
    )
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"))
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    event: Mapped[str] = mapped_column(Text, nullable=False)
    entity_names: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    claim_family: Mapped[ClaimFamilyEnum] = mapped_column(
        enum_column(ClaimFamilyEnum, "claim_family_enum"), nullable=False
    )
    yes_condition: Mapped[str] = mapped_column(Text, nullable=False)
    no_condition: Mapped[str] = mapped_column(Text, nullable=False)
    deadline_text: Mapped[str | None] = mapped_column(String(255))
    deadline_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone_text: Mapped[str | None] = mapped_column(String(128))
    resolution_definition: Mapped[str | None] = mapped_column(Text)
    directional_scoring_policy: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    official_resolution_source: Mapped[str | None] = mapped_column(String(1000))
    fallback_sources: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    official_domains: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    ambiguity_flags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    clarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    resolution_risk: Mapped[float] = mapped_column(Float, nullable=False)
    suitable_for_auto: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    template_detected: Mapped[TemplateKey] = mapped_column(
        enum_column(TemplateKey, "template_key_enum"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    analysis_request: Mapped["AnalysisRequest"] = relationship(back_populates="rule_parses")
    market: Mapped["Market | None"] = relationship(back_populates="rule_parses")
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="rule_parse")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_requests.id"), nullable=False, index=True
    )
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"))
    rule_parse_id: Mapped[int] = mapped_column(ForeignKey("rule_parses.id"), nullable=False)
    template_selected: Mapped[TemplateKey] = mapped_column(
        enum_column(TemplateKey, "template_key_enum"), nullable=False
    )
    market_mid_prob: Mapped[float | None] = mapped_column(Float)
    yes_exec_price: Mapped[float | None] = mapped_column(Float)
    no_exec_price: Mapped[float | None] = mapped_column(Float)
    priced_in_risk_label: Mapped[PricedInRiskLabelEnum | None] = mapped_column(
        enum_column(PricedInRiskLabelEnum, "priced_in_risk_label_enum")
    )
    numeric_estimate_available: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    numeric_estimate_reason: Mapped[str | None] = mapped_column(Text)
    qualitative_label: Mapped[QualitativeLabelEnum | None] = mapped_column(
        enum_column(QualitativeLabelEnum, "qualitative_label_enum")
    )
    p_hat: Mapped[float | None] = mapped_column(Float)
    p_low: Mapped[float | None] = mapped_column(Float)
    p_high: Mapped[float | None] = mapped_column(Float)
    confidence_label: Mapped[ConfidenceLabelEnum] = mapped_column(
        enum_column(ConfidenceLabelEnum, "confidence_label_enum"), nullable=False
    )
    recommendation_label: Mapped[RecommendationLabelEnum] = mapped_column(
        enum_column(RecommendationLabelEnum, "recommendation_label_enum"), nullable=False
    )
    why_wrong_summary: Mapped[str | None] = mapped_column(Text)
    final_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    request: Mapped["AnalysisRequest"] = relationship(back_populates="analysis_runs")
    market: Mapped["Market | None"] = relationship(back_populates="analysis_runs")
    rule_parse: Mapped["RuleParse"] = relationship(back_populates="analysis_runs")
    sources: Mapped[list["Source"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    passages: Mapped[list["Passage"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    fact_claims: Mapped[list["FactClaim"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    factors: Mapped[list["Factor"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    recommendation: Mapped["Recommendation | None"] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan", uselist=False
    )
    social_intel_summary: Mapped["SocialIntelSummary | None"] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan", uselist=False
    )
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list["Snapshot"]] = relationship(back_populates="analysis_run")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id"), nullable=False, index=True
    )
    url: Mapped[str | None] = mapped_column(String(1000))
    domain: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(500))
    source_kind: Mapped[SourceKindEnum] = mapped_column(
        enum_column(SourceKindEnum, "source_kind_enum"), nullable=False
    )
    source_tier: Mapped[SourceTierEnum] = mapped_column(
        enum_column(SourceTierEnum, "source_tier_enum"), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(1000))
    is_paywalled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="sources")
    documents: Mapped[list["Document"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    passages: Mapped[list["Passage"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    fact_claims: Mapped[list["FactClaim"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    canonical_url: Mapped[str | None] = mapped_column(String(1000))
    title: Mapped[str | None] = mapped_column(String(500))
    domain: Mapped[str | None] = mapped_column(String(255))
    extractor: Mapped[str | None] = mapped_column(String(64))
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="documents")
    source: Mapped["Source"] = relationship(back_populates="documents")
    passages: Mapped[list["Passage"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Passage(Base):
    __tablename__ = "passages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), nullable=False, index=True
    )
    passage_index: Mapped[int] = mapped_column(Integer, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="passages")
    source: Mapped["Source"] = relationship(back_populates="passages")
    document: Mapped["Document"] = relationship(back_populates="passages")
    fact_claims: Mapped[list["FactClaim"]] = relationship(back_populates="passage")


class FactClaim(Base):
    __tablename__ = "fact_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    passage_id: Mapped[int | None] = mapped_column(ForeignKey("passages.id"))
    normalized_fact: Mapped[str] = mapped_column(Text, nullable=False)
    exact_quote: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[ClaimTypeEnum] = mapped_column(
        enum_column(ClaimTypeEnum, "claim_type_enum"), nullable=False
    )
    directness: Mapped[DirectnessEnum] = mapped_column(
        enum_column(DirectnessEnum, "directness_enum"), nullable=False
    )
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extracted_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verifier_status: Mapped[VerifierStatusEnum] = mapped_column(
        enum_column(VerifierStatusEnum, "verifier_status_enum"), nullable=False
    )
    verifier_notes: Mapped[str | None] = mapped_column(Text)
    evidence_role: Mapped[EvidenceRoleEnum] = mapped_column(
        enum_column(EvidenceRoleEnum, "evidence_role_enum"),
        default=EvidenceRoleEnum.BACKGROUND,
        nullable=False,
    )
    uniqueness_group: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="fact_claims")
    source: Mapped["Source"] = relationship(back_populates="fact_claims")
    passage: Mapped["Passage | None"] = relationship(back_populates="fact_claims")
    factors: Mapped[list["Factor"]] = relationship(
        back_populates="fact_claim", cascade="all, delete-orphan"
    )


class Factor(Base):
    __tablename__ = "factors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id"), nullable=False, index=True
    )
    fact_claim_id: Mapped[int] = mapped_column(ForeignKey("fact_claims.id"), nullable=False)
    stance: Mapped[StanceEnum] = mapped_column(enum_column(StanceEnum, "stance_enum"), nullable=False)
    strength: Mapped[StrengthEnum] = mapped_column(
        enum_column(StrengthEnum, "strength_enum"), nullable=False
    )
    evidence_role: Mapped[EvidenceRoleEnum] = mapped_column(
        enum_column(EvidenceRoleEnum, "evidence_role_enum"), nullable=False
    )
    used_in_scoring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    source_weight: Mapped[float] = mapped_column(Float, nullable=False)
    freshness_multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    uniqueness_multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    template_multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    final_weight: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="factors")
    fact_claim: Mapped["FactClaim"] = relationship(back_populates="factors")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id"), nullable=False, unique=True, index=True
    )
    recommendation_label: Mapped[RecommendationLabelEnum] = mapped_column(
        enum_column(RecommendationLabelEnum, "recommendation_label_enum"), nullable=False
    )
    confidence_label: Mapped[ConfidenceLabelEnum] = mapped_column(
        enum_column(ConfidenceLabelEnum, "confidence_label_enum"), nullable=False
    )
    edge_yes: Mapped[float | None] = mapped_column(Float)
    edge_no: Mapped[float | None] = mapped_column(Float)
    rationale_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="recommendation")


class SocialIntelSummary(Base):
    __tablename__ = "social_intel_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id"), nullable=False, unique=True, index=True
    )
    consensus_label: Mapped[ConsensusLabelEnum] = mapped_column(
        enum_column(ConsensusLabelEnum, "consensus_label_enum"), nullable=False
    )
    consensus_strength: Mapped[ConsensusStrengthEnum] = mapped_column(
        enum_column(ConsensusStrengthEnum, "consensus_strength_enum"), nullable=False
    )
    narrative_phase: Mapped[NarrativePhaseEnum] = mapped_column(
        enum_column(NarrativePhaseEnum, "narrative_phase_enum"), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_themes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    trusted_accounts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    broad_posts_sampled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="social_intel_summary")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id"), nullable=False, index=True
    )
    decision: Mapped[ReviewDecisionEnum] = mapped_column(
        enum_column(ReviewDecisionEnum, "review_decision_enum"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="reviews")


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False, index=True)
    analysis_run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_runs.id"))
    snapshot_type: Mapped[SnapshotTypeEnum] = mapped_column(
        enum_column(SnapshotTypeEnum, "snapshot_type_enum"), nullable=False
    )
    yes_bid: Mapped[float | None] = mapped_column(Float)
    yes_ask: Mapped[float | None] = mapped_column(Float)
    no_bid: Mapped[float | None] = mapped_column(Float)
    no_ask: Mapped[float | None] = mapped_column(Float)
    midpoint_yes: Mapped[float | None] = mapped_column(Float)
    outcome: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    market: Mapped["Market"] = relationship(back_populates="snapshots")
    analysis_run: Mapped["AnalysisRun | None"] = relationship(back_populates="snapshots")

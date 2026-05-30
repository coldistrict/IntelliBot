from datetime import UTC, datetime

from app.models import (
    AnalysisRequest,
    AnalysisRun,
    FactClaim,
    Factor,
    Market,
    Recommendation,
    RuleParse,
    SocialIntelSummary,
    Source,
)
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
    SourceKindEnum,
    SourceTierEnum,
    StanceEnum,
    StrengthEnum,
    TemplateKey,
    VerifierStatusEnum,
)
from app.services.analysis_audit import build_analysis_audit, build_display_summary
from app.services.analysis_progress import (
    build_progress_snapshot,
    initial_progress_payload,
    mark_stage_complete,
    mark_stage_running,
    mark_stage_skipped,
)


def test_progress_snapshot_tracks_skipped_optional_stages():
    now = datetime.now(UTC)
    request = AnalysisRequest(
        mode=ModeEnum.MANUAL,
        input_type=InputTypeEnum.CUSTOM_CLAIM,
        input_text="Will the Fed cut rates by June?",
        input_payload={},
        progress_json=initial_progress_payload(now),
        status=RequestStatusEnum.RUNNING,
        current_stage="normalize",
        started_at=now,
    )

    mark_stage_complete(request, "normalize", "Request normalized.", now=now)
    mark_stage_skipped(request, "market_lookup", "No market lookup needed.", now=now)
    mark_stage_running(request, "rule_parse", "Interpreting the resolution wording.", now=now)

    snapshot = build_progress_snapshot(request)

    assert snapshot["current_label"] == "Rule Parse"
    assert snapshot["percent_complete"] == 18
    stage_map = {stage["key"]: stage for stage in snapshot["stages"]}
    assert stage_map["market_lookup"]["status"] == "skipped"
    assert stage_map["rule_parse"]["status"] == "running"


def test_display_summary_falls_back_to_probability_and_factor_rationales():
    now = datetime.now(UTC)
    request = AnalysisRequest(
        mode=ModeEnum.MANUAL,
        input_type=InputTypeEnum.CUSTOM_CLAIM,
        input_text="Will the Fed cut rates by June?",
        input_payload={},
        progress_json=initial_progress_payload(now),
        status=RequestStatusEnum.COMPLETE,
        current_stage="complete",
        started_at=now,
        completed_at=now,
    )
    rule_parse = RuleParse(
        analysis_request_id=1,
        question_text="Will the Fed cut rates by June?",
        event="Fed cuts rates by June",
        entity_names=["Federal Reserve"],
        action="cut rates",
        claim_family=ClaimFamilyEnum.MACRO_POLICY,
        yes_condition="YES if the Fed cuts rates by June.",
        no_condition="NO if the Fed does not cut rates by June.",
        deadline_text="June 2026",
        resolution_definition="Resolves YES if the Fed cuts rates by June 2026.",
        directional_scoring_policy={"allowed_roles": ["outcome", "direct_support", "direct_contradiction", "commentary"]},
        official_domains=["federalreserve.gov"],
        fallback_sources=[],
        ambiguity_flags=[],
        clarity_score=0.74,
        resolution_risk=0.28,
        suitable_for_auto=False,
        template_detected=TemplateKey.MACRO_POLICY,
        created_at=now,
    )
    run = AnalysisRun(
        request_id=1,
        rule_parse_id=1,
        template_selected=TemplateKey.MACRO_POLICY,
        market_mid_prob=0.5,
        yes_exec_price=None,
        no_exec_price=None,
        priced_in_risk_label=PricedInRiskLabelEnum.MEDIUM,
        numeric_estimate_available=True,
        numeric_estimate_reason=None,
        qualitative_label=QualitativeLabelEnum.LEANS_YES,
        p_hat=0.58,
        p_low=0.46,
        p_high=0.69,
        confidence_label=ConfidenceLabelEnum.MEDIUM,
        recommendation_label=RecommendationLabelEnum.ANALYSIS_ONLY,
        final_summary=None,
        created_at=now,
    )
    recommendation = Recommendation(
        analysis_run_id=1,
        recommendation_label=RecommendationLabelEnum.ANALYSIS_ONLY,
        confidence_label=ConfidenceLabelEnum.MEDIUM,
        edge_yes=None,
        edge_no=None,
        rationale_json={},
        created_at=now,
    )
    factors = [
        Factor(
            analysis_run_id=1,
            fact_claim_id=1,
            stance=StanceEnum.YES,
            strength=StrengthEnum.MEDIUM,
            evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
            used_in_scoring=True,
            exclusion_reason=None,
            source_weight=0.2,
            freshness_multiplier=1.0,
            uniqueness_multiplier=1.0,
            template_multiplier=0.7,
            final_weight=0.12,
            rationale="Cooling data is making earlier easing more plausible.",
            created_at=now,
        ),
        Factor(
            analysis_run_id=1,
            fact_claim_id=2,
            stance=StanceEnum.NO,
            strength=StrengthEnum.WEAK,
            evidence_role=EvidenceRoleEnum.DIRECT_CONTRADICTION,
            used_in_scoring=True,
            exclusion_reason=None,
            source_weight=0.2,
            freshness_multiplier=1.0,
            uniqueness_multiplier=1.0,
            template_multiplier=0.7,
            final_weight=0.04,
            rationale="Officials still sound patient on inflation risks.",
            created_at=now,
        ),
    ]

    summary = build_display_summary(
        request,
        rule_parse=rule_parse,
        analysis_run=run,
        recommendation=recommendation,
        factors=factors,
    )

    assert "YES 58%" in summary
    assert "NO 42%" in summary
    assert "Best YES case" in summary
    assert "Main NO case" in summary


def test_display_summary_prefers_point_probability_even_for_legacy_qualitative_runs():
    now = datetime.now(UTC)
    request = AnalysisRequest(
        mode=ModeEnum.MANUAL,
        input_type=InputTypeEnum.CUSTOM_CLAIM,
        input_text="Will the supreme court side with Trump's executive order?",
        input_payload={},
        progress_json=initial_progress_payload(now),
        status=RequestStatusEnum.COMPLETE,
        current_stage="complete",
        started_at=now,
        completed_at=now,
    )
    rule_parse = RuleParse(
        analysis_request_id=1,
        question_text="Will the supreme court side with Trump's executive order?",
        event="Supreme Court birthright citizenship case",
        entity_names=["Supreme Court", "Trump"],
        action="side with",
        claim_family=ClaimFamilyEnum.LEGAL_CASE,
        yes_condition="YES if the court upholds or allows Trump's executive order on the merits.",
        no_condition="NO if the court blocks or strikes down Trump's executive order on the merits.",
        deadline_text=None,
        resolution_definition="Resolves on the merits of the executive order challenge.",
        directional_scoring_policy={"allowed_roles": ["outcome", "direct_support", "direct_contradiction", "commentary"]},
        official_domains=["supremecourt.gov"],
        fallback_sources=[],
        ambiguity_flags=[],
        clarity_score=0.68,
        resolution_risk=0.32,
        suitable_for_auto=False,
        template_detected=TemplateKey.LEGAL_CASE,
        created_at=now,
    )
    run = AnalysisRun(
        request_id=1,
        rule_parse_id=1,
        template_selected=TemplateKey.LEGAL_CASE,
        market_mid_prob=None,
        yes_exec_price=None,
        no_exec_price=None,
        priced_in_risk_label=PricedInRiskLabelEnum.HIGH,
        numeric_estimate_available=False,
        numeric_estimate_reason="net directional evidence is still below the numeric threshold",
        qualitative_label=QualitativeLabelEnum.MIXED,
        p_hat=0.43,
        p_low=0.31,
        p_high=0.55,
        confidence_label=ConfidenceLabelEnum.LOW,
        recommendation_label=RecommendationLabelEnum.ANALYSIS_ONLY,
        final_summary=None,
        created_at=now,
    )
    recommendation = Recommendation(
        analysis_run_id=1,
        recommendation_label=RecommendationLabelEnum.ANALYSIS_ONLY,
        confidence_label=ConfidenceLabelEnum.LOW,
        edge_yes=None,
        edge_no=None,
        rationale_json={},
        created_at=now,
    )

    summary = build_display_summary(
        request,
        rule_parse=rule_parse,
        analysis_run=run,
        recommendation=recommendation,
        factors=[],
    )

    assert "YES 43%" in summary
    assert "NO 57%" in summary


def test_analysis_audit_exposes_probability_uncertainty_and_recommendation_math():
    now = datetime.now(UTC)
    request = AnalysisRequest(
        mode=ModeEnum.MANUAL,
        input_type=InputTypeEnum.CUSTOM_CLAIM,
        input_text="Will the Fed cut rates by June?",
        input_payload={},
        progress_json=initial_progress_payload(now),
        status=RequestStatusEnum.COMPLETE,
        current_stage="complete",
        started_at=now,
        completed_at=now,
    )
    market = Market(
        polymarket_id="fed-cut-june-2026",
        title="Will the Fed cut rates by June 2026?",
        yes_ask=0.44,
        no_ask=0.58,
        spread=0.02,
    )
    rule_parse = RuleParse(
        analysis_request_id=1,
        market_id=1,
        question_text="Will the Fed cut rates by June?",
        event="Fed cuts rates by June",
        entity_names=["Federal Reserve"],
        action="cut rates",
        claim_family=ClaimFamilyEnum.MACRO_POLICY,
        yes_condition="YES if the Fed cuts rates by June.",
        no_condition="NO if the Fed does not cut rates by June.",
        deadline_text="June 2026",
        resolution_definition="Resolves YES if the Fed cuts rates by June 2026.",
        directional_scoring_policy={"allowed_roles": ["outcome", "direct_support", "direct_contradiction", "commentary"]},
        official_domains=["federalreserve.gov"],
        fallback_sources=[],
        ambiguity_flags=[],
        clarity_score=0.72,
        resolution_risk=0.28,
        suitable_for_auto=False,
        template_detected=TemplateKey.MACRO_POLICY,
        created_at=now,
    )
    run = AnalysisRun(
        id=1,
        request_id=1,
        market_id=1,
        rule_parse_id=1,
        template_selected=TemplateKey.MACRO_POLICY,
        market_mid_prob=0.43,
        yes_exec_price=0.44,
        no_exec_price=0.58,
        priced_in_risk_label=PricedInRiskLabelEnum.HIGH,
        numeric_estimate_available=True,
        numeric_estimate_reason=None,
        qualitative_label=QualitativeLabelEnum.LEANS_YES,
        p_hat=0.61,
        p_low=0.48,
        p_high=0.74,
        confidence_label=ConfidenceLabelEnum.MEDIUM,
        recommendation_label=RecommendationLabelEnum.LEAN_YES,
        final_summary=None,
        created_at=now,
    )
    run.market = market
    recommendation = Recommendation(
        analysis_run_id=1,
        recommendation_label=RecommendationLabelEnum.LEAN_YES,
        confidence_label=ConfidenceLabelEnum.MEDIUM,
        edge_yes=0.04,
        edge_no=-0.32,
        rationale_json={},
        created_at=now,
    )
    official_source = Source(
        id=1,
        analysis_run_id=1,
        title="Federal Reserve statement",
        source_kind=SourceKindEnum.OFFICIAL,
        source_tier=SourceTierEnum.OFFICIAL_PRIMARY,
        fetched_at=now,
        content_hash="official",
        excerpt="Officials signaled the decision path remains data-dependent.",
        is_paywalled=False,
        metadata_json={},
        created_at=now,
    )
    social_source = Source(
        id=2,
        analysis_run_id=1,
        title="Nick Timiraos",
        source_kind=SourceKindEnum.LIVE_SOCIAL,
        source_tier=SourceTierEnum.HIGH_TRUST_SOCIAL,
        fetched_at=now,
        content_hash="social",
        excerpt="Fed-sensitive accounts now lean toward earlier easing.",
        is_paywalled=False,
        metadata_json={"handle": "NickTimiraos"},
        created_at=now,
    )
    official_fact = FactClaim(
        id=1,
        analysis_run_id=1,
        source_id=1,
        normalized_fact="Officials remain data-dependent.",
        exact_quote="Officials remain data-dependent.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.DIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
        created_at=now,
    )
    social_fact = FactClaim(
        id=2,
        analysis_run_id=1,
        source_id=2,
        normalized_fact="Trusted macro accounts lean toward a sooner cut.",
        exact_quote="Trusted macro accounts lean toward a sooner cut.",
        claim_type=ClaimTypeEnum.SOCIAL_SIGNAL,
        directness=DirectnessEnum.DIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.COMMENTARY,
        created_at=now,
    )
    factors = [
        Factor(
            id=1,
            analysis_run_id=1,
            fact_claim_id=1,
            stance=StanceEnum.YES,
            strength=StrengthEnum.MEDIUM,
            evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
            used_in_scoring=True,
            exclusion_reason=None,
            source_weight=0.45,
            freshness_multiplier=1.0,
            uniqueness_multiplier=1.0,
            template_multiplier=0.7,
            final_weight=0.2,
            rationale="Official language keeps an easing path live.",
            created_at=now,
        ),
        Factor(
            id=2,
            analysis_run_id=1,
            fact_claim_id=2,
            stance=StanceEnum.YES,
            strength=StrengthEnum.STRONG,
            evidence_role=EvidenceRoleEnum.COMMENTARY,
            used_in_scoring=True,
            exclusion_reason=None,
            source_weight=0.12,
            freshness_multiplier=1.0,
            uniqueness_multiplier=1.0,
            template_multiplier=0.7,
            final_weight=0.4,
            rationale="Trusted macro accounts have turned more constructive.",
            created_at=now,
        ),
    ]
    social_summary = SocialIntelSummary(
        analysis_run_id=1,
        consensus_label=ConsensusLabelEnum.BULLISH,
        consensus_strength=ConsensusStrengthEnum.STRONG,
        narrative_phase=NarrativePhaseEnum.PRICED_IN,
        summary="X consensus is bullish, but the narrative already feels crowded.",
        key_themes=["fed path", "jobs data"],
        trusted_accounts_count=1,
        broad_posts_sampled=18,
        created_at=now,
    )

    audit = build_analysis_audit(
        request=request,
        rule_parse=rule_parse,
        analysis_run=run,
        recommendation=recommendation,
        sources=[official_source, social_source],
        facts=[official_fact, social_fact],
        factors=factors,
        social_intel_summary=social_summary,
    )

    assert audit is not None
    assert audit["probability"]["prior_probability"] == 0.43
    assert audit["probability"]["non_social_evidence"] == 0.2
    assert audit["probability"]["raw_social_evidence"] == 0.4
    assert audit["probability"]["capped_social_evidence"] == 0.18
    assert audit["probability"]["crowd_signal_evidence"] == 0.143
    assert audit["probability"]["total_evidence"] == 0.523
    assert audit["recommendation_math"]["chosen_label"] == "lean_yes"
    assert any(
        adjustment["key"] == "priced_in_high"
        for adjustment in audit["uncertainty"]["adjustments"]
    )
    assert audit["social_modifier"]["narrative_phase"] == "priced_in"
    assert audit["social_modifier"]["crowd_signal_direction"] == "bullish"
    assert "Trusted account evidence remains separate" in audit["social_modifier"]["crowd_signal_reason"]
    assert audit["factor_contributions"][0]["signed_contribution"] == 0.4

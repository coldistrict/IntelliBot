from datetime import UTC, datetime

import httpx

from app.clients.polymarket_client import ResolvedMarketRecord
from app.models import AnalysisRequest, FactClaim, Factor, Market, Passage, SocialIntelSummary, Source
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
from app.services.analysis_pipeline import AnalysisProcessor, SourceContext
from app.services.analysis_progress import initial_progress_payload
from app.services.pipeline_models import EvidenceAdjudicationDraft, SearchSourceDraft, SocialIntelDraft


def test_fallback_fact_extraction_filters_low_signal_boilerplate():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Federal Reserve page",
        source_kind=SourceKindEnum.OFFICIAL,
        source_tier=SourceTierEnum.OFFICIAL_PRIMARY,
        fetched_at=datetime.now(UTC),
        content_hash="hash",
        excerpt=(
            "Skip to main content. Official websites use .gov. "
            "Fed officials kept rates unchanged in March."
        ),
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )

    facts = processor._fallback_fact_extraction(
        SourceContext(source=source, possible_facts=[]),
        "Will the Fed cut rates by June?",
    )

    assert len(facts) == 1
    assert facts[0].normalized_fact == "Fed officials kept rates unchanged in March"


def test_fallback_fact_extraction_prefers_grounded_passages_over_search_snippets():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Search result",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=datetime.now(UTC),
        content_hash="hash",
        excerpt="Fed story from Reuters.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    passage = Passage(
        analysis_run_id=1,
        source_id=1,
        document_id=1,
        passage_index=1,
        relevance_score=2.4,
        text="Federal Reserve officials said they still expect two cuts later this year if inflation cools further.",
        created_at=datetime.now(UTC),
    )

    facts = processor._fallback_fact_extraction(
        SourceContext(source=source, possible_facts=[], passages=[passage]),
        "Will the Fed cut rates by June?",
    )

    assert facts
    assert "expect two cuts later this year" in facts[0].normalized_fact.lower()


def test_rule_note_maps_to_neutral_factor():
    processor = AnalysisProcessor(enable_remote_calls=False)
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact="Will the Fed cut rates by June?",
        exact_quote="Will the Fed cut rates by June?",
        claim_type=ClaimTypeEnum.RULE_NOTE,
        directness=DirectnessEnum.DIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.BACKGROUND,
        created_at=datetime.now(UTC),
    )

    mapping = processor._fallback_factor_mapping(
        type(
            "RuleParseStub",
            (),
            {
                "question_text": "Will the Fed cut rates by June?",
                "template_detected": TemplateKey.MACRO_POLICY,
                "claim_family": ClaimFamilyEnum.MACRO_POLICY,
                "yes_condition": "YES if the Fed cuts rates by June.",
                "no_condition": "NO if the Fed does not cut rates by June.",
                "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                    ClaimFamilyEnum.MACRO_POLICY
                ),
            },
        )(),
        fact,
    )

    assert mapping.stance == StanceEnum.NEUTRAL
    assert mapping.used_in_scoring is False


def test_custom_claim_can_link_matching_polymarket_market(session_factory):
    class StubPolymarketClient:
        enabled = True

        def search_markets_for_claim(self, query: str, *, limit: int = 8):
            assert "Fed cut rates" in query
            return [
                ResolvedMarketRecord(
                    polymarket_id="fed-cut-june-2026",
                    title="Will the Fed cut rates by June 2026?",
                    url="https://polymarket.com/event/fed-cut-june-2026",
                    rules_text="Resolves YES if the Federal Reserve cuts the target rate by June 2026.",
                    description="Federal Reserve interest-rate market.",
                    yes_bid=0.81,
                    yes_ask=0.83,
                    no_bid=0.17,
                    no_ask=0.19,
                    liquidity=50000,
                    volume_24h=12000,
                    spread=0.02,
                    expiry_at=None,
                    status="active",
                )
            ]

    processor = AnalysisProcessor(
        session_factory=session_factory,
        enable_remote_calls=False,
        polymarket_client=StubPolymarketClient(),
    )

    with session_factory() as session:
        request = AnalysisRequest(
            mode=ModeEnum.MANUAL,
            input_type=InputTypeEnum.CUSTOM_CLAIM,
            input_text="Will the Fed cut rates by June 2026?",
            input_payload={},
            progress_json=initial_progress_payload(),
            status=RequestStatusEnum.QUEUED,
            current_stage="queued",
        )
        session.add(request)
        session.flush()

        market = processor._resolve_market(session, request)

        assert market is not None
        assert market.polymarket_id == "fed-cut-june-2026"
        assert request.market_id == market.id
        assert processor._market_prior(market) == 0.82


def test_model_adjudication_averages_openai_and_grok_factor_judges():
    class StubJudgeClient:
        is_configured = True

        def __init__(self, directional_score: float, rationale: str) -> None:
            self.directional_score = directional_score
            self.rationale = rationale

        def generate_structured(self, **_kwargs):
            return EvidenceAdjudicationDraft(
                stance=StanceEnum.YES,
                strength=StrengthEnum.MEDIUM,
                evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
                used_in_scoring=True,
                relevance_score=0.82,
                reliability_score=0.76,
                directional_score=self.directional_score,
                rationale=self.rationale,
            )

    processor = AnalysisProcessor(
        enable_remote_calls=False,
        openai_client=StubJudgeClient(0.68, "OpenAI reads this as supportive original reporting."),
        xai_client=StubJudgeClient(0.72, "Grok reads this as supportive but not final."),
    )
    source = Source(
        analysis_run_id=1,
        title="Sports report",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=datetime.now(UTC),
        content_hash="manager-report",
        excerpt="Club leadership advanced Jose Mourinho's candidacy after a meeting with senior officials.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact="Club leadership advanced Jose Mourinho's candidacy after a meeting with senior officials.",
        exact_quote="Club leadership advanced Jose Mourinho's candidacy after a meeting with senior officials.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.BACKGROUND,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.GENERIC_MANUAL,
            "claim_family": ClaimFamilyEnum.GENERIC_MANUAL,
            "question_text": "Will Jose Mourinho be appointed manager?",
            "action": "appointed",
            "entity_names": ["Jose Mourinho"],
            "yes_condition": "YES if Jose Mourinho is appointed manager.",
            "no_condition": "NO if Jose Mourinho is not appointed manager.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.GENERIC_MANUAL
            ),
        },
    )()

    mapping = processor._map_fact_to_factor(rule_parse, source, fact, session=object())

    assert mapping.used_in_scoring is True
    assert mapping.stance == StanceEnum.YES
    assert mapping.strength == StrengthEnum.MEDIUM
    assert mapping.evidence_role == EvidenceRoleEnum.DIRECT_SUPPORT
    assert "direction +0.70" in (mapping.rationale or "")


def test_model_adjudication_does_not_score_old_appointment_history_as_no():
    class StubJudgeClient:
        is_configured = True

        def generate_structured(self, **_kwargs):
            return EvidenceAdjudicationDraft(
                stance=StanceEnum.NO,
                strength=StrengthEnum.STRONG,
                evidence_role=EvidenceRoleEnum.DIRECT_CONTRADICTION,
                used_in_scoring=True,
                relevance_score=0.9,
                reliability_score=0.95,
                directional_score=-1.0,
                rationale="Incorrectly treats prior Real Madrid tenure as NO evidence.",
            )

    processor = AnalysisProcessor(
        enable_remote_calls=False,
        openai_client=StubJudgeClient(),
        xai_client=StubJudgeClient(),
    )
    source = Source(
        analysis_run_id=1,
        title="Biography",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=datetime.now(UTC),
        content_hash="bio",
        excerpt="On 31 May 2010, Mourinho was unveiled as the new manager of Real Madrid.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact="On 31 May 2010, Mourinho was unveiled as the new manager of Real Madrid.",
        exact_quote="On 31 May 2010, Mourinho was unveiled as the new manager of Real Madrid.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.BACKGROUND,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.BACKGROUND,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.GENERIC_MANUAL,
            "claim_family": ClaimFamilyEnum.GENERIC_MANUAL,
            "question_text": "Will Jose Mourinho be appointed manager of Real Madrid?",
            "action": "appointed",
            "entity_names": ["Jose Mourinho"],
            "yes_condition": "YES if Jose Mourinho is appointed manager of Real Madrid.",
            "no_condition": "NO if Jose Mourinho is not appointed manager of Real Madrid.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.GENERIC_MANUAL
            ),
        },
    )()

    mapping = processor._map_fact_to_factor(rule_parse, source, fact, session=object())

    assert mapping.used_in_scoring is False
    assert mapping.stance == StanceEnum.NEUTRAL
    assert mapping.evidence_role == EvidenceRoleEnum.BACKGROUND


def test_recommendation_uses_executable_prices_for_edge():
    processor = AnalysisProcessor(enable_remote_calls=False)
    market = Market(
        polymarket_id="test-market",
        title="Will an approval happen?",
        yes_ask=0.4,
        no_ask=0.62,
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact="Official filing confirmed.",
        exact_quote="Official filing confirmed.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.DIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
        created_at=datetime.now(UTC),
    )

    recommendation = processor._recommendation(
        market=market,
        p_low=0.55,
        p_high=0.62,
        confidence_label=ConfidenceLabelEnum.MEDIUM,
        priced_in_risk=PricedInRiskLabelEnum.LOW,
        facts=[fact],
    )

    assert recommendation.recommendation_label == RecommendationLabelEnum.LEAN_YES
    assert recommendation.edge_yes is not None and recommendation.edge_yes > 0


def test_social_sources_must_be_official_or_high_trust_to_create_factors():
    official_live_source = Source(
        analysis_run_id=1,
        title="Official social post",
        source_kind=SourceKindEnum.LIVE_SOCIAL,
        source_tier=SourceTierEnum.OFFICIAL_SOCIAL,
        fetched_at=datetime.now(UTC),
        content_hash="official",
        excerpt="Official confirmation posted on X.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    reporter_manual_source = Source(
        analysis_run_id=1,
        title="Reporter social post",
        source_kind=SourceKindEnum.MANUAL_SOCIAL,
        source_tier=SourceTierEnum.REPORTER_SOCIAL,
        fetched_at=datetime.now(UTC),
        content_hash="reporter",
        excerpt="Beat reporter expects movement soon.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )

    assert AnalysisProcessor._source_is_factor_eligible(official_live_source) is True
    assert AnalysisProcessor._source_is_factor_eligible(reporter_manual_source) is False

def test_social_evidence_is_capped_before_probability_update():
    social_yes_source = Source(
        id=1,
        analysis_run_id=1,
        title="Trusted macro account",
        source_kind=SourceKindEnum.LIVE_SOCIAL,
        source_tier=SourceTierEnum.HIGH_TRUST_SOCIAL,
        fetched_at=datetime.now(UTC),
        content_hash="social-yes",
        excerpt="Cut odds rising fast.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    social_no_source = Source(
        id=2,
        analysis_run_id=1,
        title="Trusted macro dissenter",
        source_kind=SourceKindEnum.LIVE_SOCIAL,
        source_tier=SourceTierEnum.OFFICIAL_SOCIAL,
        fetched_at=datetime.now(UTC),
        content_hash="social-no",
        excerpt="No cut expected.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact_yes = FactClaim(
        id=11,
        analysis_run_id=1,
        source_id=1,
        normalized_fact="Trusted account expects a cut.",
        exact_quote="Trusted account expects a cut.",
        claim_type=ClaimTypeEnum.SOCIAL_SIGNAL,
        directness=DirectnessEnum.DIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        created_at=datetime.now(UTC),
    )
    fact_no = FactClaim(
        id=12,
        analysis_run_id=1,
        source_id=2,
        normalized_fact="Another trusted account expects no cut.",
        exact_quote="Another trusted account expects no cut.",
        claim_type=ClaimTypeEnum.SOCIAL_SIGNAL,
        directness=DirectnessEnum.DIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        created_at=datetime.now(UTC),
    )
    factors = [
        type(
            "FactorStub",
            (),
            {"fact_claim_id": 11, "stance": StanceEnum.YES, "final_weight": 0.6, "used_in_scoring": True},
        )(),
        type(
            "FactorStub",
            (),
            {"fact_claim_id": 12, "stance": StanceEnum.NO, "final_weight": 0.9, "used_in_scoring": True},
        )(),
    ]

    evidence = AnalysisProcessor._capped_evidence_score(
        factors,
        {11: fact_yes, 12: fact_no},
        {1: social_yes_source, 2: social_no_source},
    )

    assert evidence == -0.18


def test_priced_in_risk_uses_social_narrative_phase():
    processor = AnalysisProcessor(enable_remote_calls=False)
    social_summary = type(
        "SocialSummaryStub",
        (),
        {
            "consensus_label": ConsensusLabelEnum.BULLISH,
            "consensus_strength": ConsensusStrengthEnum.STRONG,
            "narrative_phase": NarrativePhaseEnum.PRICED_IN,
        },
    )()

    risk = processor._priced_in_risk(
        None,
        [],
        social_summary,
    )

    assert risk == PricedInRiskLabelEnum.HIGH


def test_social_normalization_preserves_broad_strength_without_trusted_posts():
    draft = SocialIntelDraft(
        consensus_label=ConsensusLabelEnum.BULLISH,
        consensus_strength=ConsensusStrengthEnum.STRONG,
        narrative_phase=NarrativePhaseEnum.EMERGING,
        summary="Many smaller accounts independently lean YES before official confirmation.",
        key_themes=["early flow"],
        trusted_accounts_count=0,
        broad_posts_sampled=34,
        trusted_posts=[],
    )

    normalized = AnalysisProcessor._normalize_social_intelligence(draft, [])

    assert normalized.consensus_strength == ConsensusStrengthEnum.STRONG
    assert normalized.trusted_accounts_count == 0


def test_social_normalization_strips_grok_render_markup():
    draft = SocialIntelDraft(
        consensus_label=ConsensusLabelEnum.BEARISH,
        consensus_strength=ConsensusStrengthEnum.WEAK,
        narrative_phase=NarrativePhaseEnum.EMERGING,
        summary=(
            "Ceasefire chatter is skeptical."
            '<grok:render type="render_inline_citation"><argument name="citation_id">46'
            "</argument></grok:render>"
        ),
        key_themes=["skepticism<grok:render>hidden</grok:render>"],
        trusted_accounts_count=0,
        broad_posts_sampled=20,
        trusted_posts=[],
    )

    normalized = AnalysisProcessor._normalize_social_intelligence(draft, [])

    assert "<grok" not in normalized.summary
    assert "<argument" not in normalized.summary
    assert normalized.summary == "Ceasefire chatter is skeptical."
    assert normalized.key_themes == ["skepticism"]


def test_legal_case_background_is_not_scored_directionally():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="SCOTUSblog",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.EXPERT_ANALYSIS,
        fetched_at=datetime.now(UTC),
        content_hash="legal-background",
        excerpt="On Jan. 20, 2025, Trump signed an executive order ending birthright citizenship.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact="On Jan. 20, 2025, Trump signed an executive order ending birthright citizenship.",
        exact_quote="On Jan. 20, 2025, Trump signed an executive order ending birthright citizenship.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.BACKGROUND,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.LEGAL_CASE,
            "claim_family": ClaimFamilyEnum.LEGAL_CASE,
            "yes_condition": "YES if SCOTUS strikes down the executive order.",
            "no_condition": "NO if SCOTUS upholds or allows the executive order.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.LEGAL_CASE
            ),
        },
    )()

    mapping = processor._map_fact_to_factor(rule_parse, source, fact)

    assert mapping.used_in_scoring is False
    assert mapping.stance == StanceEnum.NEUTRAL
    assert mapping.evidence_role == EvidenceRoleEnum.BACKGROUND


def test_legal_case_underlying_order_text_is_downgraded_from_directional_role():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Legal source",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.EXPERT_ANALYSIS,
        fetched_at=datetime.now(UTC),
        content_hash="order-text",
        excerpt="Section 1 of the executive order declares that birthright citizenship does not extend to certain children.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact="Section 1 of the executive order declares that birthright citizenship does not extend to certain children.",
        exact_quote="Section 1 of the executive order declares that birthright citizenship does not extend to certain children.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.LEGAL_CASE,
            "claim_family": ClaimFamilyEnum.LEGAL_CASE,
            "yes_condition": "YES if SCOTUS strikes down the executive order.",
            "no_condition": "NO if SCOTUS upholds or allows the executive order.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.LEGAL_CASE
            ),
        },
    )()

    normalized_role = processor._normalize_evidence_role(
        rule_parse=rule_parse,
        source=source,
        fact=fact,
        proposed_role=EvidenceRoleEnum.DIRECT_SUPPORT,
    )

    assert normalized_role == EvidenceRoleEnum.BACKGROUND


def test_legal_case_constitutional_background_terms_do_not_align_by_overlap():
    processor = AnalysisProcessor(enable_remote_calls=False)
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.LEGAL_CASE,
            "claim_family": ClaimFamilyEnum.LEGAL_CASE,
            "yes_condition": (
                "YES if the court upholds, allows, or lets Trump's executive order on "
                "birthright citizenship take effect on the merits."
            ),
            "no_condition": (
                "NO if the court blocks, strikes down, invalidates, or rules against "
                "Trump's executive order on birthright citizenship on the merits."
            ),
        },
    )()

    alignment = processor._condition_alignment(
        rule_parse,
        "Citizenship of all babies born in the United States is discussed in the 14th Amendment.",
    )

    assert alignment == StanceEnum.NEUTRAL


def test_no_market_weak_evidence_still_produces_decision_estimate():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        id=1,
        analysis_run_id=1,
        title="Commentary source",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=datetime.now(UTC),
        content_hash="source",
        excerpt="Analysts think the path is possible.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        id=1,
        analysis_run_id=1,
        source_id=1,
        normalized_fact="Analysts think the path is possible.",
        exact_quote="Analysts think the path is possible.",
        claim_type=ClaimTypeEnum.OPINION,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.AMBIGUOUS,
        evidence_role=EvidenceRoleEnum.COMMENTARY,
        created_at=datetime.now(UTC),
    )
    factors = [
        type(
            "FactorStub",
            (),
            {
                "fact_claim_id": 1,
                "stance": StanceEnum.YES,
                "final_weight": 0.06,
                "used_in_scoring": True,
            },
        )()
    ]

    allowed, reason = processor._numeric_estimate_gate(factors, [fact], {1: source}, 0.06)

    assert allowed is True
    assert "single scored directional factor" in (reason or "")
    assert (
        processor._qualitative_label(factors, 0.06)
        == QualitativeLabelEnum.LEANS_YES
    )


def test_score_analysis_shows_low_confidence_estimate_for_light_evidence():
    processor = AnalysisProcessor(enable_remote_calls=False)
    now = datetime.now(UTC)
    source_one = Source(
        id=1,
        analysis_run_id=1,
        title="Reuters",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=now,
        content_hash="reuters",
        excerpt="Policy odds moved modestly higher.",
        is_paywalled=False,
        metadata_json={},
        created_at=now,
    )
    source_two = Source(
        id=2,
        analysis_run_id=1,
        title="SCOTUSblog",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.EXPERT_ANALYSIS,
        fetched_at=now,
        content_hash="scotusblog",
        excerpt="The court remains cautious.",
        is_paywalled=False,
        metadata_json={},
        created_at=now,
    )
    fact_one = FactClaim(
        id=1,
        analysis_run_id=1,
        source_id=1,
        normalized_fact="Policy odds moved modestly higher.",
        exact_quote="Policy odds moved modestly higher.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.DIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
        created_at=now,
    )
    fact_two = FactClaim(
        id=2,
        analysis_run_id=1,
        source_id=2,
        normalized_fact="The court remains cautious.",
        exact_quote="The court remains cautious.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.DIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_CONTRADICTION,
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
            final_weight=0.04,
            rationale="Supportive evidence remains modest.",
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
            source_weight=0.24,
            freshness_multiplier=1.0,
            uniqueness_multiplier=1.0,
            template_multiplier=0.7,
            final_weight=0.01,
            rationale="Contrary evidence is present but still light.",
            created_at=now,
        ),
    ]
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.MACRO_POLICY,
            "claim_family": ClaimFamilyEnum.MACRO_POLICY,
            "clarity_score": 0.8,
            "resolution_risk": 0.2,
        },
    )()

    outcome = processor._score_analysis(
        request=object(),
        market=None,
        rule_parse=rule_parse,
        source_contexts=[
            SourceContext(source=source_one, possible_facts=[]),
            SourceContext(source=source_two, possible_facts=[]),
        ],
        social_intel_summary=None,
        facts=[fact_one, fact_two],
        factors=factors,
    )

    assert outcome.numeric_estimate_available is True
    assert outcome.numeric_estimate_reason is not None
    assert "net directional evidence is light" in outcome.numeric_estimate_reason
    assert outcome.p_hat is not None
    assert outcome.p_low is not None
    assert outcome.p_high is not None


def test_crowd_signal_can_drive_qualitative_lean_without_trusted_posts():
    processor = AnalysisProcessor(enable_remote_calls=False)
    now = datetime.now(UTC)
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.NARRATIVE_MANUAL,
            "claim_family": ClaimFamilyEnum.NARRATIVE_MANUAL,
            "clarity_score": 0.76,
            "resolution_risk": 0.24,
        },
    )()
    social_summary = SocialIntelSummary(
        analysis_run_id=1,
        consensus_label=ConsensusLabelEnum.BULLISH,
        consensus_strength=ConsensusStrengthEnum.STRONG,
        narrative_phase=NarrativePhaseEnum.EMERGING,
        summary="Many smaller X accounts are converging on a YES read before official sources weigh in.",
        key_themes=["early flow", "rumor velocity"],
        trusted_accounts_count=0,
        broad_posts_sampled=34,
        created_at=now,
    )

    outcome = processor._score_analysis(
        request=object(),
        market=None,
        rule_parse=rule_parse,
        source_contexts=[],
        social_intel_summary=social_summary,
        facts=[],
        factors=[],
    )

    assert outcome.qualitative_label == QualitativeLabelEnum.LEANS_YES
    assert outcome.numeric_estimate_available is True
    assert outcome.numeric_estimate_reason is not None
    assert "broad X crowd flow" in outcome.numeric_estimate_reason
    assert outcome.p_hat is not None


def test_score_analysis_keeps_numeric_output_when_gate_passes_without_market():
    processor = AnalysisProcessor(enable_remote_calls=False)
    now = datetime.now(UTC)
    source_one = Source(
        id=1,
        analysis_run_id=1,
        title="Reuters",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=now,
        content_hash="reuters-strong",
        excerpt="Policy odds moved decisively higher.",
        is_paywalled=False,
        metadata_json={},
        created_at=now,
    )
    source_two = Source(
        id=2,
        analysis_run_id=1,
        title="SCOTUSblog",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.EXPERT_ANALYSIS,
        fetched_at=now,
        content_hash="scotusblog-strong",
        excerpt="The counter-case is still live but narrower.",
        is_paywalled=False,
        metadata_json={},
        created_at=now,
    )
    fact_one = FactClaim(
        id=1,
        analysis_run_id=1,
        source_id=1,
        normalized_fact="Policy odds moved decisively higher.",
        exact_quote="Policy odds moved decisively higher.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.DIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
        created_at=now,
    )
    fact_two = FactClaim(
        id=2,
        analysis_run_id=1,
        source_id=2,
        normalized_fact="The counter-case is still live but narrower.",
        exact_quote="The counter-case is still live but narrower.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.DIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_CONTRADICTION,
        created_at=now,
    )
    factors = [
        Factor(
            analysis_run_id=1,
            fact_claim_id=1,
            stance=StanceEnum.YES,
            strength=StrengthEnum.STRONG,
            evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
            used_in_scoring=True,
            exclusion_reason=None,
            source_weight=0.2,
            freshness_multiplier=1.0,
            uniqueness_multiplier=1.0,
            template_multiplier=0.7,
            final_weight=0.18,
            rationale="Supportive evidence is strong and recent.",
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
            source_weight=0.24,
            freshness_multiplier=1.0,
            uniqueness_multiplier=1.0,
            template_multiplier=0.7,
            final_weight=0.04,
            rationale="Contrary evidence is present but limited.",
            created_at=now,
        ),
    ]
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.MACRO_POLICY,
            "claim_family": ClaimFamilyEnum.MACRO_POLICY,
            "clarity_score": 0.8,
            "resolution_risk": 0.2,
        },
    )()

    outcome = processor._score_analysis(
        request=object(),
        market=None,
        rule_parse=rule_parse,
        source_contexts=[
            SourceContext(source=source_one, possible_facts=[]),
            SourceContext(source=source_two, possible_facts=[]),
        ],
        social_intel_summary=None,
        facts=[fact_one, fact_two],
        factors=factors,
    )

    assert outcome.numeric_estimate_available is True
    assert outcome.numeric_estimate_reason is None
    assert outcome.p_hat is not None
    assert outcome.p_low is not None
    assert outcome.p_high is not None


def test_search_results_soft_fail_on_tavily_timeout():
    processor = AnalysisProcessor(enable_remote_calls=False)

    class FailingTavilyClient:
        def search(self, **_: object) -> list[SearchSourceDraft]:
            raise httpx.ReadTimeout("timed out")

    processor.tavily_client = FailingTavilyClient()
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "question_text": "Will the filing happen this week?",
            "template_detected": TemplateKey.OFFICIAL_EVENT,
            "official_domains": ["sec.gov"],
        },
    )()

    assert processor._search_results_for_rule_parse(rule_parse) == []


def test_political_midterm_questions_use_narrative_forecast_playbook():
    processor = AnalysisProcessor(enable_remote_calls=False)
    question = "Will the republicans win the house in the 2026 midterms?"

    assert processor._detect_template(question) == TemplateKey.NARRATIVE_MANUAL

    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "question_text": question,
            "template_detected": TemplateKey.NARRATIVE_MANUAL,
            "official_domains": [],
        },
    )()

    search_requests = processor._search_requests(rule_parse)

    assert any("forecast polls" in request["query"] for request in search_requests)
    assert any("latest election forecast" in request["query"] for request in search_requests)


def test_political_forecast_source_aligns_with_question_side():
    processor = AnalysisProcessor(enable_remote_calls=False)
    question = "Will the republicans win the house in the 2026 midterms?"
    yes_condition, no_condition = AnalysisProcessor._yes_no_conditions(
        question,
        ClaimFamilyEnum.NARRATIVE_MANUAL,
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "question_text": question,
            "claim_family": ClaimFamilyEnum.NARRATIVE_MANUAL,
            "yes_condition": yes_condition,
            "no_condition": no_condition,
        },
    )()

    assert (
        processor._condition_alignment(
            rule_parse,
            "Election forecasters say Republicans are slight favorites to win the House in the 2026 midterms.",
        )
        == StanceEnum.YES
    )
    assert (
        processor._condition_alignment(
            rule_parse,
            "Polling analysts say Democrats are favored to win the House in the 2026 midterms.",
        )
        == StanceEnum.NO
    )
    assert (
        processor._condition_alignment(
            rule_parse,
            "Democrats could gain seats, but Republicans are favored to keep at least one chamber after the 2026 midterms.",
        )
        == StanceEnum.YES
    )


def test_political_forecast_both_chambers_aligns_against_yes_when_other_party_keeps_one():
    processor = AnalysisProcessor(enable_remote_calls=False)
    question = "Will Democrats win both chambers of Congress in the 2026 midterms?"
    yes_condition, no_condition = AnalysisProcessor._yes_no_conditions(
        question,
        ClaimFamilyEnum.NARRATIVE_MANUAL,
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "question_text": question,
            "claim_family": ClaimFamilyEnum.NARRATIVE_MANUAL,
            "yes_condition": yes_condition,
            "no_condition": no_condition,
        },
    )()

    assert (
        processor._condition_alignment(
            rule_parse,
            "Forecast analysts say Democrats could gain seats, but Republicans are favored to keep at least one chamber after the 2026 midterms.",
        )
        == StanceEnum.NO
    )
    assert (
        processor._condition_alignment(
            rule_parse,
            "The generic ballot is not strong enough for Democrats to be favored to win both the House and Senate.",
        )
        == StanceEnum.NO
    )


def test_impeachment_unlikely_forecast_aligns_with_no_case():
    processor = AnalysisProcessor(enable_remote_calls=False)
    question = "Will Trump be impeached after the 2026 midterms?"
    yes_condition, no_condition = AnalysisProcessor._yes_no_conditions(
        question,
        ClaimFamilyEnum.NARRATIVE_MANUAL,
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "question_text": question,
            "claim_family": ClaimFamilyEnum.NARRATIVE_MANUAL,
            "yes_condition": yes_condition,
            "no_condition": no_condition,
        },
    )()

    assert (
        processor._condition_alignment(
            rule_parse,
            "Analysts say Trump impeachment after the midterms remains unlikely unless Democrats win the House and a major new scandal changes congressional incentives.",
        )
        == StanceEnum.NO
    )


def test_macro_policy_hawkish_fact_aligns_with_no_case():
    processor = AnalysisProcessor(enable_remote_calls=False)
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.MACRO_POLICY,
            "claim_family": ClaimFamilyEnum.MACRO_POLICY,
            "action": "cut",
            "yes_condition": "YES if the Fed cuts rates by December.",
            "no_condition": "NO if the Fed does not cut rates by December.",
        },
    )()

    stance = processor._condition_alignment(
        rule_parse,
        "Fed no longer expected to cut until Dec 2027; 51% chance of hike by Mar 2027; hikes now > cuts.",
    )

    assert stance == StanceEnum.NO


def test_generic_manual_scenario_language_is_downgraded_from_directional_role():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Ceasefire analysis",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=datetime.now(UTC),
        content_hash="generic-manual-scenario",
        excerpt=(
            "The first scenario happens when one party tires of war and asks for peace, "
            "as Hamas did when it pushed for a ceasefire with Israel in late 2023 and early 2024."
        ),
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact=(
            "The first scenario happens when one party tires of war and asks for peace, "
            "as Hamas did when it pushed for a ceasefire with Israel in late 2023 and early 2024."
        ),
        exact_quote=(
            "The first scenario happens when one party tires of war and asks for peace, "
            "as Hamas did when it pushed for a ceasefire with Israel in late 2023 and early 2024."
        ),
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.GENERIC_MANUAL,
            "claim_family": ClaimFamilyEnum.GENERIC_MANUAL,
            "question_text": "Will the war in Iran automatically restart after the cease fire?",
            "action": "restart",
            "entity_names": ["Iran"],
            "yes_condition": "YES if the war in Iran automatically restart after the cease fire happens.",
            "no_condition": "NO if the war in Iran automatically restart after the cease fire does not happen.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.GENERIC_MANUAL
            ),
        },
    )()

    normalized_role = processor._normalize_evidence_role(
        rule_parse=rule_parse,
        source=source,
        fact=fact,
        proposed_role=EvidenceRoleEnum.DIRECT_SUPPORT,
    )
    fact.evidence_role = normalized_role
    mapping = processor._map_fact_to_factor(rule_parse, source, fact)

    assert normalized_role == EvidenceRoleEnum.BACKGROUND
    assert mapping.used_in_scoring is False
    assert mapping.stance == StanceEnum.NEUTRAL


def test_generic_manual_conditional_restart_warning_is_not_scored_directionally():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Pentagon briefing",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=datetime.now(UTC),
        content_hash="generic-manual-conditional",
        excerpt=(
            "American forces remain postured and ready to resume major combat operations at "
            "literally a moment's notice, depending on how the talks go."
        ),
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact=(
            "American forces remain postured and ready to resume major combat operations at "
            "literally a moment's notice, depending on how the talks go."
        ),
        exact_quote=(
            "American forces remain postured and ready to resume major combat operations at "
            "literally a moment's notice, depending on how the talks go."
        ),
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_CONTRADICTION,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.GENERIC_MANUAL,
            "claim_family": ClaimFamilyEnum.GENERIC_MANUAL,
            "question_text": "Will the war in Iran automatically restart after the cease fire?",
            "action": "restart",
            "entity_names": ["Iran"],
            "yes_condition": "YES if the war in Iran automatically restart after the cease fire happens.",
            "no_condition": "NO if the war in Iran automatically restart after the cease fire does not happen.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.GENERIC_MANUAL
            ),
        },
    )()

    normalized_role = processor._normalize_evidence_role(
        rule_parse=rule_parse,
        source=source,
        fact=fact,
        proposed_role=EvidenceRoleEnum.DIRECT_CONTRADICTION,
    )
    fact.evidence_role = normalized_role
    mapping = processor._map_fact_to_factor(rule_parse, source, fact)

    assert normalized_role == EvidenceRoleEnum.BACKGROUND
    assert mapping.used_in_scoring is False
    assert mapping.stance == StanceEnum.NEUTRAL


def test_generic_manual_explicit_restart_fact_stays_directional():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Conflict update",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=datetime.now(UTC),
        content_hash="generic-manual-restart",
        excerpt="Iran resumed attacks after the ceasefire collapsed overnight.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact="Iran resumed attacks after the ceasefire collapsed overnight.",
        exact_quote="Iran resumed attacks after the ceasefire collapsed overnight.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.GENERIC_MANUAL,
            "claim_family": ClaimFamilyEnum.GENERIC_MANUAL,
            "question_text": "Will the war in Iran automatically restart after the cease fire?",
            "action": "restart",
            "entity_names": ["Iran"],
            "yes_condition": "YES if the war in Iran automatically restart after the cease fire happens.",
            "no_condition": "NO if the war in Iran automatically restart after the cease fire does not happen.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.GENERIC_MANUAL
            ),
        },
    )()

    normalized_role = processor._normalize_evidence_role(
        rule_parse=rule_parse,
        source=source,
        fact=fact,
        proposed_role=EvidenceRoleEnum.DIRECT_SUPPORT,
    )
    fact.evidence_role = normalized_role
    mapping = processor._map_fact_to_factor(rule_parse, source, fact)

    assert normalized_role == EvidenceRoleEnum.DIRECT_SUPPORT
    assert mapping.used_in_scoring is True
    assert mapping.stance == StanceEnum.YES


def test_generic_manual_ceasefire_hold_fact_aligns_with_no_case():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Diplomatic update",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=datetime.now(UTC),
        content_hash="generic-manual-hold",
        excerpt="The ceasefire held and negotiations continued without renewed attacks.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact="The ceasefire held and negotiations continued without renewed attacks.",
        exact_quote="The ceasefire held and negotiations continued without renewed attacks.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_CONTRADICTION,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.GENERIC_MANUAL,
            "claim_family": ClaimFamilyEnum.GENERIC_MANUAL,
            "question_text": "Will the war in Iran automatically restart after the cease fire?",
            "action": "restart",
            "entity_names": ["Iran"],
            "yes_condition": "YES if the war in Iran automatically restart after the cease fire happens.",
            "no_condition": "NO if the war in Iran automatically restart after the cease fire does not happen.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.GENERIC_MANUAL
            ),
        },
    )()

    normalized_role = processor._normalize_evidence_role(
        rule_parse=rule_parse,
        source=source,
        fact=fact,
        proposed_role=EvidenceRoleEnum.DIRECT_CONTRADICTION,
    )
    fact.evidence_role = normalized_role
    mapping = processor._map_fact_to_factor(rule_parse, source, fact)

    assert normalized_role == EvidenceRoleEnum.DIRECT_CONTRADICTION
    assert mapping.used_in_scoring is True
    assert mapping.stance == StanceEnum.NO


def test_generic_manual_manager_article_top_choice_scores_yes_from_background():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Real Madrid manager search",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=datetime.now(UTC),
        content_hash="mourinho-top-choice",
        excerpt="Jose Mourinho is Real Madrid president Florentino Perez's top choice to succeed Alvaro Arbeloa.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact="Jose Mourinho is Real Madrid president Florentino Perez's top choice to succeed Alvaro Arbeloa.",
        exact_quote="Jose Mourinho is Real Madrid president Florentino Perez's top choice to succeed Alvaro Arbeloa.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.BACKGROUND,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.GENERIC_MANUAL,
            "claim_family": ClaimFamilyEnum.GENERIC_MANUAL,
            "question_text": "Will Mourinho become the next manager of Real Madrid?",
            "action": "resolve",
            "entity_names": ["Mourinho", "Real Madrid"],
            "yes_condition": "YES if Mourinho become the next manager of Real Madrid happens.",
            "no_condition": "NO if Mourinho become the next manager of Real Madrid does not happen.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.GENERIC_MANUAL
            ),
        },
    )()

    normalized_role = processor._normalize_evidence_role(
        rule_parse=rule_parse,
        source=source,
        fact=fact,
        proposed_role=EvidenceRoleEnum.BACKGROUND,
    )
    fact.evidence_role = normalized_role
    mapping = processor._map_fact_to_factor(rule_parse, source, fact)

    assert normalized_role == EvidenceRoleEnum.DIRECT_SUPPORT
    assert mapping.used_in_scoring is True
    assert mapping.stance == StanceEnum.YES


def test_generic_manual_manager_no_agreement_scores_no_from_background():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Real Madrid manager search",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=datetime.now(UTC),
        content_hash="mourinho-no-agreement",
        excerpt="No agreement between Real Madrid and Mourinho yet.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact="No agreement between Real Madrid and Mourinho yet.",
        exact_quote="No agreement between Real Madrid and Mourinho yet.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.BACKGROUND,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.GENERIC_MANUAL,
            "claim_family": ClaimFamilyEnum.GENERIC_MANUAL,
            "question_text": "Will Mourinho become the next manager of Real Madrid?",
            "action": "resolve",
            "entity_names": ["Mourinho", "Real Madrid"],
            "yes_condition": "YES if Mourinho become the next manager of Real Madrid happens.",
            "no_condition": "NO if Mourinho become the next manager of Real Madrid does not happen.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.GENERIC_MANUAL
            ),
        },
    )()

    normalized_role = processor._normalize_evidence_role(
        rule_parse=rule_parse,
        source=source,
        fact=fact,
        proposed_role=EvidenceRoleEnum.BACKGROUND,
    )
    fact.evidence_role = normalized_role
    mapping = processor._map_fact_to_factor(rule_parse, source, fact)

    assert normalized_role == EvidenceRoleEnum.DIRECT_CONTRADICTION
    assert mapping.used_in_scoring is True
    assert mapping.stance == StanceEnum.NO


def test_generic_manual_manager_preferred_candidate_overrides_soft_could_wording():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Transfer rumors",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=datetime.now(UTC),
        content_hash="mourinho-preferred",
        excerpt=(
            "Jose Mourinho could be in line for a surprise return as Real Madrid manager, "
            "with The Athletic reporting the Portuguese coach is Madrid president Florentino "
            "Perez' preferred candidate."
        ),
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact=(
            "Jose Mourinho could be in line for a surprise return as Real Madrid manager, "
            "with The Athletic reporting the Portuguese coach is Madrid president Florentino "
            "Perez' preferred candidate."
        ),
        exact_quote=(
            "Jose Mourinho could be in line for a surprise return as Real Madrid manager, "
            "with The Athletic reporting the Portuguese coach is Madrid president Florentino "
            "Perez' preferred candidate."
        ),
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.BACKGROUND,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.GENERIC_MANUAL,
            "claim_family": ClaimFamilyEnum.GENERIC_MANUAL,
            "question_text": "Will Mourinho become the next manager of Real Madrid?",
            "action": "resolve",
            "entity_names": ["Mourinho", "Real Madrid"],
            "yes_condition": "YES if Mourinho become the next manager of Real Madrid happens.",
            "no_condition": "NO if Mourinho become the next manager of Real Madrid does not happen.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.GENERIC_MANUAL
            ),
        },
    )()

    normalized_role = processor._normalize_evidence_role(
        rule_parse=rule_parse,
        source=source,
        fact=fact,
        proposed_role=EvidenceRoleEnum.BACKGROUND,
    )
    fact.evidence_role = normalized_role
    mapping = processor._map_fact_to_factor(rule_parse, source, fact)

    assert normalized_role == EvidenceRoleEnum.DIRECT_SUPPORT
    assert mapping.used_in_scoring is True
    assert mapping.stance == StanceEnum.YES


def test_generic_manual_social_platform_web_result_does_not_score_as_news():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Instagram",
        domain="www.instagram.com",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=datetime.now(UTC),
        content_hash="instagram",
        excerpt="Jose Mourinho will be the next coach for Real Madrid.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact="Jose Mourinho will be the next coach for Real Madrid.",
        exact_quote="Jose Mourinho will be the next coach for Real Madrid.",
        claim_type=ClaimTypeEnum.FORECAST,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.GENERIC_MANUAL,
            "claim_family": ClaimFamilyEnum.GENERIC_MANUAL,
            "question_text": "Will Mourinho become the next manager of Real Madrid?",
            "action": "resolve",
            "entity_names": ["Mourinho", "Real Madrid"],
            "yes_condition": "YES if Mourinho become the next manager of Real Madrid happens.",
            "no_condition": "NO if Mourinho become the next manager of Real Madrid does not happen.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.GENERIC_MANUAL
            ),
        },
    )()

    mapping = processor._map_fact_to_factor(rule_parse, source, fact)

    assert mapping.used_in_scoring is False
    assert mapping.exclusion_reason == "Social-platform pages scraped as web results are contextual only."


def test_generic_manual_unrelated_not_fragment_stays_neutral():
    processor = AnalysisProcessor(enable_remote_calls=False)
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.GENERIC_MANUAL,
            "claim_family": ClaimFamilyEnum.GENERIC_MANUAL,
            "question_text": "Will the war in Iran automatically restart after the cease fire?",
            "action": "restart",
            "entity_names": ["Iran"],
            "yes_condition": "YES if the war in Iran automatically restart after the cease fire happens.",
            "no_condition": "NO if the war in Iran automatically restart after the cease fire does not happen.",
        },
    )()

    stance = processor._condition_alignment(
        rule_parse,
        "Trump criticized NATO in a social media post after the meeting but did not announce a reduction in U.S.",
    )

    assert stance == StanceEnum.NEUTRAL


def test_generic_manual_ceasefire_dispute_without_restart_cue_stays_neutral():
    processor = AnalysisProcessor(enable_remote_calls=False)
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.GENERIC_MANUAL,
            "claim_family": ClaimFamilyEnum.GENERIC_MANUAL,
            "question_text": "Will the war in Iran automatically restart after the cease fire?",
            "action": "restart",
            "entity_names": ["Iran"],
            "yes_condition": "YES if the war in Iran automatically restart after the cease fire happens.",
            "no_condition": "NO if the war in Iran automatically restart after the cease fire does not happen.",
        },
    )()

    stance = processor._condition_alignment(
        rule_parse,
        "Large-scale Israeli strikes in Lebanon are a key point of contention: Iran and mediator Pakistan said that an end to fighting in Lebanon was part of the ceasefire deal, while Israel and the United States said it was not.",
    )

    assert stance == StanceEnum.NEUTRAL


def test_entity_names_strip_leading_question_words():
    entities = AnalysisProcessor._entity_names(
        "Will Anthropic win its lawsuit against the dod?"
    )

    assert entities == ["Anthropic"]


def test_legal_case_win_lawsuit_conditions_are_specific():
    yes_condition, no_condition = AnalysisProcessor._yes_no_conditions(
        "Will Anthropic win its lawsuit against the dod?",
        ClaimFamilyEnum.LEGAL_CASE,
    )

    assert "Anthropic" in yes_condition
    assert "Department of Defense" in yes_condition
    assert "wins meaningful court relief" in yes_condition
    assert "denies relief" in no_condition


def test_legal_case_side_with_order_conditions_are_specific():
    yes_condition, no_condition = AnalysisProcessor._yes_no_conditions(
        "Will the supreme court side with Trump EO on birthright citizenship?",
        ClaimFamilyEnum.LEGAL_CASE,
    )

    assert "Trump executive order on birthright citizenship" in yes_condition
    assert "upholds, allows, or lets" in yes_condition
    assert "blocks, strikes down, invalidates" in no_condition


def test_legal_case_side_with_order_conditions_are_subject_agnostic():
    yes_condition, no_condition = AnalysisProcessor._yes_no_conditions(
        "Will the supreme court side with Biden EO on asylum?",
        ClaimFamilyEnum.LEGAL_CASE,
    )

    assert "Biden executive order on asylum" in yes_condition
    assert "upholds, allows, or lets" in yes_condition
    assert "blocks, strikes down, invalidates" in no_condition


def test_legal_case_injunction_win_scores_as_directional_support():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Court filing",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.EXPERT_ANALYSIS,
        fetched_at=datetime.now(UTC),
        content_hash="injunction-win",
        excerpt="A federal judge granted Anthropic's request for a preliminary injunction against the Department of Defense.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact="A federal judge granted Anthropic's request for a preliminary injunction against the Department of Defense.",
        exact_quote="A federal judge granted Anthropic's request for a preliminary injunction against the Department of Defense.",
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.LEGAL_CASE,
            "claim_family": ClaimFamilyEnum.LEGAL_CASE,
            "question_text": "Will Anthropic win its lawsuit against the dod?",
            "action": "win",
            "entity_names": ["Anthropic"],
            "yes_condition": "YES if Anthropic wins meaningful court relief against Department of Defense, such as prevailing on the merits or obtaining the injunction or order the suit seeks.",
            "no_condition": "NO if Anthropic loses against Department of Defense, the case is dismissed, or the court denies relief and lets Department of Defense's position stand.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.LEGAL_CASE
            ),
        },
    )()

    normalized_role = processor._normalize_evidence_role(
        rule_parse=rule_parse,
        source=source,
        fact=fact,
        proposed_role=EvidenceRoleEnum.DIRECT_SUPPORT,
    )
    mapping = processor._map_fact_to_factor(rule_parse, source, fact)

    assert normalized_role == EvidenceRoleEnum.DIRECT_SUPPORT
    assert mapping.used_in_scoring is True
    assert mapping.stance == StanceEnum.YES


def test_legal_case_merits_deferral_is_not_scored_directionally():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="SCOTUSblog",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.EXPERT_ANALYSIS,
        fetched_at=datetime.now(UTC),
        content_hash="merits-deferral",
        excerpt=(
            "The justices did not, however, weigh in on the question at the center of the three "
            "lawsuits before the court: whether the birthright citizenship order itself is constitutional."
        ),
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact=(
            "The justices did not, however, weigh in on the question at the center of the three "
            "lawsuits before the court: whether the birthright citizenship order itself is constitutional."
        ),
        exact_quote=(
            "The justices did not, however, weigh in on the question at the center of the three "
            "lawsuits before the court: whether the birthright citizenship order itself is constitutional."
        ),
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.LEGAL_CASE,
            "claim_family": ClaimFamilyEnum.LEGAL_CASE,
            "question_text": "Will the supreme court side with Trump EO on birthright citizenship?",
            "action": "side with",
            "entity_names": ["Supreme Court", "Trump"],
            "yes_condition": "YES if the court upholds, allows, or lets Trump's executive order on birthright citizenship take effect on the merits.",
            "no_condition": "NO if the court blocks, strikes down, invalidates, or rules against Trump's executive order on birthright citizenship on the merits.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.LEGAL_CASE
            ),
        },
    )()

    normalized_role = processor._normalize_evidence_role(
        rule_parse=rule_parse,
        source=source,
        fact=fact,
        proposed_role=EvidenceRoleEnum.DIRECT_SUPPORT,
    )
    fact.evidence_role = normalized_role
    mapping = processor._map_fact_to_factor(rule_parse, source, fact)

    assert normalized_role == EvidenceRoleEnum.PROCEDURAL
    assert mapping.used_in_scoring is False
    assert mapping.stance == StanceEnum.NEUTRAL


def test_legal_case_injunction_scope_only_ruling_is_not_scored_directionally():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Barbara v. Trump",
        source_kind=SourceKindEnum.OFFICIAL,
        source_tier=SourceTierEnum.OFFICIAL_PRIMARY,
        fetched_at=datetime.now(UTC),
        content_hash="injunction-scope",
        excerpt=(
            "The three other courts issued universal preliminary injunctions, which the Supreme "
            "Court held were broader than necessary."
        ),
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact=(
            "The three other courts issued universal preliminary injunctions, which the Supreme "
            "Court held were broader than necessary."
        ),
        exact_quote=(
            "The three other courts issued universal preliminary injunctions, which the Supreme "
            "Court held were broader than necessary."
        ),
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.DIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.DIRECT_SUPPORT,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.LEGAL_CASE,
            "claim_family": ClaimFamilyEnum.LEGAL_CASE,
            "question_text": "Will the supreme court side with Trump EO on birthright citizenship?",
            "action": "side with",
            "entity_names": ["Supreme Court", "Trump"],
            "yes_condition": "YES if the court upholds, allows, or lets Trump's executive order on birthright citizenship take effect on the merits.",
            "no_condition": "NO if the court blocks, strikes down, invalidates, or rules against Trump's executive order on birthright citizenship on the merits.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.LEGAL_CASE
            ),
        },
    )()

    normalized_role = processor._normalize_evidence_role(
        rule_parse=rule_parse,
        source=source,
        fact=fact,
        proposed_role=EvidenceRoleEnum.DIRECT_SUPPORT,
    )
    fact.evidence_role = normalized_role
    mapping = processor._map_fact_to_factor(rule_parse, source, fact)

    assert normalized_role == EvidenceRoleEnum.PROCEDURAL
    assert mapping.used_in_scoring is False
    assert mapping.stance == StanceEnum.NEUTRAL


def test_legal_case_explicit_block_ruling_upgrades_from_background_to_no_direction():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Appeals court ruling",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
        fetched_at=datetime.now(UTC),
        content_hash="block-ruling",
        excerpt=(
            "A federal appeals court upheld a block on President Trump's executive order ending "
            "birthright citizenship."
        ),
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact=(
            "A federal appeals court upheld a block on President Trump's executive order ending "
            "birthright citizenship."
        ),
        exact_quote=(
            "A federal appeals court upheld a block on President Trump's executive order ending "
            "birthright citizenship."
        ),
        claim_type=ClaimTypeEnum.FACT,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.BACKGROUND,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.LEGAL_CASE,
            "claim_family": ClaimFamilyEnum.LEGAL_CASE,
            "question_text": "Will the supreme court side with Trump EO on birthright citizenship?",
            "action": "side with",
            "entity_names": ["Supreme Court", "Trump"],
            "yes_condition": "YES if the court upholds, allows, or lets Trump's executive order on birthright citizenship take effect on the merits.",
            "no_condition": "NO if the court blocks, strikes down, invalidates, or rules against Trump's executive order on birthright citizenship on the merits.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.LEGAL_CASE
            ),
        },
    )()

    normalized_role = processor._normalize_evidence_role(
        rule_parse=rule_parse,
        source=source,
        fact=fact,
        proposed_role=EvidenceRoleEnum.BACKGROUND,
    )
    fact.evidence_role = normalized_role
    mapping = processor._map_fact_to_factor(rule_parse, source, fact)

    assert normalized_role == EvidenceRoleEnum.DIRECT_CONTRADICTION
    assert mapping.used_in_scoring is True
    assert mapping.stance == StanceEnum.NO


def test_legal_case_likely_side_against_challenged_order_scores_no():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source = Source(
        analysis_run_id=1,
        title="Supreme Court appears likely to side against Trump on birthright citizenship",
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.EXPERT_ANALYSIS,
        fetched_at=datetime.now(UTC),
        content_hash="likely-against",
        excerpt="The Supreme Court appears likely to side against Trump on birthright citizenship.",
        is_paywalled=False,
        metadata_json={},
        created_at=datetime.now(UTC),
    )
    fact = FactClaim(
        analysis_run_id=1,
        source_id=1,
        normalized_fact="The Supreme Court appears likely to side against Trump on birthright citizenship.",
        exact_quote="The Supreme Court appears likely to side against Trump on birthright citizenship.",
        claim_type=ClaimTypeEnum.FORECAST,
        directness=DirectnessEnum.INDIRECT,
        verifier_status=VerifierStatusEnum.SUPPORTED,
        evidence_role=EvidenceRoleEnum.BACKGROUND,
        created_at=datetime.now(UTC),
    )
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.LEGAL_CASE,
            "claim_family": ClaimFamilyEnum.LEGAL_CASE,
            "question_text": "Will the supreme court side with Trump EO on birthright citizenship?",
            "action": "side with",
            "entity_names": ["Supreme Court", "Trump"],
            "yes_condition": "YES if the court upholds, allows, or lets Trump's executive order on birthright citizenship take effect on the merits.",
            "no_condition": "NO if the court blocks, strikes down, invalidates, or rules against Trump's executive order on birthright citizenship on the merits.",
            "directional_scoring_policy": AnalysisProcessor._default_scoring_policy(
                ClaimFamilyEnum.LEGAL_CASE
            ),
        },
    )()

    normalized_role = processor._normalize_evidence_role(
        rule_parse=rule_parse,
        source=source,
        fact=fact,
        proposed_role=EvidenceRoleEnum.BACKGROUND,
    )
    fact.evidence_role = normalized_role
    mapping = processor._map_fact_to_factor(rule_parse, source, fact)

    assert normalized_role == EvidenceRoleEnum.COMMENTARY
    assert mapping.used_in_scoring is True
    assert mapping.stance == StanceEnum.NO


def test_legal_case_search_requests_mix_broad_and_official_lanes():
    processor = AnalysisProcessor(enable_remote_calls=False)
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.LEGAL_CASE,
            "question_text": "Will Anthropic win its lawsuit against the dod?",
            "official_domains": ["supremecourt.gov", "uscourts.gov", "justice.gov"],
        },
    )()

    search_requests = processor._search_requests(rule_parse)

    assert len(search_requests) == 2
    assert search_requests[0]["include_domains"] is None
    assert "department of defense" in search_requests[0]["query"].lower()
    assert "injunction" in search_requests[0]["query"].lower()
    assert search_requests[1]["include_domains"] == ["supremecourt.gov", "uscourts.gov", "justice.gov"]


def test_legal_case_search_relevance_prefers_dod_case_material():
    processor = AnalysisProcessor(enable_remote_calls=False)
    rule_parse = type(
        "RuleParseStub",
        (),
        {
            "template_detected": TemplateKey.LEGAL_CASE,
            "question_text": "Will Anthropic win its lawsuit against the dod?",
            "yes_condition": "YES if Anthropic wins meaningful court relief against Department of Defense.",
            "no_condition": "NO if Anthropic loses against Department of Defense.",
            "action": "win",
            "entity_names": ["Anthropic"],
        },
    )()
    relevant = SearchSourceDraft(
        url="https://example.com/anthropic-dod",
        title="Anthropic wins preliminary injunction in DOD fight",
        excerpt="A federal judge granted Anthropic's request for a preliminary injunction against the Department of Defense.",
        source_tier=SourceTierEnum.REPUTABLE_NEWS,
    )
    irrelevant = SearchSourceDraft(
        url="https://example.com/google",
        title="U.S. and Plaintiff States v. Google LLC",
        excerpt="Google cited an Anthropic amicus brief in a separate antitrust case.",
        source_tier=SourceTierEnum.OFFICIAL_PRIMARY,
    )

    assert (
        processor._search_result_relevance(rule_parse, relevant)
        > processor._search_result_relevance(rule_parse, irrelevant)
    )


def test_premium_search_results_require_opt_in():
    request_without_premium = type(
        "RequestStub",
        (),
        {"input_payload": {}},
    )()
    request_with_premium = type(
        "RequestStub",
        (),
        {"input_payload": {"include_premium": True}},
    )()
    result = SearchSourceDraft(
        url="https://www.wsj.com/example",
        title="Premium example",
        excerpt="Premium coverage of a market-moving event.",
        source_tier=SourceTierEnum.PREMIUM_NEWS,
    )

    assert AnalysisProcessor._should_include_search_result(request_without_premium, result) is False
    assert AnalysisProcessor._should_include_search_result(request_with_premium, result) is True

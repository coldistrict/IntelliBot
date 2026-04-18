from datetime import UTC, datetime

from app.models import FactClaim, Factor, Market, Passage, Source
from app.models.enums import (
    ClaimTypeEnum,
    ClaimFamilyEnum,
    ConfidenceLabelEnum,
    ConsensusLabelEnum,
    ConsensusStrengthEnum,
    DirectnessEnum,
    EvidenceRoleEnum,
    NarrativePhaseEnum,
    PricedInRiskLabelEnum,
    QualitativeLabelEnum,
    RecommendationLabelEnum,
    SourceKindEnum,
    SourceTierEnum,
    StanceEnum,
    StrengthEnum,
    TemplateKey,
    VerifierStatusEnum,
)
from app.services.analysis_pipeline import AnalysisProcessor, SourceContext
from app.services.pipeline_models import SearchSourceDraft

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


def test_no_market_weak_evidence_suppresses_numeric_output():
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

    assert allowed is False
    assert "fewer than two scored directional factors" in (reason or "")
    assert (
        processor._qualitative_label(factors, 0.06)
        == QualitativeLabelEnum.INSUFFICIENT_BASIS
    )


def test_no_market_runs_keep_point_probability_read():
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
    assert outcome.numeric_estimate_reason is None
    assert outcome.p_hat is not None
    assert outcome.p_low is not None
    assert outcome.p_high is not None


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

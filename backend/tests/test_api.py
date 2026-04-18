from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.models import AnalysisRequest, Market, RuleParse
from app.models.enums import (
    ClaimFamilyEnum,
    ConsensusLabelEnum,
    ConsensusStrengthEnum,
    InputTypeEnum,
    ModeEnum,
    NarrativePhaseEnum,
    RequestStatusEnum,
    SourceTierEnum,
    TemplateKey,
)
from app.services.analysis_progress import (
    initial_progress_payload,
    mark_stage_complete,
    mark_stage_failed,
    mark_stage_running,
    mark_stage_skipped,
)
from app.services.analysis_pipeline import AnalysisProcessor, get_analysis_processor
from app.services.pipeline_models import SocialIntelDraft, TrustedSocialPostDraft


def test_health_endpoint(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "backend"


def test_manual_analysis_submission_and_detail(client):
    create_response = client.post(
        "/api/analyses/manual",
        json={
            "custom_claim": "Will the Fed cut rates by June?",
            "template_requested": "macro_policy",
            "include_premium": False,
        },
    )

    assert create_response.status_code == 202
    request_payload = create_response.json()["request"]
    assert request_payload["status"] == "queued"
    assert request_payload["input_type"] == "custom_claim"

    list_response = client.get("/api/analyses")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["input_text"] == "Will the Fed cut rates by June?"

    detail_response = client.get(f"/api/analyses/{request_payload['id']}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["request"]["id"] == request_payload["id"]
    assert detail_payload["market"] is None
    assert detail_payload["request"]["status"] == "complete"
    assert detail_payload["latest_rule_parse"]["template_detected"] == "macro_policy"
    assert detail_payload["latest_run"] is not None
    assert detail_payload["latest_run"]["recommendation_label"] == "analysis_only"
    assert detail_payload["recommendation"]["recommendation_label"] == "analysis_only"
    assert detail_payload["display_summary"]
    assert detail_payload["presentation"]["headline"] == "Will the Fed cut rates by June?"
    assert detail_payload["presentation"]["brief_sections"]["what_it_means"]
    assert len(detail_payload["presentation"]["artifact_statuses"]) >= 5
    assert detail_payload["progress"]["percent_complete"] == 100
    assert detail_payload["audit"] is not None
    assert detail_payload["audit"]["probability"]["p_hat"] == detail_payload["latest_run"]["p_hat"]
    assert (
        detail_payload["audit"]["confidence"]["final_label"]
        == detail_payload["latest_run"]["confidence_label"]
    )
    assert detail_payload["social_intel_summary"] is not None
    assert detail_payload["social_intel_summary"]["consensus_label"] == "unclear"
    assert detail_payload["trusted_social_sources"] == []
    assert len(detail_payload["sources"]) >= 1
    assert len(detail_payload["documents"]) >= 1
    assert len(detail_payload["passages"]) >= 1
    assert len(detail_payload["fact_claims"]) >= 1
    assert len(detail_payload["factors"]) >= 1


def test_running_analysis_detail_returns_progress_and_partial_sections(
    client,
    session_factory: sessionmaker[Session],
):
    now = datetime.now(UTC)
    with session_factory() as session:
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
        mark_stage_skipped(request, "market_lookup", "No linked market was supplied.", now=now)
        mark_stage_complete(
            request,
            "rule_parse",
            "Rules parsed into a macro-policy template.",
            now=now,
        )
        mark_stage_running(
            request,
            "retrieval",
            "Searching official and news sources.",
            now=now,
        )
        session.add(request)
        session.commit()
        session.refresh(request)

        rule_parse = RuleParse(
            analysis_request_id=request.id,
            question_text="Will the Fed cut rates by June?",
            event="Fed cuts rates by June",
            entity_names=["Federal Reserve"],
            action="cut rates",
            claim_family=ClaimFamilyEnum.MACRO_POLICY,
            yes_condition="YES if the Fed cuts rates by June.",
            no_condition="NO if the Fed does not cut rates by June.",
            deadline_text="June 2026",
            resolution_definition="Resolves YES if the Fed cuts rates by June 2026.",
            directional_scoring_policy={
                "allowed_roles": ["outcome", "direct_support", "direct_contradiction", "commentary"],
                "commentary_mode": "expert_only",
                "procedural_mode": "uncertainty_only",
            },
            official_domains=["federalreserve.gov"],
            fallback_sources=[],
            ambiguity_flags=[],
            clarity_score=0.74,
            resolution_risk=0.26,
            suitable_for_auto=False,
            template_detected=TemplateKey.MACRO_POLICY,
            created_at=now,
        )
        session.add(rule_parse)
        session.commit()
        analysis_id = request.id

    detail_response = client.get(f"/api/analyses/{analysis_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()

    assert detail_payload["request"]["status"] == "running"
    assert detail_payload["latest_rule_parse"]["template_detected"] == "macro_policy"
    assert detail_payload["latest_run"] is None
    assert detail_payload["progress"]["current_label"] == "Retrieval"
    assert detail_payload["progress"]["current_note"] == "Searching official and news sources."
    assert detail_payload["presentation"]["artifact_statuses"][0]["key"] == "rule_parse"
    assert detail_payload["display_summary"].startswith("Analysis in progress.")


def test_failed_analysis_detail_returns_failed_stage_and_readable_summary(
    client,
    session_factory: sessionmaker[Session],
):
    now = datetime.now(UTC)
    with session_factory() as session:
        request = AnalysisRequest(
            mode=ModeEnum.MANUAL,
            input_type=InputTypeEnum.CUSTOM_CLAIM,
            input_text="Will the filing arrive this week?",
            input_payload={},
            progress_json=initial_progress_payload(now),
            status=RequestStatusEnum.FAILED,
            current_stage="rule_parse",
            error_message="Rule parser could not normalize the market deadline.",
            started_at=now,
            completed_at=now,
        )
        mark_stage_complete(request, "normalize", "Request normalized.", now=now)
        mark_stage_failed(
            request,
            "rule_parse",
            "Rule parser could not normalize the market deadline.",
            now=now,
        )
        session.add(request)
        session.commit()
        analysis_id = request.id

    detail_response = client.get(f"/api/analyses/{analysis_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()

    assert detail_payload["request"]["status"] == "failed"
    assert detail_payload["progress"]["current_label"] == "Rule Parse"
    assert detail_payload["request"]["error_message"] == "Rule parser could not normalize the market deadline."
    assert detail_payload["presentation"]["thesis"].startswith("Analysis stopped during")
    assert "Analysis stopped during rule parse." in detail_payload["display_summary"]


def test_manual_analysis_links_existing_market(client, session_factory: sessionmaker[Session]):
    with session_factory() as session:
        market = Market(
            polymarket_id="fed-cut-june-2026",
            title="Will the Fed cut by June 2026?",
            url="https://polymarket.com/event/fed-cut-june-2026",
            rules_text="Sample rules",
            description="Sample market",
            yes_bid=0.41,
            yes_ask=0.43,
            no_bid=0.57,
            no_ask=0.59,
            liquidity=25000,
            volume_24h=5000,
            spread=0.02,
            status="active",
        )
        session.add(market)
        session.commit()
        session.refresh(market)
        market_id = market.id

    response = client.post(
        "/api/analyses/manual",
        json={"polymarket_market_id": "fed-cut-june-2026"},
    )

    assert response.status_code == 202
    payload = response.json()["request"]
    assert payload["market_id"] == market_id

    market_response = client.get("/api/markets")
    assert market_response.status_code == 200
    market_payload = market_response.json()
    assert market_payload["total"] == 1
    assert market_payload["items"][0]["polymarket_id"] == "fed-cut-june-2026"


def test_review_requires_completed_run(client):
    create_response = client.post(
        "/api/analyses/manual",
        json={"custom_claim": "Will a filing happen this week?"},
    )
    analysis_id = create_response.json()["request"]["id"]

    review_response = client.post(
        f"/api/analyses/{analysis_id}/review",
        json={"decision": "watch", "note": "Waiting for a real run."},
    )

    assert review_response.status_code == 200
    assert review_response.json()["decision"] == "watch"


def test_rerun_requeues_existing_request(client):
    create_response = client.post(
        "/api/analyses/manual",
        json={"custom_claim": "Will an approval land by Friday?"},
    )
    analysis_id = create_response.json()["request"]["id"]

    rerun_response = client.post(f"/api/analyses/{analysis_id}/rerun")

    assert rerun_response.status_code == 202
    payload = rerun_response.json()["request"]
    assert payload["id"] == analysis_id
    assert payload["status"] == "queued"

    detail_response = client.get(f"/api/analyses/{analysis_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["request"]["status"] == "complete"
    assert detail_payload["latest_run"] is not None
    assert detail_payload["latest_rule_parse"] is not None


def test_auto_scan_run_processes_request(client):
    response = client.post(
        "/api/analyses/auto-scan/run",
        json={"note": "Kick off the auto scanner."},
    )

    assert response.status_code == 202
    payload = response.json()["request"]
    assert payload["status"] == "queued"
    assert payload["input_text"] == "AUTO_SCAN_TRIGGER"

    detail_response = client.get(f"/api/analyses/{payload['id']}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["request"]["status"] == "complete"
    assert detail_payload["latest_run"] is not None
    assert detail_payload["latest_rule_parse"] is not None


def test_progress_endpoint_returns_lightweight_progress_payload(
    client,
    session_factory: sessionmaker[Session],
):
    now = datetime.now(UTC)
    with session_factory() as session:
        request = AnalysisRequest(
            mode=ModeEnum.MANUAL,
            input_type=InputTypeEnum.CUSTOM_CLAIM,
            input_text="Will a filing happen this week?",
            input_payload={},
            progress_json=initial_progress_payload(now),
            status=RequestStatusEnum.RUNNING,
            current_stage="retrieval",
            started_at=now,
        )
        mark_stage_complete(request, "normalize", "Request normalized.", now=now)
        mark_stage_running(request, "retrieval", "Searching trusted sources.", now=now)
        session.add(request)
        session.commit()
        session.refresh(request)

        rule_parse = RuleParse(
            analysis_request_id=request.id,
            question_text="Will a filing happen this week?",
            event="A filing happens this week",
            entity_names=["Issuer"],
            action="file",
            claim_family=ClaimFamilyEnum.OFFICIAL_EVENT,
            yes_condition="YES if the filing happens this week.",
            no_condition="NO if the filing does not happen this week.",
            deadline_text="This week",
            resolution_definition="Resolves YES if the filing lands by the end of the week.",
            directional_scoring_policy={},
            official_domains=["sec.gov"],
            fallback_sources=[],
            ambiguity_flags=[],
            clarity_score=0.8,
            resolution_risk=0.2,
            suitable_for_auto=True,
            template_detected=TemplateKey.OFFICIAL_EVENT,
            created_at=now,
        )
        session.add(rule_parse)
        session.commit()
        analysis_id = request.id

    response = client.get(f"/api/analyses/{analysis_id}/progress")
    assert response.status_code == 200
    payload = response.json()

    assert payload["request"]["status"] == "running"
    assert payload["progress"]["current_stage"] == "retrieval"
    assert payload["presentation"]["artifact_statuses"][0]["key"] == "rule_parse"
    assert "sources" not in payload
    assert "documents" not in payload


def test_live_social_intelligence_groups_trusted_timeline_and_supporting_social(
    client,
    session_factory: sessionmaker[Session],
):
    class StubXAIClient:
        is_configured = True

        def generate_structured_with_tools(self, **kwargs):
            now = datetime.now(UTC)
            return SocialIntelDraft(
                consensus_label=ConsensusLabelEnum.BULLISH,
                consensus_strength=ConsensusStrengthEnum.STRONG,
                narrative_phase=NarrativePhaseEnum.EMERGING,
                summary="Trusted macro accounts lean toward a June cut, while broader X has turned constructive but not euphoric.",
                key_themes=["fed path", "softening labor data"],
                trusted_accounts_count=2,
                broad_posts_sampled=18,
                trusted_posts=[
                    TrustedSocialPostDraft(
                        handle="NickTimiraos",
                        display_name="Nick Timiraos",
                        post_url="https://x.com/NickTimiraos/status/123",
                        post_timestamp=now,
                        account_category="reporter",
                        trust_tier=SourceTierEnum.HIGH_TRUST_SOCIAL,
                        trust_confidence=0.93,
                        relevance_reason="Frequently breaks Fed-related developments and is directly relevant to rate-cut pricing.",
                        trust_reason="Widely followed WSJ Fed reporter with a strong track record on policy signaling.",
                        post_summary="He notes that recent data is pulling the market toward a faster easing path.",
                        possible_facts=["Recent data is shifting easing expectations earlier."],
                        citation_urls=["https://www.wsj.com/finance/central-banking"],
                    ),
                    TrustedSocialPostDraft(
                        handle="RandomMacroGuy",
                        display_name="Random Macro Guy",
                        post_url="https://x.com/RandomMacroGuy/status/456",
                        post_timestamp=now,
                        account_category="analyst",
                        trust_tier=SourceTierEnum.REPORTER_SOCIAL,
                        trust_confidence=0.42,
                        relevance_reason="Talking about the same subject.",
                        trust_reason="Not strong enough to count as trusted.",
                        post_summary="He says a cut is definitely coming.",
                        possible_facts=["A cut is definitely coming."],
                        citation_urls=[],
                    ),
                ],
            )

    app.dependency_overrides[get_analysis_processor] = lambda: AnalysisProcessor(
        session_factory=session_factory,
        enable_remote_calls=False,
        xai_client=StubXAIClient(),
    )
    try:
        response = client.post(
            "/api/analyses/manual",
            json={
                "custom_claim": "Will the Fed cut rates by June?",
                "template_requested": "macro_policy",
                "include_live_x_intelligence": True,
            },
        )
    finally:
        app.dependency_overrides[get_analysis_processor] = (
            lambda: AnalysisProcessor(session_factory=session_factory, enable_remote_calls=False)
        )

    analysis_id = response.json()["request"]["id"]
    detail_response = client.get(f"/api/analyses/{analysis_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()

    assert detail_payload["social_intel_summary"] is not None
    assert detail_payload["social_intel_summary"]["consensus_label"] == "bullish"
    assert detail_payload["social_intel_summary"]["narrative_phase"] == "emerging"
    assert detail_payload["social_intel_summary"]["trusted_accounts_count"] == 1
    assert len(detail_payload["trusted_social_sources"]) == 1
    assert detail_payload["trusted_social_sources"][0]["source_tier"] == "high_trust_social"
    assert detail_payload["trusted_social_sources"][0]["metadata_json"]["handle"] == "NickTimiraos"
    assert detail_payload["trusted_social_sources"][0]["metadata_json"]["trust_reason"]
    assert detail_payload["trusted_social_sources"][0]["metadata_json"]["relevance_reason"]

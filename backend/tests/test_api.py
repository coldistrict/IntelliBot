from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.api.routes.markets import get_polymarket_client
from app.clients.polymarket_client import ResolvedMarketRecord
from app.models import AnalysisRequest, AnalysisRun, Market, Recommendation, RuleParse
from app.models.enums import (
    ClaimFamilyEnum,
    ConfidenceLabelEnum,
    ConsensusLabelEnum,
    ConsensusStrengthEnum,
    InputTypeEnum,
    ModeEnum,
    NarrativePhaseEnum,
    PricedInRiskLabelEnum,
    QualitativeLabelEnum,
    RecommendationLabelEnum,
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


def test_ledger_and_event_sourced_journal_endpoints(client):
    created = client.post(
        "/api/analyses/manual",
        json={"custom_claim": "Will the Federal Reserve cut rates at its next meeting?"},
    )
    analysis_id = created.json()["request"]["id"]

    ledger = client.get(f"/api/analyses/{analysis_id}/ledger")
    assert ledger.status_code == 200
    ledger_payload = ledger.json()
    assert len(ledger_payload["stages"]) >= 5
    assert ledger_payload["calls"]
    assert ledger_payload["run_quality"] in {"warning", "invalid"}

    before = client.post(
        f"/api/analyses/{analysis_id}/journal/before",
        json={"prior_probability": 0.35, "intended_action": "no_bet", "entry_threshold": None},
    )
    assert before.status_code == 200
    after_one = client.post(
        f"/api/analyses/{analysis_id}/journal/after",
        json={
            "decision": "no",
            "conviction": 3,
            "rationale": "The memo showed no edge.",
            "what_changed": "Lowered the prior.",
        },
    )
    after_two = client.post(
        f"/api/analyses/{analysis_id}/journal/after",
        json={
            "decision": "no_bet",
            "conviction": 2,
            "rationale": "Risk limit changed.",
            "what_changed": "Skipped the decision.",
        },
    )
    assert after_one.status_code == 200
    assert after_two.status_code == 200
    events = client.get(f"/api/analyses/{analysis_id}/journal").json()["events"]
    assert [event["event_type"] for event in events] == ["before", "after", "after"]
    assert all(event["created_at"] for event in events)


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
    assert payload["market_title"] == "Will the Fed cut by June 2026?"

    market_response = client.get("/api/markets")
    assert market_response.status_code == 200
    market_payload = market_response.json()
    assert market_payload["total"] == 1
    assert market_payload["items"][0]["polymarket_id"] == "fed-cut-june-2026"

    detail_response = client.get(f"/api/analyses/{payload['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["presentation"]["headline"] == "Will the Fed cut by June 2026?"

    list_response = client.get("/api/analyses")
    assert list_response.status_code == 200
    summaries = list_response.json()["items"]
    assert summaries[0]["market_title"] == "Will the Fed cut by June 2026?"

    filtered = client.get("/api/analyses", params={"polymarket_id": "fed-cut-june-2026"})
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert filtered_payload["total"] == 1
    assert filtered_payload["items"][0]["market_id"] == market_id

    unmatched = client.get("/api/analyses", params={"polymarket_id": "some-other-market"})
    assert unmatched.status_code == 200
    assert unmatched.json()["total"] == 0
    assert unmatched.json()["items"] == []


def test_public_market_discovery_lists_remote_polymarket_markets(client):
    class StubPolymarketClient:
        def discover_markets(self, *, query=None, view="popular", limit=25, offset=0):
            assert query is None
            assert view == "popular"
            assert limit == 2
            assert offset == 0
            return [
                ResolvedMarketRecord(
                    polymarket_id="bitcoin-100k-2026",
                    title="Will Bitcoin hit $100k in 2026?",
                    url="https://polymarket.com/event/bitcoin-100k-2026",
                    rules_text="Resolves YES if Bitcoin trades above $100k in 2026.",
                    description="Crypto market",
                    yes_bid=0.41,
                    yes_ask=0.43,
                    no_bid=0.57,
                    no_ask=0.59,
                    liquidity=150000,
                    volume_24h=42000,
                    spread=0.02,
                    expiry_at=None,
                    status="active",
                    category="Crypto",
                    event_title="Bitcoin milestone markets",
                    event_slug="bitcoin-100k-2026",
                    image="https://example.com/bitcoin.png",
                    featured=True,
                ),
                ResolvedMarketRecord(
                    polymarket_id="bitcoin-120k-2026",
                    title="Will Bitcoin hit $120k in 2026?",
                    url="https://polymarket.com/event/bitcoin-120k-2026",
                    rules_text="Resolves YES if Bitcoin trades above $120k in 2026.",
                    description="Crypto market",
                    yes_bid=0.21,
                    yes_ask=0.23,
                    no_bid=0.77,
                    no_ask=0.79,
                    liquidity=75000,
                    volume_24h=12000,
                    spread=0.02,
                    expiry_at=None,
                    status="active",
                ),
            ]

    app.dependency_overrides[get_polymarket_client] = lambda: StubPolymarketClient()

    response = client.get("/api/markets/discover?view=popular&limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["has_more"] is True
    assert payload["items"][0]["polymarket_id"] == "bitcoin-100k-2026"
    assert payload["items"][0]["category"] == "Crypto"
    assert payload["items"][0]["featured"] is True
    assert payload["items"][0]["yes_ask"] == 0.43
    assert payload["items"][0]["research_edge_signal"] == {
        "status": "analysis_needed",
        "side": None,
        "win_probability": None,
        "conservative_probability": None,
        "live_price": None,
        "edge_after_buffer": None,
        "confidence": None,
        "analysis_id": None,
        "analyzed_at": None,
        "reason": "Run the research analysis to check whether the market price offers verified edge.",
    }


def test_public_market_discovery_surfaces_verified_research_edge_signal(
    client,
    session_factory: sessionmaker[Session],
):
    now = datetime.now(UTC)
    with session_factory() as session:
        market = Market(
            polymarket_id="filing-by-friday",
            title="Will the filing arrive by Friday?",
            yes_bid=0.41,
            yes_ask=0.43,
            no_bid=0.57,
            no_ask=0.59,
            status="active",
        )
        session.add(market)
        session.flush()
        request = AnalysisRequest(
            mode=ModeEnum.MANUAL,
            input_type=InputTypeEnum.MARKET_ID,
            input_text=market.polymarket_id,
            input_payload={},
            progress_json=initial_progress_payload(now),
            market_id=market.id,
            status=RequestStatusEnum.COMPLETE,
            current_stage="complete",
            started_at=now,
            completed_at=now,
        )
        session.add(request)
        session.flush()
        rule_parse = RuleParse(
            analysis_request_id=request.id,
            market_id=market.id,
            question_text=market.title,
            event="A filing arrives by Friday",
            entity_names=["Issuer"],
            action="file",
            claim_family=ClaimFamilyEnum.OFFICIAL_EVENT,
            yes_condition="YES if the filing arrives by Friday.",
            no_condition="NO otherwise.",
            deadline_text="Friday",
            directional_scoring_policy={},
            fallback_sources=[],
            official_domains=["sec.gov"],
            ambiguity_flags=[],
            clarity_score=0.9,
            resolution_risk=0.1,
            suitable_for_auto=True,
            template_detected=TemplateKey.OFFICIAL_EVENT,
            created_at=now,
        )
        session.add(rule_parse)
        session.flush()
        run = AnalysisRun(
            request_id=request.id,
            market_id=market.id,
            rule_parse_id=rule_parse.id,
            template_selected=TemplateKey.OFFICIAL_EVENT,
            market_mid_prob=0.42,
            yes_exec_price=0.43,
            no_exec_price=0.59,
            priced_in_risk_label=PricedInRiskLabelEnum.LOW,
            numeric_estimate_available=True,
            p_hat=0.68,
            p_low=0.60,
            p_high=0.74,
            confidence_label=ConfidenceLabelEnum.MEDIUM,
            recommendation_label=RecommendationLabelEnum.LEAN_YES,
            created_at=now,
        )
        session.add(run)
        session.flush()
        session.add(
            Recommendation(
                analysis_run_id=run.id,
                recommendation_label=RecommendationLabelEnum.LEAN_YES,
                confidence_label=ConfidenceLabelEnum.MEDIUM,
                edge_yes=0.15,
                edge_no=-0.35,
                rationale_json={"friction_buffer": 0.02},
                created_at=now,
            )
        )
        session.commit()
        analysis_id = request.id

    class StubPolymarketClient:
        def discover_markets(self, *, query=None, view="popular", limit=25, offset=0):
            return [
                ResolvedMarketRecord(
                    polymarket_id="filing-by-friday",
                    title="Will the filing arrive by Friday?",
                    url="https://polymarket.com/event/filing-by-friday",
                    rules_text="Resolves YES if the filing arrives by Friday.",
                    description=None,
                    yes_bid=0.41,
                    yes_ask=0.43,
                    no_bid=0.57,
                    no_ask=0.59,
                    liquidity=25000,
                    volume_24h=5000,
                    spread=0.02,
                    expiry_at=None,
                    status="active",
                )
            ]

    app.dependency_overrides[get_polymarket_client] = lambda: StubPolymarketClient()
    response = client.get("/api/markets/discover")

    assert response.status_code == 200
    signal = response.json()["items"][0]["research_edge_signal"]
    assert signal["status"] == "favorable"
    assert signal["side"] == "yes"
    assert signal["win_probability"] == 0.68
    assert signal["conservative_probability"] == 0.60
    assert signal["live_price"] == 0.43
    assert signal["edge_after_buffer"] == 0.15
    assert signal["analysis_id"] == analysis_id

    with session_factory() as session:
        stored_run = session.get(AnalysisRun, run.id)
        assert stored_run is not None
        stored_run.created_at = now - timedelta(days=2)
        session.commit()

    stale_response = client.get("/api/markets/discover")
    stale_signal = stale_response.json()["items"][0]["research_edge_signal"]
    assert stale_signal["status"] == "no_favorable_setup"
    assert stale_signal["reason"] == (
        "The latest research is more than 24 hours old. Refresh it before acting."
    )


def test_public_market_detail_falls_back_to_local_cache(
    client,
    session_factory: sessionmaker[Session],
):
    class StubPolymarketClient:
        def get_market_by_id(self, market_id: str):
            assert market_id == "fed-cut-june-2026"
            return None

    with session_factory() as session:
        session.add(
            Market(
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
        )
        session.commit()

    app.dependency_overrides[get_polymarket_client] = lambda: StubPolymarketClient()

    response = client.get("/api/markets/remote/fed-cut-june-2026")

    assert response.status_code == 200
    payload = response.json()
    assert payload["polymarket_id"] == "fed-cut-june-2026"
    assert payload["title"] == "Will the Fed cut by June 2026?"


def test_review_accepts_completed_run(client):
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


def test_review_rejects_non_complete_analysis(
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
        session.refresh(rule_parse)

        run = AnalysisRun(
            request_id=request.id,
            market_id=None,
            rule_parse_id=rule_parse.id,
            template_selected=TemplateKey.OFFICIAL_EVENT,
            market_mid_prob=0.51,
            yes_exec_price=None,
            no_exec_price=None,
            priced_in_risk_label=PricedInRiskLabelEnum.MEDIUM,
            numeric_estimate_available=False,
            numeric_estimate_reason="Scoring still in progress.",
            qualitative_label=None,
            p_hat=None,
            p_low=None,
            p_high=None,
            confidence_label=ConfidenceLabelEnum.LOW,
            recommendation_label=RecommendationLabelEnum.ANALYSIS_ONLY,
            created_at=now,
        )
        session.add(run)
        session.commit()
        analysis_id = request.id

    review_response = client.post(
        f"/api/analyses/{analysis_id}/review",
        json={"decision": "watch", "note": "Waiting for completion."},
    )

    assert review_response.status_code == 409
    assert review_response.json()["detail"] == "Analysis must be complete before it can be reviewed."


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


def test_rerun_rejects_active_request(
    client,
    session_factory: sessionmaker[Session],
):
    now = datetime.now(UTC)
    with session_factory() as session:
        request = AnalysisRequest(
            mode=ModeEnum.MANUAL,
            input_type=InputTypeEnum.CUSTOM_CLAIM,
            input_text="Will an approval land by Friday?",
            input_payload={},
            progress_json=initial_progress_payload(now),
            status=RequestStatusEnum.RUNNING,
            current_stage="retrieval",
            started_at=now,
        )
        session.add(request)
        session.commit()
        analysis_id = request.id

    rerun_response = client.post(f"/api/analyses/{analysis_id}/rerun")

    assert rerun_response.status_code == 409
    assert rerun_response.json()["detail"] == "Analysis is already queued or running."


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
    audit_status = next(
        item for item in payload["presentation"]["artifact_statuses"] if item["key"] == "audit"
    )
    assert audit_status["status"] == "pending"
    assert audit_status["available"] is False
    assert "scored factors" in audit_status["note"]
    assert "sources" not in payload
    assert "documents" not in payload


def test_queued_analysis_detail_hides_stale_previous_attempt_artifacts(
    client,
    session_factory: sessionmaker[Session],
):
    now = datetime.now(UTC)
    earlier = now - timedelta(seconds=1)
    with session_factory() as session:
        request = AnalysisRequest(
            mode=ModeEnum.MANUAL,
            input_type=InputTypeEnum.CUSTOM_CLAIM,
            input_text="Will an approval land by Friday?",
            input_payload={},
            progress_json=initial_progress_payload(now),
            status=RequestStatusEnum.QUEUED,
            current_stage="queued",
        )
        session.add(request)
        session.commit()
        session.refresh(request)

        rule_parse = RuleParse(
            analysis_request_id=request.id,
            question_text="Will an approval land by Friday?",
            event="Approval lands by Friday",
            entity_names=["Issuer"],
            action="approve",
            claim_family=ClaimFamilyEnum.OFFICIAL_EVENT,
            yes_condition="YES if approval lands by Friday.",
            no_condition="NO if approval does not land by Friday.",
            deadline_text="Friday",
            resolution_definition="Resolves YES if approval lands by Friday.",
            directional_scoring_policy={},
            official_domains=["sec.gov"],
            fallback_sources=[],
            ambiguity_flags=[],
            clarity_score=0.86,
            resolution_risk=0.14,
            suitable_for_auto=True,
            template_detected=TemplateKey.OFFICIAL_EVENT,
            created_at=earlier,
        )
        session.add(rule_parse)
        session.commit()
        session.refresh(rule_parse)

        run = AnalysisRun(
            request_id=request.id,
            market_id=None,
            rule_parse_id=rule_parse.id,
            template_selected=TemplateKey.OFFICIAL_EVENT,
            market_mid_prob=0.61,
            yes_exec_price=None,
            no_exec_price=None,
            priced_in_risk_label=PricedInRiskLabelEnum.MEDIUM,
            numeric_estimate_available=True,
            numeric_estimate_reason=None,
            qualitative_label=None,
            p_hat=0.61,
            p_low=0.51,
            p_high=0.71,
            confidence_label=ConfidenceLabelEnum.MEDIUM,
            recommendation_label=RecommendationLabelEnum.ANALYSIS_ONLY,
            final_summary="Old run summary.",
            created_at=earlier,
        )
        session.add(run)
        session.commit()
        analysis_id = request.id

    detail_response = client.get(f"/api/analyses/{analysis_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()

    assert detail_payload["request"]["status"] == "queued"
    assert detail_payload["latest_rule_parse"] is None
    assert detail_payload["latest_run"] is None
    assert detail_payload["recommendation"] is None
    assert detail_payload["audit"] is None
    assert detail_payload["sources"] == []
    assert detail_payload["documents"] == []
    assert detail_payload["passages"] == []
    assert detail_payload["fact_claims"] == []
    assert detail_payload["factors"] == []


def test_completed_detail_ignores_newer_incomplete_run_shell(
    client,
    session_factory: sessionmaker[Session],
):
    now = datetime.now(UTC)
    with session_factory() as session:
        request = AnalysisRequest(
            mode=ModeEnum.MANUAL,
            input_type=InputTypeEnum.CUSTOM_CLAIM,
            input_text="Will Jose Mourinho be appointed as manager of Real Madrid?",
            input_payload={},
            progress_json=initial_progress_payload(now),
            status=RequestStatusEnum.COMPLETE,
            current_stage="complete",
            completed_at=now,
        )
        mark_stage_complete(request, "complete", "Analysis complete.", now=now)
        session.add(request)
        session.commit()
        session.refresh(request)

        rule_parse = RuleParse(
            analysis_request_id=request.id,
            question_text=request.input_text,
            event=request.input_text,
            entity_names=["Jose Mourinho", "Real Madrid"],
            action="appointed",
            claim_family=ClaimFamilyEnum.GENERIC_MANUAL,
            yes_condition="YES if Mourinho is appointed.",
            no_condition="NO if Mourinho is not appointed.",
            deadline_text=None,
            resolution_definition="Resolves on appointment.",
            directional_scoring_policy={},
            official_domains=[],
            fallback_sources=[],
            ambiguity_flags=[],
            clarity_score=0.8,
            resolution_risk=0.2,
            suitable_for_auto=False,
            template_detected=TemplateKey.GENERIC_MANUAL,
            created_at=now,
        )
        session.add(rule_parse)
        session.commit()
        session.refresh(rule_parse)

        completed_run = AnalysisRun(
            request_id=request.id,
            market_id=None,
            rule_parse_id=rule_parse.id,
            template_selected=TemplateKey.GENERIC_MANUAL,
            market_mid_prob=0.865,
            yes_exec_price=0.89,
            no_exec_price=0.16,
            priced_in_risk_label=PricedInRiskLabelEnum.LOW,
            numeric_estimate_available=True,
            numeric_estimate_reason=None,
            qualitative_label=None,
            p_hat=0.889,
            p_low=0.48,
            p_high=0.99,
            confidence_label=ConfidenceLabelEnum.LOW,
            recommendation_label=RecommendationLabelEnum.NEEDS_MORE_RESEARCH,
            final_summary="Completed run summary.",
            created_at=now,
        )
        newer_shell = AnalysisRun(
            request_id=request.id,
            market_id=None,
            rule_parse_id=rule_parse.id,
            template_selected=TemplateKey.GENERIC_MANUAL,
            market_mid_prob=0.865,
            yes_exec_price=0.89,
            no_exec_price=0.16,
            priced_in_risk_label=PricedInRiskLabelEnum.MEDIUM,
            numeric_estimate_available=False,
            numeric_estimate_reason="Scoring has not finished yet.",
            qualitative_label=None,
            p_hat=None,
            p_low=None,
            p_high=None,
            confidence_label=ConfidenceLabelEnum.LOW,
            recommendation_label=RecommendationLabelEnum.NEEDS_MORE_RESEARCH,
            created_at=now + timedelta(seconds=30),
        )
        session.add_all([completed_run, newer_shell])
        session.commit()
        analysis_id = request.id

    detail_response = client.get(f"/api/analyses/{analysis_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()

    assert detail_payload["latest_run"]["p_hat"] == 0.889
    assert detail_payload["latest_run"]["final_summary"] == "Completed run summary."
    assert "Completed run summary" in detail_payload["display_summary"]


def test_detail_uses_numeric_read_when_stored_brief_conflicts(
    client,
    session_factory: sessionmaker[Session],
):
    now = datetime.now(UTC)
    with session_factory() as session:
        market = Market(
            polymarket_id="resolved-yes-market",
            title="Resolved YES market?",
            url="https://polymarket.com/event/resolved-yes-market",
            rules_text="Sample rules",
            description="Sample market",
            yes_bid=0.99,
            yes_ask=1.0,
            no_bid=0.0,
            no_ask=0.01,
            liquidity=1000,
            volume_24h=100,
            spread=0.01,
            status="closed",
        )
        session.add(market)
        session.commit()
        session.refresh(market)

        request = AnalysisRequest(
            mode=ModeEnum.MANUAL,
            input_type=InputTypeEnum.MARKET_ID,
            input_text=market.polymarket_id,
            input_payload={},
            progress_json=initial_progress_payload(now),
            market_id=market.id,
            status=RequestStatusEnum.COMPLETE,
            current_stage="complete",
            started_at=now,
            completed_at=now,
        )
        mark_stage_complete(request, "complete", "Analysis complete.", now=now)
        session.add(request)
        session.commit()
        session.refresh(request)

        rule_parse = RuleParse(
            analysis_request_id=request.id,
            market_id=market.id,
            question_text=market.title,
            event=market.title,
            entity_names=["Example"],
            action="resolve yes",
            claim_family=ClaimFamilyEnum.OFFICIAL_EVENT,
            yes_condition="YES if the event happens.",
            no_condition="NO if the event does not happen.",
            deadline_text=None,
            resolution_definition="Resolves YES if the event happens.",
            directional_scoring_policy={},
            official_domains=[],
            fallback_sources=[],
            ambiguity_flags=[],
            clarity_score=0.8,
            resolution_risk=0.2,
            suitable_for_auto=False,
            template_detected=TemplateKey.OFFICIAL_EVENT,
            created_at=now,
        )
        session.add(rule_parse)
        session.commit()
        session.refresh(rule_parse)

        run = AnalysisRun(
            request_id=request.id,
            market_id=market.id,
            rule_parse_id=rule_parse.id,
            template_selected=TemplateKey.OFFICIAL_EVENT,
            market_mid_prob=0.995,
            yes_exec_price=1.0,
            no_exec_price=0.01,
            priced_in_risk_label=PricedInRiskLabelEnum.LOW,
            numeric_estimate_available=True,
            numeric_estimate_reason=None,
            qualitative_label=QualitativeLabelEnum.LEANS_NO,
            p_hat=0.9994,
            p_low=0.85,
            p_high=0.99,
            confidence_label=ConfidenceLabelEnum.MEDIUM,
            recommendation_label=RecommendationLabelEnum.NO_EDGE,
            final_summary="The current decision read is NO, despite p_hat 0.9994.",
            created_at=now,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        session.add(
            Recommendation(
                analysis_run_id=run.id,
                recommendation_label=RecommendationLabelEnum.NO_EDGE,
                confidence_label=ConfidenceLabelEnum.MEDIUM,
                edge_yes=-0.02,
                edge_no=-0.02,
                rationale_json={},
                created_at=now,
            )
        )
        session.commit()
        analysis_id = request.id

    detail_response = client.get(f"/api/analyses/{analysis_id}")

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["presentation"]["headline"] == "Resolved YES market?"
    assert "YES is more likely" in detail_payload["display_summary"]
    assert "decision read is NO" not in detail_payload["presentation"]["brief_sections"]["what_it_means"]
    assert "YES is more likely" in detail_payload["presentation"]["brief_sections"]["what_it_means"]


def test_live_social_intelligence_groups_trusted_timeline_and_supporting_social(
    client,
    session_factory: sessionmaker[Session],
):
    class StubXAIClient:
        is_configured = True

        def generate_structured_with_tools(self, **_kwargs):
            now = datetime.now(UTC)
            return SocialIntelDraft(
                consensus_label=ConsensusLabelEnum.BULLISH,
                consensus_strength=ConsensusStrengthEnum.STRONG,
                narrative_phase=NarrativePhaseEnum.EMERGING,
                summary="Trusted macro accounts lean toward a June cut, while broader X has turned constructive but not euphoric.",
                key_themes=["fed path", "softening labor data"],
                trusted_accounts_count=3,
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
                    TrustedSocialPostDraft(
                        handle="PartisanPundit",
                        display_name="Partisan Pundit",
                        post_url="https://x.com/PartisanPundit/status/789",
                        post_timestamp=now,
                        account_category="Conservative media personality",
                        trust_tier=SourceTierEnum.HIGH_TRUST_SOCIAL,
                        trust_confidence=0.94,
                        relevance_reason="Discusses the same policy question.",
                        trust_reason="Influential partisan voice on politics.",
                        post_summary="He says the Fed will obviously cut rates.",
                        possible_facts=["The Fed will obviously cut rates."],
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

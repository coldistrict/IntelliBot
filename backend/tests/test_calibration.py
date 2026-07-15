from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes.calibration import get_polymarket_client
from app.clients.polymarket_client import PolymarketClient, ResolvedMarketRecord
from app.main import app
from app.models import AnalysisRequest, AnalysisRun, JournalEvent, Market, PublishedForecast, RuleParse, Snapshot
from app.models.enums import (
    AttemptReasonEnum,
    ClaimFamilyEnum,
    ConfidenceLabelEnum,
    InputTypeEnum,
    JournalEventTypeEnum,
    ModeEnum,
    PricedInRiskLabelEnum,
    RecommendationLabelEnum,
    RequestStatusEnum,
    RunQualityEnum,
    SnapshotTypeEnum,
    TemplateKey,
)
from app.services.analysis_progress import initial_progress_payload


def _seed_market(
    session: Session,
    *,
    polymarket_id: str,
    title: str,
    resolved_outcome: str | None = None,
) -> Market:
    now = datetime.now(UTC)
    market = Market(
        polymarket_id=polymarket_id,
        title=title,
        url=f"https://polymarket.com/event/{polymarket_id}",
        yes_bid=0.55,
        yes_ask=0.58,
        no_bid=0.42,
        no_ask=0.45,
        status="active",
        resolved_outcome=resolved_outcome,
        resolved_at=now if resolved_outcome else None,
        created_at=now,
        updated_at=now,
    )
    session.add(market)
    session.commit()
    session.refresh(market)
    return market


def _seed_completed_run(
    session: Session,
    *,
    market: Market | None,
    p_hat: float | None,
    market_mid_prob: float | None = None,
    recommendation_label: RecommendationLabelEnum = RecommendationLabelEnum.ANALYSIS_ONLY,
    confidence_label: ConfidenceLabelEnum = ConfidenceLabelEnum.MEDIUM,
    yes_exec_price: float | None = None,
    no_exec_price: float | None = None,
    template: TemplateKey = TemplateKey.OFFICIAL_EVENT,
) -> AnalysisRun:
    now = datetime.now(UTC)
    request = AnalysisRequest(
        mode=ModeEnum.MANUAL,
        input_type=InputTypeEnum.CUSTOM_CLAIM,
        input_text="Will the event happen?",
        input_payload={},
        progress_json=initial_progress_payload(now),
        status=RequestStatusEnum.COMPLETE,
        current_stage="complete",
        market_id=market.id if market else None,
        started_at=now,
        completed_at=now,
    )
    session.add(request)
    session.commit()
    session.refresh(request)

    rule_parse = RuleParse(
        analysis_request_id=request.id,
        market_id=market.id if market else None,
        question_text="Will the event happen?",
        event="The event happens",
        entity_names=["Entity"],
        action="happen",
        claim_family=ClaimFamilyEnum.OFFICIAL_EVENT,
        yes_condition="YES if the event happens.",
        no_condition="NO if it does not.",
        directional_scoring_policy={},
        official_domains=[],
        fallback_sources=[],
        ambiguity_flags=[],
        clarity_score=0.9,
        resolution_risk=0.1,
        suitable_for_auto=True,
        template_detected=template,
        created_at=now,
    )
    session.add(rule_parse)
    session.commit()
    session.refresh(rule_parse)

    run = AnalysisRun(
        request_id=request.id,
        market_id=market.id if market else None,
        rule_parse_id=rule_parse.id,
        template_selected=template,
        market_mid_prob=market_mid_prob,
        yes_exec_price=yes_exec_price,
        no_exec_price=no_exec_price,
        priced_in_risk_label=PricedInRiskLabelEnum.LOW,
        numeric_estimate_available=p_hat is not None,
        p_hat=p_hat,
        p_low=p_hat - 0.1 if p_hat is not None else None,
        p_high=p_hat + 0.1 if p_hat is not None else None,
        confidence_label=confidence_label,
        recommendation_label=recommendation_label,
        created_at=now,
    )
    session.add(run)
    session.flush()
    session.add(
        PublishedForecast(
            analysis_run_id=run.id,
            request_id=request.id,
            market_id=market.id if market else None,
            published_at=now,
            model_version="test-model",
            prompt_versions_json={},
            market_snapshot_json={},
            quality_state=RunQualityEnum.CLEAN,
            attempt_reason=AttemptReasonEnum.ORIGINAL,
            is_repeat=False,
            p_hat=p_hat,
            market_mid_prob=market_mid_prob,
        )
    )
    session.commit()
    session.refresh(run)
    return run


class StubPolymarketClient(PolymarketClient):
    def __init__(self, records: dict[str, ResolvedMarketRecord]) -> None:
        super().__init__(enabled=False)
        self.records = records
        self.requested_ids: list[str] = []

    def get_market_by_id(self, market_id: str) -> ResolvedMarketRecord | None:
        self.requested_ids.append(market_id)
        return self.records.get(market_id)


def _resolved_record(polymarket_id: str, *, outcome: str) -> ResolvedMarketRecord:
    yes_price = 1.0 if outcome == "yes" else 0.0
    return ResolvedMarketRecord(
        polymarket_id=polymarket_id,
        title="Resolved market",
        url=None,
        rules_text=None,
        description=None,
        yes_bid=yes_price,
        yes_ask=yes_price,
        no_bid=1 - yes_price,
        no_ask=1 - yes_price,
        liquidity=None,
        volume_24h=None,
        spread=None,
        expiry_at=None,
        status="closed",
        closed=True,
        resolved_outcome=outcome,
        closed_time=datetime(2026, 6, 1, tzinfo=UTC),
    )


def test_refresh_outcomes_marks_resolved_markets(client, session_factory: sessionmaker[Session]):
    with session_factory() as session:
        market = _seed_market(session, polymarket_id="111", title="Resolvable market")
        _seed_completed_run(session, market=market, p_hat=0.7)
        market_id = market.id

    stub = StubPolymarketClient({"111": _resolved_record("111", outcome="yes")})
    app.dependency_overrides[get_polymarket_client] = lambda: stub

    response = client.post("/api/calibration/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["markets_checked"] == 1
    assert payload["newly_resolved"] == 1
    assert payload["still_open"] == 0

    with session_factory() as session:
        refreshed = session.get(Market, market_id)
        assert refreshed is not None
        assert refreshed.resolved_outcome == "yes"
        assert refreshed.resolved_at is not None
        assert refreshed.status == "closed"
        snapshots = session.scalars(
            select(Snapshot).where(Snapshot.market_id == market_id)
        ).all()
        resolved_snapshots = [
            snapshot for snapshot in snapshots if snapshot.snapshot_type == SnapshotTypeEnum.RESOLVED
        ]
        assert len(resolved_snapshots) == 1
        assert resolved_snapshots[0].outcome == "yes"

    # A second refresh should find nothing left to check.
    second = client.post("/api/calibration/refresh")
    assert second.status_code == 200
    assert second.json()["markets_checked"] == 0


def test_refresh_outcomes_keeps_open_markets_pending(
    client, session_factory: sessionmaker[Session]
):
    with session_factory() as session:
        market = _seed_market(session, polymarket_id="222", title="Open market")
        _seed_completed_run(session, market=market, p_hat=0.5)
        market_id = market.id

    open_record = _resolved_record("222", outcome="yes")
    open_record.closed = False
    open_record.resolved_outcome = None
    stub = StubPolymarketClient({"222": open_record})
    app.dependency_overrides[get_polymarket_client] = lambda: stub

    response = client.post("/api/calibration/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["markets_checked"] == 1
    assert payload["newly_resolved"] == 0
    assert payload["still_open"] == 1

    with session_factory() as session:
        refreshed = session.get(Market, market_id)
        assert refreshed is not None
        assert refreshed.resolved_outcome is None


def test_scoreboard_math(client, session_factory: sessionmaker[Session]):
    with session_factory() as session:
        won_market = _seed_market(
            session, polymarket_id="301", title="Won market", resolved_outcome="yes"
        )
        lost_market = _seed_market(
            session, polymarket_id="302", title="Lost market", resolved_outcome="no"
        )
        pending_market = _seed_market(session, polymarket_id="303", title="Pending market")

        # Correct lean_yes trade: bought YES at 0.50, market resolved yes -> +100.
        _seed_completed_run(
            session,
            market=won_market,
            p_hat=0.8,
            market_mid_prob=0.5,
            recommendation_label=RecommendationLabelEnum.LEAN_YES,
            yes_exec_price=0.5,
            template=TemplateKey.OFFICIAL_EVENT,
        )
        # Wrong lean_yes trade: bought YES at 0.4, market resolved no -> -100.
        _seed_completed_run(
            session,
            market=lost_market,
            p_hat=0.6,
            market_mid_prob=0.45,
            recommendation_label=RecommendationLabelEnum.LEAN_YES,
            yes_exec_price=0.4,
            template=TemplateKey.LEGAL_CASE,
        )
        # Pending market run should not affect resolved stats.
        _seed_completed_run(session, market=pending_market, p_hat=0.55)
        # Unlinked run is counted separately.
        _seed_completed_run(session, market=None, p_hat=None)

    response = client.get("/api/calibration/scoreboard")

    assert response.status_code == 200
    payload = response.json()
    summary = payload["summary"]

    assert summary["resolved_runs"] == 2
    assert summary["pending_runs"] == 1
    assert summary["unlinked_runs"] == 1
    assert summary["scored_runs"] == 2

    # Brier: (0.8-1)^2 = 0.04 and (0.6-0)^2 = 0.36 -> avg 0.2
    assert summary["avg_model_brier"] == 0.2
    # Market brier: (0.5-1)^2 = 0.25 and (0.45-0)^2 = 0.2025 -> avg 0.2263 (rounded)
    assert summary["avg_market_brier"] == 0.2263
    assert summary["head_to_head_runs"] == 2
    assert summary["model_beats_market_rate"] == 0.5

    # Directions: 0.8 -> yes (hit), 0.6 -> yes (miss) -> 0.5 hit rate.
    assert summary["direction_calls"] == 2
    assert summary["direction_hit_rate"] == 0.5

    # Trades: +100 (yes at 0.5 wins) and -100 (yes at 0.4 loses) -> 0 total.
    assert summary["trade_count"] == 2
    assert summary["trade_wins"] == 1
    assert summary["total_pnl"] == 0.0
    assert summary["roi_per_trade"] == 0.0

    resolved_rows = payload["resolved"]
    assert len(resolved_rows) == 2
    pnl_by_title = {row["title"]: row["trade_pnl"] for row in resolved_rows}
    assert pnl_by_title["Won market"] == 100.0
    assert pnl_by_title["Lost market"] == -100.0

    template_keys = {item["key"]: item for item in payload["template_slices"]}
    assert template_keys["official_event"]["total_pnl"] == 100.0
    assert template_keys["legal_case"]["total_pnl"] == -100.0

    buckets = {bucket["label"]: bucket for bucket in payload["buckets"]}
    assert buckets["60-80%"]["count"] == 1
    assert buckets["80-100%"]["count"] == 1

    pending_rows = payload["pending"]
    assert len(pending_rows) == 1
    assert pending_rows[0]["title"] == "Pending market"


def test_scoreboard_empty_state(client):
    response = client.get("/api/calibration/scoreboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["resolved_runs"] == 0
    assert payload["summary"]["avg_model_brier"] is None
    assert payload["summary"]["direction_hit_rate"] is None
    assert payload["resolved"] == []
    assert payload["pending"] == []


def test_scoreboard_preserves_tiny_nonzero_briers(client, session_factory: sessionmaker[Session]):
    with session_factory() as session:
        market = _seed_market(
            session,
            polymarket_id="tiny-brier",
            title="Tiny Brier market",
            resolved_outcome="yes",
        )
        _seed_completed_run(session, market=market, p_hat=0.9994, market_mid_prob=0.9995)

    response = client.get("/api/calibration/scoreboard")

    assert response.status_code == 200
    payload = response.json()
    row = payload["resolved"][0]
    assert 0 < row["model_brier"] < 0.001
    assert 0 < row["market_brier"] < 0.001
    assert 0 < payload["summary"]["avg_model_brier"] < 0.001


def test_scoreboard_separates_repeats_and_scores_decision_journal(
    client, session_factory: sessionmaker[Session]
):
    with session_factory() as session:
        market = _seed_market(
            session,
            polymarket_id="journal-market",
            title="Journal market",
            resolved_outcome="yes",
        )
        first = _seed_completed_run(session, market=market, p_hat=0.70, market_mid_prob=0.55)
        second = _seed_completed_run(session, market=market, p_hat=0.75, market_mid_prob=0.60)
        second.published_forecast.is_repeat = True
        session.add_all(
            [
                JournalEvent(
                    analysis_run_id=first.id,
                    event_type=JournalEventTypeEnum.BEFORE,
                    payload_json={"prior_probability": 0.35, "intended_action": "no_bet"},
                    created_at=datetime.now(UTC),
                ),
                JournalEvent(
                    analysis_run_id=first.id,
                    event_type=JournalEventTypeEnum.AFTER,
                    payload_json={"decision": "yes", "conviction": 4},
                    created_at=datetime.now(UTC),
                ),
            ]
        )
        session.commit()

    payload = client.get("/api/calibration/scoreboard").json()
    summary = payload["summary"]
    assert summary["published_forecasts"] == 2
    assert summary["distinct_markets"] == 1
    assert summary["repeated_forecasts"] == 1
    assert summary["user_before_runs"] == 1
    assert summary["avg_user_before_brier"] == 0.4225
    assert summary["user_after_runs"] == 1
    assert summary["avg_user_after_brier"] == 0.0
    assert sum(1 for row in payload["resolved"] if row["is_repeat"]) == 1

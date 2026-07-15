from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Event

import httpx

from app.clients.fred_client import FredClient
from app.clients.polymarket_client import PolymarketClient, ResolvedMarketRecord
from app.models import Market, MarketPricePoint, Source
from app.models.enums import SourceKindEnum, SourceTierEnum
from app.services.analysis_pipeline import AnalysisProcessor, SourceContext
from app.services.deadline_policy import deadline_uncertainty_adjustment
from app.services.market_matching import assess_market_match
from app.services import outcome_refresh_scheduler
from app.services.outcome_refresh_scheduler import OutcomeRefreshCoordinator
from app.services.outcome_tracker import OutcomeRefreshSummary


def _record(title: str, *, description: str = "", rules: str = "") -> ResolvedMarketRecord:
    return ResolvedMarketRecord(
        polymarket_id=title.lower().replace(" ", "-"),
        title=title,
        url=None,
        rules_text=rules,
        description=description,
        yes_bid=0.5,
        yes_ask=0.51,
        no_bid=0.49,
        no_ask=0.5,
        liquidity=1_000,
        volume_24h=100,
        spread=0.01,
        expiry_at=None,
        status="active",
    )


def test_matcher_rejects_fed_colombia_identity_collision():
    assessment = assess_market_match(
        "Will the US Federal Reserve decrease interest rates at its next FOMC meeting?",
        _record(
            "Will Banco de la República cut Colombia interest rates at its next meeting?",
            description="Colombia central bank policy decision.",
        ),
    )

    assert assessment.auto_link is False
    assert "jurisdiction_mismatch" in assessment.reason_codes


def test_matcher_auto_links_exact_proposition_identity():
    assessment = assess_market_match(
        "Will the Federal Reserve cut interest rates by 25 basis points in 2026?",
        _record(
            "Will the Federal Reserve cut interest rates by 25 basis points in 2026?",
            rules="Resolves YES if the FOMC lowers the target range by 25 bps in 2026.",
        ),
    )

    assert assessment.auto_link is True
    assert assessment.confidence == "high"
    assert assessment.reason_codes


def test_contamination_and_official_source_classification():
    assert AnalysisProcessor._contamination_reason("Access denied. Cloudflare Ray ID 123") == "access_denied"
    assert AnalysisProcessor._contamination_reason("Enable JavaScript and cookies to continue") == "bot_block"
    assert PolymarketClient._coerce_json_list('["yes-token", "no-token"]') == ["yes-token", "no-token"]
    assert (
        __import__("app.clients.tavily_client", fromlist=["TavilyClient"])
        .TavilyClient._classify_source_tier("https://www.banrep.gov.co/policy")
        == SourceTierEnum.OFFICIAL_PRIMARY
    )


def test_deadline_policy_widens_event_window_by_at_least_three_points():
    now = datetime(2026, 7, 12, tzinfo=UTC)
    near = deadline_uncertainty_adjustment(now + timedelta(days=3), now=now)
    far = deadline_uncertainty_adjustment(now + timedelta(days=180), now=now)

    assert near is not None and far is not None
    assert near["amount"] - far["amount"] >= 0.03


def test_price_history_attributes_only_moves_after_evidence():
    now = datetime(2026, 7, 12, 12, tzinfo=UTC)
    market = Market(polymarket_id="history", title="History", created_at=now, updated_at=now)
    market.price_points = [
        MarketPricePoint(token_id="yes", outcome="yes", price=0.40, observed_at=now - timedelta(hours=2), fetched_at=now),
        MarketPricePoint(token_id="yes", outcome="yes", price=0.51, observed_at=now + timedelta(hours=1), fetched_at=now),
    ]
    source = Source(
        id=1,
        analysis_run_id=1,
        source_kind=SourceKindEnum.OFFICIAL,
        source_tier=SourceTierEnum.OFFICIAL_PRIMARY,
        published_at=now - timedelta(hours=1),
        fetched_at=now,
        content_hash="source",
        excerpt="Catalyst",
        metadata_json={},
        created_at=now,
    )

    signal = AnalysisProcessor._price_history_signal(
        market, [SourceContext(source=source, possible_facts=[])]
    )
    assert signal is not None
    assert signal["risk"] == "high"
    assert signal["attributed"] is True
    assert signal["movement"] == 0.11

    source.published_at = now + timedelta(hours=2)
    assert AnalysisProcessor._price_history_signal(
        market, [SourceContext(source=source, possible_facts=[])]
    ) is None


def test_fred_adapter_persists_first_party_provenance(monkeypatch):
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"observations": [{"date": "2026-07-01", "value": "4.1"}]}

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(httpx, "Client", Client)
    client = FredClient(enabled=True)
    client.api_key = "test"
    sources = client.observations_for_claim("Will inflation fall this month?")

    assert len(sources) == 1
    assert sources[0].source_tier == SourceTierEnum.OFFICIAL_PRIMARY
    assert sources[0].published_at is not None
    assert sources[0].metadata_json["series_id"] == "CPIAUCSL"


def test_concurrent_outcome_refreshes_share_one_upstream_sweep(monkeypatch):
    entered = Event()
    release = Event()
    calls = 0

    def fake_refresh(_session, *, client):
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(timeout=2)
        return OutcomeRefreshSummary(
            markets_checked=2,
            newly_resolved=1,
            still_open=1,
            lookup_failures=0,
        )

    monkeypatch.setattr(
        "app.services.outcome_refresh_scheduler.refresh_market_outcomes",
        fake_refresh,
    )
    coordinator = OutcomeRefreshCoordinator(cooldown_seconds=30)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(coordinator.refresh, object(), client=object(), force=True)
        assert entered.wait(timeout=2)
        second = pool.submit(coordinator.refresh, object(), client=object(), force=True)
        second_result = second.result(timeout=2)
        release.set()
        first_result = first.result(timeout=2)

    assert calls == 1
    assert coordinator.sweep_count == 1
    assert first_result == OutcomeRefreshSummary(
        markets_checked=2,
        newly_resolved=1,
        still_open=1,
        lookup_failures=0,
    )
    assert second_result == OutcomeRefreshSummary(
        markets_checked=0,
        newly_resolved=0,
        still_open=0,
        lookup_failures=0,
    )


def test_coordinator_singleton_applies_updated_cooldown(monkeypatch):
    monkeypatch.setattr(outcome_refresh_scheduler, "_coordinator", None)

    first = outcome_refresh_scheduler.get_outcome_refresh_coordinator(cooldown_seconds=5)
    second = outcome_refresh_scheduler.get_outcome_refresh_coordinator(cooldown_seconds=45)

    assert second is first
    assert second.cooldown_seconds == 45


def test_startup_refresh_failure_schedules_fast_retry(monkeypatch):
    class FakeScheduler:
        def __init__(self, **_kwargs):
            self.jobs = {}
            self.running = False

        def add_job(self, func, *args, id, **kwargs):
            self.jobs[id] = (func, args, kwargs)

        def start(self):
            self.running = True

    @contextmanager
    def unavailable_session():
        raise RuntimeError("database unavailable")
        yield

    monkeypatch.setattr(outcome_refresh_scheduler, "BackgroundScheduler", FakeScheduler)
    scheduler = outcome_refresh_scheduler.start_outcome_scheduler(
        session_factory=unavailable_session,
        interval_minutes=60,
        cooldown_seconds=30,
        startup_retry_seconds=2,
    )

    startup_refresh = scheduler.jobs["outcome-refresh-startup"][0]
    startup_refresh()

    _, args, kwargs = scheduler.jobs["outcome-refresh-startup-retry"]
    assert args == ("date",)
    assert kwargs["replace_existing"] is True
    assert 1 <= (kwargs["run_date"] - datetime.now(UTC)).total_seconds() <= 2

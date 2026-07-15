from datetime import UTC, datetime, timedelta

from app.clients.polymarket_client import ResolvedMarketRecord
from app.models.analysis import AnalysisRun, Recommendation
from app.models.enums import (
    ConfidenceLabelEnum,
    PricedInRiskLabelEnum,
    RecommendationLabelEnum,
)
from app.services.market_signals import _signal_for_run, research_edge_signals_for_records


def _record(**overrides) -> ResolvedMarketRecord:
    base = dict(
        polymarket_id="mkt-1",
        title="Test market",
        url=None,
        rules_text=None,
        description=None,
        yes_bid=0.53,
        yes_ask=0.55,
        no_bid=0.43,
        no_ask=0.45,
        liquidity=1000.0,
        volume_24h=500.0,
        spread=0.02,
        expiry_at=None,
        status="active",
    )
    base.update(overrides)
    return ResolvedMarketRecord(**base)


def _run(**overrides) -> AnalysisRun:
    run = AnalysisRun(
        request_id=1,
        recommendation_label=overrides.pop(
            "recommendation_label", RecommendationLabelEnum.LEAN_YES
        ),
        confidence_label=overrides.pop("confidence_label", ConfidenceLabelEnum.HIGH),
        priced_in_risk_label=overrides.pop(
            "priced_in_risk_label", PricedInRiskLabelEnum.MEDIUM
        ),
        p_hat=overrides.pop("p_hat", 0.68),
        p_low=overrides.pop("p_low", 0.62),
        p_high=overrides.pop("p_high", 0.74),
        created_at=overrides.pop("created_at", datetime.now(UTC)),
    )
    if overrides.pop("with_recommendation", True):
        run.recommendation = Recommendation(
            recommendation_label=run.recommendation_label,
        )
    for key, value in overrides.items():
        setattr(run, key, value)
    return run


def test_favorable_yes_setup():
    signal = _signal_for_run(_run(), _record())

    assert signal.status == "favorable"
    assert signal.side == "yes"
    assert signal.conservative_probability == 0.62
    assert signal.live_price == 0.55
    # 0.62 - 0.55 - 0.02 friction buffer
    assert signal.edge_after_buffer == 0.05
    assert "YES has verified conservative edge" in signal.reason


def test_missing_recommendation_reports_unfinished_check():
    signal = _signal_for_run(_run(with_recommendation=False), _record())

    assert signal.status == "no_favorable_setup"
    assert signal.reason == "The latest analysis did not finish an executable edge check."


def test_non_executable_recommendation_reports_no_side():
    signal = _signal_for_run(
        _run(recommendation_label=RecommendationLabelEnum.NO_EDGE), _record()
    )

    assert signal.status == "no_favorable_setup"
    assert signal.reason == "The latest analysis does not recommend an executable side."


def test_inactive_market_reports_not_active():
    signal = _signal_for_run(_run(), _record(status="closed"))

    assert signal.status == "no_favorable_setup"
    assert signal.reason == "This market is not active, so there is no actionable setup."


def test_stale_analysis_reports_refresh_needed():
    signal = _signal_for_run(
        _run(created_at=datetime.now(UTC) - timedelta(hours=25)), _record()
    )

    assert signal.status == "no_favorable_setup"
    assert "more than 24 hours old" in signal.reason


def test_low_confidence_reports_confidence_gate():
    signal = _signal_for_run(_run(confidence_label=ConfidenceLabelEnum.LOW), _record())

    assert signal.status == "no_favorable_setup"
    assert signal.reason == "The latest research confidence is too low to verify price edge."


def test_high_priced_in_risk_reports_risk_gate():
    signal = _signal_for_run(
        _run(priced_in_risk_label=PricedInRiskLabelEnum.HIGH), _record()
    )

    assert signal.status == "no_favorable_setup"
    assert signal.reason == "The latest analysis flags high priced-in risk."


def test_conservative_probability_below_half_reports_no_high_chance_side():
    signal = _signal_for_run(_run(p_low=0.45), _record())

    assert signal.status == "no_favorable_setup"
    assert signal.reason == "No side has a conservative win chance above 50%."


def test_price_without_edge_reports_buffer_gate():
    signal = _signal_for_run(_run(p_low=0.56), _record(yes_ask=0.55))

    assert signal.status == "no_favorable_setup"
    assert signal.reason == "The current price no longer leaves positive edge after the 2% buffer."


def test_lean_no_uses_no_side_pricing():
    signal = _signal_for_run(
        _run(
            recommendation_label=RecommendationLabelEnum.LEAN_NO,
            p_hat=0.3,
            p_low=0.24,
            p_high=0.36,
        ),
        _record(no_ask=0.55),
    )

    assert signal.status == "favorable"
    assert signal.side == "no"
    # conservative = 1 - p_high = 0.64; edge = 0.64 - 0.55 - 0.02
    assert signal.conservative_probability == 0.64
    assert signal.edge_after_buffer == 0.07


def test_records_without_polymarket_ids_still_get_signal_entries(session_factory):
    record = _record(polymarket_id="")
    with session_factory() as session:
        signals = research_edge_signals_for_records(session, [record])

    assert signals[""].status == "analysis_needed"

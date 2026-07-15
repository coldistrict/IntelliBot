from datetime import UTC, datetime

from app.models import ExecutionEvent, FactClaim, Factor, RuleParse, Source
from app.models.enums import (
    ExecutionResultModeEnum,
    RunQualityEnum,
    SourceKindEnum,
    SourceTierEnum,
    StanceEnum,
    StrengthEnum,
)
from app.services.analysis_execution import derive_quality
from app.services.analysis_pipeline import AnalysisProcessor, SourceContext
from app.services.pipeline_models import BlindProbabilityDraft


class StubStructuredClient:
    is_configured = True

    def __init__(self, result: BlindProbabilityDraft | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[dict] = []

    def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


def _rule_parse() -> RuleParse:
    return RuleParse(
        question_text="Will the tariff take effect by September?",
        yes_condition="YES if the tariff is in force by Sep 30.",
        no_condition="NO otherwise.",
    )


def _evidence() -> tuple[list[SourceContext], list[FactClaim], list[Factor]]:
    source = Source(
        id=10,
        source_kind=SourceKindEnum.NEWS,
        source_tier=SourceTierEnum.OFFICIAL_PRIMARY,
    )
    fact = FactClaim(id=1, source_id=10, normalized_fact="The order was signed on July 1.")
    factor = Factor(
        fact_claim_id=1,
        stance=StanceEnum.YES,
        strength=StrengthEnum.STRONG,
        used_in_scoring=True,
    )
    return [SourceContext(source=source, possible_facts=[])], [fact], [factor]


def test_blind_estimate_prompt_is_market_free_and_returns_probability():
    processor = AnalysisProcessor(enable_remote_calls=False)
    stub = StubStructuredClient(result=BlindProbabilityDraft(p_yes=0.7, rationale="signed order"))
    processor.openai_client = stub
    source_contexts, facts, factors = _evidence()

    estimate = processor.blind_probability_estimate(
        object(), _rule_parse(), source_contexts, facts, factors
    )

    assert estimate == 0.7
    assert len(stub.calls) == 1
    prompt = stub.calls[0]["user_prompt"]
    assert "Never use market prices" in prompt
    assert "Will the tariff take effect by September?" in prompt
    assert "The order was signed on July 1." in prompt
    assert "source_tier=official_primary" in prompt
    assert stub.calls[0]["task_name"] == "blind_probability"


def test_blind_estimate_clamps_extreme_probabilities():
    processor = AnalysisProcessor(enable_remote_calls=False)
    processor.openai_client = StubStructuredClient(
        result=BlindProbabilityDraft(p_yes=1.0, rationale="certain")
    )
    source_contexts, facts, factors = _evidence()

    estimate = processor.blind_probability_estimate(
        object(), _rule_parse(), source_contexts, facts, factors
    )

    assert estimate == 0.999


def test_blind_estimate_failure_returns_none():
    processor = AnalysisProcessor(enable_remote_calls=False)
    processor.openai_client = StubStructuredClient(error=RuntimeError("provider down"))
    source_contexts, facts, factors = _evidence()

    estimate = processor.blind_probability_estimate(
        object(), _rule_parse(), source_contexts, facts, factors
    )

    assert estimate is None


def test_blind_estimate_skipped_without_configured_client():
    processor = AnalysisProcessor(enable_remote_calls=False)
    source_contexts, facts, factors = _evidence()

    estimate = processor.blind_probability_estimate(
        object(), _rule_parse(), source_contexts, facts, factors
    )

    assert estimate is None


def _event(task_name: str, result_mode: ExecutionResultModeEnum) -> ExecutionEvent:
    return ExecutionEvent(
        request_id=1,
        stage_key="probability_estimation",
        event_kind="model_call",
        task_name=task_name,
        result_mode=result_mode,
        cache_hit=False,
        attempt_count=1,
        latency_ms=1,
        prompt_tokens=0,
        completion_tokens=0,
        estimated_cost_usd=0.0,
        detail_json={},
        created_at=datetime.now(UTC),
    )


def test_failed_blind_probability_does_not_gate_run_quality():
    events = [
        _event("rule_parse", ExecutionResultModeEnum.MODEL),
        _event("blind_probability", ExecutionResultModeEnum.FAILED),
        _event("blind_probability", ExecutionResultModeEnum.DETERMINISTIC_FALLBACK),
    ]

    quality, reasons = derive_quality(events, has_directional_evidence=True)

    assert quality == RunQualityEnum.CLEAN
    assert reasons == []


def test_failed_core_task_still_gates_run_quality():
    events = [
        _event("rule_parse", ExecutionResultModeEnum.DETERMINISTIC_FALLBACK),
        _event("blind_probability", ExecutionResultModeEnum.MODEL),
    ]

    quality, reasons = derive_quality(events, has_directional_evidence=True)

    assert quality == RunQualityEnum.WARNING
    assert reasons == [{"code": "deterministic_fallback", "tasks": ["rule_parse"]}]

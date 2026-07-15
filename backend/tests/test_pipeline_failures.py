from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.config.settings import get_settings
from app.models import AnalysisRequest, AnalysisRun, ExecutionEvent
from app.models.enums import InputTypeEnum, ModeEnum, RequestStatusEnum
from app.services.analysis_execution import RunBudgetExceeded, enforce_run_budget, execution_context
from app.services.analysis_progress import initial_progress_payload
from app.services.analysis_pipeline import AnalysisProcessor


def test_budget_exceeded_stops_with_partial_ledger(session_factory):
    settings = get_settings()
    original = settings.max_run_calls
    settings.max_run_calls = 0
    now = datetime.now(UTC)
    try:
        with session_factory() as session:
            request = AnalysisRequest(
                mode=ModeEnum.MANUAL,
                input_type=InputTypeEnum.CUSTOM_CLAIM,
                input_text="Will the event happen?",
                input_payload={},
                progress_json=initial_progress_payload(now),
                status=RequestStatusEnum.RUNNING,
                current_stage="rule_parse",
                started_at=now,
            )
            session.add(request)
            session.commit()
            with execution_context(request.id), pytest.raises(RunBudgetExceeded, match="call_limit"):
                enforce_run_budget(session, task_name="rule_parse")
            event = session.scalar(
                select(ExecutionEvent).where(ExecutionEvent.request_id == request.id)
            )
            assert event is not None
            assert event.event_kind == "budget_exceeded"
            assert event.error_class == "RunBudgetExceeded"
            assert event.detail_json["reason"] == "call_limit"
    finally:
        settings.max_run_calls = original


def test_degraded_pipeline_records_fallbacks_and_quality(client):
    response = client.post(
        "/api/analyses/manual",
        json={"custom_claim": "Will the Federal Reserve cut rates at its next meeting?"},
    )
    analysis_id = response.json()["request"]["id"]
    detail = client.get(f"/api/analyses/{analysis_id}").json()
    ledger = client.get(f"/api/analyses/{analysis_id}/ledger").json()

    assert detail["request"]["status"] == "complete"
    assert ledger["run_quality"] in {"warning", "invalid"}
    fallbacks = [call for call in ledger["calls"] if call["result_mode"] == "deterministic_fallback"]
    assert len(fallbacks) >= 4
    assert all(call["error_class"] for call in fallbacks)


def test_fred_lane_failure_degrades_loudly_without_stopping_pipeline(session_factory):
    class BrokenFredLane:
        name = "fred"

        def retrieve(self, _rule_parse):
            raise ValueError("malformed FRED response")

    now = datetime.now(UTC)
    with session_factory() as session:
        request = AnalysisRequest(
            mode=ModeEnum.MANUAL,
            input_type=InputTypeEnum.CUSTOM_CLAIM,
            input_text="Will the Federal Reserve cut rates at its next meeting?",
            input_payload={},
            progress_json=initial_progress_payload(now),
            status=RequestStatusEnum.QUEUED,
            current_stage="queued",
        )
        session.add(request)
        session.commit()
        request_id = request.id

    processor = AnalysisProcessor(
        session_factory=session_factory,
        enable_remote_calls=False,
        retrieval_lanes=[BrokenFredLane()],
    )
    processor.process_request(request_id)

    with session_factory() as session:
        request = session.get(AnalysisRequest, request_id)
        run = session.scalar(select(AnalysisRun).where(AnalysisRun.request_id == request_id))
        event = session.scalar(
            select(ExecutionEvent).where(
                ExecutionEvent.request_id == request_id,
                ExecutionEvent.provider == "fred",
            )
        )
        assert request is not None and request.status == RequestStatusEnum.COMPLETE
        assert run is not None and run.quality_state.value in {"warning", "invalid"}
        assert event is not None
        assert event.result_mode.value == "failed"
        assert event.error_class == "ValueError"

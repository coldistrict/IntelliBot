from datetime import UTC, datetime
from threading import Event

from sqlalchemy.orm import Session, sessionmaker

from app.models import AnalysisRequest
from app.models.enums import InputTypeEnum, ModeEnum, RequestStatusEnum
from app.services.analysis_dispatch import AnalysisDispatcher
from app.services.analysis_progress import initial_progress_payload


def test_reconcile_stale_requests_requeues_running_and_queued_work(
    session_factory: sessionmaker[Session],
):
    now = datetime.now(UTC)
    with session_factory() as session:
        queued = AnalysisRequest(
            mode=ModeEnum.AUTO,
            input_type=InputTypeEnum.CUSTOM_CLAIM,
            input_text="AUTO_SCAN_TRIGGER",
            input_payload={},
            progress_json=initial_progress_payload(now),
            status=RequestStatusEnum.QUEUED,
            current_stage="queued",
        )
        running = AnalysisRequest(
            mode=ModeEnum.MANUAL,
            input_type=InputTypeEnum.CUSTOM_CLAIM,
            input_text="Will a filing happen this week?",
            input_payload={},
            progress_json=initial_progress_payload(now),
            status=RequestStatusEnum.RUNNING,
            current_stage="retrieval",
            started_at=now,
        )
        session.add_all([queued, running])
        session.commit()
        queued_id = queued.id
        running_id = running.id

    processed_ids: list[int] = []

    class StubProcessor:
        def process_request(self, request_id: int) -> None:
            processed_ids.append(request_id)

    dispatcher = AnalysisDispatcher(run_inline=True)
    reconciled = dispatcher.reconcile_stale_requests(
        processor=StubProcessor(),
        session_factory=session_factory,
    )

    assert reconciled == [queued_id, running_id]
    assert processed_ids == [queued_id, running_id]

    with session_factory() as session:
        queued = session.get(AnalysisRequest, queued_id)
        running = session.get(AnalysisRequest, running_id)

    assert queued is not None and queued.status == RequestStatusEnum.QUEUED
    assert running is not None and running.status == RequestStatusEnum.QUEUED
    assert running.current_stage == "queued"
    assert running.started_at is None


def test_dispatch_skips_duplicate_active_request():
    started = Event()
    release = Event()
    finished = Event()
    processed_ids: list[int] = []

    class StubProcessor:
        def process_request(self, request_id: int) -> None:
            processed_ids.append(request_id)
            started.set()
            release.wait(timeout=1.0)
            finished.set()

    processor = StubProcessor()
    dispatcher = AnalysisDispatcher()

    assert dispatcher.dispatch(processor, 7) is True
    assert started.wait(timeout=1.0) is True
    assert dispatcher.dispatch(processor, 7) is False

    release.set()
    assert finished.wait(timeout=1.0) is True
    assert processed_ids == [7]

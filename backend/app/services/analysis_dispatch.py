from __future__ import annotations

import logging
from functools import lru_cache
from threading import Lock, Thread
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import AnalysisRequest
from app.models.enums import RequestStatusEnum
from app.services.analysis_progress import initial_progress_payload

if TYPE_CHECKING:
    from app.services.analysis_pipeline import AnalysisProcessor

logger = logging.getLogger(__name__)


class AnalysisDispatcher:
    def __init__(self, *, run_inline: bool = False) -> None:
        self.run_inline = run_inline
        self._active_request_ids: set[int] = set()
        self._lock = Lock()

    def reserve(self, request_id: int) -> bool:
        with self._lock:
            if request_id in self._active_request_ids:
                return False
            self._active_request_ids.add(request_id)
            return True

    def release(self, request_id: int) -> None:
        with self._lock:
            self._active_request_ids.discard(request_id)

    def dispatch(
        self,
        processor: "AnalysisProcessor",
        request_id: int,
        *,
        pre_reserved: bool = False,
    ) -> bool:
        if not pre_reserved and not self.reserve(request_id):
            return False

        if self.run_inline:
            try:
                processor.process_request(request_id)
            finally:
                self.release(request_id)
            return True

        thread = Thread(
            target=self._run_request,
            args=(processor, request_id),
            name=f"analysis-request-{request_id}",
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            self.release(request_id)
            raise
        return True

    def _run_request(self, processor: "AnalysisProcessor", request_id: int) -> None:
        try:
            processor.process_request(request_id)
        finally:
            self.release(request_id)

    def reconcile_stale_requests(
        self,
        *,
        processor: "AnalysisProcessor",
        session_factory: sessionmaker[Session],
    ) -> list[int]:
        request_ids: list[int] = []
        try:
            with session_factory() as session:
                request_ids = _requeue_stale_requests(session)
                session.commit()
        except Exception:  # pragma: no cover - best-effort startup behavior
            logger.exception("Unable to reconcile stale analysis requests during startup.")
            return []

        dispatched_ids: list[int] = []
        for request_id in request_ids:
            if self.dispatch(processor, request_id):
                dispatched_ids.append(request_id)

        return dispatched_ids


def reset_request_to_queue(request: AnalysisRequest) -> None:
    request.status = RequestStatusEnum.QUEUED
    request.current_stage = "queued"
    request.error_message = None
    request.started_at = None
    request.completed_at = None
    request.progress_json = initial_progress_payload()


def _requeue_stale_requests(session: Session) -> list[int]:
    requests = session.scalars(
        select(AnalysisRequest)
        .where(AnalysisRequest.status.in_([RequestStatusEnum.QUEUED, RequestStatusEnum.RUNNING]))
        .order_by(AnalysisRequest.created_at.asc(), AnalysisRequest.id.asc())
    ).all()

    for request in requests:
        reset_request_to_queue(request)
        session.add(request)

    return [request.id for request in requests]


@lru_cache
def get_analysis_dispatcher() -> AnalysisDispatcher:
    return AnalysisDispatcher()

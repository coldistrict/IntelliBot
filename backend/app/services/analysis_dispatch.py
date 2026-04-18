from __future__ import annotations

import logging
from functools import lru_cache
from threading import Thread
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

    def dispatch(self, processor: "AnalysisProcessor", request_id: int) -> None:
        if self.run_inline:
            processor.process_request(request_id)
            return

        thread = Thread(
            target=processor.process_request,
            args=(request_id,),
            name=f"analysis-request-{request_id}",
            daemon=True,
        )
        thread.start()

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

        for request_id in request_ids:
            self.dispatch(processor, request_id)

        return request_ids


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

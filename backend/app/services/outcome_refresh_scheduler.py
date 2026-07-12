from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic, sleep

from apscheduler.schedulers.background import BackgroundScheduler

from app.clients.polymarket_client import PolymarketClient
from app.services.outcome_tracker import OutcomeRefreshSummary, refresh_market_outcomes

logger = logging.getLogger("uvicorn.error").getChild("intellibot.outcome_refresh")


@dataclass
class OutcomeRefreshCoordinator:
    cooldown_seconds: float
    coalesce_delay_seconds: float = 0.05

    def __post_init__(self) -> None:
        self._lock = Lock()
        self._last_sweep = 0.0
        self._last_summary = OutcomeRefreshSummary(0, 0, 0, 0)
        self.sweep_count = 0

    def refresh(self, session, *, client: PolymarketClient, force: bool = False) -> OutcomeRefreshSummary:
        if not self._lock.acquire(blocking=False):
            return self._last_summary
        try:
            now = monotonic()
            if not force and now - self._last_sweep < self.cooldown_seconds:
                return self._last_summary
            # Give requests that arrived in the same network burst time to observe
            # the held lock, even when the upstream sweep itself completes quickly.
            sleep(self.coalesce_delay_seconds)
            self._last_summary = refresh_market_outcomes(session, client=client)
            self._last_sweep = monotonic()
            self.sweep_count += 1
            logger.info("Outcome refresh sweep %s completed.", self.sweep_count)
            return self._last_summary
        finally:
            self._lock.release()


def start_outcome_scheduler(
    *,
    session_factory,
    interval_minutes: int,
    cooldown_seconds: int,
    startup_retry_seconds: int = 15,
):
    coordinator = get_outcome_refresh_coordinator(cooldown_seconds=cooldown_seconds)
    scheduler = BackgroundScheduler(timezone="UTC")

    def scheduled_refresh() -> bool:
        try:
            with session_factory() as session:
                coordinator.refresh(session, client=PolymarketClient(enabled=True))
            return True
        except Exception:
            logger.exception("Scheduled outcome refresh failed.")
            return False

    def startup_refresh() -> None:
        if scheduled_refresh() or not scheduler.running:
            return
        retry_at = datetime.now(UTC) + timedelta(seconds=max(startup_retry_seconds, 1))
        logger.info("Retrying startup outcome refresh at %s.", retry_at.isoformat())
        scheduler.add_job(
            startup_refresh,
            "date",
            run_date=retry_at,
            id="outcome-refresh-startup-retry",
            replace_existing=True,
        )

    scheduler.add_job(
        scheduled_refresh,
        "interval",
        minutes=max(interval_minutes, 1),
        id="outcome-refresh",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    scheduler.add_job(startup_refresh, id="outcome-refresh-startup")
    return scheduler


_coordinator: OutcomeRefreshCoordinator | None = None


def get_outcome_refresh_coordinator(*, cooldown_seconds: int = 30) -> OutcomeRefreshCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = OutcomeRefreshCoordinator(cooldown_seconds=cooldown_seconds)
    else:
        _coordinator.cooldown_seconds = cooldown_seconds
    return _coordinator

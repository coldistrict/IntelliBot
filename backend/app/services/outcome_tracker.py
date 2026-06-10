from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.polymarket_client import PolymarketClient, ResolvedMarketRecord
from app.models import Market, Snapshot
from app.models.enums import SnapshotTypeEnum

logger = logging.getLogger(__name__)

RESOLVED_OUTCOMES = {"yes", "no"}


@dataclass(frozen=True)
class OutcomeRefreshSummary:
    markets_checked: int
    newly_resolved: int
    still_open: int
    lookup_failures: int


def refresh_market_outcomes(
    session: Session,
    *,
    client: PolymarketClient,
) -> OutcomeRefreshSummary:
    markets = session.scalars(
        select(Market)
        .where(Market.resolved_outcome.is_(None))
        .where(Market.analysis_runs.any())
        .order_by(Market.id.asc())
    ).all()

    newly_resolved = 0
    still_open = 0
    lookup_failures = 0
    now = datetime.now(UTC)

    for market in markets:
        record = client.get_market_by_id(market.polymarket_id)
        if record is None:
            lookup_failures += 1
            continue
        if record.resolved_outcome in RESOLVED_OUTCOMES:
            _apply_resolution(session, market, record, now=now)
            newly_resolved += 1
        else:
            still_open += 1

    session.commit()
    return OutcomeRefreshSummary(
        markets_checked=len(markets),
        newly_resolved=newly_resolved,
        still_open=still_open,
        lookup_failures=lookup_failures,
    )


def _apply_resolution(
    session: Session,
    market: Market,
    record: ResolvedMarketRecord,
    *,
    now: datetime,
) -> None:
    market.resolved_outcome = record.resolved_outcome
    market.resolved_at = record.closed_time or now
    market.status = "closed"
    session.add(market)

    has_resolved_snapshot = session.scalar(
        select(Snapshot.id)
        .where(Snapshot.market_id == market.id)
        .where(Snapshot.snapshot_type == SnapshotTypeEnum.RESOLVED)
        .limit(1)
    )
    if has_resolved_snapshot is None:
        session.add(
            Snapshot(
                market_id=market.id,
                analysis_run_id=None,
                snapshot_type=SnapshotTypeEnum.RESOLVED,
                yes_bid=record.yes_bid,
                yes_ask=record.yes_ask,
                no_bid=record.no_bid,
                no_ask=record.no_ask,
                midpoint_yes=1.0 if record.resolved_outcome == "yes" else 0.0,
                outcome=record.resolved_outcome,
                created_at=now,
            )
        )
    logger.info(
        "Market %s (%s) resolved %s.",
        market.polymarket_id,
        market.title,
        record.resolved_outcome,
    )

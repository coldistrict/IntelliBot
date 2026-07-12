from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, Query

from app.clients.polymarket_client import PolymarketClient, ResolvedMarketRecord
from app.db.session import get_db_session
from app.models import Market
from app.schemas.market import (
    MarketListResponse,
    MarketResponse,
    PublicMarketListResponse,
    PublicMarketResponse,
    ResearchEdgeSignalResponse,
)
from app.services.market_signals import research_edge_signals_for_records

router = APIRouter(prefix="/markets")


def get_polymarket_client() -> PolymarketClient:
    return PolymarketClient(enabled=True)


def _public_market_response(
    record: ResolvedMarketRecord,
    signal: ResearchEdgeSignalResponse,
) -> PublicMarketResponse:
    return PublicMarketResponse(
        polymarket_id=record.polymarket_id,
        title=record.title,
        url=record.url,
        rules_text=record.rules_text,
        description=record.description,
        yes_bid=record.yes_bid,
        yes_ask=record.yes_ask,
        no_bid=record.no_bid,
        no_ask=record.no_ask,
        liquidity=record.liquidity,
        volume_24h=record.volume_24h,
        spread=record.spread,
        expiry_at=record.expiry_at,
        status=record.status,
        category=record.category,
        event_title=record.event_title,
        event_slug=record.event_slug,
        image=record.image,
        featured=record.featured,
        is_new=record.is_new,
        research_edge_signal=signal,
    )


def _record_from_market(market: Market) -> ResolvedMarketRecord:
    return ResolvedMarketRecord(
        polymarket_id=market.polymarket_id,
        title=market.title,
        url=market.url,
        rules_text=market.rules_text,
        description=market.description,
        yes_bid=market.yes_bid,
        yes_ask=market.yes_ask,
        no_bid=market.no_bid,
        no_ask=market.no_ask,
        liquidity=market.liquidity,
        volume_24h=market.volume_24h,
        spread=market.spread,
        expiry_at=market.expiry_at,
        status=market.status,
    )


@router.get("/discover", response_model=PublicMarketListResponse)
def discover_markets(
    q: str | None = Query(default=None, max_length=200),
    view: str = Query(
        default="popular",
        pattern="^(popular|trending|liquidity|closing_soon|newest)$",
    ),
    limit: int = Query(default=70, ge=1, le=70),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
    client: PolymarketClient = Depends(get_polymarket_client),
) -> PublicMarketListResponse:
    records = client.discover_markets(query=q, view=view, limit=limit, offset=offset)
    signals = research_edge_signals_for_records(session, records)
    has_more = not q and len(records) == limit
    return PublicMarketListResponse(
        items=[
            _public_market_response(record, signals[record.polymarket_id])
            for record in records
        ],
        # The upstream discovery feed has no real total; this counts markets
        # enumerated through this page. has_more signals further pages.
        total=offset + len(records),
        has_more=has_more,
    )


@router.get("/remote/{polymarket_id}", response_model=PublicMarketResponse)
def get_public_market(
    polymarket_id: str,
    session: Session = Depends(get_db_session),
    client: PolymarketClient = Depends(get_polymarket_client),
) -> PublicMarketResponse:
    record = client.get_market_by_id(polymarket_id)
    if record is None:
        local_market = session.scalar(select(Market).where(Market.polymarket_id == polymarket_id))
        record = _record_from_market(local_market) if local_market else None
    if record is None:
        raise HTTPException(status_code=404, detail="Polymarket market not found.")
    signal = research_edge_signals_for_records(session, [record])[record.polymarket_id]
    return _public_market_response(record, signal)


@router.get("", response_model=MarketListResponse)
def list_markets(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> MarketListResponse:
    total = session.scalar(select(func.count()).select_from(Market)) or 0
    items = session.scalars(
        select(Market).order_by(Market.updated_at.desc(), Market.id.desc()).limit(limit).offset(offset)
    ).all()
    return MarketListResponse(items=[MarketResponse.model_validate(item) for item in items], total=total)


@router.get("/{market_id}", response_model=MarketResponse)
def get_market(market_id: int, session: Session = Depends(get_db_session)) -> MarketResponse:
    market = session.get(Market, market_id)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found.")
    return MarketResponse.model_validate(market)

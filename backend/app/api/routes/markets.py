from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.session import get_db_session
from app.models import Market
from app.schemas.market import MarketListResponse, MarketResponse

router = APIRouter(prefix="/markets")


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


from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class MarketResponse(ORMModel):
    id: int
    polymarket_id: str
    title: str
    url: str | None
    rules_text: str | None
    description: str | None
    yes_bid: float | None
    yes_ask: float | None
    no_bid: float | None
    no_ask: float | None
    liquidity: float | None
    volume_24h: float | None
    spread: float | None
    expiry_at: datetime | None
    status: str | None
    created_at: datetime
    updated_at: datetime


class MarketListResponse(BaseModel):
    items: list[MarketResponse]
    total: int

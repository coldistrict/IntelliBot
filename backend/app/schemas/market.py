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


class PublicMarketResponse(BaseModel):
    polymarket_id: str
    title: str
    url: str | None = None
    rules_text: str | None = None
    description: str | None = None
    yes_bid: float | None = None
    yes_ask: float | None = None
    no_bid: float | None = None
    no_ask: float | None = None
    liquidity: float | None = None
    volume_24h: float | None = None
    spread: float | None = None
    expiry_at: datetime | None = None
    status: str | None = None
    category: str | None = None
    event_title: str | None = None
    event_slug: str | None = None
    image: str | None = None
    featured: bool = False
    is_new: bool = False


class PublicMarketListResponse(BaseModel):
    items: list[PublicMarketResponse]
    total: int
    has_more: bool = False

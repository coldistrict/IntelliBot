from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.analysis import AnalysisRequest, AnalysisRun, RuleParse, Snapshot


class Market(TimestampMixin, Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    polymarket_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000))
    rules_text: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    yes_bid: Mapped[float | None] = mapped_column(Float)
    yes_ask: Mapped[float | None] = mapped_column(Float)
    no_bid: Mapped[float | None] = mapped_column(Float)
    no_ask: Mapped[float | None] = mapped_column(Float)
    liquidity: Mapped[float | None] = mapped_column(Float)
    volume_24h: Mapped[float | None] = mapped_column(Float)
    spread: Mapped[float | None] = mapped_column(Float)
    expiry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(64))
    resolved_outcome: Mapped[str | None] = mapped_column(String(16))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    yes_token_id: Mapped[str | None] = mapped_column(String(255))
    no_token_id: Mapped[str | None] = mapped_column(String(255))

    analysis_requests: Mapped[list["AnalysisRequest"]] = relationship(back_populates="market")
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="market")
    rule_parses: Mapped[list["RuleParse"]] = relationship(back_populates="market")
    snapshots: Mapped[list["Snapshot"]] = relationship(back_populates="market")
    price_points: Mapped[list["MarketPricePoint"]] = relationship(
        back_populates="market", cascade="all, delete-orphan"
    )


class MarketPricePoint(Base):
    __tablename__ = "market_price_points"
    __table_args__ = (UniqueConstraint("market_id", "token_id", "observed_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False, index=True)
    token_id: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str] = mapped_column(String(8), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    market: Mapped["Market"] = relationship(back_populates="price_points")

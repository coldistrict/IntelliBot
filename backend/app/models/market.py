from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, Integer, String, Text
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

    analysis_requests: Mapped[list["AnalysisRequest"]] = relationship(back_populates="market")
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="market")
    rule_parses: Mapped[list["RuleParse"]] = relationship(back_populates="market")
    snapshots: Mapped[list["Snapshot"]] = relationship(back_populates="market")

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

import httpx

from app.config.settings import get_settings


@dataclass
class ResolvedMarketRecord:
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


class PolymarketClient:
    def __init__(self, *, enabled: bool = True) -> None:
        settings = get_settings()
        self.base_url = settings.polymarket_gamma_base_url.rstrip("/")
        self.enabled = enabled

    def get_market_by_id(self, market_id: str) -> ResolvedMarketRecord | None:
        if not self.enabled:
            return None
        return self._fetch_market(f"/markets/{market_id}")

    def get_market_by_url(self, url: str) -> ResolvedMarketRecord | None:
        if not self.enabled:
            return None
        slug = self._slug_from_url(url)
        if not slug:
            return None
        return self._fetch_market(f"/markets/slug/{slug}")

    def _fetch_market(self, path: str) -> ResolvedMarketRecord | None:
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.get(f"{self.base_url}{path}")
                response.raise_for_status()
        except httpx.HTTPError:
            return None

        payload = response.json()
        outcomes = self._coerce_json_list(payload.get("outcomes"))
        outcome_prices = self._coerce_json_list(payload.get("outcomePrices"))
        yes_price, no_price = self._resolve_binary_prices(outcomes, outcome_prices)
        best_bid = self._coerce_float(payload.get("bestBid"))
        best_ask = self._coerce_float(payload.get("bestAsk"))

        return ResolvedMarketRecord(
            polymarket_id=str(payload.get("id") or ""),
            title=payload.get("question") or "Untitled Polymarket market",
            url=f"https://polymarket.com/event/{payload.get('slug')}" if payload.get("slug") else None,
            rules_text=payload.get("resolutionSource"),
            description=payload.get("description"),
            yes_bid=best_bid if best_bid is not None else yes_price,
            yes_ask=best_ask if best_ask is not None else yes_price,
            no_bid=(1 - best_ask) if best_ask is not None else no_price,
            no_ask=(1 - best_bid) if best_bid is not None else no_price,
            liquidity=self._coerce_float(payload.get("liquidityNum") or payload.get("liquidity")),
            volume_24h=self._coerce_float(payload.get("volume24hr")),
            spread=(
                max(best_ask - best_bid, 0.0)
                if best_ask is not None and best_bid is not None
                else None
            ),
            expiry_at=self._coerce_datetime(payload.get("endDateIso") or payload.get("endDate")),
            status="closed" if payload.get("closed") else "active",
        )

    @staticmethod
    def _slug_from_url(url: str) -> str | None:
        parsed = urlparse(url)
        path_parts = [part for part in parsed.path.split("/") if part]
        return path_parts[-1] if path_parts else None

    @staticmethod
    def _coerce_json_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return [part.strip() for part in value.split(",") if part.strip()]
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        return []

    @staticmethod
    def _resolve_binary_prices(outcomes: list[str], prices: list[str]) -> tuple[float | None, float | None]:
        if len(outcomes) < 2 or len(prices) < 2:
            return (None, None)
        lookup = {
            outcome.strip().lower(): PolymarketClient._coerce_float(price)
            for outcome, price in zip(outcomes, prices, strict=False)
        }
        yes_price = lookup.get("yes")
        no_price = lookup.get("no")
        return yes_price, no_price

    @staticmethod
    def _coerce_float(value: object) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return None
        if not isinstance(value, (int, float, str)):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_datetime(value: object) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

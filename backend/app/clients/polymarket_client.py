from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config.settings import get_settings

HttpQueryParams = dict[str, str | int | float | bool | None]


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
    volume: float | None = None
    created_at: datetime | None = None
    category: str | None = None
    event_title: str | None = None
    event_slug: str | None = None
    image: str | None = None
    featured: bool = False
    is_new: bool = False
    closed: bool = False
    resolved_outcome: str | None = None
    closed_time: datetime | None = None


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

    def search_markets_for_claim(self, query: str, *, limit: int = 8) -> list[ResolvedMarketRecord]:
        if not self.enabled or not query.strip():
            return []
        payload = self._get_json("/public-search", params={"q": query, "limit": limit})
        if payload is None:
            return []

        return self._records_from_search_payload(payload, limit=limit)

    def discover_markets(
        self,
        *,
        query: str | None = None,
        view: str = "popular",
        limit: int = 25,
        offset: int = 0,
    ) -> list[ResolvedMarketRecord]:
        if not self.enabled:
            return []
        if query and query.strip():
            payload = self._get_json(
                "/public-search",
                params={"q": query.strip(), "limit": limit},
            )
            return self._records_from_search_payload(payload, limit=limit) if payload is not None else []

        order_by_view = {
            "popular": ("volume", False),
            "trending": ("volume24hr", False),
            "liquidity": ("liquidity", False),
            "closing_soon": ("endDate", True),
            "newest": ("createdAt", False),
        }
        order, ascending = order_by_view.get(view, order_by_view["popular"])
        payload = self._get_json(
            "/events",
            params={
                "active": "true",
                "closed": "false",
                "limit": limit,
                "offset": offset,
                "order": order,
                "ascending": str(ascending).lower(),
            },
        )
        if payload is None:
            return []
        return self._records_from_events_payload(payload, view=view, limit=limit)

    def _records_from_search_payload(
        self,
        payload: Any,
        *,
        limit: int,
    ) -> list[ResolvedMarketRecord]:
        candidates: list[ResolvedMarketRecord] = []
        seen_market_ids: set[str] = set()

        for market_payload in payload.get("markets", []) if isinstance(payload, dict) else []:
            if not isinstance(market_payload, dict):
                continue
            record = self._record_from_payload(market_payload)
            self._append_live_record(candidates, seen_market_ids, record)

        for event_payload in payload.get("events", []) if isinstance(payload, dict) else []:
            if not isinstance(event_payload, dict):
                continue
            event_slug = event_payload.get("slug")
            event_title = event_payload.get("title")
            event_category = self._coerce_string(event_payload.get("category"))
            event_image = self._coerce_string(event_payload.get("image") or event_payload.get("icon"))
            markets = event_payload.get("markets")
            if not isinstance(markets, list):
                continue
            for market_payload in markets:
                if not isinstance(market_payload, dict):
                    continue
                record = self._record_from_payload(
                    market_payload,
                    event_slug=str(event_slug) if event_slug else None,
                    event_title=str(event_title) if event_title else None,
                    event_category=event_category,
                    event_image=event_image,
                    event_featured=bool(event_payload.get("featured")),
                    event_new=bool(event_payload.get("new")),
                )
                self._append_live_record(candidates, seen_market_ids, record)

        return candidates[:limit]

    def _fetch_market(self, path: str) -> ResolvedMarketRecord | None:
        payload = self._get_json(path)
        if payload is None:
            return None
        return self._record_from_payload(payload)

    def _get_json(self, path: str, *, params: HttpQueryParams | None = None) -> Any | None:
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.get(f"{self.base_url}{path}", params=params)
                response.raise_for_status()
        except httpx.HTTPError:
            return None

        return response.json()

    def _records_from_events_payload(
        self,
        payload: Any,
        *,
        view: str,
        limit: int,
    ) -> list[ResolvedMarketRecord]:
        records: list[ResolvedMarketRecord] = []
        seen_market_ids: set[str] = set()
        events = payload if isinstance(payload, list) else []
        for event_payload in events:
            if not isinstance(event_payload, dict):
                continue
            markets = event_payload.get("markets")
            if isinstance(markets, list):
                for market_payload in markets:
                    if not isinstance(market_payload, dict):
                        continue
                    record = self._record_from_payload(
                        market_payload,
                        event_slug=self._coerce_string(event_payload.get("slug")),
                        event_title=self._coerce_string(event_payload.get("title")),
                        event_category=self._coerce_string(event_payload.get("category")),
                        event_image=self._coerce_string(
                            event_payload.get("image") or event_payload.get("icon")
                        ),
                        event_featured=bool(event_payload.get("featured")),
                        event_new=bool(event_payload.get("new")),
                    )
                    self._append_live_record(records, seen_market_ids, record)
            else:
                record = self._record_from_payload(event_payload)
                self._append_live_record(records, seen_market_ids, record)
        return self._sort_records_for_view(records, view=view)[:limit]

    def _record_from_payload(
        self,
        payload: dict[str, Any],
        *,
        event_slug: str | None = None,
        event_title: str | None = None,
        event_category: str | None = None,
        event_image: str | None = None,
        event_featured: bool = False,
        event_new: bool = False,
    ) -> ResolvedMarketRecord:
        outcomes = self._coerce_json_list(payload.get("outcomes"))
        outcome_prices = self._coerce_json_list(payload.get("outcomePrices"))
        yes_price, no_price = self._resolve_binary_prices(outcomes, outcome_prices)
        best_bid = self._coerce_float(payload.get("bestBid"))
        best_ask = self._coerce_float(payload.get("bestAsk"))
        slug = event_slug or payload.get("slug")
        closed = self._coerce_bool(payload.get("closed"))
        active = self._coerce_bool(payload.get("active"))
        status = "closed" if closed else "active" if active else None
        category = event_category or self._coerce_string(payload.get("category"))
        image = event_image or self._coerce_string(payload.get("image") or payload.get("icon"))

        description = payload.get("description")
        if event_title and description:
            description = f"{event_title}\n\n{description}"

        return ResolvedMarketRecord(
            polymarket_id=str(payload.get("id") or ""),
            title=payload.get("question") or "Untitled Polymarket market",
            url=f"https://polymarket.com/event/{slug}" if slug else None,
            rules_text=payload.get("resolutionSource"),
            description=description,
            yes_bid=best_bid if best_bid is not None else yes_price,
            yes_ask=best_ask if best_ask is not None else yes_price,
            no_bid=(1 - best_ask) if best_ask is not None else no_price,
            no_ask=(1 - best_bid) if best_bid is not None else no_price,
            liquidity=self._coerce_float(payload.get("liquidityNum") or payload.get("liquidity")),
            volume_24h=self._coerce_float(
                payload.get("volume24hr")
                or payload.get("volume24hrClob")
                or payload.get("volume_24hr")
            ),
            spread=self._resolve_spread(best_bid, best_ask),
            expiry_at=self._coerce_datetime(payload.get("endDateIso") or payload.get("endDate")),
            status=status,
            volume=self._coerce_float(payload.get("volumeNum") or payload.get("volume")),
            created_at=self._coerce_datetime(payload.get("createdAt") or payload.get("creationDate")),
            category=category,
            event_title=event_title,
            event_slug=event_slug,
            image=image,
            featured=event_featured or self._coerce_bool(payload.get("featured")),
            is_new=event_new or self._coerce_bool(payload.get("new")),
            closed=closed,
            resolved_outcome=self._derive_resolved_outcome(
                closed=closed,
                uma_resolution_status=self._coerce_string(payload.get("umaResolutionStatus")),
                yes_price=yes_price,
            ),
            closed_time=self._coerce_datetime(
                payload.get("closedTime") or payload.get("umaEndDate")
            ),
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
    def _coerce_string(value: object) -> str | None:
        return str(value).strip() if value is not None and str(value).strip() else None

    @staticmethod
    def _coerce_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes"}
        if isinstance(value, (int, float)):
            return value != 0
        return False

    @staticmethod
    def _resolve_spread(best_bid: float | None, best_ask: float | None) -> float | None:
        if best_bid is None or best_ask is None:
            return None
        return round(max(best_ask - best_bid, 0.0), 6)

    @staticmethod
    def _append_live_record(
        records: list[ResolvedMarketRecord],
        seen_market_ids: set[str],
        record: ResolvedMarketRecord,
    ) -> None:
        if not record.polymarket_id or record.status != "active":
            return
        if record.polymarket_id in seen_market_ids:
            return
        records.append(record)
        seen_market_ids.add(record.polymarket_id)

    @staticmethod
    def _sort_records_for_view(
        records: list[ResolvedMarketRecord],
        *,
        view: str,
    ) -> list[ResolvedMarketRecord]:
        if view == "closing_soon":
            return sorted(
                records,
                key=lambda record: (
                    record.expiry_at.timestamp() if record.expiry_at is not None else float("inf")
                ),
            )
        if view == "newest":
            return sorted(
                records,
                key=lambda record: (
                    record.created_at.timestamp() if record.created_at is not None else float("-inf")
                ),
                reverse=True,
            )
        attribute = {
            "liquidity": "liquidity",
            "trending": "volume_24h",
        }.get(view, "volume")
        return sorted(
            records,
            key=lambda record: getattr(record, attribute) or float("-inf"),
            reverse=True,
        )

    @staticmethod
    def _derive_resolved_outcome(
        *,
        closed: bool,
        uma_resolution_status: str | None,
        yes_price: float | None,
    ) -> str | None:
        if not closed or yes_price is None:
            return None
        if uma_resolution_status is not None and uma_resolution_status.strip().lower() not in {
            "resolved",
            "",
        }:
            return None
        if yes_price >= 0.99:
            return "yes"
        if yes_price <= 0.01:
            return "no"
        return None

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

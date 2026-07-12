from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.config.settings import get_settings
from app.models.enums import SourceTierEnum
from app.services.pipeline_models import SearchSourceDraft


class FredClient:
    SERIES = {
        "inflation": ("CPIAUCSL", "Consumer Price Index for All Urban Consumers"),
        "unemployment": ("UNRATE", "Unemployment Rate"),
        "interest_rate": ("FEDFUNDS", "Effective Federal Funds Rate"),
    }

    def __init__(self, *, enabled: bool = True) -> None:
        settings = get_settings()
        self.base_url = settings.fred_base_url.rstrip("/")
        self.api_key = (
            settings.fred_api_key.get_secret_value() if settings.fred_api_key is not None else None
        )
        self.enabled = enabled

    @property
    def is_configured(self) -> bool:
        return self.enabled and bool(self.api_key)

    def observations_for_claim(self, claim: str) -> list[SearchSourceDraft]:
        if not self.is_configured:
            return []
        series_key = self._series_key(claim)
        series_id, title = self.SERIES[series_key]
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                f"{self.base_url}/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": self.api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 3,
                },
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        observations = [
            row
            for row in payload.get("observations", [])
            if isinstance(row, dict) and row.get("value") not in {None, "."}
        ]
        if not observations:
            return []
        latest = observations[0]
        history = ", ".join(f"{row.get('date')}: {row.get('value')}" for row in observations)
        url = f"https://fred.stlouisfed.org/series/{series_id}"
        return [
            SearchSourceDraft(
                url=url,
                title=f"FRED — {title}",
                excerpt=(
                    f"Official FRED series {series_id}. Latest observation: {latest.get('date')} = "
                    f"{latest.get('value')}. Recent observations: {history}."
                ),
                domain="fred.stlouisfed.org",
                published_at=self._date(latest.get("date")),
                source_tier=SourceTierEnum.OFFICIAL_PRIMARY,
                metadata_json={"series_id": series_id, "observations": observations},
            )
        ]

    @classmethod
    def _series_key(cls, claim: str) -> str:
        lowered = claim.lower()
        if any(term in lowered for term in ("inflation", "cpi", "prices")):
            return "inflation"
        if any(term in lowered for term in ("unemployment", "jobs", "labor")):
            return "unemployment"
        return "interest_rate"

    @staticmethod
    def _date(value: object) -> datetime | None:
        try:
            return datetime.fromisoformat(str(value)).replace(tzinfo=UTC)
        except ValueError:
            return None

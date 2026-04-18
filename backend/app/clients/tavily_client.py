from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.config.settings import get_settings
from app.models.enums import SourceTierEnum
from app.services.pipeline_models import SearchSourceDraft


class TavilyClient:
    def __init__(self, *, enabled: bool = True) -> None:
        settings = get_settings()
        self.base_url = "https://api.tavily.com"
        self.api_key = (
            settings.tavily_api_key.get_secret_value() if settings.tavily_api_key is not None else None
        )
        self.enabled = enabled

    @property
    def is_configured(self) -> bool:
        return self.enabled and bool(self.api_key)

    def search(
        self,
        *,
        query: str,
        max_results: int = 4,
        include_domains: list[str] | None = None,
        topic: str = "general",
    ) -> list[SearchSourceDraft]:
        if not self.is_configured:
            return []

        payload: dict[str, Any] = {
            "query": query,
            "topic": topic,
            "max_results": max_results,
            "include_domains": include_domains or [],
            "include_answer": False,
            "search_depth": "advanced",
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=20.0) as client:
            response = client.post(f"{self.base_url}/search", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        results: list[SearchSourceDraft] = []
        for item in data.get("results", [])[:max_results]:
            published_at = self._parse_datetime(item.get("published_date"))
            url = item.get("url")
            content = item.get("content") or item.get("raw_content") or item.get("snippet") or ""
            if not url or not content:
                continue
            results.append(
                SearchSourceDraft(
                    url=url,
                    title=item.get("title"),
                    excerpt=content,
                    domain=item.get("domain"),
                    published_at=published_at,
                    source_tier=self._classify_source_tier(url),
                    is_paywalled=self._is_paywalled(url),
                    metadata_json={
                        "score": item.get("score"),
                        "favicon": item.get("favicon"),
                    },
                )
            )
        return results

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _classify_source_tier(url: str) -> SourceTierEnum:
        domain = url.split("/")[2].lower() if "://" in url else url.lower()
        if domain.endswith(".gov") or domain.endswith(".mil") or "federalreserve.gov" in domain:
            return SourceTierEnum.OFFICIAL_PRIMARY
        if any(host in domain for host in {"wsj.com", "nytimes.com", "ft.com"}):
            return SourceTierEnum.PREMIUM_NEWS
        if any(
            host in domain
            for host in {
                "scotusblog.com",
                "lawfaremedia.org",
                "brookings.edu",
                "piie.com",
                "cfr.org",
            }
        ):
            return SourceTierEnum.EXPERT_ANALYSIS
        if any(host in domain for host in {"reuters.com", "apnews.com"}):
            return SourceTierEnum.REPUTABLE_NEWS
        return SourceTierEnum.REPUTABLE_NEWS

    @staticmethod
    def _is_paywalled(url: str) -> bool:
        domain = url.split("/")[2].lower() if "://" in url else url.lower()
        return any(host in domain for host in {"wsj.com", "nytimes.com", "ft.com"})

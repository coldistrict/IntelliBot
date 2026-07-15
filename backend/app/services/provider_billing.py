from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from threading import Lock
from time import monotonic
from typing import Any

import httpx

from app.config.settings import Settings, get_settings
from app.schemas.provider_status import ProviderBillingItem, ProviderBillingResponse

OPENAI_DASHBOARD_URL = "https://platform.openai.com/usage"
XAI_DASHBOARD_URL = "https://console.x.ai/team/default/billing"


class ProviderBillingService:
    """Reads provider billing data without ever returning management credentials."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
        cache_seconds: float = 300,
    ) -> None:
        self.settings = settings or get_settings()
        self.transport = transport
        self.cache_seconds = cache_seconds
        self._cached: ProviderBillingResponse | None = None
        self._cached_at = 0.0
        self._lock = Lock()

    def get_billing(self, *, refresh: bool = False) -> ProviderBillingResponse:
        now = monotonic()
        if not refresh and self._cached and now - self._cached_at < self.cache_seconds:
            return self._cached

        with self._lock:
            now = monotonic()
            if not refresh and self._cached and now - self._cached_at < self.cache_seconds:
                return self._cached

            refreshed_at = datetime.now(UTC)
            response = ProviderBillingResponse(
                openai=self._openai_billing(refreshed_at),
                grok=self._grok_billing(refreshed_at),
                refreshed_at=refreshed_at,
            )
            self._cached = response
            self._cached_at = now
            return response

    def _openai_billing(self, now: datetime) -> ProviderBillingItem:
        key = self.settings.openai_admin_api_key
        if key is None or not self.settings.has_secret(key):
            return ProviderBillingItem(
                provider="openai",
                status="setup_required",
                balance_type="unavailable",
                message="Add an OpenAI Admin key to read organization costs.",
                setup_fields=["OPENAI_ADMIN_API_KEY", "OPENAI_MONTHLY_BUDGET_USD"],
                dashboard_url=OPENAI_DASHBOARD_URL,
            )

        try:
            spent = self._fetch_openai_month_cost(key.get_secret_value(), now)
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            return ProviderBillingItem(
                provider="openai",
                status="error",
                balance_type="unavailable",
                message=_safe_error_message("OpenAI billing is temporarily unavailable", exc),
                dashboard_url=OPENAI_DASHBOARD_URL,
            )

        budget = self.settings.openai_monthly_budget_usd
        if budget is None:
            return ProviderBillingItem(
                provider="openai",
                status="available",
                balance_type="usage_only",
                spent_month_usd=float(spent),
                message="Current-month cost is live. Add a monthly budget to estimate what remains.",
                setup_fields=["OPENAI_MONTHLY_BUDGET_USD"],
                dashboard_url=OPENAI_DASHBOARD_URL,
                as_of=now,
            )

        normalized_budget = max(Decimal(str(budget)), Decimal("0"))
        remaining = max(normalized_budget - spent, Decimal("0"))
        return ProviderBillingItem(
            provider="openai",
            status="available",
            balance_type="estimated",
            spent_month_usd=float(spent),
            budget_usd=float(normalized_budget),
            remaining_usd=float(remaining),
            message="Estimated from your monthly budget minus OpenAI costs this month.",
            dashboard_url=OPENAI_DASHBOARD_URL,
            as_of=now,
        )

    def _fetch_openai_month_cost(self, api_key: str, now: datetime) -> Decimal:
        month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
        params: dict[str, Any] = {
            "start_time": int(month_start.timestamp()),
            "end_time": int(now.timestamp()),
            "bucket_width": "1d",
            "limit": 31,
        }
        total = Decimal("0")

        with httpx.Client(timeout=15.0, transport=self.transport) as client:
            for _ in range(10):
                response = client.get(
                    f"{self.settings.openai_base_url.rstrip('/')}/organization/costs",
                    headers={"Authorization": f"Bearer {api_key}"},
                    params=params,
                )
                response.raise_for_status()
                payload = response.json()
                for bucket in payload.get("data", []):
                    for result in bucket.get("results", []):
                        amount = result.get("amount", {})
                        if str(amount.get("currency", "usd")).lower() == "usd":
                            total += _decimal(amount.get("value", 0))

                if not payload.get("has_more") or not payload.get("next_page"):
                    break
                params["page"] = payload["next_page"]

        return max(total, Decimal("0"))

    def _grok_billing(self, now: datetime) -> ProviderBillingItem:
        key = self.settings.xai_management_api_key
        team_id = (self.settings.xai_team_id or "").strip()
        missing = []
        if key is None or not self.settings.has_secret(key):
            missing.append("XAI_MANAGEMENT_API_KEY")
        if not team_id:
            missing.append("XAI_TEAM_ID")
        if missing or key is None:
            return ProviderBillingItem(
                provider="grok",
                status="setup_required",
                balance_type="unavailable",
                message="Add an xAI Management key and Team ID to read prepaid credits.",
                setup_fields=missing,
                dashboard_url=XAI_DASHBOARD_URL,
            )

        try:
            with httpx.Client(timeout=15.0, transport=self.transport) as client:
                response = client.get(
                    (
                        f"{self.settings.xai_management_base_url.rstrip('/')}"
                        f"/v1/billing/teams/{team_id}/prepaid/balance"
                    ),
                    headers={"Authorization": f"Bearer {key.get_secret_value()}"},
                )
                response.raise_for_status()
                raw_cents = _decimal(response.json()["total"]["val"])
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            return ProviderBillingItem(
                provider="grok",
                status="error",
                balance_type="unavailable",
                message=_safe_error_message("Grok billing is temporarily unavailable", exc),
                dashboard_url=XAI_DASHBOARD_URL,
            )

        # xAI represents prepaid credit as a negative ledger balance (for example -1000 = $10).
        balance = max(-raw_cents, Decimal("0")) / Decimal("100")
        return ProviderBillingItem(
            provider="grok",
            status="available",
            balance_type="exact",
            credit_balance_usd=float(balance),
            message="Exact prepaid credit balance reported by xAI.",
            dashboard_url=XAI_DASHBOARD_URL,
            as_of=now,
        )


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Provider returned an invalid currency amount.") from exc


def _safe_error_message(prefix: str, exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"{prefix} (HTTP {exc.response.status_code})."
    return f"{prefix}."


@lru_cache
def get_provider_billing_service() -> ProviderBillingService:
    return ProviderBillingService()

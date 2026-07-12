from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProviderStatusResponse(BaseModel):
    openai_configured: bool
    grok_configured: bool
    search_configured: bool
    fred_configured: bool
    premium_session_available: bool


class ProviderBillingItem(BaseModel):
    provider: Literal["openai", "grok"]
    status: Literal["available", "setup_required", "error"]
    balance_type: Literal["exact", "estimated", "usage_only", "unavailable"]
    currency: Literal["USD"] = "USD"
    credit_balance_usd: float | None = Field(default=None, ge=0)
    spent_month_usd: float | None = Field(default=None, ge=0)
    budget_usd: float | None = Field(default=None, ge=0)
    remaining_usd: float | None = Field(default=None, ge=0)
    message: str
    setup_fields: list[str] = Field(default_factory=list)
    dashboard_url: str
    as_of: datetime | None = None


class ProviderBillingResponse(BaseModel):
    openai: ProviderBillingItem
    grok: ProviderBillingItem
    refreshed_at: datetime

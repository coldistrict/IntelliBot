from typing import Annotated

from fastapi import APIRouter, Depends

from app.config.settings import get_settings
from app.schemas.provider_status import ProviderBillingResponse, ProviderStatusResponse
from app.services.provider_billing import ProviderBillingService, get_provider_billing_service

router = APIRouter(prefix="/providers")


@router.get("/status", response_model=ProviderStatusResponse)
def provider_status() -> ProviderStatusResponse:
    settings = get_settings()

    return ProviderStatusResponse(
        openai_configured=settings.has_secret(settings.openai_api_key),
        grok_configured=settings.has_secret(settings.xai_api_key),
        search_configured=settings.has_secret(settings.tavily_api_key),
        fred_configured=settings.has_secret(settings.fred_api_key),
        premium_session_available=settings.premium_session_state_path is not None,
    )


@router.get("/billing", response_model=ProviderBillingResponse)
def provider_billing(
    service: Annotated[ProviderBillingService, Depends(get_provider_billing_service)],
    refresh: bool = False,
) -> ProviderBillingResponse:
    return service.get_billing(refresh=refresh)

from pydantic import BaseModel


class ProviderStatusResponse(BaseModel):
    openai_configured: bool
    grok_configured: bool
    search_configured: bool
    fred_configured: bool
    premium_session_available: bool


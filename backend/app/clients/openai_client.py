from __future__ import annotations

from app.clients.llm_base import StructuredChatClient
from app.config.settings import get_settings


def get_openai_client(*, enabled: bool = True) -> StructuredChatClient:
    settings = get_settings()
    api_key = (
        settings.openai_api_key.get_secret_value()
        if settings.openai_api_key is not None
        else None
    )
    return StructuredChatClient(
        provider="openai",
        base_url=settings.openai_base_url,
        api_key=api_key,
        model=settings.openai_model,
        timeout_seconds=settings.llm_timeout_seconds,
        enabled=enabled,
    )

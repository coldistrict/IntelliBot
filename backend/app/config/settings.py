from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Polymarket Copilot v1"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    frontend_url: str = "http://localhost:3000"

    postgres_db: str = "polymarket_copilot"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_port: int = 5432
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/polymarket_copilot"

    openai_api_key: SecretStr | None = None
    xai_api_key: SecretStr | None = None
    openai_admin_api_key: SecretStr | None = None
    openai_monthly_budget_usd: float | None = None
    xai_management_api_key: SecretStr | None = None
    xai_team_id: str | None = None
    tavily_api_key: SecretStr | None = None
    fred_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    xai_base_url: str = "https://api.x.ai/v1"
    xai_management_base_url: str = "https://management-api.x.ai"
    openai_model: str = "gpt-5.4-mini"
    xai_model: str = "grok-4-1-fast-non-reasoning"
    xai_social_model: str = "grok-4-1-fast-non-reasoning"
    llm_timeout_seconds: float = 45.0

    polymarket_gamma_base_url: str = "https://gamma-api.polymarket.com"
    polymarket_clob_base_url: str = "https://clob.polymarket.com"
    premium_session_state_path: Path | None = None

    @field_validator(
        "openai_api_key",
        "xai_api_key",
        "openai_admin_api_key",
        "xai_management_api_key",
        "tavily_api_key",
        "fred_api_key",
        mode="before",
    )
    @classmethod
    def blank_secret_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("xai_team_id", mode="before")
    @classmethod
    def blank_text_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("premium_session_state_path", mode="before")
    @classmethod
    def blank_path_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @staticmethod
    def has_secret(value: SecretStr | None) -> bool:
        return value is not None and bool(value.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()

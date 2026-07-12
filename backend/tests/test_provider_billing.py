from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config.settings import Settings
from app.services.provider_billing import ProviderBillingService, get_provider_billing_service


def test_provider_billing_reads_openai_costs_and_exact_grok_balance() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/organization/costs":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "results": [
                                {"amount": {"value": 12.34, "currency": "usd"}},
                                {"amount": {"value": 0.66, "currency": "usd"}},
                            ]
                        }
                    ],
                    "has_more": False,
                },
            )
        if request.url.path == "/v1/billing/teams/team-123/prepaid/balance":
            return httpx.Response(200, json={"changes": [], "total": {"val": "-4250"}})
        return httpx.Response(404)

    settings = Settings(
        _env_file=None,
        openai_admin_api_key="openai-admin-secret",
        openai_monthly_budget_usd=100,
        openai_base_url="https://api.openai.test/v1",
        xai_management_api_key="xai-management-secret",
        xai_team_id="team-123",
        xai_management_base_url="https://management-api.xai.test",
    )
    service = ProviderBillingService(
        settings=settings,
        transport=httpx.MockTransport(handler),
        cache_seconds=0,
    )

    payload = service.get_billing()

    assert payload.openai.status == "available"
    assert payload.openai.balance_type == "estimated"
    assert payload.openai.spent_month_usd == pytest.approx(13.0)
    assert payload.openai.remaining_usd == pytest.approx(87.0)
    assert payload.grok.status == "available"
    assert payload.grok.balance_type == "exact"
    assert payload.grok.credit_balance_usd == pytest.approx(42.5)
    assert requests[0].headers["authorization"] == "Bearer openai-admin-secret"
    assert requests[1].headers["authorization"] == "Bearer xai-management-secret"
    serialized = payload.model_dump_json()
    assert "openai-admin-secret" not in serialized
    assert "xai-management-secret" not in serialized


def test_provider_billing_explains_missing_management_credentials() -> None:
    service = ProviderBillingService(
        settings=Settings(
            _env_file=None,
            openai_admin_api_key=None,
            openai_monthly_budget_usd=None,
            xai_management_api_key=None,
            xai_team_id=None,
        )
    )

    payload = service.get_billing()

    assert payload.openai.status == "setup_required"
    assert payload.openai.setup_fields == [
        "OPENAI_ADMIN_API_KEY",
        "OPENAI_MONTHLY_BUDGET_USD",
    ]
    assert payload.grok.status == "setup_required"
    assert payload.grok.setup_fields == ["XAI_MANAGEMENT_API_KEY", "XAI_TEAM_ID"]


def test_provider_billing_turns_remote_failures_into_safe_ui_states() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "do-not-expose-this"}})

    service = ProviderBillingService(
        settings=Settings(
            _env_file=None,
            openai_admin_api_key="bad-openai-key",
            xai_management_api_key="bad-xai-key",
            xai_team_id="team-123",
        ),
        transport=httpx.MockTransport(handler),
        cache_seconds=0,
    )

    payload = service.get_billing(refresh=True)

    assert payload.openai.status == "error"
    assert payload.openai.message == "OpenAI billing is temporarily unavailable (HTTP 401)."
    assert payload.grok.status == "error"
    assert payload.grok.message == "Grok billing is temporarily unavailable (HTTP 401)."
    assert "do-not-expose-this" not in payload.model_dump_json()


def test_provider_billing_endpoint_exposes_summary(client: TestClient) -> None:
    service = ProviderBillingService(
        settings=Settings(
            _env_file=None,
            openai_admin_api_key=None,
            openai_monthly_budget_usd=None,
            xai_management_api_key=None,
            xai_team_id=None,
        )
    )
    app.dependency_overrides[get_provider_billing_service] = lambda: service

    response = client.get("/api/providers/billing?refresh=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["openai"]["provider"] == "openai"
    assert payload["grok"]["provider"] == "grok"
    assert datetime.fromisoformat(payload["refreshed_at"]).tzinfo == UTC

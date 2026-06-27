from fastapi.testclient import TestClient
from pydantic import SecretStr

from retos.core.config import Settings
from retos.llm.providers import active_provider, list_provider_profiles


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_provider_catalog_exposes_safe_default_profiles(settings: Settings) -> None:
    profiles = {profile.name: profile for profile in list_provider_profiles(settings)}

    assert profiles["local"].configured is True
    assert profiles["local"].enabled is True
    assert profiles["local"].default_model == "gemma4"
    assert profiles["openai"].configured is False
    assert profiles["openai"].enabled is False
    assert profiles["openai"].paid is True
    assert profiles["openai"].reason == "Missing required configuration"


def test_paid_provider_stays_disabled_without_cost_opt_in() -> None:
    settings = Settings(
        env="test",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
        openai_api_key=SecretStr("sk-test"),
    )

    profiles = {profile.name: profile for profile in list_provider_profiles(settings)}

    assert profiles["openai"].configured is True
    assert profiles["openai"].enabled is False
    assert "ALLOW_PAID_LLM" in str(profiles["openai"].reason)


def test_empty_paid_provider_secret_is_not_configured() -> None:
    settings = Settings(
        env="test",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
        openai_api_key=SecretStr(" "),
    )

    profiles = {profile.name: profile for profile in list_provider_profiles(settings)}

    assert profiles["openai"].configured is False
    assert profiles["openai"].reason == "Missing required configuration"


def test_paid_provider_can_be_enabled_explicitly() -> None:
    settings = Settings(
        env="test",
        provider="openai",
        allow_paid_llm=True,
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
        openai_api_key=SecretStr("sk-test"),
    )

    provider = active_provider(settings)

    assert provider.provider == "openai"
    assert provider.paid is True
    assert provider.can_call is True


def test_llm_providers_endpoint_requires_admin(client: TestClient) -> None:
    response = client.get("/llm/providers")

    assert response.status_code == 401


def test_llm_providers_endpoint_returns_safe_catalog(client: TestClient) -> None:
    response = client.get("/llm/providers", headers=auth_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert body["active"] == {
        "provider": "local",
        "model": "ollama:gemma4",
        "paid": False,
        "can_call": True,
        "reason": None,
    }
    assert {provider["name"] for provider in body["providers"]} == {
        "fake",
        "local",
        "openai",
        "anthropic",
        "google",
        "openrouter",
        "azure",
    }
    assert "api_key" not in str(body).lower()

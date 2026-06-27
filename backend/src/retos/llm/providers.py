from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, HttpUrl, SecretStr

from retos.core.config import Settings

ProviderName = Literal["fake", "local", "openai", "anthropic", "google", "openrouter", "azure"]


class ProviderProfile(BaseModel):
    name: ProviderName
    label: str
    default_model: str
    configured: bool
    enabled: bool
    paid: bool
    reason: str | None = None
    base_url: HttpUrl | None = None


class ActiveProvider(BaseModel):
    provider: ProviderName
    model: str
    paid: bool
    can_call: bool
    reason: str | None = None


@dataclass(frozen=True)
class ProviderDefinition:
    name: ProviderName
    label: str
    paid: bool


PROVIDER_DEFINITIONS: tuple[ProviderDefinition, ...] = (
    ProviderDefinition("fake", "Deterministic test double", False),
    ProviderDefinition("local", "Ollama local runtime", False),
    ProviderDefinition("openai", "OpenAI", True),
    ProviderDefinition("anthropic", "Anthropic", True),
    ProviderDefinition("google", "Google Gemini", True),
    ProviderDefinition("openrouter", "OpenRouter", True),
    ProviderDefinition("azure", "Azure OpenAI", True),
)


def provider_model(settings: Settings, provider: ProviderName) -> str:
    models = {
        "fake": "fake:deterministic",
        "local": settings.ollama_model,
        "openai": settings.openai_model,
        "anthropic": settings.anthropic_model,
        "google": settings.google_model,
        "openrouter": settings.openrouter_model,
        "azure": settings.azure_openai_deployment or "unconfigured",
    }
    return models[provider]


def has_secret(secret: SecretStr | None) -> bool:
    return secret is not None and bool(secret.get_secret_value().strip())


def has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def provider_is_configured(settings: Settings, provider: ProviderName) -> bool:
    if provider == "fake":
        return settings.env == "test"
    if provider == "local":
        return bool(settings.ollama_base_url and settings.ollama_model.strip())
    if provider == "openai":
        return has_secret(settings.openai_api_key)
    if provider == "anthropic":
        return has_secret(settings.anthropic_api_key)
    if provider == "google":
        return has_secret(settings.google_api_key)
    if provider == "openrouter":
        return has_secret(settings.openrouter_api_key)
    return (
        has_secret(settings.azure_openai_api_key)
        and has_text(settings.azure_openai_endpoint)
        and has_text(settings.azure_openai_deployment)
    )


def provider_reason(*, configured: bool, paid: bool, allow_paid: bool) -> str | None:
    if not configured:
        return "Missing required configuration"
    if paid and not allow_paid:
        return "Paid providers are disabled by RETOS_ALLOW_PAID_LLM=false"
    return None


def list_provider_profiles(settings: Settings) -> list[ProviderProfile]:
    profiles: list[ProviderProfile] = []
    for definition in PROVIDER_DEFINITIONS:
        configured = provider_is_configured(settings, definition.name)
        reason = provider_reason(
            configured=configured,
            paid=definition.paid,
            allow_paid=settings.allow_paid_llm,
        )
        profiles.append(
            ProviderProfile(
                name=definition.name,
                label=definition.label,
                default_model=provider_model(settings, definition.name),
                configured=configured,
                enabled=reason is None,
                paid=definition.paid,
                reason=reason,
                base_url=settings.ollama_base_url if definition.name == "local" else None,
            )
        )
    return profiles


def active_provider(settings: Settings) -> ActiveProvider:
    provider = settings.provider
    if provider not in {definition.name for definition in PROVIDER_DEFINITIONS}:
        raise ValueError("Unknown provider profile")
    typed_provider = provider
    profile = next(item for item in list_provider_profiles(settings) if item.name == typed_provider)
    return ActiveProvider(
        provider=profile.name,
        model=settings.model if settings.model else profile.default_model,
        paid=profile.paid,
        can_call=profile.enabled,
        reason=profile.reason,
    )

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

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
    missing_config: list[str] = Field(default_factory=list)
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
    required_config: tuple[str, ...]


PROVIDER_DEFINITIONS: tuple[ProviderDefinition, ...] = (
    ProviderDefinition("fake", "Deterministic test double", False, ()),
    ProviderDefinition("local", "Ollama local runtime", False, ("RETOS_OLLAMA_MODEL",)),
    ProviderDefinition("openai", "OpenAI", True, ("RETOS_OPENAI_API_KEY",)),
    ProviderDefinition("anthropic", "Anthropic", True, ("RETOS_ANTHROPIC_API_KEY",)),
    ProviderDefinition("google", "Google Gemini", True, ("RETOS_GOOGLE_API_KEY",)),
    ProviderDefinition("openrouter", "OpenRouter", True, ("RETOS_OPENROUTER_API_KEY",)),
    ProviderDefinition(
        "azure",
        "Azure OpenAI",
        True,
        (
            "RETOS_AZURE_OPENAI_API_KEY",
            "RETOS_AZURE_OPENAI_ENDPOINT",
            "RETOS_AZURE_OPENAI_DEPLOYMENT",
        ),
    ),
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


def provider_is_configured(settings: Settings, provider: ProviderName) -> bool:
    return not missing_provider_config(settings, provider)


def missing_provider_config(settings: Settings, provider: ProviderName) -> list[str]:
    return settings.missing_provider_config(provider)


def provider_reason(*, configured: bool, paid: bool, allow_paid: bool) -> str | None:
    if not configured:
        return "Missing required configuration"
    if paid and not allow_paid:
        return "Paid providers are disabled by RETOS_ALLOW_PAID_LLM=false"
    return None


def list_provider_profiles(settings: Settings) -> list[ProviderProfile]:
    profiles: list[ProviderProfile] = []
    for definition in PROVIDER_DEFINITIONS:
        missing_config = missing_provider_config(settings, definition.name)
        configured = not missing_config
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
                missing_config=missing_config,
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

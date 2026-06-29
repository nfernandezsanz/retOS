from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from retos.core.config import AgentRuntimeMode, Settings

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


class RuntimeSwitchPlan(BaseModel):
    provider: ProviderName
    model: str
    agent_runtime: AgentRuntimeMode
    paid_provider: bool
    paid_providers_enabled: bool
    can_start: bool
    restart_required: bool = True
    env: dict[str, str]
    missing_config: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
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


def provider_model_env_key(provider: ProviderName) -> str | None:
    keys = {
        "fake": None,
        "local": "RETOS_OLLAMA_MODEL",
        "openai": "RETOS_OPENAI_MODEL",
        "anthropic": "RETOS_ANTHROPIC_MODEL",
        "google": "RETOS_GOOGLE_MODEL",
        "openrouter": "RETOS_OPENROUTER_MODEL",
        "azure": "RETOS_AZURE_OPENAI_DEPLOYMENT",
    }
    return keys[provider]


def requested_model(settings: Settings, provider: ProviderName) -> str:
    if provider == settings.provider and settings.model:
        return settings.model
    if provider == "local":
        return f"ollama:{settings.ollama_model}"
    return provider_model(settings, provider)


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


def plan_runtime_switch(
    settings: Settings,
    *,
    provider: ProviderName,
    agent_runtime: AgentRuntimeMode,
    allow_paid_llm: bool | None = None,
) -> RuntimeSwitchPlan:
    definition = next(item for item in PROVIDER_DEFINITIONS if item.name == provider)
    paid_enabled = settings.allow_paid_llm if allow_paid_llm is None else allow_paid_llm
    missing_config = missing_provider_config(settings, provider)
    configured = not missing_config
    reason = provider_reason(
        configured=configured,
        paid=definition.paid,
        allow_paid=paid_enabled,
    )
    model = requested_model(settings, provider)
    env = {
        "RETOS_PROVIDER": provider,
        "RETOS_AGENT_RUNTIME": agent_runtime,
        "RETOS_MODEL": model,
        "RETOS_ALLOW_PAID_LLM": str(paid_enabled).lower(),
    }
    model_env_key = provider_model_env_key(provider)
    if model_env_key is not None:
        env[model_env_key] = provider_model(settings, provider)
    if provider == "local":
        env["RETOS_OLLAMA_BASE_URL"] = settings.ollama_base_url

    warnings = ["Restart API and worker after changing runtime environment."]
    if agent_runtime == "deepagents":
        warnings.append("Deep Agents synthesis may call the active provider during queries.")
    if definition.paid:
        warnings.append("Paid provider use requires an explicit budget owner and key review.")
    if missing_config:
        warnings.append("Set missing provider configuration before restart.")

    return RuntimeSwitchPlan(
        provider=provider,
        model=model,
        agent_runtime=agent_runtime,
        paid_provider=definition.paid,
        paid_providers_enabled=paid_enabled,
        can_start=reason is None,
        env=env,
        missing_config=missing_config,
        warnings=warnings,
        reason=reason,
    )

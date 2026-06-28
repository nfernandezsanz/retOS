from functools import lru_cache
from typing import Literal

from pydantic import EmailStr, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from retos.core.security import hash_password

Environment = Literal["development", "test", "production"]
AgentRuntimeMode = Literal["deterministic", "deepagents"]

DEVELOPMENT_JWT_SECRET = "change-this-development-secret-at-least-32-chars"
DEVELOPMENT_ADMIN_PASSWORD = "retos-dev-admin-change-me"
KNOWN_PROVIDER_PROFILES: frozenset[str] = frozenset(
    {
        "fake",
        "local",
        "openai",
        "anthropic",
        "google",
        "openrouter",
        "azure",
    }
)
PAID_PROVIDER_PROFILES: frozenset[str] = frozenset(
    {"openai", "anthropic", "google", "openrouter", "azure"}
)


class BootstrapAdmin(BaseSettings):
    email: EmailStr
    password_hash: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RETOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = "development"
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = "postgresql+asyncpg://retos:retos@localhost:5432/retos"
    database_create_all: bool = False
    celery_broker_url: str = "amqp://retos:retos@localhost:5672//"
    celery_result_backend: str | None = None
    jwt_secret: SecretStr = SecretStr(DEVELOPMENT_JWT_SECRET)
    jwt_issuer: str = "retos"
    jwt_audience: str = "retos-api"
    access_token_ttl_minutes: int = Field(default=30, ge=5, le=1440)
    bootstrap_admin_email: EmailStr | None = "admin@retos.dev"
    bootstrap_admin_password: SecretStr | None = SecretStr(DEVELOPMENT_ADMIN_PASSWORD)
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:8080",
        ]
    )
    storage_root: str = "/var/lib/retos/storage"
    index_root: str = "/var/lib/retos/index"
    eval_dataset_root: str = "/var/lib/retos/evals/datasets"
    eval_report_root: str = "/var/lib/retos/evals/reports"
    provider: str = "local"
    model: str = "ollama:gemma4"
    ollama_model: str = "gemma4"
    ollama_base_url: str = "http://localhost:11434"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5-mini"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    google_api_key: SecretStr | None = None
    google_model: str = "gemini-2.5-flash"
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str = "openai/gpt-5-mini"
    azure_openai_api_key: SecretStr | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    allow_paid_llm: bool = False
    agent_runtime: AgentRuntimeMode = "deterministic"

    @property
    def bootstrap_admin(self) -> BootstrapAdmin | None:
        if self.bootstrap_admin_email is None or self.bootstrap_admin_password is None:
            return None
        return BootstrapAdmin(
            email=self.bootstrap_admin_email,
            password_hash=hash_password(self.bootstrap_admin_password.get_secret_value()),
        )

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    def missing_provider_config(self, provider: str) -> list[str]:
        if provider == "fake":
            return [] if self.env == "test" else ["RETOS_ENV=test"]
        if provider == "local":
            missing = []
            if not self.ollama_model.strip():
                missing.append("RETOS_OLLAMA_MODEL")
            if not self.ollama_base_url.strip():
                missing.append("RETOS_OLLAMA_BASE_URL")
            return missing
        if provider == "openai":
            return (
                []
                if self.openai_api_key is not None
                and self.openai_api_key.get_secret_value().strip()
                else ["RETOS_OPENAI_API_KEY"]
            )
        if provider == "anthropic":
            return (
                []
                if self.anthropic_api_key is not None
                and self.anthropic_api_key.get_secret_value().strip()
                else ["RETOS_ANTHROPIC_API_KEY"]
            )
        if provider == "google":
            return (
                []
                if self.google_api_key is not None
                and self.google_api_key.get_secret_value().strip()
                else ["RETOS_GOOGLE_API_KEY"]
            )
        if provider == "openrouter":
            return (
                []
                if self.openrouter_api_key is not None
                and self.openrouter_api_key.get_secret_value().strip()
                else ["RETOS_OPENROUTER_API_KEY"]
            )
        if provider == "azure":
            missing = []
            if (
                self.azure_openai_api_key is None
                or not self.azure_openai_api_key.get_secret_value().strip()
            ):
                missing.append("RETOS_AZURE_OPENAI_API_KEY")
            if self.azure_openai_endpoint is None or not self.azure_openai_endpoint.strip():
                missing.append("RETOS_AZURE_OPENAI_ENDPOINT")
            if self.azure_openai_deployment is None or not self.azure_openai_deployment.strip():
                missing.append("RETOS_AZURE_OPENAI_DEPLOYMENT")
            return missing
        return ["RETOS_PROVIDER"]

    def validate_runtime_security(self) -> None:
        secret = self.jwt_secret.get_secret_value()
        if len(secret) < 32:
            raise ValueError("RETOS_JWT_SECRET must contain at least 32 characters")
        if self.is_production and secret == DEVELOPMENT_JWT_SECRET:
            raise ValueError("RETOS_JWT_SECRET must be changed in production")
        if (
            self.is_production
            and self.bootstrap_admin_password is not None
            and self.bootstrap_admin_password.get_secret_value() == DEVELOPMENT_ADMIN_PASSWORD
        ):
            raise ValueError(
                "The development bootstrap admin password is not allowed in production"
            )
        if self.is_production and any(str(origin) == "*" for origin in self.allowed_origins):
            raise ValueError("Wildcard CORS origins are not allowed in production")
        if self.provider not in KNOWN_PROVIDER_PROFILES:
            raise ValueError("RETOS_PROVIDER must be a known provider profile")
        if self.provider in PAID_PROVIDER_PROFILES and not self.allow_paid_llm:
            raise ValueError("Paid LLM providers require RETOS_ALLOW_PAID_LLM=true")
        missing_provider_config = self.missing_provider_config(self.provider)
        if missing_provider_config:
            missing = ", ".join(missing_provider_config)
            raise ValueError(f"RETOS_PROVIDER={self.provider} is missing: {missing}")
        if self.agent_runtime not in {"deterministic", "deepagents"}:
            raise ValueError("RETOS_AGENT_RUNTIME must be deterministic or deepagents")


@lru_cache
def get_settings() -> Settings:
    return Settings()

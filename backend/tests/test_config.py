import pytest
from pydantic import SecretStr, ValidationError

from retos.core.config import DEVELOPMENT_ADMIN_PASSWORD, DEVELOPMENT_JWT_SECRET, Settings


def test_production_rejects_development_jwt_secret() -> None:
    settings = Settings(env="production", jwt_secret=SecretStr(DEVELOPMENT_JWT_SECRET))

    with pytest.raises(ValueError, match="JWT_SECRET"):
        settings.validate_runtime_security()


def test_production_rejects_development_admin_password() -> None:
    settings = Settings(
        env="production",
        jwt_secret=SecretStr("production-secret-value-that-is-long-enough"),
        bootstrap_admin_password=SecretStr(DEVELOPMENT_ADMIN_PASSWORD),
    )

    with pytest.raises(ValueError, match="bootstrap admin"):
        settings.validate_runtime_security()


def test_bootstrap_admin_can_be_disabled() -> None:
    settings = Settings(
        env="production",
        jwt_secret=SecretStr("production-secret-value-that-is-long-enough"),
        bootstrap_admin_email=None,
        bootstrap_admin_password=None,
    )

    settings.validate_runtime_security()
    assert settings.bootstrap_admin is None


def test_short_jwt_secret_is_rejected() -> None:
    settings = Settings(env="development", jwt_secret=SecretStr("short"))

    with pytest.raises(ValueError, match="at least 32"):
        settings.validate_runtime_security()


def test_bootstrap_admin_hashes_password() -> None:
    settings = Settings(
        env="test",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
        bootstrap_admin_password=SecretStr("test-admin-password"),
    )

    admin = settings.bootstrap_admin

    assert admin is not None
    assert admin.email == "admin@retos.dev"
    assert admin.password_hash != "test-admin-password"


def test_paid_provider_requires_explicit_opt_in() -> None:
    settings = Settings(
        env="test",
        provider="openai",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
    )

    with pytest.raises(ValueError, match="Paid LLM"):
        settings.validate_runtime_security()


def test_paid_provider_requires_runtime_configuration_after_opt_in() -> None:
    settings = Settings(
        env="test",
        provider="openai",
        allow_paid_llm=True,
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
    )

    with pytest.raises(ValueError, match="RETOS_OPENAI_API_KEY"):
        settings.validate_runtime_security()


@pytest.mark.parametrize(
    ("provider", "secret_field", "missing_name"),
    [
        ("anthropic", "anthropic_api_key", "RETOS_ANTHROPIC_API_KEY"),
        ("google", "google_api_key", "RETOS_GOOGLE_API_KEY"),
        ("openrouter", "openrouter_api_key", "RETOS_OPENROUTER_API_KEY"),
    ],
)
def test_paid_provider_profiles_accept_explicit_keys(
    provider: str,
    secret_field: str,
    missing_name: str,
) -> None:
    missing_settings = Settings(
        env="test",
        provider=provider,
        allow_paid_llm=True,
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
    )
    configured_settings = Settings(
        env="test",
        provider=provider,
        allow_paid_llm=True,
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
        **{secret_field: SecretStr("provider-secret")},
    )

    with pytest.raises(ValueError, match=missing_name):
        missing_settings.validate_runtime_security()
    configured_settings.validate_runtime_security()


def test_azure_provider_requires_all_runtime_configuration() -> None:
    settings = Settings(
        env="test",
        provider="azure",
        allow_paid_llm=True,
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
        azure_openai_api_key=SecretStr("az-test"),
        azure_openai_endpoint="https://retos.openai.azure.com",
    )

    with pytest.raises(ValueError, match="RETOS_AZURE_OPENAI_DEPLOYMENT"):
        settings.validate_runtime_security()


def test_azure_provider_accepts_complete_runtime_configuration() -> None:
    settings = Settings(
        env="test",
        provider="azure",
        allow_paid_llm=True,
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
        azure_openai_api_key=SecretStr("az-test"),
        azure_openai_endpoint="https://retos.openai.azure.com",
        azure_openai_deployment="retos-deployment",
    )

    settings.validate_runtime_security()


def test_local_provider_requires_model_name() -> None:
    settings = Settings(
        env="test",
        provider="local",
        ollama_model=" ",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
    )

    with pytest.raises(ValueError, match="OLLAMA_MODEL"):
        settings.validate_runtime_security()


def test_local_provider_requires_base_url() -> None:
    settings = Settings(
        env="test",
        provider="local",
        ollama_base_url=" ",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
    )

    with pytest.raises(ValueError, match="OLLAMA_BASE_URL"):
        settings.validate_runtime_security()


def test_fake_provider_is_test_only() -> None:
    development_settings = Settings(
        env="development",
        provider="fake",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
    )
    test_settings = Settings(
        env="test",
        provider="fake",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
    )

    with pytest.raises(ValueError, match="RETOS_ENV=test"):
        development_settings.validate_runtime_security()
    test_settings.validate_runtime_security()


def test_runtime_security_rejects_wildcard_cors_in_production() -> None:
    settings = Settings(
        env="production",
        jwt_secret=SecretStr("production-secret-value-that-is-long-enough"),
        bootstrap_admin_password=SecretStr("production-admin-password"),
        allowed_origins=["*"],
    )

    with pytest.raises(ValueError, match="Wildcard CORS"):
        settings.validate_runtime_security()


def test_runtime_security_rejects_unknown_provider_profile() -> None:
    settings = Settings(
        env="test",
        provider="unknown",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
    )

    with pytest.raises(ValueError, match="known provider"):
        settings.validate_runtime_security()


def test_agent_runtime_must_be_known() -> None:
    with pytest.raises(ValidationError, match="agent_runtime"):
        Settings(
            env="test",
            agent_runtime="classic-langgraph",  # type: ignore[arg-type]
            jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
        )


def test_eval_roots_have_docker_defaults() -> None:
    settings = Settings()

    assert settings.eval_dataset_root == "/var/lib/retos/evals/datasets"
    assert settings.eval_report_root == "/var/lib/retos/evals/reports"

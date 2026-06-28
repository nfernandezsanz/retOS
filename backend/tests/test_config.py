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


def test_local_provider_requires_model_name() -> None:
    settings = Settings(
        env="test",
        provider="local",
        ollama_model=" ",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
    )

    with pytest.raises(ValueError, match="OLLAMA_MODEL"):
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

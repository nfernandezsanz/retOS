import pytest
from pydantic import SecretStr

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

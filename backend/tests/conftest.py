from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from retos.api.app import create_app
from retos.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
        bootstrap_admin_password=SecretStr("test-admin-password"),
        allowed_origins=["http://localhost:5173"],
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client

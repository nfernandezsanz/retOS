from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from retos.api.app import create_app
from retos.core.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    db_path = tmp_path / "retos-test.db"
    return Settings(
        env="test",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        database_create_all=True,
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
        bootstrap_admin_password=SecretStr("test-admin-password"),
        allowed_origins=["http://localhost:5173"],
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client

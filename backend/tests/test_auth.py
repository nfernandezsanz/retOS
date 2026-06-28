import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from retos.core.config import Settings
from retos.core.security import decode_access_token


def sqlite_path(settings: Settings) -> Path:
    database = make_url(settings.database_url)
    assert database.database is not None
    return Path(database.database)


def test_login_issues_admin_token(client: TestClient, settings: Settings) -> None:
    response = client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    claims = decode_access_token(body["access_token"], settings)
    assert claims.roles == ("admin",)


def test_bootstrap_admin_is_persisted(client: TestClient, settings: Settings) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200

    connection = sqlite3.connect(sqlite_path(settings))
    try:
        count = connection.execute(
            "select count(*) from admin_users where email = ?",
            ("admin@retos.dev",),
        ).fetchone()[0]
    finally:
        connection.close()

    assert count == 1


def test_login_rejects_bad_password(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_login_rejects_when_bootstrap_admin_disabled(settings) -> None:  # type: ignore[no-untyped-def]
    disabled = settings.model_copy(
        update={"bootstrap_admin_email": None, "bootstrap_admin_password": None}
    )
    from retos.api.app import create_app

    with TestClient(create_app(disabled)) as local_client:
        response = local_client.post(
            "/auth/login",
            json={"email": "admin@retos.dev", "password": "test-admin-password"},
        )

    assert response.status_code == 401

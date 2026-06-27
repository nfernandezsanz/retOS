from fastapi.testclient import TestClient


def test_login_issues_admin_token(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


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

    assert response.status_code == 503

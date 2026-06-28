from fastapi.testclient import TestClient

from retos.core.config import Settings
from retos.core.security import create_access_token


def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_users_require_admin_token(client: TestClient) -> None:
    response = client.get("/admin/users")

    assert response.status_code == 401


def test_admin_users_reject_non_admin_role(client: TestClient, settings: Settings) -> None:
    token = create_access_token(
        subject="admin@retos.dev",
        roles=("viewer",),
        settings=settings,
    )

    response = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


def test_admin_users_list_bootstrap_admin(client: TestClient) -> None:
    response = client.get("/admin/users", headers=admin_headers(client))

    assert response.status_code == 200
    users = response.json()
    assert len(users) == 1
    assert users[0]["email"] == "admin@retos.dev"
    assert users[0]["is_active"] is True
    assert "password_hash" not in users[0]


def test_admin_user_create_rejects_short_password(client: TestClient) -> None:
    response = client.post(
        "/admin/users",
        headers=admin_headers(client),
        json={"email": "short@retos.dev", "password": "short"},
    )

    assert response.status_code == 422


def test_admin_user_create_login_and_duplicate_guard(client: TestClient) -> None:
    headers = admin_headers(client)

    created = client.post(
        "/admin/users",
        headers=headers,
        json={"email": "OPS@RETOS.DEV", "password": "ops-admin-password"},
    )
    duplicate = client.post(
        "/admin/users",
        headers=headers,
        json={"email": "ops@retos.dev", "password": "ops-admin-password"},
    )
    login = client.post(
        "/auth/login",
        json={"email": "ops@retos.dev", "password": "ops-admin-password"},
    )

    assert created.status_code == 201
    assert created.json()["email"] == "ops@retos.dev"
    assert created.json()["is_active"] is True
    assert duplicate.status_code == 409
    assert login.status_code == 200

    journals = client.get("/audit/journal-events", headers=headers)
    assert journals.status_code == 200
    assert any(
        event["event_type"] == "admin_user.created"
        and event["entity_id"] == created.json()["id"]
        and event["payload"]["email"] == "ops@retos.dev"
        for event in journals.json()
    )


def test_admin_user_status_update_invalidates_existing_token(client: TestClient) -> None:
    headers = admin_headers(client)
    created = client.post(
        "/admin/users",
        headers=headers,
        json={"email": "disabled@retos.dev", "password": "disabled-password"},
    )
    assert created.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "disabled@retos.dev", "password": "disabled-password"},
    )
    assert login.status_code == 200
    disabled_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    disabled = client.patch(
        f"/admin/users/{created.json()['id']}/status",
        headers=headers,
        json={"is_active": False},
    )
    listed_with_disabled_token = client.get("/admin/users", headers=disabled_headers)
    login_after_disable = client.post(
        "/auth/login",
        json={"email": "disabled@retos.dev", "password": "disabled-password"},
    )

    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    assert listed_with_disabled_token.status_code == 401
    assert listed_with_disabled_token.json()["detail"] == "Admin account is inactive"
    assert login_after_disable.status_code == 401


def test_admin_user_cannot_deactivate_self(client: TestClient) -> None:
    headers = admin_headers(client)
    users = client.get("/admin/users", headers=headers).json()

    response = client.patch(
        f"/admin/users/{users[0]['id']}/status",
        headers=headers,
        json={"is_active": False},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "You cannot deactivate your own admin account"


def test_admin_user_password_reset(client: TestClient) -> None:
    headers = admin_headers(client)
    created = client.post(
        "/admin/users",
        headers=headers,
        json={"email": "reset@retos.dev", "password": "initial-password"},
    )
    assert created.status_code == 201

    reset = client.post(
        f"/admin/users/{created.json()['id']}/password",
        headers=headers,
        json={"password": "updated-password"},
    )
    old_login = client.post(
        "/auth/login",
        json={"email": "reset@retos.dev", "password": "initial-password"},
    )
    new_login = client.post(
        "/auth/login",
        json={"email": "reset@retos.dev", "password": "updated-password"},
    )

    assert reset.status_code == 200
    assert reset.json()["email"] == "reset@retos.dev"
    assert old_login.status_code == 401
    assert new_login.status_code == 200


def test_admin_user_mutations_reject_missing_user(client: TestClient) -> None:
    headers = admin_headers(client)

    status_response = client.patch(
        "/admin/users/missing/status",
        headers=headers,
        json={"is_active": False},
    )
    password_response = client.post(
        "/admin/users/missing/password",
        headers=headers,
        json={"password": "updated-password"},
    )

    assert status_response.status_code == 404
    assert password_response.status_code == 404

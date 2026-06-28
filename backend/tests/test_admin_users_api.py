from fastapi.testclient import TestClient

from retos.core.config import Settings
from retos.core.security import create_access_token, decode_access_token


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
    assert response.json()["detail"] == "Token roles are no longer valid"


def test_admin_users_list_bootstrap_admin(client: TestClient) -> None:
    response = client.get("/admin/users", headers=admin_headers(client))

    assert response.status_code == 200
    users = response.json()
    assert len(users) == 1
    assert users[0]["email"] == "admin@retos.dev"
    assert users[0]["roles"] == ["admin"]
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
    assert created.json()["roles"] == ["admin"]
    assert created.json()["is_active"] is True
    assert duplicate.status_code == 409
    assert login.status_code == 200

    journals = client.get("/audit/journal-events", headers=headers)
    assert journals.status_code == 200
    assert any(
        event["event_type"] == "admin_user.created"
        and event["entity_id"] == created.json()["id"]
        and event["payload"]["email"] == "ops@retos.dev"
        and event["payload"]["roles"] == ["admin"]
        for event in journals.json()
    )


def test_admin_user_create_viewer_role_and_reject_admin_endpoint(
    client: TestClient,
    settings: Settings,
) -> None:
    headers = admin_headers(client)

    created = client.post(
        "/admin/users",
        headers=headers,
        json={
            "email": "viewer@retos.dev",
            "password": "viewer-password",
            "roles": ["viewer"],
        },
    )
    login = client.post(
        "/auth/login",
        json={"email": "viewer@retos.dev", "password": "viewer-password"},
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    listed = client.get("/admin/users", headers=viewer_headers)

    assert created.status_code == 201
    assert created.json()["roles"] == ["viewer"]
    assert login.status_code == 200
    assert decode_access_token(login.json()["access_token"], settings).roles == ("viewer",)
    assert listed.status_code == 403
    assert listed.json()["detail"] == "Admin role required"


def test_admin_user_create_rejects_unsupported_role(client: TestClient) -> None:
    response = client.post(
        "/admin/users",
        headers=admin_headers(client),
        json={
            "email": "bad-role@retos.dev",
            "password": "valid-password",
            "roles": ["owner"],
        },
    )

    assert response.status_code == 422


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


def test_admin_user_roles_update_invalidates_existing_admin_token(client: TestClient) -> None:
    headers = admin_headers(client)
    created = client.post(
        "/admin/users",
        headers=headers,
        json={"email": "role-change@retos.dev", "password": "role-change-password"},
    )
    assert created.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "role-change@retos.dev", "password": "role-change-password"},
    )
    assert login.status_code == 200
    original_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    updated = client.patch(
        f"/admin/users/{created.json()['id']}/roles",
        headers=headers,
        json={"roles": ["viewer"]},
    )
    listed_with_old_token = client.get("/admin/users", headers=original_headers)
    viewer_login = client.post(
        "/auth/login",
        json={"email": "role-change@retos.dev", "password": "role-change-password"},
    )
    listed_with_new_token = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {viewer_login.json()['access_token']}"},
    )

    assert updated.status_code == 200
    assert updated.json()["roles"] == ["viewer"]
    assert listed_with_old_token.status_code == 403
    assert listed_with_new_token.status_code == 403
    journals = client.get("/audit/journal-events", headers=headers)
    assert any(
        event["event_type"] == "admin_user.roles_updated"
        and event["entity_id"] == created.json()["id"]
        and event["payload"]["from_roles"] == ["admin"]
        and event["payload"]["to_roles"] == ["viewer"]
        for event in journals.json()
    )


def test_admin_user_cannot_remove_own_admin_role(client: TestClient) -> None:
    headers = admin_headers(client)
    users = client.get("/admin/users", headers=headers).json()

    response = client.patch(
        f"/admin/users/{users[0]['id']}/roles",
        headers=headers,
        json={"roles": ["viewer"]},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "You cannot remove your own admin role"


def test_admin_user_cannot_remove_last_active_admin_role(client: TestClient) -> None:
    headers = admin_headers(client)
    created = client.post(
        "/admin/users",
        headers=headers,
        json={"email": "second-admin@retos.dev", "password": "second-admin-password"},
    )
    assert created.status_code == 201
    disabled = client.patch(
        f"/admin/users/{created.json()['id']}/status",
        headers=headers,
        json={"is_active": False},
    )
    assert disabled.status_code == 200

    response = client.patch(
        f"/admin/users/{created.json()['id']}/roles",
        headers=headers,
        json={"roles": ["viewer"]},
    )

    assert response.status_code == 200
    users = client.get("/admin/users", headers=headers).json()
    bootstrap = next(user for user in users if user["email"] == "admin@retos.dev")
    self_remove = client.patch(
        f"/admin/users/{bootstrap['id']}/roles",
        headers=headers,
        json={"roles": ["viewer"]},
    )
    assert self_remove.status_code == 409


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
    roles_response = client.patch(
        "/admin/users/missing/roles",
        headers=headers,
        json={"roles": ["viewer"]},
    )
    password_response = client.post(
        "/admin/users/missing/password",
        headers=headers,
        json={"password": "updated-password"},
    )

    assert status_response.status_code == 404
    assert roles_response.status_code == 404
    assert password_response.status_code == 404

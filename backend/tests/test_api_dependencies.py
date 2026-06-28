from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from retos.api.dependencies import (
    AuthPrincipal,
    require_principal,
    require_viewer,
    visible_domain_ids_for_actor,
)
from retos.core.config import Settings
from retos.core.security import create_access_token
from retos.domain.admin import AdminUser


class FakeAdminUsers:
    def __init__(self, admin: AdminUser | None) -> None:
        self.admin = admin

    async def get_by_email(self, email: str) -> AdminUser | None:
        return self.admin if self.admin and self.admin.email == email else None


class FakeUnitOfWork:
    def __init__(self, admin: AdminUser | None) -> None:
        self.admin_users = FakeAdminUsers(admin)
        self.entered = 0

    async def __aenter__(self) -> FakeUnitOfWork:
        self.entered += 1
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def bearer_credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def admin_user(
    *,
    email: str = "admin@retos.dev",
    roles: tuple[str, ...] = ("admin",),
    is_active: bool = True,
) -> AdminUser:
    now = datetime.now(UTC)
    return AdminUser(
        id="admin-id",
        email=email,
        password_hash="not-used",  # noqa: S106 - test fixture hash placeholder.
        roles=roles,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_require_principal_rejects_invalid_token(settings: Settings) -> None:
    uow = FakeUnitOfWork(admin_user())

    with pytest.raises(HTTPException) as exc_info:
        await require_principal(bearer_credentials("not-a-token"), settings, uow)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid access token"
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}
    assert uow.entered == 0


@pytest.mark.asyncio
async def test_require_principal_rejects_inactive_admin(settings: Settings) -> None:
    token = create_access_token(
        subject="inactive@retos.dev",
        roles=("viewer",),
        settings=settings,
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_principal(
            bearer_credentials(token),
            settings,
            FakeUnitOfWork(
                admin_user(email="inactive@retos.dev", roles=("viewer",), is_active=False)
            ),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Admin account is inactive"


@pytest.mark.asyncio
async def test_require_principal_rejects_stale_token_roles(settings: Settings) -> None:
    token = create_access_token(
        subject="viewer@retos.dev",
        roles=("viewer", "admin"),
        settings=settings,
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_principal(
            bearer_credentials(token),
            settings,
            FakeUnitOfWork(admin_user(email="viewer@retos.dev", roles=("viewer",))),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Token roles are no longer valid"


@pytest.mark.asyncio
async def test_require_viewer_rejects_principal_without_viewer_role() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_viewer(AuthPrincipal(subject="svc@retos.dev", roles=("service",)))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Viewer role required"


@pytest.mark.asyncio
async def test_visible_domain_ids_returns_empty_set_for_missing_actor() -> None:
    visible = await visible_domain_ids_for_actor(
        actor="missing@retos.dev",
        uow=FakeUnitOfWork(None),  # type: ignore[arg-type]
    )

    assert visible == set()

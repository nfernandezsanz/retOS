from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import IntegrityError

from retos.api.routes.admin_users import (
    AdminUserCreate,
    AdminUserDomainGrantCreate,
    AdminUserPasswordReset,
    AdminUserRolesUpdate,
    AdminUserStatusUpdate,
    create_admin_user,
    create_admin_user_domain_grant,
    reset_admin_user_password,
    update_admin_user_roles,
    update_admin_user_status,
)
from retos.domain.admin import AdminUser, AdminUserDomainGrant
from retos.domain.documents import Domain

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_admin(
    *,
    admin_id: str = "admin-1",
    email: str = "target@retos.dev",
    roles: tuple[str, ...] = ("admin",),
    is_active: bool = True,
) -> AdminUser:
    return AdminUser(
        id=admin_id,
        email=email,
        password_hash="test-password-hash",  # noqa: S106 - fixture hash, not a credential.
        roles=roles,
        is_active=is_active,
        created_at=NOW,
        updated_at=NOW,
    )


def make_domain(domain_id: str = "domain-1") -> Domain:
    return Domain(
        id=domain_id,
        slug="domain-one",
        name="Domain One",
        description=None,
        archived_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeJournalEvents:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def add(self, **event: Any) -> None:
        self.events.append(event)


class FakeDomains:
    def __init__(self, domain: Domain | None = None) -> None:
        self.domain = domain

    async def get(self, domain_id: str) -> Domain | None:
        if self.domain is None or self.domain.id != domain_id:
            return None
        return self.domain


class FakeAdminUsers:
    def __init__(
        self,
        *,
        admin: AdminUser | None = None,
        active_admin_count: int = 2,
        existing_email: AdminUser | None = None,
        existing_grant: AdminUserDomainGrant | None = None,
    ) -> None:
        self.admin = admin
        self.active_admin_count = active_admin_count
        self.existing_email = existing_email
        self.existing_grant = existing_grant
        self.update_active_result: AdminUser | None = admin
        self.update_roles_result: AdminUser | None = admin
        self.update_password_result: AdminUser | None = admin

    async def get_by_email(self, email: str) -> AdminUser | None:
        return (
            self.existing_email
            if self.existing_email and self.existing_email.email == email
            else None
        )

    async def add(
        self,
        *,
        email: str,
        password_hash: str,
        roles: tuple[str, ...],
        is_active: bool,
    ) -> AdminUser:
        self.admin = make_admin(
            admin_id="new-admin",
            email=email,
            roles=roles,
            is_active=is_active,
        )
        return self.admin

    async def get(self, admin_user_id: str) -> AdminUser | None:
        if self.admin is None or self.admin.id != admin_user_id:
            return None
        return self.admin

    async def count_active_admins(self) -> int:
        return self.active_admin_count

    async def update_active(self, *, admin_user_id: str, is_active: bool) -> AdminUser | None:
        return self.update_active_result

    async def get_domain_grant(
        self,
        *,
        admin_user_id: str,
        domain_id: str,
    ) -> AdminUserDomainGrant | None:
        if (
            self.existing_grant is not None
            and self.existing_grant.admin_user_id == admin_user_id
            and self.existing_grant.domain_id == domain_id
        ):
            return self.existing_grant
        return None

    async def add_domain_grant(
        self,
        *,
        admin_user_id: str,
        domain_id: str,
    ) -> AdminUserDomainGrant:
        self.existing_grant = AdminUserDomainGrant(
            id="grant-1",
            admin_user_id=admin_user_id,
            domain_id=domain_id,
            created_at=NOW,
        )
        return self.existing_grant

    async def update_roles(self, *, admin_user_id: str, roles: tuple[str, ...]) -> AdminUser | None:
        return self.update_roles_result

    async def update_password(self, *, admin_user_id: str, password_hash: str) -> AdminUser | None:
        return self.update_password_result


class FakeAdminUnitOfWork:
    def __init__(
        self,
        *,
        admin: AdminUser | None = None,
        domain: Domain | None = None,
        active_admin_count: int = 2,
        fail_commit: bool = False,
    ) -> None:
        self.admin_users = FakeAdminUsers(admin=admin, active_admin_count=active_admin_count)
        self.domains = FakeDomains(domain)
        self.journal_events = FakeJournalEvents()
        self.fail_commit = fail_commit
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self) -> FakeAdminUnitOfWork:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1
        if self.fail_commit:
            raise IntegrityError("statement", {}, Exception("race"))

    async def rollback(self) -> None:
        self.rollbacks += 1


def test_admin_user_payload_validators_reject_invalid_values() -> None:
    with pytest.raises(ValidationError, match="Unsupported admin role"):
        AdminUserRolesUpdate(roles=["owner"])

    with pytest.raises(ValidationError, match="Admin password must be at least 12 characters"):
        AdminUserPasswordReset(password=SecretStr("short"))


@pytest.mark.asyncio
async def test_create_admin_user_rolls_back_integrity_race() -> None:
    uow = FakeAdminUnitOfWork(fail_commit=True)

    with pytest.raises(HTTPException) as exc_info:
        await create_admin_user(
            AdminUserCreate(
                email="race@retos.dev",
                password=SecretStr("race-password"),
                roles=["admin"],
            ),
            actor="admin@retos.dev",
            uow=uow,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Admin user already exists"
    assert uow.rollbacks == 1


@pytest.mark.asyncio
async def test_update_admin_user_status_rejects_last_active_admin() -> None:
    admin = make_admin(admin_id="target-admin", email="target@retos.dev")
    uow = FakeAdminUnitOfWork(admin=admin, active_admin_count=1)

    with pytest.raises(HTTPException) as exc_info:
        await update_admin_user_status(
            "target-admin",
            AdminUserStatusUpdate(is_active=False),
            actor="ops@retos.dev",
            uow=uow,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "At least one active admin role is required"


@pytest.mark.asyncio
async def test_update_admin_user_status_rejects_missing_after_update() -> None:
    uow = FakeAdminUnitOfWork(admin=make_admin(admin_id="target-admin"))
    uow.admin_users.update_active_result = None

    with pytest.raises(HTTPException) as exc_info:
        await update_admin_user_status(
            "target-admin",
            AdminUserStatusUpdate(is_active=False),
            actor="ops@retos.dev",
            uow=uow,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Admin user not found"


@pytest.mark.asyncio
async def test_create_admin_user_domain_grant_rolls_back_integrity_race() -> None:
    uow = FakeAdminUnitOfWork(
        admin=make_admin(admin_id="viewer-1", roles=("viewer",)),
        domain=make_domain("domain-1"),
        fail_commit=True,
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_admin_user_domain_grant(
            "viewer-1",
            AdminUserDomainGrantCreate(domain_id="domain-1"),
            actor="admin@retos.dev",
            uow=uow,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Domain grant already exists"
    assert uow.rollbacks == 1


@pytest.mark.asyncio
async def test_update_admin_user_roles_rejects_last_active_admin_role() -> None:
    admin = make_admin(admin_id="target-admin", email="target@retos.dev")
    uow = FakeAdminUnitOfWork(admin=admin, active_admin_count=1)

    with pytest.raises(HTTPException) as exc_info:
        await update_admin_user_roles(
            "target-admin",
            AdminUserRolesUpdate(roles=["viewer"]),
            actor="ops@retos.dev",
            uow=uow,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "At least one active admin role is required"


@pytest.mark.asyncio
async def test_update_admin_user_roles_rejects_missing_after_update() -> None:
    uow = FakeAdminUnitOfWork(admin=make_admin(admin_id="target-admin"))
    uow.admin_users.update_roles_result = None

    with pytest.raises(HTTPException) as exc_info:
        await update_admin_user_roles(
            "target-admin",
            AdminUserRolesUpdate(roles=["admin", "viewer"]),
            actor="ops@retos.dev",
            uow=uow,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Admin user not found"


@pytest.mark.asyncio
async def test_reset_admin_user_password_rejects_missing_after_update() -> None:
    uow = FakeAdminUnitOfWork(admin=make_admin(admin_id="target-admin"))
    uow.admin_users.update_password_result = None

    with pytest.raises(HTTPException) as exc_info:
        await reset_admin_user_password(
            "target-admin",
            AdminUserPasswordReset(password=SecretStr("updated-password")),
            actor="ops@retos.dev",
            uow=uow,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Admin user not found"

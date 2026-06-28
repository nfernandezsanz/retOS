from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator
from sqlalchemy.exc import IntegrityError

from retos.api.dependencies import AdminSubjectDep, UnitOfWorkDep
from retos.core.security import hash_password
from retos.domain.admin import ALLOWED_ADMIN_ROLES, AdminUser, normalize_admin_roles

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


class AdminUserRead(BaseModel):
    id: str
    email: str
    roles: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_admin(cls, admin: AdminUser) -> AdminUserRead:
        return cls(
            id=admin.id,
            email=admin.email,
            roles=list(admin.roles),
            is_active=admin.is_active,
            created_at=admin.created_at,
            updated_at=admin.updated_at,
        )


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: SecretStr
    roles: list[str] = Field(default_factory=lambda: ["admin"])
    is_active: bool = True

    @field_validator("password")
    @classmethod
    def validate_password(cls, password: SecretStr) -> SecretStr:
        if len(password.get_secret_value()) < 12:
            raise ValueError("Admin password must be at least 12 characters")
        return password

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, roles: list[str]) -> list[str]:
        try:
            return list(normalize_admin_roles(roles))
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class AdminUserStatusUpdate(BaseModel):
    is_active: bool


class AdminUserRolesUpdate(BaseModel):
    roles: list[str]

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, roles: list[str]) -> list[str]:
        try:
            return list(normalize_admin_roles(roles))
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class AdminUserPasswordReset(BaseModel):
    password: SecretStr

    @field_validator("password")
    @classmethod
    def validate_password(cls, password: SecretStr) -> SecretStr:
        if len(password.get_secret_value()) < 12:
            raise ValueError("Admin password must be at least 12 characters")
        return password


@router.get("", response_model=list[AdminUserRead])
async def list_admin_users(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
) -> list[AdminUserRead]:
    async with uow:
        admins = await uow.admin_users.list(limit=100)
    return [AdminUserRead.from_admin(admin) for admin in admins]


@router.post("", response_model=AdminUserRead, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    payload: AdminUserCreate,
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
) -> AdminUserRead:
    email = str(payload.email).lower()
    async with uow:
        existing = await uow.admin_users.get_by_email(email)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Admin user already exists",
            )
        admin = await uow.admin_users.add(
            email=email,
            password_hash=hash_password(payload.password.get_secret_value()),
            roles=tuple(payload.roles),
            is_active=payload.is_active,
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="admin_user.created",
            entity_type="admin_user",
            entity_id=admin.id,
            payload={
                "email": admin.email,
                "roles": list(admin.roles),
                "is_active": admin.is_active,
            },
        )
        try:
            await uow.commit()
        except IntegrityError as exc:
            await uow.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Admin user already exists",
            ) from exc
    return AdminUserRead.from_admin(admin)


@router.patch("/{admin_user_id}/status", response_model=AdminUserRead)
async def update_admin_user_status(
    admin_user_id: str,
    payload: AdminUserStatusUpdate,
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
) -> AdminUserRead:
    async with uow:
        admin = await uow.admin_users.get(admin_user_id)
        if admin is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Admin user not found",
            )
        if admin.email == actor and not payload.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You cannot deactivate your own admin account",
            )
        active_admin_count = await uow.admin_users.count_active_admins()
        if (
            admin.is_active
            and not payload.is_active
            and "admin" in admin.roles
            and active_admin_count <= 1
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one active admin role is required",
            )
        updated = await uow.admin_users.update_active(
            admin_user_id=admin_user_id,
            is_active=payload.is_active,
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Admin user not found",
            )
        await uow.journal_events.add(
            actor=actor,
            event_type="admin_user.status_updated",
            entity_type="admin_user",
            entity_id=updated.id,
            payload={
                "email": updated.email,
                "from_active": admin.is_active,
                "to_active": updated.is_active,
            },
        )
        await uow.commit()
    return AdminUserRead.from_admin(updated)


@router.patch("/{admin_user_id}/roles", response_model=AdminUserRead)
async def update_admin_user_roles(
    admin_user_id: str,
    payload: AdminUserRolesUpdate,
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
) -> AdminUserRead:
    roles = tuple(payload.roles)
    async with uow:
        admin = await uow.admin_users.get(admin_user_id)
        if admin is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Admin user not found",
            )
        if admin.email == actor and "admin" not in roles:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You cannot remove your own admin role",
            )
        active_admin_count = await uow.admin_users.count_active_admins()
        if (
            admin.is_active
            and "admin" in admin.roles
            and "admin" not in roles
            and active_admin_count <= 1
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one active admin role is required",
            )
        updated = await uow.admin_users.update_roles(
            admin_user_id=admin_user_id,
            roles=roles,
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Admin user not found",
            )
        await uow.journal_events.add(
            actor=actor,
            event_type="admin_user.roles_updated",
            entity_type="admin_user",
            entity_id=updated.id,
            payload={
                "email": updated.email,
                "from_roles": list(admin.roles),
                "to_roles": list(updated.roles),
                "allowed_roles": sorted(ALLOWED_ADMIN_ROLES),
            },
        )
        await uow.commit()
    return AdminUserRead.from_admin(updated)


@router.post("/{admin_user_id}/password", response_model=AdminUserRead)
async def reset_admin_user_password(
    admin_user_id: str,
    payload: AdminUserPasswordReset,
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
) -> AdminUserRead:
    async with uow:
        admin = await uow.admin_users.get(admin_user_id)
        if admin is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Admin user not found",
            )
        updated = await uow.admin_users.update_password(
            admin_user_id=admin_user_id,
            password_hash=hash_password(payload.password.get_secret_value()),
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Admin user not found",
            )
        await uow.journal_events.add(
            actor=actor,
            event_type="admin_user.password_reset",
            entity_type="admin_user",
            entity_id=updated.id,
            payload={"email": updated.email},
        )
        await uow.commit()
    return AdminUserRead.from_admin(updated)

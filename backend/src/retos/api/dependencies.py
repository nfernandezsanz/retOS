from typing import Annotated, Literal, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from retos.core.config import Settings
from retos.core.security import TokenError, decode_access_token
from retos.persistence.database import SessionFactory
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork

bearer = HTTPBearer(auto_error=False)


def get_request_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_session_factory(request: Request) -> SessionFactory:
    return cast(SessionFactory, request.app.state.session_factory)


SettingsDep = Annotated[Settings, Depends(get_request_settings)]
SessionFactoryDep = Annotated[SessionFactory, Depends(get_session_factory)]
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def get_unit_of_work(factory: SessionFactoryDep) -> SQLAlchemyUnitOfWork:
    return SQLAlchemyUnitOfWork(factory)


UnitOfWorkDep = Annotated[SQLAlchemyUnitOfWork, Depends(get_unit_of_work)]

Role = Literal["admin", "viewer"]
ROLE_ORDER: dict[Role, int] = {"viewer": 0, "admin": 1}


class AuthPrincipal(BaseModel):
    subject: str
    roles: tuple[str, ...]

    def has_role(self, required: Role) -> bool:
        required_rank = ROLE_ORDER[required]
        return any(ROLE_ORDER.get(cast(Role, role), -1) >= required_rank for role in self.roles)


async def require_principal(
    credentials: BearerDep,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
) -> AuthPrincipal:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    async with uow:
        admin = await uow.admin_users.get_by_email(claims.subject)
    if admin is None or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    persisted_roles = tuple(admin.roles)
    if not set(claims.roles).issubset(set(persisted_roles)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token roles are no longer valid",
        )
    return AuthPrincipal(subject=claims.subject, roles=persisted_roles)


async def require_viewer(principal: Annotated[AuthPrincipal, Depends(require_principal)]) -> str:
    if not principal.has_role("viewer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewer role required",
        )
    return principal.subject


async def require_admin(principal: Annotated[AuthPrincipal, Depends(require_principal)]) -> str:
    if not principal.has_role("admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return principal.subject


async def ensure_domain_access(*, actor: str, domain_id: str, uow: SQLAlchemyUnitOfWork) -> None:
    allowed = await uow.admin_users.can_access_domain(email=actor, domain_id=domain_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Domain access required",
        )


async def visible_domain_ids_for_actor(
    *,
    actor: str,
    uow: SQLAlchemyUnitOfWork,
) -> set[str] | None:
    admin = await uow.admin_users.get_by_email(actor)
    if admin is None:
        return set()
    if "admin" in admin.roles:
        return None
    grants = await uow.admin_users.list_domain_grants(admin.id)
    return {grant.domain_id for grant in grants}


ViewerSubjectDep = Annotated[str, Depends(require_viewer)]
AdminSubjectDep = Annotated[str, Depends(require_admin)]

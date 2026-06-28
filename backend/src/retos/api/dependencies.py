from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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


async def require_admin(
    credentials: BearerDep,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
) -> str:
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
    if "admin" not in claims.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    async with uow:
        admin = await uow.admin_users.get_by_email(claims.subject)
    if admin is None or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if "admin" not in admin.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return claims.subject


AdminSubjectDep = Annotated[str, Depends(require_admin)]

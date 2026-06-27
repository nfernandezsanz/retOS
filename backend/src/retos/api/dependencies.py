from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from retos.core.config import Settings
from retos.core.security import TokenError, decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_request_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


SettingsDep = Annotated[Settings, Depends(get_request_settings)]
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def require_admin(
    credentials: BearerDep,
    settings: SettingsDep,
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
    return claims.subject


AdminSubjectDep = Annotated[str, Depends(require_admin)]

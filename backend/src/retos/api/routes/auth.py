from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, SecretStr

from retos.api.dependencies import SettingsDep
from retos.core.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, settings: SettingsDep) -> TokenResponse:
    bootstrap = settings.bootstrap_admin
    if bootstrap is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bootstrap admin is not configured",
        )

    password = payload.password.get_secret_value()
    if payload.email != bootstrap.email or not verify_password(password, bootstrap.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        subject=bootstrap.email,
        roles=("admin",),
        settings=settings,
    )
    return TokenResponse(access_token=token)

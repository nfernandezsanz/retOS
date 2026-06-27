from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, SecretStr

from retos.api.dependencies import SettingsDep, UnitOfWorkDep
from retos.core.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
) -> TokenResponse:
    password = payload.password.get_secret_value()
    async with uow:
        admin = await uow.admin_users.get_by_email(str(payload.email))

    if admin is None or not admin.is_active or not verify_password(password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        subject=admin.email,
        roles=("admin",),
        settings=settings,
    )
    return TokenResponse(access_token=token)

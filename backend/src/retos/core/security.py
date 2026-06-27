from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import jwt
from pwdlib import PasswordHash
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from retos.core.config import Settings

ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()


class TokenError(ValueError):
    """Raised when an access token cannot be trusted."""


class TokenClaims(BaseModel):
    subject: str
    roles: tuple[str, ...] = Field(default_factory=tuple)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(
    *,
    subject: str,
    roles: tuple[str, ...],
    settings: Settings,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.access_token_ttl_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "roles": list(roles),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(issued_at.timestamp()),
        "nbf": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    encoded = jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=ALGORITHM,
    )
    return cast(str, encoded)


def decode_access_token(token: str, settings: Settings) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "iss", "aud", "iat", "nbf", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid access token") from exc

    subject = payload.get("sub")
    roles = payload.get("roles", [])
    if not isinstance(subject, str) or not subject:
        raise TokenError("Invalid token subject")
    if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
        raise TokenError("Invalid token roles")
    return TokenClaims(subject=subject, roles=tuple(roles))

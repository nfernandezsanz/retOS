from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import SecretStr

from retos.core.config import Settings
from retos.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")

    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)


def test_token_roundtrip() -> None:
    settings = Settings(
        env="test",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
    )
    token = create_access_token(subject="admin@retos.dev", roles=("admin",), settings=settings)

    claims = decode_access_token(token, settings)

    assert claims.subject == "admin@retos.dev"
    assert claims.roles == ("admin",)


def test_expired_token_is_rejected() -> None:
    settings = Settings(
        env="test",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
    )
    token = create_access_token(
        subject="admin@retos.dev",
        roles=("admin",),
        settings=settings,
        now=datetime.now(UTC) - timedelta(days=1),
    )

    with pytest.raises(TokenError):
        decode_access_token(token, settings)


def test_invalid_token_is_rejected() -> None:
    settings = Settings(
        env="test",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
    )

    with pytest.raises(TokenError):
        decode_access_token("not-a-token", settings)


def test_token_with_invalid_roles_is_rejected() -> None:
    settings = Settings(
        env="test",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
    )
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "admin@retos.dev",
            "roles": "admin",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )

    with pytest.raises(TokenError, match="roles"):
        decode_access_token(token, settings)

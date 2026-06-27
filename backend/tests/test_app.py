import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import SecretStr

from retos.api.app import create_app
from retos.api.dependencies import require_admin
from retos.core.config import Settings
from retos.core.security import create_access_token


def test_app_registers_expected_routes(settings: Settings) -> None:
    app = create_app(settings)
    route_paths = set(app.openapi()["paths"])

    assert "/healthz" in route_paths
    assert "/auth/login" in route_paths
    assert "/domains" in route_paths
    assert "/domains/{domain_id}/sources" in route_paths
    assert "/domains/{domain_id}/documents" in route_paths
    assert "/documents/{document_id}/versions" in route_paths
    assert "/document-versions/{version_id}/artifacts" in route_paths
    assert "/document-versions/{version_id}/segments" in route_paths
    assert "/jobs" in route_paths
    assert "/jobs/{job_id}/start" in route_paths
    assert "/jobs/{job_id}/complete" in route_paths
    assert "/llm/providers" in route_paths
    assert "/domains/{domain_id}/queries" in route_paths
    assert "/evals/smoke" in route_paths
    assert "/evals/squad" in route_paths
    assert "/evals/runs" in route_paths
    assert "/audit/journal-events" in route_paths
    assert "/audit/progress-events" in route_paths
    assert "/events/progress" in route_paths


def test_app_rejects_insecure_runtime_settings() -> None:
    settings = Settings(env="production", jwt_secret=SecretStr("short"))

    try:
        create_app(settings)
    except ValueError as exc:
        assert "JWT_SECRET" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected insecure settings to fail")


def test_require_admin_accepts_valid_token(settings: Settings) -> None:
    token = create_access_token(
        subject="admin@retos.dev",
        roles=("admin",),
        settings=settings,
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    assert require_admin(credentials, settings) == "admin@retos.dev"


def test_require_admin_rejects_non_admin_token(settings: Settings) -> None:
    token = create_access_token(
        subject="user@retos.dev",
        roles=("viewer",),
        settings=settings,
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc:
        require_admin(credentials, settings)

    assert exc.value.status_code == 403

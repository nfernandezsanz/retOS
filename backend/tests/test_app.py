from pydantic import SecretStr

from retos.api.app import create_app
from retos.core.config import Settings


def test_app_registers_expected_routes(settings: Settings) -> None:
    app = create_app(settings)
    route_paths = set(app.openapi()["paths"])

    assert "/healthz" in route_paths
    assert "/readyz" in route_paths
    assert "/versionz" in route_paths
    assert "/auth/login" in route_paths
    assert "/admin/users" in route_paths
    assert "/admin/users/{admin_user_id}/status" in route_paths
    assert "/admin/users/{admin_user_id}/password" in route_paths
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
    assert "/domains/{domain_id}/ingestions/upload" in route_paths
    assert "/evals/smoke" in route_paths
    assert "/evals/squad" in route_paths
    assert "/evals/hotpotqa-agent" in route_paths
    assert "/evals/runs" in route_paths
    assert "/evals/runs/compare" in route_paths
    assert "/audit/journal-events" in route_paths
    assert "/audit/progress-events" in route_paths
    assert "/audit/export" in route_paths
    assert "/events/progress" in route_paths


def test_app_rejects_insecure_runtime_settings() -> None:
    settings = Settings(env="production", jwt_secret=SecretStr("short"))

    try:
        create_app(settings)
    except ValueError as exc:
        assert "JWT_SECRET" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected insecure settings to fail")

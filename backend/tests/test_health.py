from fastapi.testclient import TestClient

from retos.api.app import create_app
from retos.core.config import Settings


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "retos-api"}


def test_readyz_checks_database(client: TestClient) -> None:
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "retos-api",
        "components": {"database": "ok"},
    }


def test_versionz_reports_runtime_metadata(settings: Settings) -> None:
    app = create_app(
        settings.model_copy(
            update={
                "version": "2026.06.29-local",
                "revision": "abc1234",
                "created": "2026-06-29T12:00:00Z",
            }
        )
    )

    with TestClient(app) as test_client:
        response = test_client.get("/versionz")

    assert response.status_code == 200
    assert response.json() == {
        "service": "retos-api",
        "version": "2026.06.29-local",
        "revision": "abc1234",
        "created": "2026-06-29T12:00:00Z",
    }


def test_readyz_reports_database_failure(settings: Settings) -> None:
    class FailingSession:
        async def __aenter__(self) -> FailingSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def execute(self, statement: object) -> None:
            raise RuntimeError("database unavailable")

    app = create_app(settings)
    with TestClient(app) as test_client:
        app.state.session_factory = lambda: FailingSession()
        response = test_client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "service": "retos-api",
        "components": {"database": "unavailable"},
    }

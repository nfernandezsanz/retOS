from pathlib import Path
from typing import cast

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from retos.api.app import create_app
from retos.api.routes.demo import DemoSeedRequest, seed_demo
from retos.core.config import Settings
from retos.persistence.database import SessionFactory


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_demo_seed_requires_admin_token(client: TestClient) -> None:
    response = client.post("/demo/seed", json={"rebuild_index": True})

    assert response.status_code == 401


def test_demo_seed_endpoint_creates_searchable_fixture(
    settings: Settings,
    tmp_path: Path,
) -> None:
    local_settings = settings.model_copy(update={"index_root": str(tmp_path / "index")})
    with TestClient(create_app(local_settings)) as client:
        _assert_demo_seed_endpoint_creates_searchable_fixture(client)


def _assert_demo_seed_endpoint_creates_searchable_fixture(client: TestClient) -> None:
    headers = auth_headers(client)

    created = client.post("/demo/seed", json={"rebuild_index": True}, headers=headers)
    assert created.status_code == 200
    created_body = created.json()
    assert created_body["created_documents"] == 3
    assert created_body["skipped_documents"] == 0
    assert created_body["indexed_segments"] >= 3

    repeated = client.post("/demo/seed", json={"rebuild_index": True}, headers=headers)
    assert repeated.status_code == 200
    repeated_body = repeated.json()
    assert repeated_body["domain_id"] == created_body["domain_id"]
    assert repeated_body["source_id"] == created_body["source_id"]
    assert repeated_body["created_documents"] == 0
    assert repeated_body["skipped_documents"] == 3

    search = client.get(
        f"/domains/{created_body['domain_id']}/search",
        params={"q": "Apollo guidance"},
        headers=headers,
    )
    assert search.status_code == 200
    hits = search.json()["hits"]
    assert hits
    assert hits[0]["title"] == "Apollo Guidance Notes"


@pytest.mark.asyncio
async def test_demo_seed_is_disabled_in_production(settings: Settings) -> None:
    production_settings = settings.model_copy(
        update={
            "env": "production",
            "jwt_secret": SecretStr("production-secret-value-that-is-long-enough"),
            "bootstrap_admin_password": SecretStr("production-admin-password"),
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await seed_demo(
            DemoSeedRequest(rebuild_index=True),
            "admin@retos.dev",
            session_factory=cast(SessionFactory, None),
            settings=production_settings,
        )

    assert exc_info.value.status_code == 403

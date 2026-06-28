from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retos.agent.harness import create_research_harness
from retos.agent.service import (
    AgentQueryError,
    budget_from_payload,
    build_grounded_answer,
    fail_agent_query_job,
    hits_within_budget,
    run_agent_query,
)
from retos.api.app import create_app
from retos.api.routes.agent import enqueue_agent_query
from retos.core.config import Settings
from retos.domain.documents import utc_now
from retos.domain.jobs import Job
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork
from retos.search.index import SearchHit, TantivySearchIndex


@pytest.fixture
def agent_client(settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'retos-agent.db'}",
            "database_create_all": True,
            "index_root": str(tmp_path / "index"),
        }
    )
    with TestClient(create_app(local_settings)) as test_client:
        yield test_client


@pytest.fixture
def agent_admin_headers(agent_client: TestClient) -> dict[str, str]:
    response = agent_client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_agent_fixture(client: TestClient, headers: dict[str, str]) -> str:
    domain_response = client.post(
        "/domains",
        json={"slug": "agent-domain", "name": "Agent Domain"},
        headers=headers,
    )
    domain_id = domain_response.json()["id"]
    source_response = client.post(
        f"/domains/{domain_id}/sources",
        json={"kind": "upload", "name": "Agent source", "uri": "inline://agent"},
        headers=headers,
    )
    document_response = client.post(
        f"/domains/{domain_id}/documents",
        json={
            "source_id": source_response.json()["id"],
            "title": "Apollo Guidance Memo",
            "content_hash": "sha256:aaaaaaaaaaaaaaaa",
            "source_uri": "inline://agent/apollo.txt",
            "size_bytes": 120,
        },
        headers=headers,
    )
    versions = client.get(
        f"/documents/{document_response.json()['id']}/versions",
        headers=headers,
    )
    version_id = versions.json()[0]["id"]
    client.post(
        f"/document-versions/{version_id}/segments",
        json={
            "ordinal": 0,
            "text": "Apollo guidance computers used deterministic checklists.",
            "anchor": "paragraph=0",
            "token_count": 6,
            "content_hash": "sha256:bbbbbbbbbbbbbbbb",
        },
        headers=headers,
    )
    client.post(
        f"/document-versions/{version_id}/segments",
        json={
            "ordinal": 1,
            "text": "Apollo mission reviews required cited evidence and audit trails.",
            "anchor": "paragraph=1",
            "token_count": 8,
            "content_hash": "sha256:cccccccccccccccc",
        },
        headers=headers,
    )
    rebuild = client.post(
        f"/domains/{domain_id}/index/rebuild",
        json={"run_inline": True},
        headers=headers,
    )
    assert rebuild.status_code == 202
    assert rebuild.json()["status"] == "succeeded"
    return domain_id


def test_agent_query_requires_admin(agent_client: TestClient) -> None:
    response = agent_client.post(
        "/domains/missing/queries",
        json={"question": "What is indexed?"},
    )

    assert response.status_code == 401


def test_agent_query_requires_existing_index(
    agent_client: TestClient,
    agent_admin_headers: dict[str, str],
) -> None:
    domain_response = agent_client.post(
        "/domains",
        json={"slug": "no-index", "name": "No Index"},
        headers=agent_admin_headers,
    )

    response = agent_client.post(
        f"/domains/{domain_response.json()['id']}/queries",
        json={"question": "What evidence exists?", "run_inline": True},
        headers=agent_admin_headers,
    )

    assert response.status_code == 409
    assert "Search index" in response.json()["detail"]


def test_agent_query_rejects_missing_domain(
    agent_client: TestClient,
    agent_admin_headers: dict[str, str],
) -> None:
    response = agent_client.post(
        "/domains/missing/queries",
        json={"question": "What evidence exists?", "run_inline": True},
        headers=agent_admin_headers,
    )

    assert response.status_code == 404


def test_agent_query_runs_inline_with_citations(
    agent_client: TestClient,
    agent_admin_headers: dict[str, str],
) -> None:
    domain_id = create_agent_fixture(agent_client, agent_admin_headers)

    response = agent_client.post(
        f"/domains/{domain_id}/queries",
        json={"question": "What did Apollo computers use?", "limit": 5, "run_inline": True},
        headers=agent_admin_headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job"]["kind"] == "agent.query"
    assert body["job"]["status"] == "succeeded"
    assert body["job"]["payload"]["result"]["provider"] == "local"
    assert body["job"]["payload"]["budget"]["max_citations"] == 5
    assert body["job"]["payload"]["result"]["usage"]["within_budget"] is True
    assert body["result"]["provider"] == "local"
    assert body["result"]["model"] == "ollama:gemma4"
    assert body["result"]["usage"]["budget"]["max_searches"] == 8
    assert body["result"]["usage"]["search_count"] == 1
    assert "Apollo guidance computers" in body["result"]["answer"]
    assert body["result"]["citations"][0]["title"] == "Apollo Guidance Memo"
    assert body["result"]["citations"][0]["anchor"] == "paragraph=0"


def test_agent_query_applies_citation_budget(
    agent_client: TestClient,
    agent_admin_headers: dict[str, str],
) -> None:
    domain_id = create_agent_fixture(agent_client, agent_admin_headers)

    response = agent_client.post(
        f"/domains/{domain_id}/queries",
        json={
            "question": "What did Apollo reviews require?",
            "limit": 5,
            "run_inline": True,
            "budget": {"max_citations": 1},
        },
        headers=agent_admin_headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert len(body["result"]["citations"]) == 1
    assert body["result"]["usage"]["citation_count"] == 1
    assert body["result"]["usage"]["budget"]["max_citations"] == 1


def test_agent_query_applies_evidence_token_budget(
    agent_client: TestClient,
    agent_admin_headers: dict[str, str],
) -> None:
    domain_id = create_agent_fixture(agent_client, agent_admin_headers)

    response = agent_client.post(
        f"/domains/{domain_id}/queries",
        json={
            "question": "What evidence exists?",
            "run_inline": True,
            "budget": {"max_evidence_tokens": 1},
        },
        headers=agent_admin_headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["result"]["citations"] == []
    assert body["result"]["usage"]["evidence_tokens"] == 0
    assert "could not find enough indexed evidence" in body["result"]["answer"]


def test_agent_query_rejects_invalid_budget(
    agent_client: TestClient,
    agent_admin_headers: dict[str, str],
) -> None:
    domain_response = agent_client.post(
        "/domains",
        json={"slug": "invalid-budget", "name": "Invalid Budget"},
        headers=agent_admin_headers,
    )

    response = agent_client.post(
        f"/domains/{domain_response.json()['id']}/queries",
        json={"question": "What?", "budget": {"max_citations": 0}},
        headers=agent_admin_headers,
    )

    assert response.status_code == 422


def test_agent_query_can_queue_for_worker(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_settings = settings.model_copy(
        update={
            "env": "development",
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'retos-agent-queued.db'}",
            "database_create_all": True,
            "index_root": str(tmp_path / "index"),
        }
    )
    delayed: list[str] = []
    monkeypatch.setattr(
        "retos.api.routes.agent.agent_query_job.delay",
        lambda job_id: delayed.append(job_id),
    )

    with TestClient(create_app(local_settings)) as client:
        headers = agent_admin_headers_for(client)
        domain_response = client.post(
            "/domains",
            json={"slug": "queued-agent", "name": "Queued Agent"},
            headers=headers,
        )
        response = client.post(
            f"/domains/{domain_response.json()['id']}/queries",
            json={"question": "What should the worker answer?"},
            headers=headers,
        )

    assert response.status_code == 202
    body = response.json()
    assert body["job"]["status"] == "queued"
    assert body["result"] is None
    assert delayed == [body["job"]["id"]]


def agent_admin_headers_for(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_build_grounded_answer_abstains_without_hits() -> None:
    answer = build_grounded_answer("What happened?", [])

    assert "could not find enough indexed evidence" in answer


def test_agent_budget_defaults_and_validation() -> None:
    budget = budget_from_payload({})

    assert budget.max_searches == 8
    assert budget.max_citations == 5
    assert budget.max_evidence_tokens == 16_000
    assert budget.max_runtime_seconds == 120
    with pytest.raises(AgentQueryError, match="budget must be an object"):
        budget_from_payload({"budget": "invalid"})
    with pytest.raises(AgentQueryError, match="max_searches"):
        budget_from_payload({"budget": {"max_searches": True}})
    with pytest.raises(AgentQueryError, match="max_citations"):
        budget_from_payload({"budget": {"max_citations": "many"}})


def test_hits_within_budget_caps_citations_and_evidence() -> None:
    budget = budget_from_payload({"budget": {"max_citations": 2, "max_evidence_tokens": 4}})
    hits = [
        SearchHit(
            segment_id="s1",
            document_id="d1",
            document_version_id="v1",
            title="One",
            text="one two",
            anchor=None,
            ordinal=0,
            score=3.0,
        ),
        SearchHit(
            segment_id="s2",
            document_id="d1",
            document_version_id="v1",
            title="Two",
            text="three four",
            anchor=None,
            ordinal=1,
            score=2.0,
        ),
        SearchHit(
            segment_id="s3",
            document_id="d1",
            document_version_id="v1",
            title="Three",
            text="five six",
            anchor=None,
            ordinal=2,
            score=1.0,
        ),
    ]

    assert [hit.segment_id for hit in hits_within_budget(hits, budget)] == ["s1", "s2"]
    tiny_budget = budget_from_payload({"budget": {"max_evidence_tokens": 1}})
    assert hits_within_budget(hits, tiny_budget) == []


@pytest.mark.asyncio
async def test_run_agent_query_rejects_missing_job(
    agent_client: TestClient,
    settings: Settings,
) -> None:
    with pytest.raises(AgentQueryError, match="Job not found"):
        await run_agent_query(
            job_id="missing",
            uow=SQLAlchemyUnitOfWork(agent_client.app.state.session_factory),
            index=TantivySearchIndex(settings.index_root),
            settings=settings,
        )


@pytest.mark.asyncio
async def test_fail_agent_query_job_ignores_missing_job(agent_client: TestClient) -> None:
    await fail_agent_query_job(
        job_id="missing",
        uow=SQLAlchemyUnitOfWork(agent_client.app.state.session_factory),
        error="not found",
        actor="test-suite",
    )


def test_enqueue_agent_query_dispatches_celery_task(monkeypatch: pytest.MonkeyPatch) -> None:
    delayed: list[str] = []
    now = utc_now()
    job = Job(
        id="job-agent",
        kind="agent.query",
        status="queued",
        domain_id="domain-agent",
        source_id=None,
        payload={"question": "What happened?"},
        error=None,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(
        "retos.api.routes.agent.agent_query_job.delay",
        lambda job_id: delayed.append(job_id),
    )

    enqueue_agent_query(job)

    assert delayed == ["job-agent"]


def test_create_research_harness_uses_deepagents(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_create_deep_agent(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"graph": "fake"}

    monkeypatch.setattr("retos.agent.harness.create_deep_agent", fake_create_deep_agent)

    harness = create_research_harness(settings=settings, tools=[])

    assert harness == {"graph": "fake"}
    assert calls[0]["model"] == "ollama:gemma4"
    assert calls[0]["name"] == "retos-research-agent"

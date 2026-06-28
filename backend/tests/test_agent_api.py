from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retos.agent.harness import create_research_harness
from retos.agent.service import (
    AgentQueryError,
    budget_from_payload,
    build_grounded_answer,
    extract_harness_answer,
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
    client.post(
        f"/document-versions/{version_id}/segments",
        json={
            "ordinal": 2,
            "text": "Engineering signoff followed the review checklist.",
            "anchor": "paragraph=2",
            "token_count": 6,
            "content_hash": "sha256:dddddddddddddddd",
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


def create_multi_document_agent_fixture(client: TestClient, headers: dict[str, str]) -> str:
    domain_response = client.post(
        "/domains",
        json={"slug": "multi-agent-domain", "name": "Multi Agent Domain"},
        headers=headers,
    )
    domain_id = domain_response.json()["id"]
    source_response = client.post(
        f"/domains/{domain_id}/sources",
        json={"kind": "upload", "name": "Multi source", "uri": "inline://multi-agent"},
        headers=headers,
    )
    source_id = source_response.json()["id"]

    document_payloads = [
        (
            "Apollo Review Notes",
            "inline://multi-agent/apollo.txt",
            "sha256:aaaaaaaaaaaaaa01",
            "Apollo checklist review confirmed guidance readiness.",
            "sha256:bbbbbbbbbbbbbb01",
        ),
        (
            "Telemetry Review Notes",
            "inline://multi-agent/telemetry.txt",
            "sha256:aaaaaaaaaaaaaa02",
            "Mission checklist review compared guidance telemetry.",
            "sha256:bbbbbbbbbbbbbb02",
        ),
    ]
    for title, source_uri, document_hash, segment_text, segment_hash in document_payloads:
        document_response = client.post(
            f"/domains/{domain_id}/documents",
            json={
                "source_id": source_id,
                "title": title,
                "content_hash": document_hash,
                "source_uri": source_uri,
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
                "text": segment_text,
                "anchor": "paragraph=0",
                "token_count": len(segment_text.split()),
                "content_hash": segment_hash,
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
    assert body["job"]["payload"]["result"]["runtime"] == "deterministic"
    assert body["job"]["payload"]["result"]["evidence_audit"]["grounded"] is True
    assert body["job"]["payload"]["result"]["contradiction_audit"]["conflict_count"] == 0
    assert body["job"]["payload"]["result"]["multi_hop_audit"]["checked"] is True
    assert body["job"]["payload"]["result"]["query_plan"]["strategy"] == "direct_evidence_lookup"
    assert body["job"]["payload"]["result"]["evidence_route"]["coverage_level"] in {
        "single_segment",
        "single_document",
    }
    assert isinstance(body["job"]["payload"]["result"]["neighbor_context"], list)
    assert body["job"]["payload"]["budget"]["max_citations"] == 5
    assert body["job"]["payload"]["result"]["usage"]["within_budget"] is True
    assert body["result"]["provider"] == "local"
    assert body["result"]["model"] == "ollama:gemma4"
    assert body["result"]["runtime"] == "deterministic"
    assert body["result"]["evidence_audit"]["grounded"] is True
    assert body["result"]["evidence_audit"]["cited_segment_ids"] == [
        citation["segment_id"] for citation in body["result"]["citations"]
    ]
    assert body["result"]["contradiction_audit"]["checked"] is True
    assert body["result"]["contradiction_audit"]["conflict_count"] == 0
    assert body["result"]["multi_hop_audit"]["checked"] is True
    assert body["result"]["multi_hop_audit"]["status"] in {
        "not_required",
        "opportunistic_multi_document",
    }
    assert body["result"]["query_plan"]["expected_evidence"] == "single_document_or_abstain"
    assert body["result"]["query_plan"]["steps"][0]["name"] == "search"
    assert body["result"]["evidence_route"]["segment_count"] == len(body["result"]["citations"])
    assert body["result"]["evidence_route"]["document_count"] == 1
    assert body["result"]["evidence_route"]["has_neighbor_context"] is bool(
        body["result"]["neighbor_context"]
    )
    assert body["result"]["usage"]["budget"]["max_searches"] == 8
    assert body["result"]["usage"]["search_count"] == 1
    assert isinstance(body["result"]["neighbor_context"], list)
    assert body["result"]["usage"]["evidence_tokens"] >= sum(
        citation["text"].count(" ") + 1 for citation in body["result"]["citations"]
    )
    assert "Apollo guidance computers" in body["result"]["answer"]
    assert "Evidence ledger:" in body["result"]["answer"]
    assert body["result"]["citations"][0]["title"] == "Apollo Guidance Memo"
    assert body["result"]["citations"][0]["anchor"] == "paragraph=0"


def test_agent_query_records_multi_hop_audit_for_cross_document_evidence(
    agent_client: TestClient,
    agent_admin_headers: dict[str, str],
) -> None:
    domain_id = create_multi_document_agent_fixture(agent_client, agent_admin_headers)

    response = agent_client.post(
        f"/domains/{domain_id}/queries",
        json={
            "question": "Compare Apollo checklist review and telemetry guidance",
            "limit": 5,
            "run_inline": True,
            "budget": {"max_citations": 5, "max_evidence_tokens": 80},
        },
        headers=agent_admin_headers,
    )

    assert response.status_code == 202
    body = response.json()
    audit = body["result"]["multi_hop_audit"]
    assert audit["checked"] is True
    assert audit["requires_multi_hop"] is True
    assert audit["status"] == "supported_multi_document"
    assert audit["document_count"] == 2
    assert {"checklist", "review", "guidance"}.issuperset(set(audit["bridge_terms"]))
    assert audit["warnings"] == []
    plan = body["result"]["query_plan"]
    assert plan["strategy"] == "multi_hop_evidence_route"
    assert plan["requires_multi_hop"] is True
    assert plan["expected_evidence"] == "multi_document"
    assert plan["search_queries"][0] == "Compare Apollo checklist review and telemetry guidance"
    assert body["job"]["payload"]["result"]["query_plan"] == plan
    assert body["result"]["usage"]["search_count"] > 1
    assert body["result"]["evidence_route"]["coverage_level"] == "multi_document"


def test_agent_query_respects_search_budget_for_planned_subqueries(
    agent_client: TestClient,
    agent_admin_headers: dict[str, str],
) -> None:
    domain_id = create_multi_document_agent_fixture(agent_client, agent_admin_headers)

    response = agent_client.post(
        f"/domains/{domain_id}/queries",
        json={
            "question": "Compare Apollo checklist review and telemetry guidance",
            "limit": 5,
            "run_inline": True,
            "budget": {"max_searches": 1, "max_citations": 5, "max_evidence_tokens": 80},
        },
        headers=agent_admin_headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["result"]["query_plan"]["strategy"] == "multi_hop_evidence_route"
    assert body["result"]["usage"]["search_count"] == 1
    assert body["result"]["usage"]["within_budget"] is True


def test_agent_query_expands_neighbor_context_within_evidence_budget(
    agent_client: TestClient,
    agent_admin_headers: dict[str, str],
) -> None:
    domain_id = create_agent_fixture(agent_client, agent_admin_headers)

    response = agent_client.post(
        f"/domains/{domain_id}/queries",
        json={
            "question": "What did Apollo computers use?",
            "limit": 1,
            "run_inline": True,
            "budget": {"max_citations": 1, "max_evidence_tokens": 20},
        },
        headers=agent_admin_headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert len(body["result"]["citations"]) == 1
    assert body["result"]["neighbor_context"][0]["anchor"] == "paragraph=1"
    assert (
        body["result"]["neighbor_context"][0]["source_segment_id"]
        == body["result"]["citations"][0]["segment_id"]
    )
    assert body["result"]["neighbor_context"][0]["distance"] == 1
    assert "audit trails" in body["result"]["neighbor_context"][0]["text"]
    assert body["result"]["evidence_route"]["has_neighbor_context"] is True
    assert body["result"]["evidence_route"]["warnings"] == [
        "single_citation",
        "single_document",
    ]
    assert body["result"]["usage"]["evidence_tokens"] > body["result"]["citations"][0][
        "text"
    ].count(" ")


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
    assert body["result"]["neighbor_context"] == []
    assert body["result"]["evidence_route"]["coverage_level"] == "no_evidence"
    assert body["result"]["evidence_route"]["warnings"] == ["no_citations"]
    assert body["result"]["evidence_audit"]["grounded"] is True
    assert body["result"]["usage"]["evidence_tokens"] == 0
    assert "could not find enough indexed evidence" in body["result"]["answer"]


def test_agent_query_can_use_mocked_deepagents_runtime(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'retos-agent-deep.db'}",
            "database_create_all": True,
            "index_root": str(tmp_path / "index"),
            "agent_runtime": "deepagents",
        }
    )
    invocations: list[dict[str, object]] = []
    tool_names: list[str] = []

    class FakeHarness:
        def invoke(self, payload: dict[str, object], *, config: dict[str, object]) -> object:
            invocations.append({"payload": payload, "config": config})
            messages = payload["messages"]
            assert isinstance(messages, list)
            prompt = messages[0]["content"]  # type: ignore[index]
            assert "Seed evidence returned by search_corpus" in prompt
            assert "Apollo guidance computers" in prompt
            assert "Use map_sources" in prompt
            assert "Use inspect_evidence_table" in prompt
            return {"messages": [{"role": "assistant", "content": "Deep answer without ids."}]}

    def fake_create_research_harness(
        *,
        settings: Settings,
        tools: list[object],
    ) -> FakeHarness:
        assert settings.agent_runtime == "deepagents"
        tool_names.extend(getattr(tool, "__name__", "") for tool in tools)
        return FakeHarness()

    monkeypatch.setattr(
        "retos.agent.service.create_research_harness",
        fake_create_research_harness,
    )

    with TestClient(create_app(local_settings)) as client:
        headers = agent_admin_headers_for(client)
        domain_id = create_agent_fixture(client, headers)
        response = client.post(
            f"/domains/{domain_id}/queries",
            json={"question": "What did Apollo computers use?", "run_inline": True},
            headers=headers,
        )

    assert response.status_code == 202
    body = response.json()
    assert body["result"]["answer"].startswith("Deep answer without ids.")
    assert "Evidence ledger:" in body["result"]["answer"]
    assert body["result"]["runtime"] == "deepagents"
    assert body["result"]["evidence_audit"]["grounded"] is True
    assert body["result"]["evidence_audit"]["cited_segment_ids"] == [
        citation["segment_id"] for citation in body["result"]["citations"]
    ]
    assert body["result"]["contradiction_audit"]["conflict_count"] == 0
    assert body["result"]["evidence_route"]["coverage_level"] in {
        "single_segment",
        "single_document",
    }
    assert body["result"]["usage"]["search_count"] == 1
    assert tool_names == [
        "search_corpus",
        "read_citation",
        "map_sources",
        "inspect_evidence_table",
    ]
    assert invocations[0]["config"] == {"recursion_limit": 25}


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


def test_extract_harness_answer_reads_latest_message_content() -> None:
    answer = extract_harness_answer(
        {
            "messages": [
                {"role": "user", "content": "Question"},
                {"role": "assistant", "content": [{"type": "text", "text": "Final answer"}]},
            ]
        }
    )

    assert answer == "Final answer"


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
    registered: list[tuple[str, object]] = []

    def fake_create_deep_agent(**kwargs: object) -> object:
        calls.append(kwargs)
        return {"graph": "fake"}

    def fake_register_harness_profile(model: str, profile: object) -> None:
        registered.append((model, profile))

    monkeypatch.setattr("retos.agent.harness.create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr(
        "retos.agent.harness.register_harness_profile",
        fake_register_harness_profile,
    )

    def fake_tool() -> str:
        return "ok"

    harness = create_research_harness(settings=settings, tools=[fake_tool])

    assert harness == {"graph": "fake"}
    assert registered[0][0] == "ollama:gemma4"
    assert "execute" in registered[0][1].excluded_tools
    assert "read_file" in registered[0][1].excluded_tools
    assert calls[0]["model"] == "ollama:gemma4"
    assert calls[0]["name"] == "retos-research-agent"
    assert calls[0]["tools"] == [fake_tool]
    assert [subagent["name"] for subagent in calls[0]["subagents"]] == [
        "evidence_checker",
        "contradiction_checker",
    ]
    assert calls[0]["subagents"][0]["tools"] == [fake_tool]

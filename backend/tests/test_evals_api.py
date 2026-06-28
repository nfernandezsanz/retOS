import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from retos.api.app import create_app
from retos.api.routes.evals import (
    HotpotQAEvalRequest,
    OCRBenchmarkEvalRequest,
    rerun_plan_from_eval_job,
)
from retos.core.config import Settings
from retos.domain.jobs import Job
from retos.evals.ocr import OCRCaseResult, OCRQualityReport
from retos.evals.smoke import EvalCaseResult, EvalSuiteReport


@pytest.fixture
def evals_client(settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'retos-evals.db'}",
            "database_create_all": True,
            "index_root": str(tmp_path / "index"),
            "eval_dataset_root": str(tmp_path / "evals" / "datasets"),
            "eval_report_root": str(tmp_path / "evals" / "reports"),
        }
    )
    with TestClient(create_app(local_settings)) as test_client:
        yield test_client


@pytest.fixture
def evals_admin_headers(evals_client: TestClient) -> dict[str, str]:
    response = evals_client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def evals_viewer_headers(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
) -> dict[str, str]:
    created = evals_client.post(
        "/admin/users",
        headers=evals_admin_headers,
        json={
            "email": "evals-viewer@retos.dev",
            "password": "evals-viewer-password",
            "roles": ["viewer"],
        },
    )
    assert created.status_code == 201
    response = evals_client.post(
        "/auth/login",
        json={"email": "evals-viewer@retos.dev", "password": "evals-viewer-password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def squad_dataset_root(tmp_path: Path) -> Path:
    return tmp_path / "evals" / "datasets"


@pytest.fixture
def squad_report_root(tmp_path: Path) -> Path:
    return tmp_path / "evals" / "reports"


def write_squad_api_fixture(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": "v2.0",
                "data": [
                    {
                        "title": "Solar System",
                        "paragraphs": [
                            {
                                "context": (
                                    "Mars is called the Red Planet because iron oxide dust "
                                    "covers much of its surface."
                                ),
                                "qas": [
                                    {
                                        "id": "mars-red-planet",
                                        "question": "Why is Mars called the Red Planet?",
                                        "answers": [
                                            {"text": "iron oxide dust", "answer_start": 39}
                                        ],
                                        "is_impossible": False,
                                    },
                                    {
                                        "id": "mars-ocean-depth",
                                        "question": "How deep are the oceans on Mars today?",
                                        "answers": [],
                                        "is_impossible": True,
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def create_eval_domain(
    client: TestClient,
    headers: dict[str, str],
    *,
    slug: str = "eval-domain",
) -> str:
    response = client.post(
        "/domains",
        headers=headers,
        json={
            "slug": slug,
            "name": f"Eval Domain {slug}",
            "description": "Eval ownership fixture",
        },
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def create_eval_viewer_with_grant(
    client: TestClient,
    headers: dict[str, str],
    *,
    domain_id: str,
    email: str = "evals-domain-viewer@retos.dev",
) -> dict[str, str]:
    created = client.post(
        "/admin/users",
        headers=headers,
        json={
            "email": email,
            "password": "evals-viewer-password",
            "roles": ["viewer"],
        },
    )
    assert created.status_code == 201
    grant = client.post(
        f"/admin/users/{created.json()['id']}/domain-grants",
        headers=headers,
        json={"domain_id": domain_id},
    )
    assert grant.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": email, "password": "evals-viewer-password"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def write_hotpotqa_api_fixture(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [
                {
                    "_id": "vela-air-force",
                    "question": (
                        "Which agency operated Vela spacecraft in the United States "
                        "Air Force history?"
                    ),
                    "answer": "United States Air Force",
                    "supporting_facts": [["Vela", 0], ["United States Air Force", 0]],
                    "context": [
                        [
                            "Vela",
                            [
                                "Vela spacecraft were satellites operated by "
                                "the United States Air Force."
                            ],
                        ],
                        [
                            "United States Air Force",
                            ["The United States Air Force operated satellite programs."],
                        ],
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    return path


def write_natural_questions_api_fixture(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "example_id": 123,
                "question_text": "Which star is Mercury closest to?",
                "document_title": "Mercury (planet)",
                "document_text": (
                    "Mercury is the closest planet to the Sun and has a short orbital year."
                ),
                "annotations": [
                    {
                        "long_answer": {"start_token": 0, "end_token": 14},
                        "short_answers": [{"start_token": 7, "end_token": 8}],
                        "yes_no_answer": "NONE",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def eval_job(payload: dict[str, object]) -> Job:
    now = datetime.now(UTC)
    return Job(
        id="job-fixture",
        kind="eval.run",
        status="succeeded",
        domain_id=None,
        source_id=None,
        payload=payload,
        error=None,
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )


def test_smoke_eval_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.post("/evals/smoke")

    assert response.status_code == 401


def test_squad_eval_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.post("/evals/squad", json={"dataset_path": "fixture.json"})

    assert response.status_code == 401


def test_hotpotqa_eval_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.post("/evals/hotpotqa", json={"dataset_path": "fixture.json"})

    assert response.status_code == 401


def test_hotpotqa_agent_eval_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.post("/evals/hotpotqa-agent", json={"dataset_path": "fixture.json"})

    assert response.status_code == 401


def test_natural_questions_eval_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.post(
        "/evals/natural-questions",
        json={"dataset_path": "fixture.json"},
    )

    assert response.status_code == 401


def test_agent_multihop_eval_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.post("/evals/agent-multihop")

    assert response.status_code == 401


def test_ocr_benchmark_eval_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.post(
        "/evals/ocr-benchmark",
        json={"dataset_path": "fixture.json"},
    )

    assert response.status_code == 401


def test_eval_runs_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.get("/evals/runs")

    assert response.status_code == 401


def test_eval_run_compare_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.get(
        "/evals/runs/compare",
        params={"baseline_job_id": "job-a", "candidate_job_id": "job-b"},
    )

    assert response.status_code == 401


def test_eval_regression_gate_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.get(
        "/evals/runs/regression-gate",
        params={"baseline_job_id": "job-a", "candidate_job_id": "job-b"},
    )

    assert response.status_code == 401


def test_eval_run_trends_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.get("/evals/runs/trends")

    assert response.status_code == 401


def test_eval_rerun_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.post("/evals/runs/job-eval-1/rerun")

    assert response.status_code == 401


def test_viewer_eval_history_requires_domain_scope(
    evals_client: TestClient,
    evals_viewer_headers: dict[str, str],
) -> None:
    runs = evals_client.get("/evals/runs", headers=evals_viewer_headers)
    trends = evals_client.get("/evals/runs/trends", headers=evals_viewer_headers)

    assert runs.status_code == 403
    assert runs.json()["detail"] == "Domain-scoped eval requires domain_id"
    assert trends.status_code == 403
    assert trends.json()["detail"] == "Domain-scoped eval requires domain_id"


def test_viewer_eval_compare_and_global_rerun_require_domain_scope(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    evals_viewer_headers: dict[str, str],
) -> None:
    comparison = evals_client.get(
        "/evals/runs/compare",
        headers=evals_viewer_headers,
        params={"baseline_job_id": "job-a", "candidate_job_id": "job-b"},
    )
    assert comparison.status_code == 403
    assert comparison.json()["detail"] == "Domain-scoped eval requires domain_id"

    original = evals_client.post("/evals/smoke", headers=evals_admin_headers)
    assert original.status_code == 202
    rerun = evals_client.post(
        f"/evals/runs/{original.json()['job']['id']}/rerun",
        headers=evals_viewer_headers,
    )
    assert rerun.status_code == 403
    assert rerun.json()["detail"] == "Domain-scoped eval requires domain_id"


def test_smoke_eval_runs_and_persists_auditable_job(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
) -> None:
    response = evals_client.post("/evals/smoke", headers=evals_admin_headers)

    assert response.status_code == 202
    body = response.json()
    assert body["job"]["kind"] == "eval.run"
    assert body["job"]["status"] == "succeeded"
    assert body["job"]["payload"]["result"]["passed"] is True
    assert body["report"]["suite_name"] == "retos-smoke"
    assert body["report"]["metadata"] == {
        "dataset": "retos-smoke-fixtures",
        "source": "built-in",
    }
    assert body["report"]["passed"] is True
    assert body["report"]["case_count"] == 3
    assert body["report"]["metrics"] == {
        "retrieval_recall": 1.0,
        "citation_validity": 1.0,
        "grounded_answer": 1.0,
        "abstention": 1.0,
        "budget_compliance": 1.0,
    }
    assert [case["case_id"] for case in body["report"]["cases"]] == [
        "apollo-guidance",
        "marine-salinity",
        "no-evidence",
    ]

    job_id = body["job"]["id"]
    jobs = evals_client.get("/jobs", headers=evals_admin_headers)
    journals = evals_client.get("/audit/journal-events", headers=evals_admin_headers)
    progress_events = evals_client.get("/audit/progress-events", headers=evals_admin_headers)

    assert jobs.status_code == 200
    assert any(job["id"] == job_id and job["kind"] == "eval.run" for job in jobs.json())
    assert journals.status_code == 200
    assert any(
        event["event_type"] == "eval.completed"
        and event["entity_id"] == job_id
        and event["payload"]["metadata"]["dataset"] == "retos-smoke-fixtures"
        for event in journals.json()
    )
    assert progress_events.status_code == 200
    assert any(
        event["event_type"] == "eval.completed"
        and event["job_id"] == job_id
        and event["payload"]["metadata"]["source"] == "built-in"
        for event in progress_events.json()
    )

    eval_runs = evals_client.get("/evals/runs", headers=evals_admin_headers)
    assert eval_runs.status_code == 200
    assert eval_runs.json()[0]["job"]["id"] == job_id
    assert eval_runs.json()[0]["report"]["passed"] is True
    assert eval_runs.json()[0]["report"]["case_count"] == 3


def test_smoke_eval_rerun_creates_new_job_with_origin(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    original = evals_client.post("/evals/smoke", headers=evals_admin_headers)
    assert original.status_code == 202
    original_job_id = original.json()["job"]["id"]

    rerun = evals_client.post(
        f"/evals/runs/{original_job_id}/rerun",
        headers=evals_admin_headers,
    )

    assert rerun.status_code == 202
    body = rerun.json()
    assert body["job"]["id"] != original_job_id
    assert body["job"]["kind"] == "eval.run"
    assert body["job"]["status"] == "succeeded"
    assert body["job"]["payload"]["suite_name"] == "retos-smoke"
    assert body["job"]["payload"]["rerun_from_job_id"] == original_job_id
    assert body["report"]["suite_name"] == "retos-smoke"

    connection = sqlite3.connect(tmp_path / "retos-evals.db")
    try:
        journal_payload = connection.execute(
            "select payload from journal_events where entity_id = ? and event_type = 'eval.queued'",
            (body["job"]["id"],),
        ).fetchone()[0]
        progress_payload = connection.execute(
            "select payload from progress_events where job_id = ? and event_type = 'eval.started'",
            (body["job"]["id"],),
        ).fetchone()[0]
    finally:
        connection.close()
    assert json.loads(journal_payload)["rerun_from_job_id"] == original_job_id
    assert json.loads(progress_payload)["rerun_from_job_id"] == original_job_id


def test_agent_multihop_eval_runs_and_persists_auditable_job(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
) -> None:
    response = evals_client.post("/evals/agent-multihop", headers=evals_admin_headers)

    assert response.status_code == 202
    body = response.json()
    assert body["job"]["kind"] == "eval.run"
    assert body["job"]["status"] == "succeeded"
    assert body["job"]["payload"]["suite_name"] == "agent-multihop"
    assert body["report"]["suite_name"] == "agent-multihop"
    assert body["report"]["metadata"] == {
        "dataset": "agent-multihop-fixtures",
        "source": "built-in",
    }
    assert body["report"]["metrics"] == {
        "query_plan": 1.0,
        "multi_hop_support": 1.0,
        "evidence_route": 1.0,
        "citation_validity": 1.0,
        "grounded_answer": 1.0,
        "budget_compliance": 1.0,
    }
    assert body["report"]["cases"][0]["usage"]["search_count"] >= 2
    assert (
        body["report"]["cases"][0]["audits"]["query_plan"]["strategy"] == "multi_hop_evidence_route"
    )

    job_id = body["job"]["id"]
    journals = evals_client.get("/audit/journal-events", headers=evals_admin_headers)
    progress_events = evals_client.get("/audit/progress-events", headers=evals_admin_headers)
    assert journals.status_code == 200
    assert any(
        event["event_type"] == "eval.completed"
        and event["entity_id"] == job_id
        and event["payload"]["metrics"]["multi_hop_support"] == 1.0
        for event in journals.json()
    )
    assert progress_events.status_code == 200
    assert any(
        event["event_type"] == "eval.completed"
        and event["job_id"] == job_id
        and event["payload"]["metadata"]["dataset"] == "agent-multihop-fixtures"
        for event in progress_events.json()
    )


def test_agent_multihop_eval_rerun_creates_new_job_with_origin(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
) -> None:
    original = evals_client.post("/evals/agent-multihop", headers=evals_admin_headers)
    assert original.status_code == 202
    original_job_id = original.json()["job"]["id"]

    rerun = evals_client.post(
        f"/evals/runs/{original_job_id}/rerun",
        headers=evals_admin_headers,
    )

    assert rerun.status_code == 202
    body = rerun.json()
    assert body["job"]["id"] != original_job_id
    assert body["job"]["kind"] == "eval.run"
    assert body["job"]["status"] == "succeeded"
    assert body["job"]["payload"]["suite_name"] == "agent-multihop"
    assert body["job"]["payload"]["rerun_from_job_id"] == original_job_id
    assert body["report"]["suite_name"] == "agent-multihop"


def test_squad_eval_runs_and_exports_report(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
    squad_report_root: Path,
) -> None:
    write_squad_api_fixture(squad_dataset_root / "tiny-squad.json")

    response = evals_client.post(
        "/evals/squad",
        headers=evals_admin_headers,
        json={
            "dataset_path": "tiny-squad.json",
            "max_cases": 2,
            "write_report": True,
            "report_stem": "nightly/squad v2",
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job"]["kind"] == "eval.run"
    assert body["job"]["status"] == "succeeded"
    assert body["report"]["suite_name"] == "squad-v2"
    assert body["report"]["metadata"] == {
        "adapter": "squad-v2",
        "dataset_path": str(squad_dataset_root / "tiny-squad.json"),
        "max_cases": 2,
        "source": "api",
    }
    assert body["report"]["passed"] is True
    assert body["report"]["case_count"] == 2
    assert body["report_paths"] == {
        "json": str(squad_report_root / "nightly-squad-v2.json"),
        "markdown": str(squad_report_root / "nightly-squad-v2.md"),
    }
    assert (squad_report_root / "nightly-squad-v2.json").exists()
    assert (squad_report_root / "nightly-squad-v2.md").exists()
    assert body["job"]["payload"]["dataset_path"] == str(squad_dataset_root / "tiny-squad.json")
    assert body["job"]["payload"]["max_cases"] == 2
    assert body["job"]["payload"]["report_paths"] == body["report_paths"]
    assert body["job"]["payload"]["result"]["case_count"] == 2
    assert body["job"]["payload"]["result"]["metadata"]["adapter"] == "squad-v2"
    assert json.loads((squad_report_root / "nightly-squad-v2.json").read_text())["metadata"][
        "dataset_path"
    ] == str(squad_dataset_root / "tiny-squad.json")

    eval_runs = evals_client.get("/evals/runs", headers=evals_admin_headers)
    assert eval_runs.status_code == 200
    assert eval_runs.json()[0]["job"]["id"] == body["job"]["id"]
    assert eval_runs.json()[0]["report"]["suite_name"] == "squad-v2"


def test_dataset_eval_can_be_owned_by_domain_and_filtered(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
) -> None:
    write_squad_api_fixture(squad_dataset_root / "tiny-squad.json")
    domain_id = create_eval_domain(evals_client, evals_admin_headers)
    unowned = evals_client.post("/evals/smoke", headers=evals_admin_headers)
    assert unowned.status_code == 202

    response = evals_client.post(
        "/evals/squad",
        headers=evals_admin_headers,
        json={
            "dataset_path": "tiny-squad.json",
            "domain_id": domain_id,
            "max_cases": 2,
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job"]["domain_id"] == domain_id
    assert body["job"]["payload"]["domain_id"] == domain_id
    assert body["job"]["payload"]["result"]["metadata"]["domain_id"] == domain_id

    filtered_runs = evals_client.get(
        "/evals/runs",
        headers=evals_admin_headers,
        params={"domain_id": domain_id},
    )
    assert filtered_runs.status_code == 200
    assert [run["job"]["id"] for run in filtered_runs.json()] == [body["job"]["id"]]

    filtered_trends = evals_client.get(
        "/evals/runs/trends",
        headers=evals_admin_headers,
        params={"domain_id": domain_id},
    )
    assert filtered_trends.status_code == 200
    assert filtered_trends.json()[0]["suite_name"] == "squad-v2"


def test_viewer_can_run_and_read_domain_scoped_dataset_eval(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
) -> None:
    write_squad_api_fixture(squad_dataset_root / "viewer-squad.json")
    domain_id = create_eval_domain(evals_client, evals_admin_headers, slug="viewer-evals")
    viewer_headers = create_eval_viewer_with_grant(
        evals_client,
        evals_admin_headers,
        domain_id=domain_id,
    )

    without_scope = evals_client.post(
        "/evals/squad",
        headers=viewer_headers,
        json={"dataset_path": "viewer-squad.json", "max_cases": 1},
    )
    assert without_scope.status_code == 403
    assert without_scope.json()["detail"] == "Domain-scoped eval requires domain_id"

    response = evals_client.post(
        "/evals/squad",
        headers=viewer_headers,
        json={
            "dataset_path": "viewer-squad.json",
            "domain_id": domain_id,
            "max_cases": 1,
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job"]["domain_id"] == domain_id
    assert body["job"]["payload"]["domain_id"] == domain_id
    assert body["job"]["payload"]["result"]["metadata"]["domain_id"] == domain_id

    runs = evals_client.get(
        "/evals/runs",
        headers=viewer_headers,
        params={"domain_id": domain_id},
    )
    assert runs.status_code == 200
    assert [run["job"]["id"] for run in runs.json()] == [body["job"]["id"]]

    trends = evals_client.get(
        "/evals/runs/trends",
        headers=viewer_headers,
        params={"domain_id": domain_id},
    )
    assert trends.status_code == 200
    assert trends.json()[0]["suite_name"] == "squad-v2"


def test_viewer_can_compare_and_gate_domain_scoped_eval_runs(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
) -> None:
    write_squad_api_fixture(squad_dataset_root / "viewer-compare-squad.json")
    domain_id = create_eval_domain(evals_client, evals_admin_headers, slug="viewer-compare")
    viewer_headers = create_eval_viewer_with_grant(
        evals_client,
        evals_admin_headers,
        domain_id=domain_id,
        email="evals-compare-viewer@retos.dev",
    )
    baseline = evals_client.post(
        "/evals/squad",
        headers=evals_admin_headers,
        json={
            "dataset_path": "viewer-compare-squad.json",
            "domain_id": domain_id,
            "max_cases": 1,
        },
    )
    candidate = evals_client.post(
        "/evals/squad",
        headers=evals_admin_headers,
        json={
            "dataset_path": "viewer-compare-squad.json",
            "domain_id": domain_id,
            "max_cases": 1,
        },
    )
    assert baseline.status_code == 202
    assert candidate.status_code == 202

    params = {
        "baseline_job_id": baseline.json()["job"]["id"],
        "candidate_job_id": candidate.json()["job"]["id"],
        "domain_id": domain_id,
    }
    comparison = evals_client.get(
        "/evals/runs/compare",
        headers=viewer_headers,
        params=params,
    )
    gate = evals_client.get(
        "/evals/runs/regression-gate",
        headers=viewer_headers,
        params=params,
    )

    assert comparison.status_code == 200
    assert comparison.json()["baseline"]["job_id"] == baseline.json()["job"]["id"]
    assert comparison.json()["candidate"]["job_id"] == candidate.json()["job"]["id"]
    assert comparison.json()["status"] == "unchanged"
    assert gate.status_code == 200
    assert gate.json()["passed"] is True
    assert gate.json()["baseline"]["job_id"] == baseline.json()["job"]["id"]
    assert gate.json()["candidate"]["job_id"] == candidate.json()["job"]["id"]


def test_viewer_compare_rejects_runs_outside_granted_domain(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
) -> None:
    write_squad_api_fixture(squad_dataset_root / "viewer-outside-squad.json")
    domain_id = create_eval_domain(evals_client, evals_admin_headers, slug="viewer-outside")
    viewer_headers = create_eval_viewer_with_grant(
        evals_client,
        evals_admin_headers,
        domain_id=domain_id,
        email="evals-outside-viewer@retos.dev",
    )
    global_baseline = evals_client.post("/evals/smoke", headers=evals_admin_headers)
    global_candidate = evals_client.post("/evals/agent-multihop", headers=evals_admin_headers)
    assert global_baseline.status_code == 202
    assert global_candidate.status_code == 202

    response = evals_client.get(
        "/evals/runs/compare",
        headers=viewer_headers,
        params={
            "baseline_job_id": global_baseline.json()["job"]["id"],
            "candidate_job_id": global_candidate.json()["job"]["id"],
            "domain_id": domain_id,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Eval run not found"


def test_dataset_eval_rejects_unknown_domain(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
) -> None:
    write_squad_api_fixture(squad_dataset_root / "tiny-squad.json")

    response = evals_client.post(
        "/evals/squad",
        headers=evals_admin_headers,
        json={
            "dataset_path": "tiny-squad.json",
            "domain_id": "missing-domain",
            "max_cases": 2,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Domain not found"


def test_dataset_eval_rerun_preserves_domain_scope(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
) -> None:
    write_squad_api_fixture(squad_dataset_root / "tiny-squad.json")
    domain_id = create_eval_domain(evals_client, evals_admin_headers)
    original = evals_client.post(
        "/evals/squad",
        headers=evals_admin_headers,
        json={
            "dataset_path": "tiny-squad.json",
            "domain_id": domain_id,
            "max_cases": 2,
        },
    )
    assert original.status_code == 202

    rerun = evals_client.post(
        f"/evals/runs/{original.json()['job']['id']}/rerun",
        headers=evals_admin_headers,
    )

    assert rerun.status_code == 202
    assert rerun.json()["job"]["domain_id"] == domain_id
    assert rerun.json()["job"]["payload"]["domain_id"] == domain_id
    assert rerun.json()["job"]["payload"]["rerun_from_job_id"] == original.json()["job"]["id"]


def test_viewer_can_rerun_domain_scoped_dataset_eval(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
) -> None:
    write_squad_api_fixture(squad_dataset_root / "viewer-rerun-squad.json")
    domain_id = create_eval_domain(evals_client, evals_admin_headers, slug="viewer-rerun")
    viewer_headers = create_eval_viewer_with_grant(
        evals_client,
        evals_admin_headers,
        domain_id=domain_id,
        email="evals-rerun-viewer@retos.dev",
    )
    original = evals_client.post(
        "/evals/squad",
        headers=evals_admin_headers,
        json={
            "dataset_path": "viewer-rerun-squad.json",
            "domain_id": domain_id,
            "max_cases": 1,
        },
    )
    assert original.status_code == 202

    rerun = evals_client.post(
        f"/evals/runs/{original.json()['job']['id']}/rerun",
        headers=viewer_headers,
    )

    assert rerun.status_code == 202
    assert rerun.json()["job"]["domain_id"] == domain_id
    assert rerun.json()["job"]["payload"]["domain_id"] == domain_id
    assert rerun.json()["job"]["payload"]["rerun_from_job_id"] == original.json()["job"]["id"]


def test_eval_comparison_rejects_mixed_domain_scopes(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
) -> None:
    write_squad_api_fixture(squad_dataset_root / "tiny-squad.json")
    domain_id = create_eval_domain(evals_client, evals_admin_headers)
    baseline = evals_client.post("/evals/smoke", headers=evals_admin_headers)
    candidate = evals_client.post(
        "/evals/squad",
        headers=evals_admin_headers,
        json={
            "dataset_path": "tiny-squad.json",
            "domain_id": domain_id,
            "max_cases": 2,
        },
    )
    assert baseline.status_code == 202
    assert candidate.status_code == 202

    response = evals_client.get(
        "/evals/runs/compare",
        headers=evals_admin_headers,
        params={
            "baseline_job_id": baseline.json()["job"]["id"],
            "candidate_job_id": candidate.json()["job"]["id"],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Eval runs must belong to the same domain scope"


def test_squad_eval_rerun_reuses_persisted_dataset_payload(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
    squad_report_root: Path,
) -> None:
    write_squad_api_fixture(squad_dataset_root / "rerun-squad.json")
    original = evals_client.post(
        "/evals/squad",
        headers=evals_admin_headers,
        json={
            "dataset_path": "rerun-squad.json",
            "max_cases": 2,
            "write_report": True,
            "report_stem": "reruns/squad",
        },
    )
    assert original.status_code == 202
    original_job_id = original.json()["job"]["id"]

    rerun = evals_client.post(
        f"/evals/runs/{original_job_id}/rerun",
        headers=evals_admin_headers,
    )

    assert rerun.status_code == 202
    body = rerun.json()
    assert body["job"]["id"] != original_job_id
    assert body["job"]["payload"]["dataset_path"] == str(squad_dataset_root / "rerun-squad.json")
    assert body["job"]["payload"]["max_cases"] == 2
    assert body["job"]["payload"]["write_report"] is True
    assert body["job"]["payload"]["report_stem"] == "reruns/squad"
    assert body["job"]["payload"]["rerun_from_job_id"] == original_job_id
    assert body["report_paths"] == {
        "json": str(squad_report_root / "reruns-squad.json"),
        "markdown": str(squad_report_root / "reruns-squad.md"),
    }


def test_hotpotqa_eval_runs_and_exports_report(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
    squad_report_root: Path,
) -> None:
    write_hotpotqa_api_fixture(squad_dataset_root / "tiny-hotpot.json")

    response = evals_client.post(
        "/evals/hotpotqa",
        headers=evals_admin_headers,
        json={
            "dataset_path": "tiny-hotpot.json",
            "max_cases": 1,
            "write_report": True,
            "report_stem": "nightly/hotpotqa",
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job"]["kind"] == "eval.run"
    assert body["job"]["status"] == "succeeded"
    assert body["report"]["suite_name"] == "hotpotqa"
    assert body["report"]["passed"] is True
    assert body["report"]["case_count"] == 1
    assert body["report_paths"] == {
        "json": str(squad_report_root / "nightly-hotpotqa.json"),
        "markdown": str(squad_report_root / "nightly-hotpotqa.md"),
    }
    assert body["job"]["payload"]["dataset_path"] == str(squad_dataset_root / "tiny-hotpot.json")
    assert body["job"]["payload"]["max_cases"] == 1
    assert body["job"]["payload"]["report_paths"] == body["report_paths"]
    assert body["job"]["payload"]["result"]["suite_name"] == "hotpotqa"

    eval_runs = evals_client.get("/evals/runs", headers=evals_admin_headers)
    assert eval_runs.status_code == 200
    assert eval_runs.json()[0]["job"]["id"] == body["job"]["id"]
    assert eval_runs.json()[0]["report"]["suite_name"] == "hotpotqa"


def test_hotpotqa_agent_eval_runs_exports_report_and_reruns(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
    squad_report_root: Path,
) -> None:
    write_hotpotqa_api_fixture(squad_dataset_root / "tiny-hotpot-agent.json")

    response = evals_client.post(
        "/evals/hotpotqa-agent",
        headers=evals_admin_headers,
        json={
            "dataset_path": "tiny-hotpot-agent.json",
            "max_cases": 1,
            "write_report": True,
            "report_stem": "nightly/hotpotqa-agent",
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job"]["kind"] == "eval.run"
    assert body["job"]["status"] == "succeeded"
    assert body["report"]["suite_name"] == "hotpotqa-agent"
    assert body["report"]["passed"] is True
    assert body["report"]["case_count"] == 1
    assert body["report"]["metrics"]["multi_hop_support"] == 1.0
    assert body["report"]["metadata"] == {
        "adapter": "hotpotqa-agent",
        "dataset_path": str(squad_dataset_root / "tiny-hotpot-agent.json"),
        "max_cases": 1,
        "source": "api",
    }
    assert body["report_paths"] == {
        "json": str(squad_report_root / "nightly-hotpotqa-agent.json"),
        "markdown": str(squad_report_root / "nightly-hotpotqa-agent.md"),
    }

    rerun = evals_client.post(
        f"/evals/runs/{body['job']['id']}/rerun",
        headers=evals_admin_headers,
    )

    assert rerun.status_code == 202
    rerun_body = rerun.json()
    assert rerun_body["job"]["id"] != body["job"]["id"]
    assert rerun_body["job"]["payload"]["suite_name"] == "hotpotqa-agent"
    assert rerun_body["job"]["payload"]["rerun_from_job_id"] == body["job"]["id"]
    assert rerun_body["report"]["suite_name"] == "hotpotqa-agent"


def test_natural_questions_eval_runs_and_exports_report(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
    squad_report_root: Path,
) -> None:
    write_natural_questions_api_fixture(squad_dataset_root / "tiny-nq.jsonl")

    response = evals_client.post(
        "/evals/natural-questions",
        headers=evals_admin_headers,
        json={
            "dataset_path": "tiny-nq.jsonl",
            "max_cases": 1,
            "write_report": True,
            "report_stem": "nightly/natural questions",
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job"]["kind"] == "eval.run"
    assert body["job"]["status"] == "succeeded"
    assert body["report"]["suite_name"] == "natural-questions"
    assert body["report"]["passed"] is True
    assert body["report"]["case_count"] == 1
    assert body["report_paths"] == {
        "json": str(squad_report_root / "nightly-natural-questions.json"),
        "markdown": str(squad_report_root / "nightly-natural-questions.md"),
    }
    assert body["job"]["payload"]["dataset_path"] == str(squad_dataset_root / "tiny-nq.jsonl")
    assert body["job"]["payload"]["max_cases"] == 1
    assert body["job"]["payload"]["report_paths"] == body["report_paths"]
    assert body["job"]["payload"]["result"]["suite_name"] == "natural-questions"

    eval_runs = evals_client.get("/evals/runs", headers=evals_admin_headers)
    assert eval_runs.status_code == 200
    assert eval_runs.json()[0]["job"]["id"] == body["job"]["id"]
    assert eval_runs.json()[0]["report"]["suite_name"] == "natural-questions"


def test_ocr_benchmark_eval_runs_and_exports_report(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
    squad_report_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_dir = squad_dataset_root / "ocr-benchmark"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "receipt.pdf").write_bytes(b"%PDF-1.7\n%%EOF\n")
    (dataset_dir / "manifest.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "receipt-001",
                        "input_path": "receipt.pdf",
                        "expected_text": "Receipt total 42",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_ocr_suite(**kwargs: object) -> OCRQualityReport:
        assert kwargs["suite_name"] == "ocr-manifest"
        assert kwargs["max_character_error_rate"] == 0.15
        assert kwargs["max_word_error_rate"] == 0.25
        assert kwargs["max_pages"] == 2
        return OCRQualityReport(
            suite_name="ocr-manifest",
            passed=True,
            case_count=1,
            character_error_rate=0.0,
            word_error_rate=0.0,
            key_value_recall=None,
            cases=(
                OCRCaseResult(
                    case_id="receipt-001",
                    expected_text="Receipt total 42",
                    actual_text="Receipt total 42",
                    character_error_rate=0.0,
                    word_error_rate=0.0,
                    key_value_recall=None,
                    passed=True,
                    failures=(),
                ),
            ),
        )

    monkeypatch.setattr("retos.api.routes.evals.run_ocr_quality_suite", fake_ocr_suite)

    response = evals_client.post(
        "/evals/ocr-benchmark",
        headers=evals_admin_headers,
        json={
            "dataset_path": "ocr-benchmark/manifest.json",
            "dataset_format": "manifest",
            "max_cases": 1,
            "write_report": True,
            "report_stem": "nightly/ocr manifest",
            "max_character_error_rate": 0.15,
            "max_word_error_rate": 0.25,
            "max_pages": 2,
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job"]["kind"] == "eval.run"
    assert body["job"]["status"] == "succeeded"
    assert body["report"]["suite_name"] == "ocr-manifest"
    assert body["report"]["metrics"] == {
        "character_error_rate": 0.0,
        "word_error_rate": 0.0,
    }
    assert body["report"]["cases"][0]["case_id"] == "receipt-001"
    assert body["report_paths"] == {
        "json": str(squad_report_root / "nightly-ocr-manifest.json"),
        "markdown": str(squad_report_root / "nightly-ocr-manifest.md"),
    }
    assert body["job"]["payload"]["dataset_format"] == "manifest"
    assert body["job"]["payload"]["report_paths"] == body["report_paths"]

    eval_runs = evals_client.get("/evals/runs", headers=evals_admin_headers)
    assert eval_runs.status_code == 200
    assert eval_runs.json()[0]["job"]["id"] == body["job"]["id"]
    assert eval_runs.json()[0]["report"]["suite_name"] == "ocr-manifest"


def test_ocr_benchmark_rerun_reuses_threshold_payload(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_dir = squad_dataset_root / "ocr-rerun"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "receipt.pdf").write_bytes(b"%PDF-1.7\n%%EOF\n")
    (dataset_dir / "manifest.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "receipt-rerun",
                        "input_path": "receipt.pdf",
                        "expected_text": "Receipt total 42",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    def fake_ocr_suite(**kwargs: object) -> OCRQualityReport:
        calls.append(kwargs)
        return OCRQualityReport(
            suite_name="ocr-manifest",
            passed=True,
            case_count=1,
            character_error_rate=0.0,
            word_error_rate=0.0,
            key_value_recall=None,
            cases=(
                OCRCaseResult(
                    case_id="receipt-rerun",
                    expected_text="Receipt total 42",
                    actual_text="Receipt total 42",
                    character_error_rate=0.0,
                    word_error_rate=0.0,
                    key_value_recall=None,
                    passed=True,
                    failures=(),
                ),
            ),
        )

    monkeypatch.setattr("retos.api.routes.evals.run_ocr_quality_suite", fake_ocr_suite)
    original = evals_client.post(
        "/evals/ocr-benchmark",
        headers=evals_admin_headers,
        json={
            "dataset_path": "ocr-rerun/manifest.json",
            "dataset_format": "manifest",
            "max_cases": 1,
            "max_character_error_rate": 0.12,
            "max_word_error_rate": 0.22,
            "max_pages": 3,
        },
    )
    assert original.status_code == 202
    original_job_id = original.json()["job"]["id"]

    rerun = evals_client.post(
        f"/evals/runs/{original_job_id}/rerun",
        headers=evals_admin_headers,
    )

    assert rerun.status_code == 202
    assert len(calls) == 2
    assert calls[1]["max_character_error_rate"] == 0.12
    assert calls[1]["max_word_error_rate"] == 0.22
    assert calls[1]["max_pages"] == 3
    assert rerun.json()["job"]["payload"]["rerun_from_job_id"] == original_job_id


def test_squad_eval_accepts_absolute_dataset_path_inside_root(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
) -> None:
    dataset_path = write_squad_api_fixture(squad_dataset_root / "absolute-squad.json")

    response = evals_client.post(
        "/evals/squad",
        headers=evals_admin_headers,
        json={"dataset_path": str(dataset_path), "max_cases": 1},
    )

    assert response.status_code == 202
    assert response.json()["report"]["case_count"] == 1


def test_squad_eval_rejects_dataset_path_escape(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
) -> None:
    response = evals_client.post(
        "/evals/squad",
        headers=evals_admin_headers,
        json={"dataset_path": "../outside.json"},
    )

    assert response.status_code == 422
    assert "RETOS_EVAL_DATASET_ROOT" in response.json()["detail"]


def test_squad_eval_rejects_missing_dataset(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
) -> None:
    response = evals_client.post(
        "/evals/squad",
        headers=evals_admin_headers,
        json={"dataset_path": "missing.json"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Eval dataset file not found"


def test_eval_runs_lists_recent_reports_first(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = evals_client.post("/evals/smoke", headers=evals_admin_headers)
    assert first.status_code == 202

    def fake_suite(*, index_root: object) -> EvalSuiteReport:
        return EvalSuiteReport(
            suite_name="retos-smoke",
            passed=False,
            case_count=1,
            retrieval_recall=0.0,
            citation_validity=1.0,
            grounded_answer=0.0,
            abstention=1.0,
            budget_compliance=1.0,
            cases=(
                EvalCaseResult(
                    case_id="later-failing-case",
                    question="What failed later?",
                    passed=False,
                    retrieval_recall=False,
                    citation_validity=True,
                    grounded_answer=False,
                    abstention=True,
                    budget_compliance=True,
                    answer="No grounded answer.",
                    citations=(),
                    failures=("retrieval_recall", "grounded_answer"),
                ),
            ),
        )

    monkeypatch.setattr("retos.api.routes.evals.run_smoke_eval_suite", fake_suite)

    second = evals_client.post("/evals/smoke", headers=evals_admin_headers)
    assert second.status_code == 202

    eval_runs = evals_client.get("/evals/runs?limit=2", headers=evals_admin_headers)

    assert eval_runs.status_code == 200
    runs = eval_runs.json()
    assert [run["job"]["id"] for run in runs] == [
        second.json()["job"]["id"],
        first.json()["job"]["id"],
    ]
    assert runs[0]["report"]["passed"] is False
    assert runs[1]["report"]["passed"] is True


def test_eval_run_compare_returns_metric_deltas(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = evals_client.post("/evals/smoke", headers=evals_admin_headers)
    assert first.status_code == 202

    def fake_suite(*, index_root: object) -> EvalSuiteReport:
        return EvalSuiteReport(
            suite_name="retos-smoke",
            passed=False,
            case_count=1,
            retrieval_recall=0.0,
            citation_validity=1.0,
            grounded_answer=0.0,
            abstention=1.0,
            budget_compliance=1.0,
            cases=(
                EvalCaseResult(
                    case_id="later-failing-case",
                    question="What failed later?",
                    passed=False,
                    retrieval_recall=False,
                    citation_validity=True,
                    grounded_answer=False,
                    abstention=True,
                    budget_compliance=True,
                    answer="No grounded answer.",
                    citations=(),
                    failures=("retrieval_recall", "grounded_answer"),
                ),
            ),
        )

    monkeypatch.setattr("retos.api.routes.evals.run_smoke_eval_suite", fake_suite)

    second = evals_client.post("/evals/smoke", headers=evals_admin_headers)
    assert second.status_code == 202

    response = evals_client.get(
        "/evals/runs/compare",
        headers=evals_admin_headers,
        params={
            "baseline_job_id": first.json()["job"]["id"],
            "candidate_job_id": second.json()["job"]["id"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["baseline"]["job_id"] == first.json()["job"]["id"]
    assert body["baseline"]["suite_name"] == "retos-smoke"
    assert body["candidate"]["job_id"] == second.json()["job"]["id"]
    assert body["candidate"]["passed"] is False
    assert body["status"] == "regressed"
    assert body["average_delta"] == -0.4
    assert body["metrics"] == [
        {"name": "retrieval_recall", "baseline": 1.0, "candidate": 0.0, "delta": -1.0},
        {"name": "citation_validity", "baseline": 1.0, "candidate": 1.0, "delta": 0.0},
        {"name": "grounded_answer", "baseline": 1.0, "candidate": 0.0, "delta": -1.0},
        {"name": "abstention", "baseline": 1.0, "candidate": 1.0, "delta": 0.0},
        {"name": "budget_compliance", "baseline": 1.0, "candidate": 1.0, "delta": 0.0},
    ]


def test_eval_regression_gate_flags_metric_drops(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = evals_client.post("/evals/smoke", headers=evals_admin_headers)
    assert baseline.status_code == 202

    def regressed_suite(*, index_root: object) -> EvalSuiteReport:
        return EvalSuiteReport(
            suite_name="retos-smoke",
            passed=False,
            case_count=1,
            retrieval_recall=0.5,
            citation_validity=1.0,
            grounded_answer=1.0,
            abstention=1.0,
            budget_compliance=1.0,
            cases=(),
        )

    monkeypatch.setattr("retos.api.routes.evals.run_smoke_eval_suite", regressed_suite)
    candidate = evals_client.post("/evals/smoke", headers=evals_admin_headers)
    assert candidate.status_code == 202

    response = evals_client.get(
        "/evals/runs/regression-gate",
        headers=evals_admin_headers,
        params={
            "baseline_job_id": baseline.json()["job"]["id"],
            "candidate_job_id": candidate.json()["job"]["id"],
            "metric_drop_tolerance": 0.1,
            "average_drop_tolerance": 0.05,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["metric_drop_tolerance"] == 0.1
    assert body["average_drop_tolerance"] == 0.05
    assert body["average_normalized_delta"] == -0.1
    assert body["regressions"] == [
        {
            "name": "retrieval_recall",
            "baseline": 1.0,
            "candidate": 0.5,
            "delta": -0.5,
            "normalized_delta": -0.5,
            "direction": "regressed",
            "regressed": True,
        }
    ]

    tolerated = evals_client.get(
        "/evals/runs/regression-gate",
        headers=evals_admin_headers,
        params={
            "baseline_job_id": baseline.json()["job"]["id"],
            "candidate_job_id": candidate.json()["job"]["id"],
            "metric_drop_tolerance": 0.5,
            "average_drop_tolerance": 0.1,
        },
    )
    assert tolerated.status_code == 200
    assert tolerated.json()["passed"] is True
    assert tolerated.json()["regressions"] == []


def test_eval_regression_gate_treats_error_rate_increase_as_regression(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def ocr_suite(*, character_error_rate: float, word_error_rate: float):
        def fake_suite(**kwargs: object) -> OCRQualityReport:
            return OCRQualityReport(
                suite_name="ocr-manifest",
                passed=True,
                case_count=1,
                character_error_rate=character_error_rate,
                word_error_rate=word_error_rate,
                key_value_recall=None,
                cases=(),
            )

        return fake_suite

    dataset_dir = squad_dataset_root / "ocr-gate"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "receipt.pdf").write_bytes(b"%PDF-1.7\n%%EOF\n")
    (dataset_dir / "manifest.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "receipt-gate",
                        "input_path": "receipt.pdf",
                        "expected_text": "Receipt total 42",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "retos.api.routes.evals.run_ocr_quality_suite",
        ocr_suite(character_error_rate=0.05, word_error_rate=0.10),
    )
    baseline = evals_client.post(
        "/evals/ocr-benchmark",
        headers=evals_admin_headers,
        json={"dataset_path": "ocr-gate/manifest.json", "dataset_format": "manifest"},
    )
    assert baseline.status_code == 202
    monkeypatch.setattr(
        "retos.api.routes.evals.run_ocr_quality_suite",
        ocr_suite(character_error_rate=0.15, word_error_rate=0.10),
    )
    candidate = evals_client.post(
        "/evals/ocr-benchmark",
        headers=evals_admin_headers,
        json={"dataset_path": "ocr-gate/manifest.json", "dataset_format": "manifest"},
    )
    assert candidate.status_code == 202

    response = evals_client.get(
        "/evals/runs/regression-gate",
        headers=evals_admin_headers,
        params={
            "baseline_job_id": baseline.json()["job"]["id"],
            "candidate_job_id": candidate.json()["job"]["id"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    character_error = next(
        metric for metric in body["metrics"] if metric["name"] == "character_error_rate"
    )
    assert character_error["delta"] == 0.09999999999999999
    assert character_error["normalized_delta"] == -0.09999999999999999
    assert character_error["direction"] == "regressed"
    assert character_error["regressed"] is True


def test_eval_run_trends_group_suites_and_metric_directions(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    squad_dataset_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = evals_client.post("/evals/smoke", headers=evals_admin_headers)
    assert first.status_code == 202

    def regressed_smoke_suite(*, index_root: object) -> EvalSuiteReport:
        return EvalSuiteReport(
            suite_name="retos-smoke",
            passed=False,
            case_count=1,
            retrieval_recall=0.0,
            citation_validity=1.0,
            grounded_answer=0.0,
            abstention=1.0,
            budget_compliance=1.0,
            cases=(
                EvalCaseResult(
                    case_id="later-failing-case",
                    question="What failed later?",
                    passed=False,
                    retrieval_recall=False,
                    citation_validity=True,
                    grounded_answer=False,
                    abstention=True,
                    budget_compliance=True,
                    answer="No grounded answer.",
                    citations=(),
                    failures=("retrieval_recall", "grounded_answer"),
                ),
            ),
        )

    monkeypatch.setattr("retos.api.routes.evals.run_smoke_eval_suite", regressed_smoke_suite)
    second = evals_client.post("/evals/smoke", headers=evals_admin_headers)
    assert second.status_code == 202

    def stable_ocr_suite(**kwargs: object) -> OCRQualityReport:
        return OCRQualityReport(
            suite_name="ocr-manifest",
            passed=True,
            case_count=1,
            character_error_rate=0.10,
            word_error_rate=0.20,
            key_value_recall=None,
            cases=(
                OCRCaseResult(
                    case_id="receipt-trend",
                    expected_text="Receipt total 42",
                    actual_text="Receipt total 42",
                    character_error_rate=0.10,
                    word_error_rate=0.20,
                    key_value_recall=None,
                    passed=True,
                    failures=(),
                ),
            ),
        )

    monkeypatch.setattr("retos.api.routes.evals.run_ocr_quality_suite", stable_ocr_suite)
    dataset_dir = squad_dataset_root / "ocr-trend"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "receipt.pdf").write_bytes(b"%PDF-1.7\n%%EOF\n")
    (dataset_dir / "manifest.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "receipt-trend",
                        "input_path": "receipt.pdf",
                        "expected_text": "Receipt total 42",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    ocr = evals_client.post(
        "/evals/ocr-benchmark",
        headers=evals_admin_headers,
        json={"dataset_path": "ocr-trend/manifest.json", "dataset_format": "manifest"},
    )
    assert ocr.status_code == 202

    trends = evals_client.get("/evals/runs/trends", headers=evals_admin_headers)

    assert trends.status_code == 200
    body = trends.json()
    smoke_trend = next(item for item in body if item["suite_name"] == "retos-smoke")
    assert smoke_trend["run_count"] == 2
    assert smoke_trend["pass_rate"] == 0.5
    assert smoke_trend["latest"]["job_id"] == second.json()["job"]["id"]
    assert [point["job_id"] for point in smoke_trend["points"]] == [
        first.json()["job"]["id"],
        second.json()["job"]["id"],
    ]
    retrieval = next(
        metric for metric in smoke_trend["metrics"] if metric["name"] == "retrieval_recall"
    )
    assert retrieval == {
        "name": "retrieval_recall",
        "first": 1.0,
        "latest": 0.0,
        "delta": -1.0,
        "minimum": 0.0,
        "maximum": 1.0,
        "average": 0.5,
        "direction": "regressed",
    }

    ocr_trend = next(item for item in body if item["suite_name"] == "ocr-manifest")
    character_error = next(
        metric for metric in ocr_trend["metrics"] if metric["name"] == "character_error_rate"
    )
    assert character_error["direction"] == "unchanged"

    filtered = evals_client.get(
        "/evals/runs/trends",
        headers=evals_admin_headers,
        params={"suite_name": "ocr-manifest"},
    )
    assert filtered.status_code == 200
    assert [item["suite_name"] for item in filtered.json()] == ["ocr-manifest"]


def test_eval_run_compare_rejects_missing_or_unreported_runs(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
) -> None:
    first = evals_client.post("/evals/smoke", headers=evals_admin_headers)
    assert first.status_code == 202
    created = evals_client.post(
        "/jobs",
        headers=evals_admin_headers,
        json={
            "kind": "eval.run",
            "payload": {"suite_name": "retos-smoke"},
        },
    )
    assert created.status_code == 201

    missing = evals_client.get(
        "/evals/runs/compare",
        headers=evals_admin_headers,
        params={
            "baseline_job_id": "missing",
            "candidate_job_id": first.json()["job"]["id"],
        },
    )
    malformed = evals_client.get(
        "/evals/runs/compare",
        headers=evals_admin_headers,
        params={
            "baseline_job_id": first.json()["job"]["id"],
            "candidate_job_id": created.json()["id"],
        },
    )

    assert missing.status_code == 404
    assert missing.json()["detail"] == "Eval run not found"
    assert malformed.status_code == 409
    assert malformed.json()["detail"] == "Eval run does not have a comparable report"


def test_eval_rerun_rejects_missing_or_unrunnable_payloads(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
) -> None:
    missing = evals_client.post("/evals/runs/missing/rerun", headers=evals_admin_headers)
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Eval run not found"

    without_dataset = evals_client.post(
        "/jobs",
        headers=evals_admin_headers,
        json={"kind": "eval.run", "payload": {"suite_name": "squad-v2"}},
    )
    assert without_dataset.status_code == 201
    no_dataset_rerun = evals_client.post(
        f"/evals/runs/{without_dataset.json()['id']}/rerun",
        headers=evals_admin_headers,
    )
    assert no_dataset_rerun.status_code == 422
    assert no_dataset_rerun.json()["detail"] == "Eval run cannot be rerun without dataset_path"

    unknown_suite = evals_client.post(
        "/jobs",
        headers=evals_admin_headers,
        json={"kind": "eval.run", "payload": {"suite_name": "unknown-eval"}},
    )
    assert unknown_suite.status_code == 201
    unknown_rerun = evals_client.post(
        f"/evals/runs/{unknown_suite.json()['id']}/rerun",
        headers=evals_admin_headers,
    )
    assert unknown_rerun.status_code == 422
    assert unknown_rerun.json()["detail"] == "Eval suite unknown-eval cannot be rerun"


def test_eval_rerun_plan_recovers_legacy_dataset_payload() -> None:
    plan = rerun_plan_from_eval_job(
        eval_job(
            {
                "suite_name": "hotpotqa",
                "dataset_path": "legacy-hotpot.json",
                "max_cases": "7",
                "report_paths": {"json": "legacy.json", "markdown": "legacy.md"},
            }
        )
    )

    assert plan.suite_name == "hotpotqa"
    assert isinstance(plan.request, HotpotQAEvalRequest)
    assert plan.request.dataset_path == "legacy-hotpot.json"
    assert plan.request.max_cases == 7
    assert plan.request.write_report is True
    assert plan.request.report_stem is None


def test_eval_rerun_plan_recovers_hotpotqa_agent_payload() -> None:
    plan = rerun_plan_from_eval_job(
        eval_job(
            {
                "suite_name": "hotpotqa-agent",
                "dataset_path": "legacy-hotpot-agent.json",
                "max_cases": "5",
                "write_report": False,
            }
        )
    )

    assert plan.suite_name == "hotpotqa-agent"
    assert isinstance(plan.request, HotpotQAEvalRequest)
    assert plan.request.dataset_path == "legacy-hotpot-agent.json"
    assert plan.request.max_cases == 5
    assert plan.request.write_report is False


def test_eval_rerun_plan_recovers_legacy_ocr_payload_defaults() -> None:
    plan = rerun_plan_from_eval_job(
        eval_job(
            {
                "suite_name": "ocr-manifest",
                "dataset_path": "legacy-ocr/manifest.json",
                "max_cases": True,
                "write_report": "yes",
                "max_character_error_rate": "0.11",
                "max_word_error_rate": "not-a-float",
                "max_pages": "3",
            }
        )
    )

    assert plan.suite_name == "ocr-manifest"
    assert isinstance(plan.request, OCRBenchmarkEvalRequest)
    assert plan.request.dataset_format == "manifest"
    assert plan.request.max_cases == 50
    assert plan.request.write_report is False
    assert plan.request.max_character_error_rate == 0.11
    assert plan.request.max_word_error_rate == 0.35
    assert plan.request.max_pages == 3


def test_eval_rerun_plan_rejects_invalid_legacy_payload() -> None:
    with pytest.raises(HTTPException) as exc:
        rerun_plan_from_eval_job(
            eval_job(
                {
                    "suite_name": "ocr-custom",
                    "dataset_path": "legacy-ocr/manifest.json",
                    "dataset_format": "custom",
                }
            )
        )

    assert exc.value.status_code == 422
    assert exc.value.detail == "Eval run payload cannot be rerun"


def test_eval_runs_tolerates_malformed_report_payload(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
) -> None:
    created = evals_client.post(
        "/jobs",
        headers=evals_admin_headers,
        json={
            "kind": "eval.run",
            "payload": {"result": {"suite_name": "retos-smoke"}},
        },
    )
    assert created.status_code == 201

    eval_runs = evals_client.get("/evals/runs", headers=evals_admin_headers)

    assert eval_runs.status_code == 200
    assert eval_runs.json()[0]["job"]["id"] == created.json()["id"]
    assert eval_runs.json()[0]["report"] is None


def test_smoke_eval_persists_failed_report(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_suite(*, index_root: object) -> EvalSuiteReport:
        return EvalSuiteReport(
            suite_name="retos-smoke",
            passed=False,
            case_count=1,
            retrieval_recall=0.0,
            citation_validity=1.0,
            grounded_answer=0.0,
            abstention=1.0,
            budget_compliance=1.0,
            cases=(
                EvalCaseResult(
                    case_id="failing-case",
                    question="What failed?",
                    passed=False,
                    retrieval_recall=False,
                    citation_validity=True,
                    grounded_answer=False,
                    abstention=True,
                    budget_compliance=True,
                    answer="No grounded answer.",
                    citations=(),
                    failures=("retrieval_recall", "grounded_answer"),
                ),
            ),
        )

    monkeypatch.setattr("retos.api.routes.evals.run_smoke_eval_suite", fake_suite)

    response = evals_client.post("/evals/smoke", headers=evals_admin_headers)

    assert response.status_code == 202
    body = response.json()
    assert body["job"]["status"] == "failed"
    assert body["job"]["error"] == "Eval smoke suite failed"
    assert body["report"]["passed"] is False
    assert body["report"]["cases"][0]["failures"] == [
        "retrieval_recall",
        "grounded_answer",
    ]


def test_smoke_eval_marks_job_failed_when_suite_crashes(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_suite(*, index_root: object) -> EvalSuiteReport:
        raise RuntimeError("broken eval fixture")

    monkeypatch.setattr("retos.api.routes.evals.run_smoke_eval_suite", broken_suite)

    response = evals_client.post("/evals/smoke", headers=evals_admin_headers)

    assert response.status_code == 500
    assert response.json()["detail"] == "Eval smoke suite failed to run"

    jobs = evals_client.get("/jobs", headers=evals_admin_headers)
    assert jobs.status_code == 200
    eval_jobs = [job for job in jobs.json() if job["kind"] == "eval.run"]
    assert len(eval_jobs) == 1
    assert eval_jobs[0]["status"] == "failed"
    assert eval_jobs[0]["error"] == "broken eval fixture"

    eval_runs = evals_client.get("/evals/runs", headers=evals_admin_headers)
    assert eval_runs.status_code == 200
    assert eval_runs.json()[0]["job"]["id"] == eval_jobs[0]["id"]
    assert eval_runs.json()[0]["report"] is None

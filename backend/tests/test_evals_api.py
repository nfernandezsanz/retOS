from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retos.api.app import create_app
from retos.core.config import Settings
from retos.evals.smoke import EvalCaseResult, EvalSuiteReport


@pytest.fixture
def evals_client(settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'retos-evals.db'}",
            "database_create_all": True,
            "index_root": str(tmp_path / "index"),
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


def test_smoke_eval_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.post("/evals/smoke")

    assert response.status_code == 401


def test_eval_runs_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.get("/evals/runs")

    assert response.status_code == 401


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
        event["event_type"] == "eval.completed" and event["entity_id"] == job_id
        for event in journals.json()
    )
    assert progress_events.status_code == 200
    assert any(
        event["event_type"] == "eval.completed" and event["job_id"] == job_id
        for event in progress_events.json()
    )

    eval_runs = evals_client.get("/evals/runs", headers=evals_admin_headers)
    assert eval_runs.status_code == 200
    assert eval_runs.json()[0]["job"]["id"] == job_id
    assert eval_runs.json()[0]["report"]["passed"] is True
    assert eval_runs.json()[0]["report"]["case_count"] == 3


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

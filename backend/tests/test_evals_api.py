import json
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


def test_natural_questions_eval_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.post(
        "/evals/natural-questions",
        json={"dataset_path": "fixture.json"},
    )

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


def test_eval_rerun_requires_admin_token(evals_client: TestClient) -> None:
    response = evals_client.post("/evals/runs/job-eval-1/rerun")

    assert response.status_code == 401


def test_eval_history_requires_admin_role(
    evals_client: TestClient,
    evals_viewer_headers: dict[str, str],
) -> None:
    runs = evals_client.get("/evals/runs", headers=evals_viewer_headers)
    comparison = evals_client.get(
        "/evals/runs/compare",
        headers=evals_viewer_headers,
        params={"baseline_job_id": "job-a", "candidate_job_id": "job-b"},
    )

    assert runs.status_code == 403
    assert runs.json()["detail"] == "Admin role required"
    assert comparison.status_code == 403
    assert comparison.json()["detail"] == "Admin role required"

    rerun = evals_client.post("/evals/runs/job-eval-1/rerun", headers=evals_viewer_headers)
    assert rerun.status_code == 403
    assert rerun.json()["detail"] == "Admin role required"


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


def test_smoke_eval_rerun_creates_new_job_with_origin(
    evals_client: TestClient,
    evals_admin_headers: dict[str, str],
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

    eval_runs = evals_client.get("/evals/runs", headers=evals_admin_headers)
    assert eval_runs.status_code == 200
    assert eval_runs.json()[0]["job"]["id"] == body["job"]["id"]
    assert eval_runs.json()[0]["report"]["suite_name"] == "squad-v2"


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

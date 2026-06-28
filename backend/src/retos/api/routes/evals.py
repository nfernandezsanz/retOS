from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, ValidationError

from retos.api.dependencies import AdminSubjectDep, SettingsDep, UnitOfWorkDep
from retos.api.routes.events import progress_store
from retos.api.routes.jobs import JobRead
from retos.domain.jobs import Job, JobStatus
from retos.evals.datasets import DatasetAdapterError, SquadAdapterOptions, load_squad_v2_cases
from retos.evals.reports import write_report_files
from retos.evals.smoke import EvalCaseResult, EvalSuiteReport, run_smoke_eval_suite

router = APIRouter(prefix="/evals", tags=["evals"])


class EvalMetricsRead(BaseModel):
    retrieval_recall: float
    citation_validity: float
    grounded_answer: float
    abstention: float
    budget_compliance: float


class EvalCaseRead(BaseModel):
    case_id: str
    question: str
    passed: bool
    retrieval_recall: bool
    citation_validity: bool
    grounded_answer: bool
    abstention: bool
    budget_compliance: bool
    answer: str
    citations: list[dict[str, Any]]
    failures: list[str]

    @classmethod
    def from_case(cls, case: EvalCaseResult) -> EvalCaseRead:
        return cls(
            case_id=case.case_id,
            question=case.question,
            passed=case.passed,
            retrieval_recall=case.retrieval_recall,
            citation_validity=case.citation_validity,
            grounded_answer=case.grounded_answer,
            abstention=case.abstention,
            budget_compliance=case.budget_compliance,
            answer=case.answer,
            citations=list(case.citations),
            failures=list(case.failures),
        )


class EvalReportRead(BaseModel):
    suite_name: str
    passed: bool
    case_count: int
    metrics: EvalMetricsRead
    cases: list[EvalCaseRead]

    @classmethod
    def from_report(cls, report: EvalSuiteReport) -> EvalReportRead:
        return cls(
            suite_name=report.suite_name,
            passed=report.passed,
            case_count=report.case_count,
            metrics=EvalMetricsRead(
                retrieval_recall=report.retrieval_recall,
                citation_validity=report.citation_validity,
                grounded_answer=report.grounded_answer,
                abstention=report.abstention,
                budget_compliance=report.budget_compliance,
            ),
            cases=[EvalCaseRead.from_case(case) for case in report.cases],
        )


class EvalRunResponse(BaseModel):
    job: JobRead
    report: EvalReportRead
    report_paths: dict[str, str] | None = None


class EvalRunRead(BaseModel):
    job: JobRead
    report: EvalReportRead | None


class EvalRunSummaryRead(BaseModel):
    job_id: str
    suite_name: str
    passed: bool
    case_count: int
    completed_at: datetime | None


class EvalMetricComparisonRead(BaseModel):
    name: str
    baseline: float
    candidate: float
    delta: float


class EvalRunComparisonRead(BaseModel):
    baseline: EvalRunSummaryRead
    candidate: EvalRunSummaryRead
    metrics: list[EvalMetricComparisonRead]
    average_delta: float
    status: str


def report_from_payload(payload: dict[str, Any]) -> EvalReportRead | None:
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    try:
        return EvalReportRead.model_validate(result)
    except ValidationError:
        return None


class SquadEvalRequest(BaseModel):
    dataset_path: str = Field(min_length=1, max_length=500)
    max_cases: int = Field(default=50, ge=1, le=1000)
    write_report: bool = False
    report_stem: str | None = Field(default=None, max_length=120)


@router.get("/runs", response_model=list[EvalRunRead])
async def list_eval_runs(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[EvalRunRead]:
    async with uow:
        jobs = await uow.jobs.list_by_kind(kind="eval.run", limit=limit)
    return [
        EvalRunRead(
            job=JobRead.from_job(job),
            report=report_from_payload(job.payload),
        )
        for job in jobs
    ]


@router.get("/runs/compare", response_model=EvalRunComparisonRead)
async def compare_eval_runs(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    baseline_job_id: Annotated[str, Query(min_length=1)],
    candidate_job_id: Annotated[str, Query(min_length=1)],
) -> EvalRunComparisonRead:
    async with uow:
        baseline_job = await uow.jobs.get(baseline_job_id)
        candidate_job = await uow.jobs.get(candidate_job_id)

    baseline_report = report_from_eval_job(baseline_job)
    candidate_report = report_from_eval_job(candidate_job)
    assert baseline_job is not None
    assert candidate_job is not None
    baseline_metrics = baseline_report.metrics.model_dump()
    candidate_metrics = candidate_report.metrics.model_dump()
    common_names = [name for name in baseline_metrics if name in candidate_metrics]
    metric_comparisons = [
        EvalMetricComparisonRead(
            name=name,
            baseline=baseline_metrics[name],
            candidate=candidate_metrics[name],
            delta=candidate_metrics[name] - baseline_metrics[name],
        )
        for name in common_names
    ]
    average_delta = (
        sum(metric.delta for metric in metric_comparisons) / len(metric_comparisons)
        if metric_comparisons
        else 0.0
    )
    return EvalRunComparisonRead(
        baseline=summary_from_eval_run(baseline_job, baseline_report),
        candidate=summary_from_eval_run(candidate_job, candidate_report),
        metrics=metric_comparisons,
        average_delta=average_delta,
        status=comparison_status(average_delta),
    )


@router.post(
    "/smoke",
    response_model=EvalRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_smoke_evals(
    actor: AdminSubjectDep,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
) -> EvalRunResponse:
    suite_name = "retos-smoke"
    now = datetime.now(UTC)
    job = await queue_eval_job(
        actor=actor,
        uow=uow,
        suite_name=suite_name,
        requested_at=now,
        queued_message="Queued local smoke eval suite",
        started_message="Started local smoke eval suite",
    )
    try:
        report = run_smoke_eval_suite(index_root=Path(settings.index_root) / "evals")
    except Exception as exc:
        await mark_eval_failed(job_id=job.id, actor=actor, uow=uow, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Eval smoke suite failed to run",
        ) from exc

    completed = await complete_eval_job(
        actor=actor,
        uow=uow,
        job_id=job.id,
        requested_at=now,
        report=report,
        failure_error="Eval smoke suite failed",
    )
    return EvalRunResponse(
        job=JobRead.from_job(completed), report=EvalReportRead.from_report(report)
    )


@router.post(
    "/squad",
    response_model=EvalRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_squad_evals(
    request: SquadEvalRequest,
    actor: AdminSubjectDep,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
) -> EvalRunResponse:
    dataset_path = resolve_dataset_path(settings.eval_dataset_root, request.dataset_path)
    if not dataset_path.exists() or not dataset_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eval dataset file not found",
        )

    suite_name = "squad-v2"
    now = datetime.now(UTC)
    job = await queue_eval_job(
        actor=actor,
        uow=uow,
        suite_name=suite_name,
        requested_at=now,
        queued_message="Queued SQuAD eval suite",
        started_message="Started SQuAD eval suite",
        payload={
            "dataset_path": str(dataset_path),
            "max_cases": request.max_cases,
            "write_report": request.write_report,
        },
    )
    try:
        cases = load_squad_v2_cases(
            dataset_path,
            SquadAdapterOptions(max_cases=request.max_cases),
        )
        if not cases:
            raise DatasetAdapterError("SQuAD dataset produced no eval cases")
        report = run_smoke_eval_suite(
            index_root=Path(settings.index_root) / "evals" / "squad",
            suite_name=suite_name,
            cases=cases,
        )
    except DatasetAdapterError as exc:
        await mark_eval_failed(job_id=job.id, actor=actor, uow=uow, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        await mark_eval_failed(job_id=job.id, actor=actor, uow=uow, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SQuAD eval suite failed to run",
        ) from exc

    report_paths: dict[str, str] | None = None
    if request.write_report:
        try:
            json_path, markdown_path = write_report_files(
                report=report,
                report_dir=Path(settings.eval_report_root),
                report_stem=request.report_stem,
            )
        except Exception as exc:
            await mark_eval_failed(job_id=job.id, actor=actor, uow=uow, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SQuAD eval report failed to write",
            ) from exc
        report_paths = {
            "json": str(json_path),
            "markdown": str(markdown_path),
        }

    completed = await complete_eval_job(
        actor=actor,
        uow=uow,
        job_id=job.id,
        requested_at=now,
        report=report,
        failure_error="SQuAD eval suite failed",
        payload={
            "dataset_path": str(dataset_path),
            "max_cases": request.max_cases,
            "report_paths": report_paths,
        },
    )
    return EvalRunResponse(
        job=JobRead.from_job(completed),
        report=EvalReportRead.from_report(report),
        report_paths=report_paths,
    )


def resolve_dataset_path(dataset_root: str, dataset_path: str) -> Path:
    root = Path(dataset_root).expanduser().resolve(strict=False)
    raw_path = Path(dataset_path).expanduser()
    candidate = raw_path if raw_path.is_absolute() else root / raw_path
    resolved = candidate.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Eval dataset path must stay inside RETOS_EVAL_DATASET_ROOT",
        )
    return resolved


def report_from_eval_job(job: Job | None) -> EvalReportRead:
    if job is None or job.kind != "eval.run":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval run not found")
    report = report_from_payload(job.payload)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Eval run does not have a comparable report",
        )
    return report


def summary_from_eval_run(job: Job, report: EvalReportRead) -> EvalRunSummaryRead:
    return EvalRunSummaryRead(
        job_id=job.id,
        suite_name=report.suite_name,
        passed=report.passed,
        case_count=report.case_count,
        completed_at=job.completed_at,
    )


def comparison_status(average_delta: float) -> str:
    if average_delta > 0:
        return "improved"
    if average_delta < 0:
        return "regressed"
    return "unchanged"


async def queue_eval_job(
    *,
    actor: str,
    uow: UnitOfWorkDep,
    suite_name: str,
    requested_at: datetime,
    queued_message: str,
    started_message: str,
    payload: dict[str, Any] | None = None,
) -> Job:
    job_payload = {
        "suite_name": suite_name,
        "requested_at": requested_at.isoformat(),
        **(payload or {}),
    }
    async with uow:
        job = await uow.jobs.add(
            kind="eval.run",
            status="queued",
            domain_id=None,
            source_id=None,
            payload=job_payload,
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="eval.queued",
            entity_type="job",
            entity_id=job.id,
            payload={"suite_name": suite_name},
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="eval.queued",
            message=queued_message,
            payload={"suite_name": suite_name},
        )
        running = await uow.jobs.update_status(
            job_id=job.id,
            status="running",
            started_at=requested_at,
        )
        if running is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval job not found")
        await uow.journal_events.add(
            actor=actor,
            event_type="job.running",
            entity_type="job",
            entity_id=job.id,
            payload={"from_status": "queued", "to_status": "running"},
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="eval.started",
            message=started_message,
            payload={"suite_name": suite_name},
        )
        await uow.commit()

    progress_store.append("eval.started", {"job_id": job.id, "suite_name": suite_name})
    return job


async def complete_eval_job(
    *,
    actor: str,
    uow: UnitOfWorkDep,
    job_id: str,
    requested_at: datetime,
    report: EvalSuiteReport,
    failure_error: str,
    payload: dict[str, Any] | None = None,
) -> Job:
    completed_at = datetime.now(UTC)
    next_status: JobStatus = "succeeded" if report.passed else "failed"
    report_payload = report.to_dict()
    job_payload = {
        "suite_name": report.suite_name,
        "requested_at": requested_at.isoformat(),
        "result": report_payload,
        **(payload or {}),
    }
    async with uow:
        await uow.jobs.update_payload(
            job_id=job_id,
            payload=job_payload,
        )
        completed = await uow.jobs.update_status(
            job_id=job_id,
            status=next_status,
            completed_at=completed_at,
            error=None if report.passed else failure_error,
        )
        if completed is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval job not found")
        await uow.journal_events.add(
            actor=actor,
            event_type="eval.completed" if report.passed else "eval.failed",
            entity_type="job",
            entity_id=job_id,
            payload={
                "suite_name": report.suite_name,
                "passed": report.passed,
                "case_count": report.case_count,
                "metrics": report_payload["metrics"],
            },
        )
        await uow.journal_events.add(
            actor=actor,
            event_type=f"job.{next_status}",
            entity_type="job",
            entity_id=job_id,
            payload={"from_status": "running", "to_status": next_status},
        )
        await uow.progress_events.add(
            job_id=job_id,
            event_type="eval.completed" if report.passed else "eval.failed",
            message=f"Completed {report.case_count} eval cases",
            payload={
                "suite_name": report.suite_name,
                "passed": report.passed,
                "case_count": report.case_count,
            },
        )
        await uow.commit()

    progress_store.append(
        "eval.completed" if report.passed else "eval.failed",
        {
            "job_id": job_id,
            "suite_name": report.suite_name,
            "passed": report.passed,
            "case_count": report.case_count,
        },
    )
    return completed


async def mark_eval_failed(
    *,
    job_id: str,
    actor: str,
    uow: UnitOfWorkDep,
    error: str,
) -> None:
    completed_at = datetime.now(UTC)
    async with uow:
        await uow.jobs.update_status(
            job_id=job_id,
            status="failed",
            completed_at=completed_at,
            error=error,
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="eval.failed",
            entity_type="job",
            entity_id=job_id,
            payload={"error": error},
        )
        await uow.progress_events.add(
            job_id=job_id,
            event_type="eval.failed",
            message="Local smoke eval suite failed",
            payload={"error": error},
        )
        await uow.commit()
    progress_store.append("eval.failed", {"job_id": job_id, "error": error})

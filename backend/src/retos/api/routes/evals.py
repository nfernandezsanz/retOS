from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ValidationError

from retos.api.dependencies import AdminSubjectDep, SettingsDep, UnitOfWorkDep
from retos.api.routes.events import progress_store
from retos.api.routes.jobs import JobRead
from retos.domain.jobs import JobStatus
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


class EvalRunRead(BaseModel):
    job: JobRead
    report: EvalReportRead | None


def report_from_payload(payload: dict[str, Any]) -> EvalReportRead | None:
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    try:
        return EvalReportRead.model_validate(result)
    except ValidationError:
        return None


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
    now = datetime.now(UTC)
    async with uow:
        job = await uow.jobs.add(
            kind="eval.run",
            status="queued",
            domain_id=None,
            source_id=None,
            payload={"suite_name": "retos-smoke", "requested_at": now.isoformat()},
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="eval.queued",
            entity_type="job",
            entity_id=job.id,
            payload={"suite_name": "retos-smoke"},
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="eval.queued",
            message="Queued local smoke eval suite",
            payload={"suite_name": "retos-smoke"},
        )
        running = await uow.jobs.update_status(
            job_id=job.id,
            status="running",
            started_at=now,
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
            message="Started local smoke eval suite",
            payload={"suite_name": "retos-smoke"},
        )
        await uow.commit()

    progress_store.append("eval.started", {"job_id": job.id, "suite_name": "retos-smoke"})
    try:
        report = run_smoke_eval_suite(index_root=Path(settings.index_root) / "evals")
    except Exception as exc:
        await mark_eval_failed(job_id=job.id, actor=actor, uow=uow, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Eval smoke suite failed to run",
        ) from exc

    completed_at = datetime.now(UTC)
    next_status: JobStatus = "succeeded" if report.passed else "failed"
    report_payload = report.to_dict()
    async with uow:
        await uow.jobs.update_payload(
            job_id=job.id,
            payload={
                "suite_name": report.suite_name,
                "requested_at": now.isoformat(),
                "result": report_payload,
            },
        )
        completed = await uow.jobs.update_status(
            job_id=job.id,
            status=next_status,
            completed_at=completed_at,
            error=None if report.passed else "Eval smoke suite failed",
        )
        if completed is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval job not found")
        await uow.journal_events.add(
            actor=actor,
            event_type="eval.completed" if report.passed else "eval.failed",
            entity_type="job",
            entity_id=job.id,
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
            entity_id=job.id,
            payload={"from_status": "running", "to_status": next_status},
        )
        await uow.progress_events.add(
            job_id=job.id,
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
            "job_id": job.id,
            "suite_name": report.suite_name,
            "passed": report.passed,
            "case_count": report.case_count,
        },
    )
    return EvalRunResponse(
        job=JobRead.from_job(completed), report=EvalReportRead.from_report(report)
    )


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

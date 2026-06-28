from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi import Path as PathParam
from pydantic import BaseModel, Field, ValidationError

from retos.api.dependencies import AdminSubjectDep, SettingsDep, UnitOfWorkDep
from retos.api.routes.events import progress_store
from retos.api.routes.jobs import JobRead
from retos.domain.jobs import Job, JobStatus
from retos.evals.datasets import (
    DatasetAdapterError,
    HotpotQAAdapterOptions,
    NaturalQuestionsAdapterOptions,
    SquadAdapterOptions,
    load_hotpotqa_cases,
    load_natural_questions_cases,
    load_squad_v2_cases,
)
from retos.evals.ocr import (
    OCRBenchmarkAdapterError,
    OCRBenchmarkOptions,
    OCRQualityReport,
    load_ocr_benchmark_cases,
    run_ocr_quality_suite,
)
from retos.evals.reports import write_report_files
from retos.evals.smoke import EvalCase, EvalSuiteReport, run_smoke_eval_suite

router = APIRouter(prefix="/evals", tags=["evals"])


class EvalReportRead(BaseModel):
    suite_name: str
    passed: bool
    case_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float]
    cases: list[dict[str, Any]]

    @classmethod
    def from_report(cls, report: EvalSuiteReport | OCRQualityReport) -> EvalReportRead:
        return cls.model_validate(report.to_dict())


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


class EvalTrendPointRead(BaseModel):
    job_id: str
    suite_name: str
    passed: bool
    case_count: int
    completed_at: datetime | None
    metrics: dict[str, float]


class EvalMetricTrendRead(BaseModel):
    name: str
    first: float
    latest: float
    delta: float
    minimum: float
    maximum: float
    average: float
    direction: str


class EvalSuiteTrendRead(BaseModel):
    suite_name: str
    run_count: int
    pass_rate: float
    latest: EvalRunSummaryRead
    metrics: list[EvalMetricTrendRead]
    points: list[EvalTrendPointRead]


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


class HotpotQAEvalRequest(BaseModel):
    dataset_path: str = Field(min_length=1, max_length=500)
    max_cases: int = Field(default=50, ge=1, le=1000)
    write_report: bool = False
    report_stem: str | None = Field(default=None, max_length=120)


class NaturalQuestionsEvalRequest(BaseModel):
    dataset_path: str = Field(min_length=1, max_length=500)
    max_cases: int = Field(default=50, ge=1, le=1000)
    write_report: bool = False
    report_stem: str | None = Field(default=None, max_length=120)


class OCRBenchmarkEvalRequest(BaseModel):
    dataset_path: str = Field(min_length=1, max_length=500)
    dataset_format: str = Field(default="manifest", pattern="^(manifest|funsd|sroie)$")
    max_cases: int = Field(default=50, ge=1, le=1000)
    write_report: bool = False
    report_stem: str | None = Field(default=None, max_length=120)
    max_character_error_rate: float = Field(default=0.20, ge=0, le=1)
    max_word_error_rate: float = Field(default=0.35, ge=0, le=1)
    max_pages: int = Field(default=1, ge=1, le=100)


class EvalRerunPlan(BaseModel):
    suite_name: str
    request: (
        SquadEvalRequest
        | HotpotQAEvalRequest
        | NaturalQuestionsEvalRequest
        | OCRBenchmarkEvalRequest
        | None
    ) = None


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


@router.get("/runs/trends", response_model=list[EvalSuiteTrendRead])
async def list_eval_run_trends(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    limit: Annotated[int, Query(ge=2, le=200)] = 100,
    suite_name: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
) -> list[EvalSuiteTrendRead]:
    async with uow:
        jobs = await uow.jobs.list_by_kind(kind="eval.run", limit=limit)
    return eval_trends_from_jobs(jobs=jobs, suite_name=suite_name)


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
    baseline_metrics = baseline_report.metrics
    candidate_metrics = candidate_report.metrics
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
    "/runs/{job_id}/rerun",
    response_model=EvalRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def rerun_eval(
    actor: AdminSubjectDep,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
    job_id: Annotated[str, PathParam(min_length=1)],
) -> EvalRunResponse:
    async with uow:
        original_job = await uow.jobs.get(job_id)
    plan = rerun_plan_from_eval_job(original_job)
    if plan.suite_name == "retos-smoke":
        return await run_smoke_eval_plan(
            actor=actor,
            settings=settings,
            uow=uow,
            rerun_from_job_id=job_id,
        )
    if plan.suite_name == "squad-v2" and isinstance(plan.request, SquadEvalRequest):
        return await run_squad_eval_plan(
            request=plan.request,
            actor=actor,
            settings=settings,
            uow=uow,
            rerun_from_job_id=job_id,
        )
    if plan.suite_name == "hotpotqa" and isinstance(plan.request, HotpotQAEvalRequest):
        return await run_hotpotqa_eval_plan(
            request=plan.request,
            actor=actor,
            settings=settings,
            uow=uow,
            rerun_from_job_id=job_id,
        )
    if plan.suite_name == "natural-questions" and isinstance(
        plan.request,
        NaturalQuestionsEvalRequest,
    ):
        return await run_natural_questions_eval_plan(
            request=plan.request,
            actor=actor,
            settings=settings,
            uow=uow,
            rerun_from_job_id=job_id,
        )
    if plan.suite_name.startswith("ocr-") and isinstance(plan.request, OCRBenchmarkEvalRequest):
        return await run_ocr_benchmark_eval_plan(
            request=plan.request,
            actor=actor,
            settings=settings,
            uow=uow,
            rerun_from_job_id=job_id,
        )
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"Eval suite {plan.suite_name} cannot be rerun",
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
    return await run_smoke_eval_plan(actor=actor, settings=settings, uow=uow)


async def run_smoke_eval_plan(
    *,
    actor: str,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
    rerun_from_job_id: str | None = None,
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
        payload=rerun_payload(rerun_from_job_id),
    )
    try:
        report = with_eval_metadata(
            run_smoke_eval_suite(index_root=Path(settings.index_root) / "evals"),
            {"source": "built-in", "dataset": "retos-smoke-fixtures"},
        )
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
        payload=rerun_payload(rerun_from_job_id),
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
    return await run_squad_eval_plan(request=request, actor=actor, settings=settings, uow=uow)


async def run_squad_eval_plan(
    *,
    request: SquadEvalRequest,
    actor: str,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
    rerun_from_job_id: str | None = None,
) -> EvalRunResponse:
    return await run_dataset_evals(
        request=request,
        actor=actor,
        settings=settings,
        uow=uow,
        suite_name="squad-v2",
        suite_label="SQuAD",
        index_namespace="squad",
        rerun_from_job_id=rerun_from_job_id,
        load_cases=lambda dataset_path: load_squad_v2_cases(
            dataset_path,
            SquadAdapterOptions(max_cases=request.max_cases),
        ),
    )


@router.post(
    "/hotpotqa",
    response_model=EvalRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_hotpotqa_evals(
    request: HotpotQAEvalRequest,
    actor: AdminSubjectDep,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
) -> EvalRunResponse:
    return await run_hotpotqa_eval_plan(request=request, actor=actor, settings=settings, uow=uow)


async def run_hotpotqa_eval_plan(
    *,
    request: HotpotQAEvalRequest,
    actor: str,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
    rerun_from_job_id: str | None = None,
) -> EvalRunResponse:
    return await run_dataset_evals(
        request=request,
        actor=actor,
        settings=settings,
        uow=uow,
        suite_name="hotpotqa",
        suite_label="HotpotQA",
        index_namespace="hotpotqa",
        rerun_from_job_id=rerun_from_job_id,
        load_cases=lambda dataset_path: load_hotpotqa_cases(
            dataset_path,
            HotpotQAAdapterOptions(max_cases=request.max_cases),
        ),
    )


@router.post(
    "/natural-questions",
    response_model=EvalRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_natural_questions_evals(
    request: NaturalQuestionsEvalRequest,
    actor: AdminSubjectDep,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
) -> EvalRunResponse:
    return await run_natural_questions_eval_plan(
        request=request,
        actor=actor,
        settings=settings,
        uow=uow,
    )


async def run_natural_questions_eval_plan(
    *,
    request: NaturalQuestionsEvalRequest,
    actor: str,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
    rerun_from_job_id: str | None = None,
) -> EvalRunResponse:
    return await run_dataset_evals(
        request=request,
        actor=actor,
        settings=settings,
        uow=uow,
        suite_name="natural-questions",
        suite_label="Natural Questions",
        index_namespace="natural-questions",
        rerun_from_job_id=rerun_from_job_id,
        load_cases=lambda dataset_path: load_natural_questions_cases(
            dataset_path,
            NaturalQuestionsAdapterOptions(max_cases=request.max_cases),
        ),
    )


@router.post(
    "/ocr-benchmark",
    response_model=EvalRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_ocr_benchmark_evals(
    request: OCRBenchmarkEvalRequest,
    actor: AdminSubjectDep,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
) -> EvalRunResponse:
    return await run_ocr_benchmark_eval_plan(
        request=request,
        actor=actor,
        settings=settings,
        uow=uow,
    )


async def run_ocr_benchmark_eval_plan(
    *,
    request: OCRBenchmarkEvalRequest,
    actor: str,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
    rerun_from_job_id: str | None = None,
) -> EvalRunResponse:
    dataset_path = resolve_dataset_path(settings.eval_dataset_root, request.dataset_path)
    if not dataset_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eval dataset file not found",
        )

    suite_name = f"ocr-{request.dataset_format}"
    now = datetime.now(UTC)
    job = await queue_eval_job(
        actor=actor,
        uow=uow,
        suite_name=suite_name,
        requested_at=now,
        queued_message="Queued OCR benchmark eval suite",
        started_message="Started OCR benchmark eval suite",
        payload={
            "dataset_path": str(dataset_path),
            "dataset_format": request.dataset_format,
            "max_cases": request.max_cases,
            "write_report": request.write_report,
            "report_stem": request.report_stem,
            "max_character_error_rate": request.max_character_error_rate,
            "max_word_error_rate": request.max_word_error_rate,
            "max_pages": request.max_pages,
            **rerun_payload(rerun_from_job_id),
        },
    )
    try:
        cases = load_ocr_benchmark_cases(
            dataset_path,
            OCRBenchmarkOptions(
                max_cases=request.max_cases,
                dataset_format=request.dataset_format,
            ),
        )
        if not cases:
            raise OCRBenchmarkAdapterError("OCR benchmark dataset produced no eval cases")
        report = run_ocr_quality_suite(
            work_dir=Path(settings.index_root) / "evals" / suite_name,
            suite_name=suite_name,
            cases=cases,
            max_character_error_rate=request.max_character_error_rate,
            max_word_error_rate=request.max_word_error_rate,
            max_pages=request.max_pages,
        )
    except OCRBenchmarkAdapterError as exc:
        await mark_eval_failed(job_id=job.id, actor=actor, uow=uow, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        await mark_eval_failed(job_id=job.id, actor=actor, uow=uow, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OCR benchmark eval suite failed to run",
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
                detail="OCR benchmark eval report failed to write",
            ) from exc
        report_paths = {"json": str(json_path), "markdown": str(markdown_path)}

    completed = await complete_eval_job(
        actor=actor,
        uow=uow,
        job_id=job.id,
        requested_at=now,
        report=report,
        failure_error="OCR benchmark eval suite failed",
        payload={
            "dataset_path": str(dataset_path),
            "dataset_format": request.dataset_format,
            "max_cases": request.max_cases,
            "write_report": request.write_report,
            "report_stem": request.report_stem,
            "max_character_error_rate": request.max_character_error_rate,
            "max_word_error_rate": request.max_word_error_rate,
            "max_pages": request.max_pages,
            "report_paths": report_paths,
            **rerun_payload(rerun_from_job_id),
        },
    )
    return EvalRunResponse(
        job=JobRead.from_job(completed),
        report=EvalReportRead.from_report(report),
        report_paths=report_paths,
    )


async def run_dataset_evals(
    *,
    request: SquadEvalRequest | HotpotQAEvalRequest | NaturalQuestionsEvalRequest,
    actor: str,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
    suite_name: str,
    suite_label: str,
    index_namespace: str,
    rerun_from_job_id: str | None = None,
    load_cases: Callable[[Path], tuple[EvalCase, ...]],
) -> EvalRunResponse:
    dataset_path = resolve_dataset_path(settings.eval_dataset_root, request.dataset_path)
    if not dataset_path.exists() or not dataset_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eval dataset file not found",
        )

    now = datetime.now(UTC)
    job = await queue_eval_job(
        actor=actor,
        uow=uow,
        suite_name=suite_name,
        requested_at=now,
        queued_message=f"Queued {suite_label} eval suite",
        started_message=f"Started {suite_label} eval suite",
        payload={
            "dataset_path": str(dataset_path),
            "max_cases": request.max_cases,
            "write_report": request.write_report,
            "report_stem": request.report_stem,
            **rerun_payload(rerun_from_job_id),
        },
    )
    try:
        cases = load_cases(dataset_path)
        if not cases:
            raise DatasetAdapterError(f"{suite_label} dataset produced no eval cases")
        report = with_eval_metadata(
            run_smoke_eval_suite(
                index_root=Path(settings.index_root) / "evals" / index_namespace,
                suite_name=suite_name,
                cases=cases,
            ),
            {
                "adapter": suite_name,
                "dataset_path": str(dataset_path),
                "max_cases": request.max_cases,
                "source": "api",
            },
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
            detail=f"{suite_label} eval suite failed to run",
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
                detail=f"{suite_label} eval report failed to write",
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
        failure_error=f"{suite_label} eval suite failed",
        payload={
            "dataset_path": str(dataset_path),
            "max_cases": request.max_cases,
            "write_report": request.write_report,
            "report_stem": request.report_stem,
            "report_paths": report_paths,
            **rerun_payload(rerun_from_job_id),
        },
    )
    return EvalRunResponse(
        job=JobRead.from_job(completed),
        report=EvalReportRead.from_report(report),
        report_paths=report_paths,
    )


def with_eval_metadata(
    report: EvalSuiteReport,
    metadata: dict[str, Any],
) -> EvalSuiteReport:
    return replace(report, metadata={**report.metadata, **metadata})


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


def rerun_plan_from_eval_job(job: Job | None) -> EvalRerunPlan:
    if job is None or job.kind != "eval.run":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval run not found")

    payload = job.payload
    suite_name = string_from_payload(payload, "suite_name")
    if suite_name == "retos-smoke":
        return EvalRerunPlan(suite_name=suite_name)

    if suite_name in {"squad-v2", "hotpotqa", "natural-questions"}:
        request_payload = {
            "dataset_path": required_string_from_payload(payload, "dataset_path"),
            "max_cases": int_from_payload(payload, "max_cases", default=50),
            "write_report": bool_from_payload(
                payload,
                "write_report",
                default=payload.get("report_paths") is not None,
            ),
            "report_stem": optional_string_from_payload(payload, "report_stem"),
        }
        request_type: type[SquadEvalRequest | HotpotQAEvalRequest | NaturalQuestionsEvalRequest]
        if suite_name == "squad-v2":
            request_type = SquadEvalRequest
        elif suite_name == "hotpotqa":
            request_type = HotpotQAEvalRequest
        else:
            request_type = NaturalQuestionsEvalRequest
        return EvalRerunPlan(
            suite_name=suite_name,
            request=validated_rerun_request(request_type, request_payload),
        )

    if suite_name.startswith("ocr-"):
        dataset_format = optional_string_from_payload(payload, "dataset_format")
        if dataset_format is None:
            dataset_format = suite_name.removeprefix("ocr-") or "manifest"
        request_payload = {
            "dataset_path": required_string_from_payload(payload, "dataset_path"),
            "dataset_format": dataset_format,
            "max_cases": int_from_payload(payload, "max_cases", default=50),
            "write_report": bool_from_payload(
                payload,
                "write_report",
                default=payload.get("report_paths") is not None,
            ),
            "report_stem": optional_string_from_payload(payload, "report_stem"),
            "max_character_error_rate": float_from_payload(
                payload,
                "max_character_error_rate",
                default=0.20,
            ),
            "max_word_error_rate": float_from_payload(
                payload,
                "max_word_error_rate",
                default=0.35,
            ),
            "max_pages": int_from_payload(payload, "max_pages", default=1),
        }
        return EvalRerunPlan(
            suite_name=suite_name,
            request=validated_rerun_request(OCRBenchmarkEvalRequest, request_payload),
        )

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"Eval suite {suite_name or '<missing>'} cannot be rerun",
    )


def validated_rerun_request(
    request_type: type[
        SquadEvalRequest
        | HotpotQAEvalRequest
        | NaturalQuestionsEvalRequest
        | OCRBenchmarkEvalRequest
    ],
    payload: dict[str, Any],
) -> SquadEvalRequest | HotpotQAEvalRequest | NaturalQuestionsEvalRequest | OCRBenchmarkEvalRequest:
    try:
        return request_type.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Eval run payload cannot be rerun",
        ) from exc


def string_from_payload(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def required_string_from_payload(payload: dict[str, Any], key: str) -> str:
    value = string_from_payload(payload, key)
    if not value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Eval run cannot be rerun without {key}",
        )
    return value


def optional_string_from_payload(payload: dict[str, Any], key: str) -> str | None:
    value = string_from_payload(payload, key)
    return value or None


def int_from_payload(payload: dict[str, Any], key: str, *, default: int) -> int:
    value = payload.get(key)
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def float_from_payload(payload: dict[str, Any], key: str, *, default: float) -> float:
    value = payload.get(key)
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def bool_from_payload(payload: dict[str, Any], key: str, *, default: bool) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    return default


def rerun_payload(rerun_from_job_id: str | None) -> dict[str, str]:
    if rerun_from_job_id is None:
        return {}
    return {"rerun_from_job_id": rerun_from_job_id}


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


def eval_trends_from_jobs(
    *,
    jobs: list[Job],
    suite_name: str | None = None,
) -> list[EvalSuiteTrendRead]:
    grouped: dict[str, list[tuple[Job, EvalReportRead]]] = {}
    for job in jobs:
        if job.kind != "eval.run":
            continue
        report = report_from_payload(job.payload)
        if report is None:
            continue
        if suite_name is not None and report.suite_name != suite_name:
            continue
        grouped.setdefault(report.suite_name, []).append((job, report))

    trends: list[EvalSuiteTrendRead] = []
    for suite, runs in grouped.items():
        chronological = sorted(
            runs, key=lambda item: (item[0].completed_at or item[0].updated_at, item[0].id)
        )
        latest_job, latest_report = chronological[-1]
        points = [
            EvalTrendPointRead(
                job_id=job.id,
                suite_name=report.suite_name,
                passed=report.passed,
                case_count=report.case_count,
                completed_at=job.completed_at,
                metrics=report.metrics,
            )
            for job, report in chronological
        ]
        trends.append(
            EvalSuiteTrendRead(
                suite_name=suite,
                run_count=len(chronological),
                pass_rate=sum(1 for _, report in chronological if report.passed)
                / len(chronological),
                latest=summary_from_eval_run(latest_job, latest_report),
                metrics=metric_trends_for_points(points),
                points=points,
            )
        )
    return sorted(
        trends,
        key=lambda trend: (trend.latest.completed_at or datetime.min.replace(tzinfo=UTC)),
        reverse=True,
    )


def metric_trends_for_points(points: list[EvalTrendPointRead]) -> list[EvalMetricTrendRead]:
    metric_names = sorted({name for point in points for name in point.metrics})
    trends: list[EvalMetricTrendRead] = []
    for name in metric_names:
        values = [point.metrics[name] for point in points if name in point.metrics]
        if not values:
            continue
        first = values[0]
        latest = values[-1]
        delta = latest - first
        trends.append(
            EvalMetricTrendRead(
                name=name,
                first=first,
                latest=latest,
                delta=delta,
                minimum=min(values),
                maximum=max(values),
                average=sum(values) / len(values),
                direction=metric_trend_direction(name=name, delta=delta),
            )
        )
    return trends


def metric_trend_direction(*, name: str, delta: float) -> str:
    if delta == 0:
        return "unchanged"
    lower_is_better = name.endswith("_error_rate") or "error_rate" in name
    if lower_is_better:
        return "improved" if delta < 0 else "regressed"
    return "improved" if delta > 0 else "regressed"


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
    report: EvalSuiteReport | OCRQualityReport,
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
                "metadata": report_payload.get("metadata", {}),
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
                "metadata": report_payload.get("metadata", {}),
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
            "metadata": report_payload.get("metadata", {}),
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

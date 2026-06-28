from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, Field

from retos.agent.service import (
    DEFAULT_AGENT_BUDGET,
    AgentQueryError,
    AgentQueryResult,
    fail_agent_query_job,
    run_agent_query,
)
from retos.api.dependencies import AdminSubjectDep, SettingsDep, UnitOfWorkDep
from retos.api.routes.events import progress_store
from retos.api.routes.jobs import JobRead
from retos.domain.jobs import Job
from retos.jobs.tasks import agent_query_job
from retos.search.index import TantivySearchIndex

router = APIRouter(tags=["agent"])


class AgentBudgetRequest(BaseModel):
    max_searches: int = Field(default=DEFAULT_AGENT_BUDGET["max_searches"], ge=1, le=50)
    max_citations: int = Field(default=DEFAULT_AGENT_BUDGET["max_citations"], ge=1, le=20)
    max_evidence_tokens: int = Field(
        default=DEFAULT_AGENT_BUDGET["max_evidence_tokens"],
        ge=1,
        le=100_000,
    )
    max_runtime_seconds: int = Field(
        default=DEFAULT_AGENT_BUDGET["max_runtime_seconds"],
        ge=1,
        le=3_600,
    )


class AgentQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)
    run_inline: bool = False
    budget: AgentBudgetRequest = Field(default_factory=AgentBudgetRequest)


class AgentCitationRead(BaseModel):
    segment_id: str
    document_id: str
    document_version_id: str
    title: str
    anchor: str | None
    score: float
    text: str


class AgentNeighborContextRead(BaseModel):
    segment_id: str
    source_segment_id: str
    document_id: str
    document_version_id: str
    title: str
    anchor: str | None
    ordinal: int
    distance: int
    text: str
    token_count: int


class AgentBudgetRead(BaseModel):
    max_searches: int
    max_citations: int
    max_evidence_tokens: int
    max_runtime_seconds: int


class AgentBudgetUsageRead(BaseModel):
    budget: AgentBudgetRead
    search_count: int
    citation_count: int
    evidence_tokens: int
    runtime_ms: int
    within_budget: bool


class AgentEvidenceAuditRead(BaseModel):
    grounded: bool
    cited_segment_ids: list[str]
    unreferenced_citation_ids: list[str]


class AgentContradictionFindingRead(BaseModel):
    segment_ids: list[str]
    shared_terms: list[str]
    summary: str


class AgentContradictionAuditRead(BaseModel):
    checked: bool
    conflict_count: int
    findings: list[AgentContradictionFindingRead]


class AgentMultiHopAuditRead(BaseModel):
    checked: bool
    requires_multi_hop: bool
    status: str
    document_count: int
    bridge_terms: list[str]
    warnings: list[str]


class AgentQueryPlanStepRead(BaseModel):
    name: str
    description: str
    status: str


class AgentQueryPlanRead(BaseModel):
    strategy: str
    requires_multi_hop: bool
    search_queries: list[str]
    expected_evidence: str
    steps: list[AgentQueryPlanStepRead]
    warnings: list[str]


class AgentEvidenceRouteDocumentRead(BaseModel):
    document_id: str
    title: str
    segment_ids: list[str]
    anchors: list[str]


class AgentEvidenceRouteRead(BaseModel):
    coverage_level: str
    segment_count: int
    document_count: int
    anchor_count: int
    multi_document: bool
    has_neighbor_context: bool
    warnings: list[str]
    documents: list[AgentEvidenceRouteDocumentRead]


class AgentQueryResultRead(BaseModel):
    answer: str
    provider: str
    model: str
    runtime: str
    evidence_audit: AgentEvidenceAuditRead
    contradiction_audit: AgentContradictionAuditRead
    multi_hop_audit: AgentMultiHopAuditRead
    query_plan: AgentQueryPlanRead
    evidence_route: AgentEvidenceRouteRead
    usage: AgentBudgetUsageRead
    citations: list[AgentCitationRead]
    neighbor_context: list[AgentNeighborContextRead]

    @classmethod
    def from_result(cls, result: AgentQueryResult) -> AgentQueryResultRead:
        return cls(
            answer=result.answer,
            provider=result.provider,
            model=result.model,
            runtime=result.runtime,
            evidence_audit=AgentEvidenceAuditRead(
                grounded=result.evidence_audit.grounded,
                cited_segment_ids=result.evidence_audit.cited_segment_ids,
                unreferenced_citation_ids=result.evidence_audit.unreferenced_citation_ids,
            ),
            contradiction_audit=AgentContradictionAuditRead(
                checked=result.contradiction_audit.checked,
                conflict_count=result.contradiction_audit.conflict_count,
                findings=[
                    AgentContradictionFindingRead(
                        segment_ids=finding.segment_ids,
                        shared_terms=finding.shared_terms,
                        summary=finding.summary,
                    )
                    for finding in result.contradiction_audit.findings
                ],
            ),
            multi_hop_audit=AgentMultiHopAuditRead(
                checked=result.multi_hop_audit.checked,
                requires_multi_hop=result.multi_hop_audit.requires_multi_hop,
                status=result.multi_hop_audit.status,
                document_count=result.multi_hop_audit.document_count,
                bridge_terms=result.multi_hop_audit.bridge_terms,
                warnings=result.multi_hop_audit.warnings,
            ),
            query_plan=AgentQueryPlanRead(
                strategy=result.query_plan.strategy,
                requires_multi_hop=result.query_plan.requires_multi_hop,
                search_queries=result.query_plan.search_queries,
                expected_evidence=result.query_plan.expected_evidence,
                warnings=result.query_plan.warnings,
                steps=[
                    AgentQueryPlanStepRead(
                        name=step.name,
                        description=step.description,
                        status=step.status,
                    )
                    for step in result.query_plan.steps
                ],
            ),
            evidence_route=AgentEvidenceRouteRead(
                coverage_level=result.evidence_route.coverage_level,
                segment_count=result.evidence_route.segment_count,
                document_count=result.evidence_route.document_count,
                anchor_count=result.evidence_route.anchor_count,
                multi_document=result.evidence_route.multi_document,
                has_neighbor_context=result.evidence_route.has_neighbor_context,
                warnings=result.evidence_route.warnings,
                documents=[
                    AgentEvidenceRouteDocumentRead(
                        document_id=document.document_id,
                        title=document.title,
                        segment_ids=document.segment_ids,
                        anchors=document.anchors,
                    )
                    for document in result.evidence_route.documents
                ],
            ),
            usage=AgentBudgetUsageRead(
                budget=AgentBudgetRead(
                    max_searches=result.usage.budget.max_searches,
                    max_citations=result.usage.budget.max_citations,
                    max_evidence_tokens=result.usage.budget.max_evidence_tokens,
                    max_runtime_seconds=result.usage.budget.max_runtime_seconds,
                ),
                search_count=result.usage.search_count,
                citation_count=result.usage.citation_count,
                evidence_tokens=result.usage.evidence_tokens,
                runtime_ms=result.usage.runtime_ms,
                within_budget=result.usage.within_budget,
            ),
            citations=[
                AgentCitationRead(
                    segment_id=citation.segment_id,
                    document_id=citation.document_id,
                    document_version_id=citation.document_version_id,
                    title=citation.title,
                    anchor=citation.anchor,
                    score=citation.score,
                    text=citation.text,
                )
                for citation in result.citations
            ],
            neighbor_context=[
                AgentNeighborContextRead(
                    segment_id=context.segment_id,
                    source_segment_id=context.source_segment_id,
                    document_id=context.document_id,
                    document_version_id=context.document_version_id,
                    title=context.title,
                    anchor=context.anchor,
                    ordinal=context.ordinal,
                    distance=context.distance,
                    text=context.text,
                    token_count=len(context.text.split()),
                )
                for context in result.neighbor_context
            ],
        )


class AgentQueryResponse(BaseModel):
    job: JobRead
    result: AgentQueryResultRead | None = None


def enqueue_agent_query(job: Job) -> None:
    agent_query_job.delay(job.id)


@router.post(
    "/domains/{domain_id}/queries",
    response_model=AgentQueryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def query_domain(
    payload: AgentQueryRequest,
    actor: AdminSubjectDep,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
    domain_id: Annotated[str, Path(min_length=1)],
) -> AgentQueryResponse:
    question = payload.question.strip()
    async with uow:
        domain = await uow.domains.get(domain_id)
        if domain is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")

        job = await uow.jobs.add(
            kind="agent.query",
            status="queued",
            domain_id=domain_id,
            source_id=None,
            payload={
                "question": question,
                "limit": payload.limit,
                "budget": payload.budget.model_dump(),
                "requested_at": datetime.now().isoformat(),
            },
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="agent.queued",
            entity_type="job",
            entity_id=job.id,
            payload={
                "domain_id": domain_id,
                "question": question,
                "limit": payload.limit,
                "budget": payload.budget.model_dump(),
            },
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="agent.queued",
            message=f"Queued research query for {domain.slug}",
            payload={
                "domain_id": domain_id,
                "domain_slug": domain.slug,
                "budget": payload.budget.model_dump(),
            },
        )
        await uow.commit()

    progress_store.append("agent.queued", {"job_id": job.id, "domain_id": domain_id})
    if payload.run_inline or settings.env == "test":
        try:
            result = await run_agent_query(
                job_id=job.id,
                uow=uow,
                index=TantivySearchIndex(settings.index_root),
                settings=settings,
                actor=actor,
            )
        except AgentQueryError as exc:
            await fail_agent_query_job(job_id=job.id, uow=uow, error=str(exc), actor=actor)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        async with uow:
            completed = await uow.jobs.get(job.id)
        if completed is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return AgentQueryResponse(
            job=JobRead.from_job(completed),
            result=AgentQueryResultRead.from_result(result),
        )

    enqueue_agent_query(job)
    return AgentQueryResponse(job=JobRead.from_job(job), result=None)

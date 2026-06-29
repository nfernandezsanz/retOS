from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from retos.api.dependencies import AdminSubjectDep, SessionFactoryDep, SettingsDep
from retos.demo.seed import DemoSeedResult, seed_demo_corpus

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoSeedRequest(BaseModel):
    rebuild_index: bool = True


class DemoSeedRead(BaseModel):
    domain_id: str
    source_id: str
    created_documents: int
    skipped_documents: int
    index_job_id: str | None
    indexed_segments: int

    @classmethod
    def from_result(cls, result: DemoSeedResult) -> DemoSeedRead:
        return cls(
            domain_id=result.domain_id,
            source_id=result.source_id,
            created_documents=result.created_documents,
            skipped_documents=result.skipped_documents,
            index_job_id=result.index_job_id,
            indexed_segments=result.indexed_segments,
        )


@router.post("/seed", response_model=DemoSeedRead, status_code=status.HTTP_200_OK)
async def seed_demo(
    payload: DemoSeedRequest,
    _actor: AdminSubjectDep,
    session_factory: SessionFactoryDep,
    settings: SettingsDep,
) -> DemoSeedRead:
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo seed is disabled in production",
        )
    result = await seed_demo_corpus(
        session_factory=session_factory,
        index_root=settings.index_root,
        rebuild_index=payload.rebuild_index,
    )
    return DemoSeedRead.from_result(result)

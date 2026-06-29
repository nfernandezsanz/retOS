from fastapi import APIRouter
from pydantic import BaseModel

from retos.api.dependencies import SettingsDep, ViewerSubjectDep
from retos.core.config import AgentRuntimeMode
from retos.llm.providers import (
    ActiveProvider,
    ProviderName,
    ProviderProfile,
    RuntimeSwitchPlan,
    active_provider,
    list_provider_profiles,
    plan_runtime_switch,
)

router = APIRouter(prefix="/llm", tags=["llm"])


class ProviderCatalogResponse(BaseModel):
    active: ActiveProvider
    agent_runtime: str
    paid_providers_enabled: bool
    providers: list[ProviderProfile]


class RuntimePlanRequest(BaseModel):
    provider: ProviderName
    agent_runtime: AgentRuntimeMode
    allow_paid_llm: bool | None = None


@router.get("/providers", response_model=ProviderCatalogResponse)
async def providers(
    _: ViewerSubjectDep,
    settings: SettingsDep,
) -> ProviderCatalogResponse:
    return ProviderCatalogResponse(
        active=active_provider(settings),
        agent_runtime=settings.agent_runtime,
        paid_providers_enabled=settings.allow_paid_llm,
        providers=list_provider_profiles(settings),
    )


@router.post("/runtime-plan", response_model=RuntimeSwitchPlan)
async def runtime_plan(
    payload: RuntimePlanRequest,
    _: ViewerSubjectDep,
    settings: SettingsDep,
) -> RuntimeSwitchPlan:
    return plan_runtime_switch(
        settings,
        provider=payload.provider,
        agent_runtime=payload.agent_runtime,
        allow_paid_llm=payload.allow_paid_llm,
    )

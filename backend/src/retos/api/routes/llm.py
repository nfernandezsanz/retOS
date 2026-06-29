from fastapi import APIRouter
from pydantic import BaseModel

from retos.api.dependencies import SettingsDep, ViewerSubjectDep
from retos.llm.providers import (
    ActiveProvider,
    ProviderProfile,
    active_provider,
    list_provider_profiles,
)

router = APIRouter(prefix="/llm", tags=["llm"])


class ProviderCatalogResponse(BaseModel):
    active: ActiveProvider
    agent_runtime: str
    paid_providers_enabled: bool
    providers: list[ProviderProfile]


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

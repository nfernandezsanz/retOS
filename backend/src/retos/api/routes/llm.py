from fastapi import APIRouter
from pydantic import BaseModel

from retos.api.dependencies import AdminSubjectDep, SettingsDep
from retos.llm.providers import (
    ActiveProvider,
    ProviderProfile,
    active_provider,
    list_provider_profiles,
)

router = APIRouter(prefix="/llm", tags=["llm"])


class ProviderCatalogResponse(BaseModel):
    active: ActiveProvider
    providers: list[ProviderProfile]


@router.get("/providers", response_model=ProviderCatalogResponse)
async def providers(
    _: AdminSubjectDep,
    settings: SettingsDep,
) -> ProviderCatalogResponse:
    return ProviderCatalogResponse(
        active=active_provider(settings),
        providers=list_provider_profiles(settings),
    )

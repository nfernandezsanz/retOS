from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from retos.api.dependencies import SessionFactoryDep, SettingsDep

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadinessResponse(BaseModel):
    status: str
    service: str
    components: dict[str, str]


class VersionResponse(BaseModel):
    service: str
    version: str
    revision: str
    created: str


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service="retos-api")


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readyz(session_factory: SessionFactoryDep, response: Response) -> ReadinessResponse:
    try:
        async with session_factory() as session:
            await session.execute(text("select 1"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="degraded",
            service="retos-api",
            components={"database": "unavailable"},
        )
    return ReadinessResponse(
        status="ok",
        service="retos-api",
        components={"database": "ok"},
    )


@router.get("/versionz", response_model=VersionResponse)
async def versionz(settings: SettingsDep) -> VersionResponse:
    return VersionResponse(
        service="retos-api",
        version=settings.version,
        revision=settings.revision,
        created=settings.created,
    )

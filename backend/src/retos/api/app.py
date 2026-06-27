from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from retos.api.routes import auth, events, health
from retos.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    resolved.validate_runtime_security()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(
        title="RetOS API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in resolved.allowed_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(events.router)
    return app

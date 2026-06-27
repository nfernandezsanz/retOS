from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from retos.api.routes import auth, documents, domains, events, health, ingestions, jobs, llm, search
from retos.core.config import Settings, get_settings
from retos.persistence.bootstrap import bootstrap_admin_user
from retos.persistence.database import (
    create_engine,
    create_schema,
    create_session_factory,
    dispose_engine,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    resolved.validate_runtime_security()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(resolved.database_url)
        app.state.database_engine = engine
        app.state.session_factory = create_session_factory(engine)
        if resolved.database_create_all:
            await create_schema(engine)
        await bootstrap_admin_user(
            settings=resolved,
            session_factory=app.state.session_factory,
        )
        try:
            yield
        finally:
            await dispose_engine(engine)

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
    app.include_router(domains.router)
    app.include_router(documents.router)
    app.include_router(ingestions.router)
    app.include_router(jobs.router)
    app.include_router(llm.router)
    app.include_router(search.router)
    app.include_router(events.router)
    return app

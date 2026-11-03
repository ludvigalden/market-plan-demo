"""FastAPI application factory with lifespan-managed resources."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from plandesk.ai.provider import AdaptationProvider
from plandesk.ai.stub import StubProvider
from plandesk.config import Settings, get_settings
from plandesk.db import build_engine, build_sessionmaker
from plandesk.errors import install_error_handlers
from plandesk.middleware import CorrelationIdMiddleware
from plandesk.routers import campaigns, suggestions
from plandesk.schemas import Health
from plandesk.services.holidays import HolidayClient

log = logging.getLogger("plandesk")


def _operation_id(route: APIRoute) -> str:
    """Stable operation ids: the endpoint function name, so generated clients never churn."""
    return route.name


def build_provider(settings: Settings) -> AdaptationProvider:
    if settings.ai_provider == "foundry":
        from plandesk.ai.foundry import FoundryProvider

        return FoundryProvider(settings.foundry_project_endpoint, settings.foundry_model_deployment)
    return StubProvider()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(settings.database_url)
        http = httpx.AsyncClient(
            timeout=settings.holidays_timeout_seconds,
            headers={"User-Agent": "market-plan-desk/0.1"},
        )
        app.state.settings = settings
        app.state.engine = engine
        app.state.sessionmaker = build_sessionmaker(engine)
        app.state.holiday_client = HolidayClient(
            http,
            settings.holidays_base_url,
            max_attempts=settings.holidays_max_attempts,
            backoff_seconds=settings.holidays_backoff_seconds,
        )
        provider = build_provider(settings)
        app.state.ai_provider = provider
        log.info("started ai_provider=%s", provider.name)
        try:
            yield
        finally:
            close = getattr(provider, "aclose", None)
            if close is not None:
                await close()
            await http.aclose()
            await engine.dispose()

    app = FastAPI(
        title="Market Plan Desk API",
        version="0.1.0",
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
    )
    app.add_middleware(CorrelationIdMiddleware)
    install_error_handlers(app)

    api = APIRouter(prefix="/api")
    api.include_router(campaigns.router)
    api.include_router(suggestions.router)
    app.include_router(api)

    @app.get("/healthz", response_model=Health, tags=["health"])
    async def healthz(request: Request) -> Health:
        db = "ok"
        try:
            async with request.app.state.engine.connect() as conn:
                await conn.execute(text("select 1"))
        except Exception:
            db = "unavailable"
        return Health(
            status="ok" if db == "ok" else "degraded",
            database=db,
            ai_provider=request.app.state.ai_provider.name,
        )

    if settings.static_dir:
        _mount_spa(app, Path(settings.static_dir))
    return app


def _mount_spa(app: FastAPI, root: Path) -> None:
    """Serve the built SPA: hashed assets, a fixed set of top-level files, else index.html."""
    index = root / "index.html"
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")
    top_level = {p.name: p for p in root.iterdir() if p.is_file()} if root.is_dir() else {}

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:  # pyright: ignore[reportUnusedFunction]
        return FileResponse(top_level.get(path, index))


app = create_app()

"""FastAPI application factory and foundational health endpoints."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

import structlog
from fastapi import FastAPI, Response, status
from pydantic import BaseModel
from rag_core.config import AppSettings, get_settings
from rag_core.observability.logging import configure_logging


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: Literal["ok", "not_ready"]
    checks: dict[str, bool]


def _readiness_checks(settings: AppSettings) -> dict[str, bool]:
    return {
        "database_configured": bool(settings.database_url),
        "groq_configured": settings.groq_api_key is not None,
        "redis_configured": bool(settings.redis_broker_url),
    }


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level, resolved_settings.json_logs)
    logger = structlog.get_logger(__name__)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "api_started",
            environment=resolved_settings.environment,
            service=resolved_settings.service_name,
        )
        yield
        logger.info("api_stopped", service=resolved_settings.service_name)

    application = FastAPI(
        title="RAG Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings

    @application.get("/health/live", response_model=LivenessResponse)
    async def live() -> LivenessResponse:
        return LivenessResponse(service=resolved_settings.service_name, version="0.1.0")

    @application.get("/health/ready", response_model=ReadinessResponse)
    async def ready(response: Response) -> ReadinessResponse:
        checks = _readiness_checks(resolved_settings)
        is_ready = all(checks.values())
        if not is_ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="ok" if is_ready else "not_ready", checks=checks)

    return application


app = create_app()

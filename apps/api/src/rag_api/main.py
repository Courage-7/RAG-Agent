import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

import structlog
from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import HTMLResponse, StreamingResponse
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field
from rag_core.agent.graph import AdaptiveRagGraph
from rag_core.config import AppSettings, get_settings
from rag_core.database.connection import check_database_health, create_async_pool
from rag_core.database.redis import check_redis_health
from rag_core.errors import DocumentParsingError
from rag_core.ingestion.parsers import DocumentParser
from rag_core.ingestion.repository import create_ingestion_job
from rag_core.jobs.models import JobStatus
from rag_core.models.contracts import ChatMessage
from rag_core.observability.logging import configure_logging
from rag_core.retrieval.models import AnswerStatus, GroundedAnswer
from rag_core.retrieval.service import QueryRequest, RagService


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: Literal["ok", "not_ready"]
    checks: dict[str, bool]


class IngestionRequest(BaseModel):
    workspace_id: UUID
    knowledge_base_id: UUID
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)


class IngestionResponse(BaseModel):
    job_id: UUID
    document_id: UUID
    document_version_id: UUID
    status: JobStatus = JobStatus.QUEUED


class AgentQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    workspace_id: UUID
    user_id: UUID
    knowledge_base_ids: tuple[UUID, ...] = ()
    chat_history: tuple[ChatMessage, ...] = ()
    thread_id: str | None = None


class AgentQueryResponse(BaseModel):
    thread_id: str
    route: str
    effective_query: str
    status: str
    answer: str
    citations: tuple[dict[str, Any], ...] = ()
    web_content: str = ""


async def _readiness_checks(settings: AppSettings) -> dict[str, bool]:
    checks = {
        "database_configured": bool(settings.database_url),
        "groq_configured": settings.groq_api_key is not None,
        "redis_configured": bool(settings.redis_broker_url),
    }
    if settings.active_readiness_probes:
        checks["database_connected"] = await check_database_health(settings.database_url)
        checks["redis_connected"] = await check_redis_health(settings.redis_broker_url)
    return checks


def create_app(
    settings: AppSettings | None = None,
    rag_service: RagService | None = None,
    pool: AsyncConnectionPool | None = None,
    agent_graph: AdaptiveRagGraph | None = None,
) -> FastAPI:
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
        pool_to_close: AsyncConnectionPool | None = getattr(application.state, "pool", None)
        if pool_to_close is not None:
            await pool_to_close.close()
        logger.info("api_stopped", service=resolved_settings.service_name)

    application = FastAPI(
        title="RAG Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.rag_service = rag_service
    application.state.pool = pool
    if agent_graph is None and rag_service is not None:
        agent_graph = AdaptiveRagGraph(
            model=rag_service._model,
            retriever=rag_service._retriever,
            reranker=rag_service._reranker,
        )
    application.state.agent_graph = agent_graph

    @application.get("/", response_class=HTMLResponse)
    async def dashboard() -> HTMLResponse:
        template_path = Path(__file__).parent / "templates" / "index.html"
        if template_path.exists():
            return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>RAG-Agent Platform</h1><p>API is operational.</p>")

    @application.get("/health/live", response_model=LivenessResponse)
    async def live() -> LivenessResponse:
        return LivenessResponse(service=resolved_settings.service_name, version="0.1.0")

    @application.get("/health/ready", response_model=ReadinessResponse)
    async def ready(response: Response) -> ReadinessResponse:
        checks = await _readiness_checks(resolved_settings)
        is_ready = all(checks.values())
        if not is_ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="ok" if is_ready else "not_ready", checks=checks)

    @application.post("/v1/query", response_model=GroundedAnswer)
    async def query_endpoint(
        request: QueryRequest,
        response: Response,
    ) -> GroundedAnswer:
        service: RagService | None = getattr(application.state, "rag_service", None)
        if service is None:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return GroundedAnswer(
                status=AnswerStatus.ABSTAINED,
                text="RAG service is not initialized or configured.",
                confidence=0.0,
                diagnostic_codes=("service_unavailable",),
            )
        try:
            return await service.answer_query(request)
        except Exception as exc:
            logger.error("query_execution_failed", error=str(exc))
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return GroundedAnswer(
                status=AnswerStatus.ABSTAINED,
                text="An internal error occurred while processing the query.",
                confidence=0.0,
                diagnostic_codes=("internal_error",),
            )

    @application.post("/v1/chat/stream")
    async def chat_stream_endpoint(
        request: QueryRequest,
        response: Response,
    ) -> StreamingResponse:
        service: RagService | None = getattr(application.state, "rag_service", None)
        if service is None:

            async def unavailable_stream() -> AsyncIterator[str]:
                payload = json.dumps({"status": "abstained", "text": "RAG service is unavailable"})
                yield f"event: error\ndata: {payload}\n\n"

            return StreamingResponse(
                unavailable_stream(),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                media_type="text/event-stream",
            )

        async def sse_generator() -> AsyncIterator[str]:
            try:
                async for item in service.answer_query_stream(request):
                    event_name = item.get("event", "message")
                    data_str = json.dumps(item.get("data", {}))
                    yield f"event: {event_name}\ndata: {data_str}\n\n"
            except Exception as exc:
                logger.error("streaming_error", error=str(exc))
                error_payload = json.dumps({"error": "Internal streaming error"})
                yield f"event: error\ndata: {error_payload}\n\n"

        return StreamingResponse(sse_generator(), media_type="text/event-stream")

    @application.post("/v1/agent/query", response_model=AgentQueryResponse)
    async def agent_query_endpoint(
        request: AgentQueryRequest,
        response: Response,
    ) -> AgentQueryResponse:
        agent: AdaptiveRagGraph | None = getattr(application.state, "agent_graph", None)
        if agent is None:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return AgentQueryResponse(
                thread_id=request.thread_id or str(request.user_id),
                route="direct",
                effective_query=request.query,
                status="abstained",
                answer="Agent service is not initialized or configured.",
                citations=(),
            )
        try:
            state = await agent.ainvoke(
                query=request.query,
                workspace_id=request.workspace_id,
                user_id=request.user_id,
                knowledge_base_ids=request.knowledge_base_ids,
                chat_history=request.chat_history,
                thread_id=request.thread_id,
            )
            return AgentQueryResponse(
                thread_id=request.thread_id or f"thread-{request.user_id}",
                route=state.route,
                effective_query=state.effective_query,
                status=state.status,
                answer=state.answer,
                citations=state.citations,
                web_content=state.web_content,
            )
        except Exception as exc:
            logger.error("agent_query_failed", error=str(exc))
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            return AgentQueryResponse(
                thread_id=request.thread_id or str(request.user_id),
                route="direct",
                effective_query=request.query,
                status="error",
                answer="An internal error occurred while executing the adaptive agent.",
                citations=(),
            )

    @application.post("/v1/agent/stream")
    async def agent_stream_endpoint(
        request: AgentQueryRequest,
        response: Response,
    ) -> StreamingResponse:
        agent: AdaptiveRagGraph | None = getattr(application.state, "agent_graph", None)
        if agent is None:

            async def unavailable_stream() -> AsyncIterator[str]:
                payload = json.dumps(
                    {"status": "abstained", "text": "Agent service is unavailable"}
                )
                yield f"event: error\ndata: {payload}\n\n"

            return StreamingResponse(
                unavailable_stream(),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                media_type="text/event-stream",
            )

        async def sse_generator() -> AsyncIterator[str]:
            try:
                async for item in agent.astream(
                    query=request.query,
                    workspace_id=request.workspace_id,
                    user_id=request.user_id,
                    knowledge_base_ids=request.knowledge_base_ids,
                    chat_history=request.chat_history,
                    thread_id=request.thread_id,
                ):
                    event_name = item.get("event", "message")
                    data_str = json.dumps(item.get("data", {}))
                    yield f"event: {event_name}\ndata: {data_str}\n\n"
            except Exception as exc:
                logger.error("agent_streaming_error", error=str(exc))
                error_payload = json.dumps({"error": "Internal agent streaming error"})
                yield f"event: error\ndata: {error_payload}\n\n"

        return StreamingResponse(sse_generator(), media_type="text/event-stream")

    @application.post(
        "/v1/documents",
        response_model=IngestionResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def ingest_document(
        request: IngestionRequest,
        response: Response,
    ) -> IngestionResponse:
        pool: AsyncConnectionPool | None = getattr(application.state, "pool", None)
        if pool is None:
            if resolved_settings.database_url:
                pool = create_async_pool(resolved_settings.database_url)
                application.state.pool = pool
            else:
                response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Database pool is not configured",
                )
        try:
            result = await create_ingestion_job(
                pool,
                workspace_id=request.workspace_id,
                knowledge_base_id=request.knowledge_base_id,
                title=request.title,
                content=request.content,
                idempotency_key=request.idempotency_key,
            )
            return IngestionResponse(
                job_id=result.job_id,
                document_id=result.document_id,
                document_version_id=result.document_version_id,
                status=result.status,
            )
        except Exception as exc:
            logger.error("document_ingestion_endpoint_failed", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to ingest document",
            ) from exc

    @application.post(
        "/v1/documents/upload",
        response_model=IngestionResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def upload_document(
        file: Annotated[UploadFile, File()],
        workspace_id: Annotated[UUID, Form()],
        knowledge_base_id: Annotated[UUID, Form()],
        title: Annotated[str | None, Form()] = None,
        idempotency_key: Annotated[str | None, Form()] = None,
    ) -> IngestionResponse:
        pool: AsyncConnectionPool | None = getattr(application.state, "pool", None)
        if pool is None:
            if resolved_settings.database_url:
                pool = create_async_pool(resolved_settings.database_url)
                application.state.pool = pool
            else:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Database pool is not configured",
                )
        try:
            raw_bytes = await file.read()
            parsed = DocumentParser.parse(
                raw_bytes,
                file_type=file.content_type or "text/plain",
                metadata={"filename": file.filename or "uploaded_file"},
            )
            doc_title = title or file.filename or "Uploaded Document"
            result = await create_ingestion_job(
                pool,
                workspace_id=workspace_id,
                knowledge_base_id=knowledge_base_id,
                title=doc_title,
                content=parsed.text,
                idempotency_key=idempotency_key,
            )
            return IngestionResponse(
                job_id=result.job_id,
                document_id=result.document_id,
                document_version_id=result.document_version_id,
                status=result.status,
            )
        except DocumentParsingError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            logger.error("document_upload_failed", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload and ingest document",
            ) from exc

    return application


app = create_app()

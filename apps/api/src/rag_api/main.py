import functools
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

import anyio
import structlog
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field
from rag_core.agent.graph import AdaptiveRagGraph
from rag_core.auth.models import UserIdentity
from rag_core.auth.tokens import SupabaseTokenVerifier, check_workspace_access
from rag_core.config import AppSettings, get_settings
from rag_core.database.connection import check_database_health, create_async_pool
from rag_core.database.redis import check_redis_health
from rag_core.errors import AuthenticationError, AuthorizationError, DocumentParsingError
from rag_core.ingestion.parsers import DocumentParser
from rag_core.ingestion.repository import create_ingestion_job
from rag_core.jobs.models import JobStatus
from rag_core.models.contracts import ChatMessage
from rag_core.models.groq import GroqChatModelProvider
from rag_core.observability.logging import configure_logging
from rag_core.retrieval.embeddings import FastEmbedProvider
from rag_core.retrieval.hybrid import HybridRetriever
from rag_core.retrieval.models import AnswerStatus, GroundedAnswer
from rag_core.retrieval.reranker import FlashRankReranker
from rag_core.retrieval.service import QueryRequest, RagService

logger = structlog.get_logger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB


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
    content: str = Field(min_length=1, max_length=5_000_000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)


class IngestionResponse(BaseModel):
    job_id: UUID
    document_id: UUID
    document_version_id: UUID
    status: JobStatus = JobStatus.QUEUED


class AgentQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    workspace_id: UUID
    user_id: UUID | None = None
    knowledge_base_ids: tuple[UUID, ...] = Field(min_length=1)
    chat_history: tuple[ChatMessage, ...] = Field(default=(), max_length=100)
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


async def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> UserIdentity:
    """Extract and verify user identity via Supabase JWT or provide dev bypass."""
    settings: AppSettings = request.app.state.settings
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
        jwt_secret = (
            settings.supabase_jwt_secret.get_secret_value()
            if settings.supabase_jwt_secret
            else "super-secret-jwt-token-with-at-least-32-characters-long"
        )
        verifier = SupabaseTokenVerifier(secret_or_public_key=jwt_secret)
        return verifier.verify(token)

    if settings.is_auth_enforced:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Dev/test bypass identity with administrative access
    return UserIdentity(
        user_id=UUID("00000000-0000-0000-0000-000000000003"),
        email="dev@local",
        roles=("service_role",),
        workspace_ids=(),
    )


async def _get_pool(app: FastAPI, settings: AppSettings) -> AsyncConnectionPool:
    """Retrieve existing connection pool or initialize and open a new one."""
    pool: AsyncConnectionPool | None = getattr(app.state, "pool", None)
    if pool is not None:
        return pool
    if not settings.database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database pool is not configured",
        )
    pool = create_async_pool(settings.database_url)
    await pool.open()
    app.state.pool = pool
    return pool


async def _sse_stream(
    generator: AsyncIterator[dict[str, Any]],
    logger_context: str,
) -> AsyncIterator[str]:
    """Uniform SSE streaming generator with structured error handling."""
    try:
        async for item in generator:
            event_name = item.get("event", "message")
            data_str = json.dumps(item.get("data", {}))
            yield f"event: {event_name}\ndata: {data_str}\n\n"
    except Exception as exc:
        logger.error(logger_context, error=str(exc))
        error_payload = json.dumps({"error": f"Internal streaming error: {logger_context}"})
        yield f"event: error\ndata: {error_payload}\n\n"


def _unavailable_stream(message: str) -> AsyncIterator[str]:
    """Helper for streaming early unavailability errors."""
    async def _generator() -> AsyncIterator[str]:
        payload = json.dumps({"status": "abstained", "text": message})
        yield f"event: error\ndata: {payload}\n\n"

    return _generator()


def create_app(
    settings: AppSettings | None = None,
    rag_service: RagService | None = None,
    pool: AsyncConnectionPool | None = None,
    agent_graph: AdaptiveRagGraph | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level, resolved_settings.json_logs)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "api_started",
            environment=resolved_settings.environment,
            service=resolved_settings.service_name,
        )

        owns_pool = False
        pool_inst: AsyncConnectionPool | None = getattr(application.state, "pool", None)
        if pool_inst is None and resolved_settings.database_url:
            pool_inst = create_async_pool(resolved_settings.database_url)
            await pool_inst.open()
            application.state.pool = pool_inst
            owns_pool = True
        elif pool_inst is not None and hasattr(pool_inst, "open"):
            if getattr(pool_inst, "_opened", False) is False:
                with suppress(Exception):
                    await pool_inst.open()

        # Wire RAG pipeline and agent if not pre-injected
        current_rag: RagService | None = getattr(application.state, "rag_service", None)
        if current_rag is None and pool_inst is not None:
            try:
                embedder = FastEmbedProvider(model_name=resolved_settings.embedding_model)
                retriever = HybridRetriever(pool_inst, embedder)
                reranker = FlashRankReranker()
                if resolved_settings.groq_api_key:
                    chat_model = GroqChatModelProvider(
                        api_key=resolved_settings.groq_api_key,
                        profiles=resolved_settings.model_profiles(),
                    )
                    current_rag = RagService(
                        retriever=retriever,
                        model_provider=chat_model,
                        reranker=reranker,
                    )
                    application.state.rag_service = current_rag
                else:
                    logger.warning("groq_api_key_not_configured_rag_service_unwired")
            except Exception as exc:
                logger.error("failed_to_initialize_rag_pipeline", error=str(exc))

        current_graph: AdaptiveRagGraph | None = getattr(application.state, "agent_graph", None)
        if current_graph is None and current_rag is not None:
            application.state.agent_graph = AdaptiveRagGraph(
                model=current_rag._model,
                retriever=current_rag._retriever,
                reranker=current_rag._reranker,
            )

        yield

        pool_to_close: AsyncConnectionPool | None = getattr(application.state, "pool", None)
        if pool_to_close is not None and owns_pool:
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
    if (
        agent_graph is None
        and rag_service is not None
        and hasattr(rag_service, "_model")
        and hasattr(rag_service, "_retriever")
    ):
        agent_graph = AdaptiveRagGraph(
            model=rag_service._model,
            retriever=rag_service._retriever,
            reranker=getattr(rag_service, "_reranker", None),
        )
    application.state.agent_graph = agent_graph

    @application.exception_handler(AuthenticationError)
    async def auth_error_handler(_: Request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": str(exc)},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @application.exception_handler(AuthorizationError)
    async def forbidden_error_handler(_: Request, exc: AuthorizationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": str(exc)},
        )

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
        current_user: Annotated[UserIdentity, Depends(get_current_user)],
    ) -> GroundedAnswer:
        check_workspace_access(current_user, request.workspace_id)
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
        current_user: Annotated[UserIdentity, Depends(get_current_user)],
    ) -> StreamingResponse:
        check_workspace_access(current_user, request.workspace_id)
        service: RagService | None = getattr(application.state, "rag_service", None)
        if service is None:
            return StreamingResponse(
                _unavailable_stream("RAG service is unavailable"),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                media_type="text/event-stream",
            )

        return StreamingResponse(
            _sse_stream(service.answer_query_stream(request), "streaming_error"),
            media_type="text/event-stream",
        )

    @application.post("/v1/agent/query", response_model=AgentQueryResponse)
    async def agent_query_endpoint(
        request: AgentQueryRequest,
        response: Response,
        current_user: Annotated[UserIdentity, Depends(get_current_user)],
    ) -> AgentQueryResponse:
        check_workspace_access(current_user, request.workspace_id)
        effective_user_id = (
            request.user_id
            if request.user_id is not None and "service_role" in current_user.roles
            else current_user.user_id
        )
        thread_id = request.thread_id or f"{request.workspace_id}:{effective_user_id}:{uuid4()}"

        agent: AdaptiveRagGraph | None = getattr(application.state, "agent_graph", None)
        if agent is None:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return AgentQueryResponse(
                thread_id=thread_id,
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
                user_id=effective_user_id,
                knowledge_base_ids=request.knowledge_base_ids,
                chat_history=request.chat_history,
                thread_id=thread_id,
            )
            return AgentQueryResponse(
                thread_id=thread_id,
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
                thread_id=thread_id,
                route="direct",
                effective_query=request.query,
                status="error",
                answer="An internal error occurred while executing the adaptive agent.",
                citations=(),
            )

    @application.post("/v1/agent/stream")
    async def agent_stream_endpoint(
        request: AgentQueryRequest,
        current_user: Annotated[UserIdentity, Depends(get_current_user)],
    ) -> StreamingResponse:
        check_workspace_access(current_user, request.workspace_id)
        effective_user_id = (
            request.user_id
            if request.user_id is not None and "service_role" in current_user.roles
            else current_user.user_id
        )
        thread_id = request.thread_id or f"{request.workspace_id}:{effective_user_id}:{uuid4()}"

        agent: AdaptiveRagGraph | None = getattr(application.state, "agent_graph", None)
        if agent is None:
            return StreamingResponse(
                _unavailable_stream("Agent service is unavailable"),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                media_type="text/event-stream",
            )

        stream_gen = agent.astream(
            query=request.query,
            workspace_id=request.workspace_id,
            user_id=effective_user_id,
            knowledge_base_ids=request.knowledge_base_ids,
            chat_history=request.chat_history,
            thread_id=thread_id,
        )
        return StreamingResponse(
            _sse_stream(stream_gen, "agent_streaming_error"),
            media_type="text/event-stream",
        )

    @application.post(
        "/v1/documents",
        response_model=IngestionResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def ingest_document(
        request: IngestionRequest,
        current_user: Annotated[UserIdentity, Depends(get_current_user)],
    ) -> IngestionResponse:
        check_workspace_access(current_user, request.workspace_id)
        pool = await _get_pool(application, resolved_settings)
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
        current_user: Annotated[UserIdentity, Depends(get_current_user)],
        title: Annotated[str | None, Form()] = None,
        idempotency_key: Annotated[str | None, Form()] = None,
    ) -> IngestionResponse:
        check_workspace_access(current_user, workspace_id)
        pool = await _get_pool(application, resolved_settings)
        try:
            raw_bytes = await file.read()
            if len(raw_bytes) > MAX_UPLOAD_BYTES:
                limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"File exceeds maximum allowed size ({limit_mb}MB)",
                )

            file_type = file.content_type or "text/plain"
            parse_fn = functools.partial(
                DocumentParser.parse,
                raw_bytes,
                file_type,
                metadata={"filename": file.filename or "uploaded_file"},
            )
            parsed = await anyio.to_thread.run_sync(parse_fn)
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
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("document_upload_failed", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload and ingest document",
            ) from exc

    return application


app = create_app()

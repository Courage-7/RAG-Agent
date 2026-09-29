"""Dramatiq background actor for document ingestion, chunking, and vector embedding."""

from typing import Any
from uuid import UUID

import anyio
import dramatiq
import structlog
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field
from rag_core.config import get_settings
from rag_core.database.connection import create_async_pool
from rag_core.ingestion.chunking import RecursiveCharacterChunker
from rag_core.ingestion.repository import store_document_chunks
from rag_core.retrieval.embeddings import FastEmbedProvider

logger = structlog.get_logger(__name__)


class IngestionPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: UUID
    workspace_id: UUID
    knowledge_base_id: UUID
    document_id: UUID
    document_version_id: UUID
    content: str = Field(min_length=1)


async def process_document_ingestion(payload_data: dict[str, Any]) -> int:
    """Async business logic for parsing, embedding, and persisting document chunks."""
    settings = get_settings()

    # Support both direct payload and database-authoritative envelope
    if "content" not in payload_data or payload_data.get("content") is None:
        raw_job_id = payload_data.get("job_id")
        if not raw_job_id:
            raise ValueError("Payload missing both content and job_id")
        job_id = UUID(str(raw_job_id))
        pool = create_async_pool(settings.database_url)
        async with (
            pool,
            pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            query = """
                select
                    j.id as job_id,
                    j.workspace_id,
                    d.knowledge_base_id,
                    d.id as document_id,
                    v.id as document_version_id,
                    v.raw_content as content
                from public.ingestion_jobs j
                join public.document_versions v on v.id = j.document_version_id
                join public.documents d on d.id = v.document_id
                where j.id = %(job_id)s;
            """
            await cursor.execute(query, {"job_id": job_id})
            row = await cursor.fetchone()
            if not row or not row.get("content"):
                logger.warning(
                    "ingestion_job_content_empty_or_not_found",
                    job_id=str(job_id),
                )
                return 0
            payload = IngestionPayload.model_validate(row)
    else:
        payload = IngestionPayload.model_validate(payload_data)

    logger.info("ingestion_task_started", job_id=str(payload.job_id))

    pool = create_async_pool(settings.database_url)
    async with pool:
        # 1. Mark job as running
        try:
            async with pool.connection() as conn, conn.cursor() as cursor:
                await cursor.execute(
                    """
                    update public.ingestion_jobs
                    set status = 'running',
                        current_stage = 'chunking',
                        started_at = coalesce(started_at, now()),
                        updated_at = now()
                    where id = %(job_id)s
                      and status in ('queued', 'retry_scheduled');
                    """,
                    {"job_id": payload.job_id},
                )
        except Exception as exc:
            logger.warning("could_not_mark_job_running", error=str(exc))

        try:
            # 2. Chunk document content
            chunker = RecursiveCharacterChunker(chunk_size=500, chunk_overlap=50)
            chunks = chunker.split(payload.content)
            if not chunks:
                logger.warning("ingestion_empty_content", job_id=str(payload.job_id))
                return 0

            # 3. Generate embeddings
            embedder = FastEmbedProvider()
            texts = [c.content for c in chunks]
            embeddings = await embedder.embed_documents(texts)

            # 4. Store chunks and activate document version
            count = await store_document_chunks(
                pool,
                workspace_id=payload.workspace_id,
                knowledge_base_id=payload.knowledge_base_id,
                document_id=payload.document_id,
                document_version_id=payload.document_version_id,
                chunks=chunks,
                embeddings=embeddings,
                job_id=payload.job_id,
            )

            logger.info("ingestion_task_completed", job_id=str(payload.job_id), chunk_count=count)
            return count
        except Exception as exc:
            logger.error("ingestion_task_failed", job_id=str(payload.job_id), error=str(exc))
            try:
                async with pool.connection() as conn, conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        update public.ingestion_jobs
                        set status = 'failed',
                            failure_code = 'processing_error',
                            failure_message = %(failure_msg)s,
                            failed_at = now(),
                            updated_at = now()
                        where id = %(job_id)s;
                        """,
                        {"job_id": payload.job_id, "failure_msg": str(exc)[:250]},
                    )
            except Exception as update_exc:
                logger.error("failed_to_update_job_failure_state", error=str(update_exc))
            raise


@dramatiq.actor(
    actor_name="document_ingestion",
    queue_name="ingestion",
    max_retries=3,
    min_backoff=15_000,
    max_backoff=300_000,
    time_limit=600_000,
)
def document_ingestion(payload: dict[str, Any]) -> None:
    """Worker task executing document chunking, embedding, and storage."""
    anyio.run(process_document_ingestion, payload)

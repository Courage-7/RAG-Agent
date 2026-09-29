import hashlib
from uuid import UUID, uuid4

import structlog
from pgvector import Vector
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, ConfigDict

from rag_core.errors import IngestionStorageError
from rag_core.ingestion.chunking import TextChunk
from rag_core.jobs.models import JobStatus

logger = structlog.get_logger(__name__)


class DocumentIngestionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: UUID
    document_id: UUID
    document_version_id: UUID
    status: JobStatus = JobStatus.QUEUED


async def store_document_chunks(
    pool: AsyncConnectionPool,
    *,
    workspace_id: UUID,
    knowledge_base_id: UUID,
    document_id: UUID,
    document_version_id: UUID,
    chunks: list[TextChunk],
    embeddings: list[list[float]],
    job_id: UUID | None = None,
) -> int:
    """Store document chunks with pgvector embeddings and activate the version atomically."""
    if len(chunks) != len(embeddings):
        raise ValueError("Number of chunks must match number of embedding vectors")

    insert_chunk_sql = """
        insert into public.document_chunks (
            document_version_id,
            document_id,
            workspace_id,
            knowledge_base_id,
            chunk_index,
            content,
            embedding
        ) values (
            %(document_version_id)s,
            %(document_id)s,
            %(workspace_id)s,
            %(knowledge_base_id)s,
            %(chunk_index)s,
            %(content)s,
            %(embedding)s
        );
    """

    update_version_sql = """
        update public.document_versions
        set status = 'active',
            chunk_count = %(chunk_count)s,
            activated_at = now()
        where id = %(document_version_id)s;
    """

    update_job_sql = """
        update public.ingestion_jobs
        set status = 'completed',
            current_stage = 'completed',
            completed_at = now(),
            updated_at = now()
        where id = %(job_id)s;
    """

    try:
        async with (
            pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                params = {
                    "document_version_id": document_version_id,
                    "document_id": document_id,
                    "workspace_id": workspace_id,
                    "knowledge_base_id": knowledge_base_id,
                    "chunk_index": chunk.index,
                    "content": chunk.content,
                    "embedding": Vector(embedding),
                }
                await cursor.execute(insert_chunk_sql, params)

            # Atomically activate document version
            await cursor.execute(
                update_version_sql,
                {
                    "document_version_id": document_version_id,
                    "chunk_count": len(chunks),
                },
            )

            # Mark job as completed
            if job_id is not None:
                await cursor.execute(update_job_sql, {"job_id": job_id})

        return len(chunks)
    except Exception as exc:
        logger.error("store_document_chunks_failed", error=str(exc))
        raise IngestionStorageError(
            "Failed to persist document chunks and activate version"
        ) from exc


async def create_ingestion_job(
    pool: AsyncConnectionPool,
    *,
    workspace_id: UUID,
    knowledge_base_id: UUID,
    title: str,
    content: str,
    idempotency_key: str | None = None,
) -> DocumentIngestionResult:
    """Transactionally ingest document metadata, raw staged version, job, and outbox event."""
    encoded = content.encode("utf-8")
    sha256_hash = hashlib.sha256(encoded).hexdigest()
    byte_size = len(encoded)

    doc_id = uuid4()
    version_id = uuid4()
    job_id = uuid4()
    key = idempotency_key or f"ingest-{version_id}"

    insert_doc_sql = """
        insert into public.documents (
            id, workspace_id, knowledge_base_id, title, byte_size, sha256
        ) values (
            %(id)s, %(workspace_id)s, %(knowledge_base_id)s, %(title)s, %(byte_size)s, %(sha256)s
        );
    """

    insert_version_sql = """
        insert into public.document_versions (
            id, document_id, workspace_id, version_number, status, raw_content
        ) values (
            %(id)s, %(document_id)s, %(workspace_id)s, 1, 'staged', %(raw_content)s
        );
    """

    insert_job_sql = """
        insert into public.ingestion_jobs (
            id, workspace_id, document_version_id, operation, status, current_stage,
            idempotency_key, pipeline_version
        ) values (
            %(id)s, %(workspace_id)s, %(document_version_id)s,
            'document_ingestion', 'queued', 'queued',
            %(idempotency_key)s, 'pipeline-v1'
        );
    """

    insert_outbox_sql = """
        insert into private.job_dispatch_outbox (
            job_id, operation, payload
        ) values (
            %(job_id)s, 'document_ingestion', %(payload)s
        );
    """

    try:
        async with (
            pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(
                insert_doc_sql,
                {
                    "id": doc_id,
                    "workspace_id": workspace_id,
                    "knowledge_base_id": knowledge_base_id,
                    "title": title,
                    "byte_size": byte_size,
                    "sha256": sha256_hash,
                },
            )
            await cursor.execute(
                insert_version_sql,
                {
                    "id": version_id,
                    "document_id": doc_id,
                    "workspace_id": workspace_id,
                    "raw_content": content,
                },
            )
            await cursor.execute(
                insert_job_sql,
                {
                    "id": job_id,
                    "workspace_id": workspace_id,
                    "document_version_id": version_id,
                    "idempotency_key": key,
                },
            )
            await cursor.execute(
                insert_outbox_sql,
                {
                    "job_id": job_id,
                    "payload": Json({"job_id": str(job_id), "idempotency_key": key}),
                },
            )

        logger.info(
            "document_ingestion_job_created",
            job_id=str(job_id),
            document_id=str(doc_id),
            document_version_id=str(version_id),
        )
        return DocumentIngestionResult(
            job_id=job_id,
            document_id=doc_id,
            document_version_id=version_id,
            status=JobStatus.QUEUED,
        )
    except Exception as exc:
        logger.error("create_ingestion_job_failed", error=str(exc))
        raise IngestionStorageError("Failed to create document ingestion job") from exc

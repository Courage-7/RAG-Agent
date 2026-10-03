"""Real end-to-end integration tests using local PostgreSQL (pgvector) and Redis."""

from uuid import UUID, uuid4

import pytest
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from rag_core.config import AppSettings
from rag_core.database.redis import check_redis_health
from rag_core.ingestion.chunking import RecursiveCharacterChunker
from rag_core.ingestion.repository import create_ingestion_job, store_document_chunks
from rag_core.jobs.models import JobStatus
from rag_core.retrieval.embeddings import FastEmbedProvider
from rag_core.retrieval.hybrid import HybridRetriever
from rag_core.retrieval.models import RetrievalQuery, RetrievalStrategy


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_database_and_pgvector(real_db_pool: AsyncConnectionPool) -> None:
    """Verify that PostgreSQL is live and pgvector extension is operational."""
    async with real_db_pool.connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute("select '[1.0, 2.0, 3.0]'::vector as test_vec;")
        row = await cursor.fetchone()
        assert row is not None
        assert row["test_vec"] is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_redis_connectivity(settings: AppSettings) -> None:
    """Verify that the local Redis broker is running and healthy."""
    is_healthy = await check_redis_health(settings.redis_broker_url)
    assert is_healthy is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_ingestion_and_hybrid_retrieval(
    real_db_pool: AsyncConnectionPool,
    test_workspace: tuple[UUID, UUID],
) -> None:
    """Verify end-to-end: job creation, chunking, FastEmbed, and hybrid RPC retrieval."""
    workspace_id, kb_id = test_workspace
    title = "Architectural Decision Record 001"
    content = (
        "PostgreSQL 16 with pgvector serves as the authoritative source of truth. "
        "Reciprocal Rank Fusion merges dense vector search with full-text lexical ranking. "
        "The transactional outbox guarantees exactly-once dispatch to Dramatiq workers."
    )

    # 1. Transactionally stage ingestion job and outbox event
    job_result = await create_ingestion_job(
        real_db_pool,
        workspace_id=workspace_id,
        knowledge_base_id=kb_id,
        title=title,
        content=content,
        idempotency_key=f"int-test-{uuid4().hex[:12]}",
    )

    assert job_result.job_id is not None
    assert job_result.status == JobStatus.QUEUED

    # Verify rows in real DB
    async with real_db_pool.connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(
            "select status, operation from public.ingestion_jobs where id = %(id)s;",
            {"id": job_result.job_id},
        )
        job_row = await cursor.fetchone()
        assert job_row is not None
        assert job_row["status"] == "queued"
        assert job_row["operation"] == "document_ingestion"

        # Verify outbox entry
        await cursor.execute(
            "select job_id, operation from private.job_dispatch_outbox where job_id = %(id)s;",
            {"id": job_result.job_id},
        )
        outbox_row = await cursor.fetchone()
        assert outbox_row is not None
        assert outbox_row["operation"] == "document_ingestion"

    # 2. Real chunking and real CPU FastEmbed embedding
    chunker = RecursiveCharacterChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.split(content)
    assert len(chunks) >= 1

    embedder = FastEmbedProvider()
    embeddings = await embedder.embed_documents([c.content for c in chunks])
    assert len(embeddings) == len(chunks)
    assert len(embeddings[0]) == 384

    # 3. Store chunks and activate version atomically in real DB
    stored_count = await store_document_chunks(
        real_db_pool,
        workspace_id=workspace_id,
        knowledge_base_id=kb_id,
        document_id=job_result.document_id,
        document_version_id=job_result.document_version_id,
        chunks=chunks,
        embeddings=embeddings,
        job_id=job_result.job_id,
    )
    assert stored_count == len(chunks)

    # Verify document version status is now 'active'
    async with real_db_pool.connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(
            "select status, chunk_count from public.document_versions where id = %(id)s;",
            {"id": job_result.document_version_id},
        )
        ver_row = await cursor.fetchone()
        assert ver_row is not None
        assert ver_row["status"] == "active"
        assert ver_row["chunk_count"] == len(chunks)

    # 4. Execute real hybrid search with RRF against the database
    retriever = HybridRetriever(real_db_pool, embedder)
    query = RetrievalQuery(
        text="What is used for authoritative storage and Reciprocal Rank Fusion?",
        workspace_id=workspace_id,
        user_id=uuid4(),
        knowledge_base_ids=(kb_id,),
        top_k=5,
    )

    retrieval_res = await retriever.retrieve(query)
    assert retrieval_res.strategy == RetrievalStrategy.HYBRID
    assert len(retrieval_res.chunks) > 0
    top_chunk = retrieval_res.chunks[0]
    assert "pgvector" in top_chunk.content or "Reciprocal Rank Fusion" in top_chunk.content
    assert top_chunk.dense_score is not None
    assert top_chunk.fused_score is not None
    assert top_chunk.fused_score > 0

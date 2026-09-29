from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from rag_core.ingestion.chunking import RecursiveCharacterChunker, TextChunk
from rag_core.ingestion.repository import create_ingestion_job, store_document_chunks
from rag_core.jobs.models import JobStatus
from rag_worker.tasks.ingestion import process_document_ingestion


def _create_mock_pool(mock_cursor: MagicMock) -> MagicMock:
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_pool.__aenter__ = AsyncMock(return_value=mock_pool)
    mock_pool.__aexit__ = AsyncMock(return_value=None)
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_conn.transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_conn.cursor = MagicMock()
    mock_conn.cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_pool


def test_chunker_splits_and_preserves_indices() -> None:
    chunker = RecursiveCharacterChunker(chunk_size=100, chunk_overlap=20)
    sample_text = (
        "PostgreSQL pgvector extension provides fast vector similarity search.\n\n"
        "It supports HNSW and IVFFlat index types for high scale workloads.\n\n"
        "Reciprocal Rank Fusion fuses lexical and dense rankings."
    )

    chunks = chunker.split(sample_text)

    assert len(chunks) >= 2
    for i, chunk in enumerate(chunks):
        assert chunk.index == i
        assert len(chunk.content) > 0
        assert len(chunk.content) <= 120  # allowed leeway on word break boundary


def test_chunker_handles_empty_and_short_text() -> None:
    chunker = RecursiveCharacterChunker(chunk_size=200, chunk_overlap=20)
    assert chunker.split("") == []
    assert chunker.split("   ") == []

    single = chunker.split("Short text")
    assert len(single) == 1
    assert single[0].content == "Short text"
    assert single[0].index == 0


@pytest.mark.asyncio
async def test_store_document_chunks_executes_transactional_insert() -> None:
    doc_id = uuid4()
    ver_id = uuid4()
    ws_id = uuid4()
    kb_id = uuid4()
    job_id = uuid4()

    chunks = [
        TextChunk(index=0, content="Chunk 0"),
        TextChunk(index=1, content="Chunk 1"),
    ]
    embeddings = [[0.1] * 384, [0.2] * 384]

    mock_cursor = MagicMock()
    mock_cursor.execute = AsyncMock()
    mock_pool = _create_mock_pool(mock_cursor)

    count = await store_document_chunks(
        mock_pool,
        workspace_id=ws_id,
        knowledge_base_id=kb_id,
        document_id=doc_id,
        document_version_id=ver_id,
        chunks=chunks,
        embeddings=embeddings,
        job_id=job_id,
    )

    assert count == 2
    # 2 chunk inserts + 1 version update + 1 job update = 4 executes
    assert mock_cursor.execute.call_count == 4


@pytest.mark.asyncio
async def test_create_ingestion_job_executes_atomic_intake() -> None:
    ws_id = uuid4()
    kb_id = uuid4()

    mock_cursor = MagicMock()
    mock_cursor.execute = AsyncMock()
    mock_pool = _create_mock_pool(mock_cursor)

    result = await create_ingestion_job(
        mock_pool,
        workspace_id=ws_id,
        knowledge_base_id=kb_id,
        title="Architecture Guide",
        content="This document outlines our retrieval system.",
        idempotency_key="ingest-key-12345",
    )

    assert result.status == JobStatus.QUEUED
    assert result.job_id is not None
    assert result.document_id is not None
    assert result.document_version_id is not None
    # 1 document insert + 1 version insert + 1 job insert + 1 outbox insert = 4 executes
    assert mock_cursor.execute.call_count == 4


@pytest.mark.asyncio
async def test_process_document_ingestion_executes_pipeline() -> None:
    payload = {
        "job_id": str(uuid4()),
        "workspace_id": str(uuid4()),
        "knowledge_base_id": str(uuid4()),
        "document_id": str(uuid4()),
        "document_version_id": str(uuid4()),
        "content": "This is a document about distributed RAG platforms.",
    }

    mock_stored_count = 1
    mock_cursor = MagicMock()
    mock_cursor.execute = AsyncMock()
    mock_pool = _create_mock_pool(mock_cursor)

    with (
        patch("rag_worker.tasks.ingestion.FastEmbedProvider") as mock_embedder_cls,
        patch("rag_worker.tasks.ingestion.create_async_pool", return_value=mock_pool),
        patch(
            "rag_worker.tasks.ingestion.store_document_chunks",
            new_callable=AsyncMock,
        ) as mock_store,
    ):
        mock_embedder = MagicMock()
        mock_embedder.embed_documents = AsyncMock(return_value=[[0.05] * 384])
        mock_embedder_cls.return_value = mock_embedder

        mock_store.return_value = mock_stored_count

        count = await process_document_ingestion(payload)

        assert count == mock_stored_count
        mock_store.assert_called_once()
        # Verify status was updated to running
        assert mock_cursor.execute.call_count >= 1


@pytest.mark.asyncio
async def test_process_document_ingestion_resolves_envelope_from_database() -> None:
    job_id = uuid4()
    ws_id = uuid4()
    kb_id = uuid4()
    doc_id = uuid4()
    ver_id = uuid4()

    mock_cursor = MagicMock()
    mock_cursor.execute = AsyncMock()
    mock_cursor.fetchone = AsyncMock(
        return_value={
            "job_id": job_id,
            "workspace_id": ws_id,
            "knowledge_base_id": kb_id,
            "document_id": doc_id,
            "document_version_id": ver_id,
            "content": "Database stored document text for RAG retrieval.",
        }
    )
    mock_pool = _create_mock_pool(mock_cursor)

    with (
        patch("rag_worker.tasks.ingestion.FastEmbedProvider") as mock_embedder_cls,
        patch("rag_worker.tasks.ingestion.create_async_pool", return_value=mock_pool),
        patch(
            "rag_worker.tasks.ingestion.store_document_chunks",
            new_callable=AsyncMock,
        ) as mock_store,
    ):
        mock_embedder = MagicMock()
        mock_embedder.embed_documents = AsyncMock(return_value=[[0.02] * 384])
        mock_embedder_cls.return_value = mock_embedder
        mock_store.return_value = 1

        # Pass only job_id as sent by Dramatiq outbox envelope
        count = await process_document_ingestion({"job_id": str(job_id)})

        assert count == 1
        mock_store.assert_called_once()

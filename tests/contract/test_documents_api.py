from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from rag_api.main import create_app
from rag_core.config import AppSettings
from rag_core.ingestion.repository import DocumentIngestionResult
from rag_core.jobs.models import JobStatus


@pytest.mark.asyncio
async def test_ingest_document_returns_202_with_job_and_ids() -> None:
    job_id = uuid4()
    doc_id = uuid4()
    ver_id = uuid4()

    mock_pool = AsyncMock()
    app = create_app(
        AppSettings(_env_file=None, database_url="postgresql://user:pass@localhost:5432/db"),  # type: ignore[call-arg]
        pool=mock_pool,
    )

    expected_result = DocumentIngestionResult(
        job_id=job_id,
        document_id=doc_id,
        document_version_id=ver_id,
        status=JobStatus.QUEUED,
    )

    with patch(
        "rag_api.main.create_ingestion_job",
        new_callable=AsyncMock,
        return_value=expected_result,
    ) as mock_create:
        payload = {
            "workspace_id": str(uuid4()),
            "knowledge_base_id": str(uuid4()),
            "title": "Production RAG Architecture",
            "content": "Comprehensive details on vector retrieval and outbox pattern.",
            "idempotency_key": "ingest-key-unique-1234",
        }

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post("/v1/documents", json=payload)

        assert res.status_code == 202
        body = res.json()
        assert body["job_id"] == str(job_id)
        assert body["document_id"] == str(doc_id)
        assert body["document_version_id"] == str(ver_id)
        assert body["status"] == "queued"
        mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_ingest_document_returns_503_when_no_db_pool() -> None:
    app = create_app(AppSettings(_env_file=None, database_url=""), pool=None)  # type: ignore[call-arg]

    payload = {
        "workspace_id": str(uuid4()),
        "knowledge_base_id": str(uuid4()),
        "title": "Doc Title",
        "content": "Content text",
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/documents", json=payload)

    assert res.status_code == 503
    assert "Database pool is not configured" in res.json()["detail"]


@pytest.mark.asyncio
async def test_ingest_document_validates_schema() -> None:
    mock_pool = AsyncMock()
    app = create_app(
        AppSettings(_env_file=None, database_url="postgresql://user:pass@localhost:5432/db"),  # type: ignore[call-arg]
        pool=mock_pool,
    )

    # Empty content and invalid idempotency_key length
    payload = {
        "workspace_id": str(uuid4()),
        "knowledge_base_id": str(uuid4()),
        "title": "",
        "content": "",
        "idempotency_key": "short",
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/documents", json=payload)

    assert res.status_code == 422


@pytest.mark.asyncio
async def test_upload_document_returns_202_with_parsed_text() -> None:
    job_id = uuid4()
    doc_id = uuid4()
    ver_id = uuid4()

    mock_pool = AsyncMock()
    app = create_app(
        AppSettings(_env_file=None, database_url="postgresql://user:pass@localhost:5432/db"),  # type: ignore[call-arg]
        pool=mock_pool,
    )

    expected_result = DocumentIngestionResult(
        job_id=job_id,
        document_id=doc_id,
        document_version_id=ver_id,
        status=JobStatus.QUEUED,
    )

    with patch(
        "rag_api.main.create_ingestion_job",
        new_callable=AsyncMock,
        return_value=expected_result,
    ) as mock_create:
        data = {
            "workspace_id": str(uuid4()),
            "knowledge_base_id": str(uuid4()),
            "title": "Uploaded Spec",
        }
        files = {
            "file": ("spec.txt", b"System architecture specification content.", "text/plain"),
        }

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post("/v1/documents/upload", data=data, files=files)

        assert res.status_code == 202
        body = res.json()
        assert body["job_id"] == str(job_id)
        assert body["document_id"] == str(doc_id)
        assert body["status"] == "queued"
        mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_document_rejects_empty_file() -> None:
    mock_pool = AsyncMock()
    app = create_app(
        AppSettings(_env_file=None, database_url="postgresql://user:pass@localhost:5432/db"),  # type: ignore[call-arg]
        pool=mock_pool,
    )

    data = {
        "workspace_id": str(uuid4()),
        "knowledge_base_id": str(uuid4()),
    }
    files = {
        "file": ("empty.txt", b"", "text/plain"),
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/documents/upload", data=data, files=files)

    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()

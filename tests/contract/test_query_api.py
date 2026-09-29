from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from rag_api.main import create_app
from rag_core.config import AppSettings
from rag_core.retrieval.models import AnswerStatus, Citation, GroundedAnswer


async def post_json(app: object, path: str, json_data: Mapping[str, Any]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=json_data)


@pytest.mark.asyncio
async def test_query_endpoint_returns_grounded_answer() -> None:
    chunk_id = uuid4()
    doc_id = uuid4()

    mock_rag_service = AsyncMock()
    mock_rag_service.answer_query.return_value = GroundedAnswer(
        status=AnswerStatus.ANSWERED,
        text="Vector search in PostgreSQL uses pgvector and HNSW [1].",
        citations=(
            Citation(
                ordinal=1,
                chunk_id=chunk_id,
                document_id=doc_id,
                source_label="Source Chunk 1",
            ),
        ),
        confidence=0.92,
    )

    app = create_app(AppSettings(_env_file=None), rag_service=mock_rag_service)  # type: ignore[call-arg]

    payload = {
        "query": "How does vector search work in PostgreSQL?",
        "workspace_id": str(uuid4()),
        "user_id": str(uuid4()),
        "knowledge_base_ids": [str(uuid4())],
        "top_k": 5,
    }

    res = await post_json(app, "/v1/query", payload)

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "answered"
    assert "Vector search in PostgreSQL" in data["text"]
    assert len(data["citations"]) == 1
    assert data["citations"][0]["chunk_id"] == str(chunk_id)


@pytest.mark.asyncio
async def test_query_endpoint_returns_503_when_service_uninitialized() -> None:
    app = create_app(AppSettings(_env_file=None), rag_service=None)  # type: ignore[call-arg]

    payload = {
        "query": "Hello?",
        "workspace_id": str(uuid4()),
        "user_id": str(uuid4()),
        "knowledge_base_ids": [str(uuid4())],
    }

    res = await post_json(app, "/v1/query", payload)

    assert res.status_code == 503
    data = res.json()
    assert data["status"] == "abstained"
    assert "service_unavailable" in data["diagnostic_codes"]


@pytest.mark.asyncio
async def test_query_endpoint_validates_schema() -> None:
    app = create_app(AppSettings(_env_file=None))  # type: ignore[call-arg]

    # Missing mandatory fields
    res = await post_json(app, "/v1/query", {"query": ""})
    assert res.status_code == 422

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from rag_api.main import create_app
from rag_core.config import AppSettings


@pytest.mark.asyncio
async def test_chat_stream_delivers_sse_tokens_and_citations() -> None:
    async def mock_stream(_: Any) -> AsyncIterator[dict[str, Any]]:
        yield {
            "event": "evidence",
            "data": {
                "items": [
                    {
                        "ordinal": 1,
                        "chunk_id": str(uuid4()),
                        "document_id": str(uuid4()),
                        "source_label": "Source 1",
                    }
                ]
            },
        }
        yield {"event": "token", "data": {"text": "PostgreSQL "}}
        yield {"event": "token", "data": {"text": "hybrid search [1]."}}
        yield {
            "event": "done",
            "data": {
                "status": "answered",
                "citations": [{"ordinal": 1, "source_label": "Source 1"}],
                "confidence": 0.95,
            },
        }

    mock_rag_service = MagicMock()
    mock_rag_service.answer_query_stream = mock_stream

    app = create_app(AppSettings(_env_file=None), rag_service=mock_rag_service)  # type: ignore[call-arg]

    payload = {
        "query": "How does hybrid search work?",
        "workspace_id": str(uuid4()),
        "user_id": str(uuid4()),
        "knowledge_base_ids": [str(uuid4())],
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/chat/stream", json=payload)

    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    body = res.text
    assert "event: evidence" in body
    assert "event: token" in body
    assert "PostgreSQL" in body
    assert "event: done" in body
    assert "answered" in body


@pytest.mark.asyncio
async def test_chat_stream_returns_503_when_service_missing() -> None:
    app = create_app(AppSettings(_env_file=None), rag_service=None)  # type: ignore[call-arg]

    payload = {
        "query": "Hello?",
        "workspace_id": str(uuid4()),
        "user_id": str(uuid4()),
        "knowledge_base_ids": [str(uuid4())],
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/chat/stream", json=payload)

    assert res.status_code == 503
    assert "text/event-stream" in res.headers["content-type"]
    assert "abstained" in res.text

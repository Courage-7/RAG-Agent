from collections.abc import AsyncIterator, Mapping
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from rag_api.main import create_app
from rag_core.agent.graph import AdaptiveRagGraph, AgentState
from rag_core.config import AppSettings


async def post_json(app: object, path: str, json_data: Mapping[str, Any]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=json_data)


@pytest.mark.asyncio
async def test_dashboard_serves_html() -> None:
    app = create_app(AppSettings(_env_file=None))  # type: ignore[call-arg]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")

    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "RAG-Agent" in res.text
    assert "LangGraph" in res.text


@pytest.mark.asyncio
async def test_agent_query_endpoint_success() -> None:
    mock_agent = AsyncMock(spec=AdaptiveRagGraph)
    mock_agent.ainvoke.return_value = AgentState(
        query="Explain HNSW indexing",
        workspace_id=uuid4(),
        user_id=uuid4(),
        knowledge_base_ids=(uuid4(),),
        route="retrieve",
        effective_query="Explain HNSW indexing",
        answer="HNSW creates multi-layer graph structures for logarithmic nearest-neighbor search.",
        status="answered",
        citations=({"ordinal": 1, "chunk_id": str(uuid4()), "source_label": "HNSW docs"},),
    )

    app = create_app(AppSettings(_env_file=None), agent_graph=mock_agent)  # type: ignore[call-arg]

    payload = {
        "query": "Explain HNSW indexing",
        "workspace_id": str(uuid4()),
        "user_id": str(uuid4()),
        "knowledge_base_ids": [str(uuid4())],
    }

    res = await post_json(app, "/v1/agent/query", payload)

    assert res.status_code == 200
    data = res.json()
    assert data["route"] == "retrieve"
    assert data["status"] == "answered"
    assert "HNSW creates multi-layer" in data["answer"]
    assert len(data["citations"]) == 1


@pytest.mark.asyncio
async def test_agent_query_endpoint_unconfigured() -> None:
    app = create_app(AppSettings(_env_file=None), rag_service=None, agent_graph=None)  # type: ignore[call-arg]

    payload = {
        "query": "Explain HNSW indexing",
        "workspace_id": str(uuid4()),
        "user_id": str(uuid4()),
        "knowledge_base_ids": [str(uuid4())],
    }

    res = await post_json(app, "/v1/agent/query", payload)

    assert res.status_code == 503
    data = res.json()
    assert data["status"] == "abstained"
    assert "not initialized" in data["answer"]


@pytest.mark.asyncio
async def test_agent_stream_endpoint_success() -> None:
    mock_agent = AsyncMock(spec=AdaptiveRagGraph)

    async def fake_astream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        yield {"event": "routing", "data": {"route": "retrieve", "effective_query": "HNSW query"}}
        yield {
            "event": "answer",
            "data": {"answer": "HNSW is efficient.", "citations": (), "status": "answered"},
        }
        yield {"event": "done", "data": {"thread_id": "thread-123"}}

    mock_agent.astream = fake_astream

    app = create_app(AppSettings(_env_file=None), agent_graph=mock_agent)  # type: ignore[call-arg]

    transport = httpx.ASGITransport(app=app)
    payload = {
        "query": "How fast is HNSW?",
        "workspace_id": str(uuid4()),
        "user_id": str(uuid4()),
        "knowledge_base_ids": [str(uuid4())],
        "thread_id": "thread-123",
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/agent/stream", json=payload)

    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    text = res.text
    assert "event: routing" in text
    assert "event: answer" in text
    assert "event: done" in text
    assert "HNSW is efficient." in text


@pytest.mark.asyncio
async def test_agent_stream_endpoint_unconfigured() -> None:
    app = create_app(AppSettings(_env_file=None), rag_service=None, agent_graph=None)  # type: ignore[call-arg]

    transport = httpx.ASGITransport(app=app)
    payload = {
        "query": "How fast is HNSW?",
        "workspace_id": str(uuid4()),
        "user_id": str(uuid4()),
        "knowledge_base_ids": [str(uuid4())],
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/agent/stream", json=payload)

    assert res.status_code == 503
    assert "event: error" in res.text

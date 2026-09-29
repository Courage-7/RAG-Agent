from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from rag_core.agent.graph import AdaptiveRagGraph
from rag_core.models.contracts import ChatModelPort, ModelResponse
from rag_core.retrieval.models import (
    RetrievalResult,
    RetrievalStrategy,
    RetrievedChunk,
)
from rag_core.retrieval.ports import RetrieverPort, WebSearchPort, WebSearchResult


@pytest.mark.asyncio
async def test_agent_graph_routes_direct_for_greeting() -> None:
    mock_model = AsyncMock(spec=ChatModelPort)
    mock_model.complete.return_value = ModelResponse(
        text="Hello! How can I assist your engineering work today?",
        model="llama-3.3-70b-versatile",
    )
    mock_retriever = AsyncMock(spec=RetrieverPort)

    agent = AdaptiveRagGraph(model=mock_model, retriever=mock_retriever)

    result = await agent.ainvoke(
        "Hello!",
        workspace_id=uuid4(),
        user_id=uuid4(),
        knowledge_base_ids=(uuid4(),),
    )

    assert result.route == "direct"
    assert "Hello!" in result.answer
    mock_retriever.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_graph_retrieves_and_synthesizes() -> None:
    mock_model = AsyncMock(spec=ChatModelPort)
    mock_model.complete.return_value = ModelResponse(
        text="PostgreSQL pgvector provides fast vector indexing [1].",
        model="llama-3.3-70b-versatile",
    )
    mock_retriever = AsyncMock(spec=RetrieverPort)
    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        content="PostgreSQL pgvector documentation details.",
        rank=1,
    )
    mock_retriever.retrieve.return_value = RetrievalResult(
        strategy=RetrievalStrategy.HYBRID,
        chunks=(chunk,),
    )

    agent = AdaptiveRagGraph(model=mock_model, retriever=mock_retriever)

    result = await agent.ainvoke(
        "Tell me about pgvector",
        workspace_id=uuid4(),
        user_id=uuid4(),
        knowledge_base_ids=(uuid4(),),
    )

    assert result.route == "retrieve"
    assert result.status == "answered"
    assert len(result.citations) == 1
    assert result.citations[0]["chunk_id"] == str(chunk.chunk_id)
    mock_retriever.retrieve.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_graph_falls_back_to_web_search_when_no_chunks() -> None:
    mock_model = AsyncMock(spec=ChatModelPort)
    mock_model.complete.return_value = ModelResponse(
        text="Based on web sources, the event occurred recently.",
        model="llama-3.3-70b-versatile",
    )
    mock_retriever = AsyncMock(spec=RetrieverPort)
    mock_retriever.retrieve.return_value = RetrievalResult(
        strategy=RetrievalStrategy.HYBRID,
        chunks=(),
    )
    mock_web = AsyncMock(spec=WebSearchPort)
    mock_web.search.return_value = [
        WebSearchResult(
            title="Tech News",
            url="https://news.example.com",
            content="Recent announcements.",
        )
    ]

    agent = AdaptiveRagGraph(
        model=mock_model,
        retriever=mock_retriever,
        web_search=mock_web,
    )

    result = await agent.ainvoke(
        "What is the latest breakthrough today?",
        workspace_id=uuid4(),
        user_id=uuid4(),
        knowledge_base_ids=(uuid4(),),
    )

    assert result.status == "answered"
    assert "Recent announcements" in result.web_content
    mock_web.search.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_graph_astream_emits_step_events() -> None:
    mock_model = AsyncMock(spec=ChatModelPort)
    mock_model.complete.return_value = ModelResponse(
        text="Hello there!",
        model="llama-3.3-70b-versatile",
    )
    mock_retriever = AsyncMock(spec=RetrieverPort)

    agent = AdaptiveRagGraph(model=mock_model, retriever=mock_retriever)

    events: list[dict[str, Any]] = []
    async for event in agent.astream(
        "Hi!",
        workspace_id=uuid4(),
        user_id=uuid4(),
        knowledge_base_ids=(uuid4(),),
        thread_id="test-session-123",
    ):
        events.append(event)

    event_names = [e["event"] for e in events]
    assert "routing" in event_names
    assert "answer" in event_names
    assert "done" in event_names
    done_event = next(e for e in events if e["event"] == "done")
    assert done_event["data"]["thread_id"] == "test-session-123"

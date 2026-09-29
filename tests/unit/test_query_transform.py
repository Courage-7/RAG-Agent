from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from rag_core.models.contracts import ChatMessage, ChatModelPort, ModelResponse
from rag_core.retrieval.models import (
    RetrievalResult,
    RetrievalStrategy,
    RetrievedChunk,
)
from rag_core.retrieval.ports import RetrieverPort
from rag_core.retrieval.query_transform import condense_query
from rag_core.retrieval.service import QueryRequest, RagService


@pytest.mark.asyncio
async def test_condense_query_skips_when_history_empty() -> None:
    mock_model = AsyncMock(spec=ChatModelPort)
    result = await condense_query(mock_model, [], "What is pgvector?")
    assert result == "What is pgvector?"
    mock_model.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_condense_query_calls_model_with_history() -> None:
    mock_model = AsyncMock(spec=ChatModelPort)
    mock_model.complete.return_value = ModelResponse(
        text='"pgvector HNSW index performance in PostgreSQL"',
        model="llama-3.1-8b-instant",
    )

    history = [
        ChatMessage(role="user", content="Tell me about pgvector."),
        ChatMessage(role="assistant", content="pgvector provides vector search."),
    ]
    latest = "How fast is its HNSW indexing?"

    condensed = await condense_query(mock_model, history, latest)

    assert condensed == "pgvector HNSW index performance in PostgreSQL"
    mock_model.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_condense_query_falls_back_on_error() -> None:
    mock_model = AsyncMock(spec=ChatModelPort)
    mock_model.complete.side_effect = RuntimeError("Model provider error")

    history = [ChatMessage(role="user", content="Hello")]
    latest = "Can you help me?"

    result = await condense_query(mock_model, history, latest)
    assert result == latest


@pytest.mark.asyncio
async def test_rag_service_condenses_query_when_history_present() -> None:
    mock_retriever = AsyncMock(spec=RetrieverPort)
    mock_model = AsyncMock(spec=ChatModelPort)

    c1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        content="HNSW creates a multi-layer graph [1].",
        rank=1,
    )
    mock_retriever.retrieve.return_value = RetrievalResult(
        strategy=RetrievalStrategy.HYBRID,
        chunks=(c1,),
    )
    # First complete is for query condensation, second is for synthesis
    mock_model.complete.side_effect = [
        ModelResponse(text="pgvector HNSW graph structure", model="llama-3.1-8b-instant"),
        ModelResponse(text="HNSW uses a multi-layer graph [1].", model="llama-3.3-70b-versatile"),
    ]

    service = RagService(retriever=mock_retriever, model_provider=mock_model)

    request = QueryRequest(
        query="How does its layer structure work?",
        workspace_id=uuid4(),
        user_id=uuid4(),
        knowledge_base_ids=(uuid4(),),
        chat_history=(
            ChatMessage(role="user", content="What is HNSW in pgvector?"),
            ChatMessage(role="assistant", content="HNSW is an index."),
        ),
    )

    answer = await service.answer_query(request)

    assert answer.status == "answered"
    assert mock_model.complete.await_count == 2
    # Verify retrieval query received the condensed search text
    called_retrieval_query = mock_retriever.retrieve.call_args[0][0]
    assert called_retrieval_query.text == "pgvector HNSW graph structure"

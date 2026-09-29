from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from rag_core.models.contracts import ChatModelPort, ModelResponse
from rag_core.retrieval.models import (
    RetrievalResult,
    RetrievalStrategy,
    RetrievedChunk,
)
from rag_core.retrieval.ports import RerankerPort, RetrieverPort
from rag_core.retrieval.reranker import FlashRankReranker
from rag_core.retrieval.service import QueryRequest, RagService


@pytest.mark.asyncio
async def test_flashrank_reranker_scores_and_orders_chunks() -> None:
    reranker = FlashRankReranker()

    c1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        content="Cooking recipes for chocolate cake and frosting.",
        rank=1,
    )
    c2 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        content="PostgreSQL pgvector extension enables fast vector similarity search.",
        rank=2,
    )
    c3 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        content="Database index optimization with HNSW and IVFFlat.",
        rank=3,
    )

    query = "How to search vectors in postgres?"
    results = await reranker.rerank(query, [c1, c2, c3], top_k=2)

    assert len(results) == 2
    # The postgres vector chunk (c2) must rank first
    assert results[0].chunk_id == c2.chunk_id
    assert results[0].rank == 1
    assert results[0].reranker_score is not None
    assert results[1].reranker_score is not None
    assert results[0].reranker_score > results[1].reranker_score


@pytest.mark.asyncio
async def test_flashrank_reranker_handles_empty() -> None:
    reranker = FlashRankReranker()
    results = await reranker.rerank("any query", [])
    assert results == []


@pytest.mark.asyncio
async def test_rag_service_uses_reranker_when_provided() -> None:
    mock_retriever = AsyncMock(spec=RetrieverPort)
    mock_model = AsyncMock(spec=ChatModelPort)
    mock_reranker = AsyncMock(spec=RerankerPort)

    c1 = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        content="PostgreSQL pgvector documentation [1].",
        rank=1,
    )
    mock_retriever.retrieve.return_value = RetrievalResult(
        strategy=RetrievalStrategy.HYBRID,
        chunks=(c1,),
    )
    mock_reranker.rerank.return_value = [c1]
    mock_model.complete.return_value = ModelResponse(
        text="PostgreSQL pgvector supports vector search [1].",
        model="llama-3.3-70b-versatile",
    )

    service = RagService(
        retriever=mock_retriever,
        model_provider=mock_model,
        reranker=mock_reranker,
    )

    request = QueryRequest(
        query="Tell me about pgvector",
        workspace_id=uuid4(),
        user_id=uuid4(),
        knowledge_base_ids=(uuid4(),),
        top_k=5,
    )

    answer = await service.answer_query(request)

    assert answer.status == "answered"
    mock_reranker.rerank.assert_awaited_once()

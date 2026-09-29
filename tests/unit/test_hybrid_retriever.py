from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from rag_core.retrieval.embeddings import DEFAULT_EMBEDDING_DIMENSIONS, FastEmbedProvider
from rag_core.retrieval.hybrid import HybridRetriever, RetrievalExecutionError
from rag_core.retrieval.models import RetrievalQuery, RetrievalStrategy


class FakeEmbeddingProvider:
    async def embed_query(self, text: str) -> list[float]:
        return [0.1] * DEFAULT_EMBEDDING_DIMENSIONS

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * DEFAULT_EMBEDDING_DIMENSIONS for _ in texts]


@pytest.mark.asyncio
async def test_fastembed_generates_correct_dimensions() -> None:
    embedder = FastEmbedProvider()
    vec = await embedder.embed_query("Hello world")
    assert len(vec) == DEFAULT_EMBEDDING_DIMENSIONS


@pytest.mark.asyncio
async def test_hybrid_retriever_executes_rpc_and_maps_chunks() -> None:
    chunk_id = uuid4()
    doc_id = uuid4()
    ver_id = uuid4()
    workspace_id = uuid4()
    kb_id = uuid4()

    mock_row = {
        "chunk_id": chunk_id,
        "document_id": doc_id,
        "document_version_id": ver_id,
        "content": "PostgreSQL hybrid search result",
        "source_label": "Technical Documentation",
        "fused_score": 0.032,
        "dense_score": 0.88,
        "lexical_score": 0.42,
        "rank": 1,
    }

    mock_cursor = AsyncMock()
    mock_cursor.fetchall.return_value = [mock_row]

    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor

    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__.return_value = mock_conn

    retriever = HybridRetriever(mock_pool, FakeEmbeddingProvider())

    query = RetrievalQuery(
        text="How does hybrid search work?",
        workspace_id=workspace_id,
        user_id=uuid4(),
        knowledge_base_ids=(kb_id,),
        top_k=5,
    )

    result = await retriever.retrieve(query)

    assert result.strategy == RetrievalStrategy.HYBRID
    assert len(result.chunks) == 1
    chunk = result.chunks[0]
    assert chunk.chunk_id == chunk_id
    assert chunk.document_id == doc_id
    assert chunk.content == "PostgreSQL hybrid search result"
    assert chunk.fused_score == 0.032
    assert chunk.dense_score == 0.88
    assert chunk.rank == 1


@pytest.mark.asyncio
async def test_hybrid_retriever_raises_on_db_error() -> None:
    mock_pool = MagicMock()
    mock_pool.connection.side_effect = RuntimeError("Database connection lost")

    retriever = HybridRetriever(mock_pool, FakeEmbeddingProvider())

    query = RetrievalQuery(
        text="Fail query",
        workspace_id=uuid4(),
        user_id=uuid4(),
        knowledge_base_ids=(uuid4(),),
        top_k=5,
    )

    with pytest.raises(RetrievalExecutionError, match="Hybrid retrieval database query failed"):
        await retriever.retrieve(query)

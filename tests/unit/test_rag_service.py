from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from rag_core.models.contracts import ModelResponse, ModelUsage
from rag_core.retrieval.models import (
    AnswerStatus,
    RetrievalResult,
    RetrievalStrategy,
    RetrievedChunk,
)
from rag_core.retrieval.service import QueryRequest, RagService


@pytest.mark.asyncio
async def test_rag_service_generates_answered_with_citations() -> None:
    chunk_id = uuid4()
    doc_id = uuid4()

    mock_retriever = AsyncMock()
    mock_retriever.retrieve.return_value = RetrievalResult(
        strategy=RetrievalStrategy.HYBRID,
        chunks=(
            RetrievedChunk(
                chunk_id=chunk_id,
                document_id=doc_id,
                document_version_id=uuid4(),
                content="PostgreSQL pgvector enables HNSW indexing.",
                rank=1,
                fused_score=0.9,
            ),
        ),
    )

    mock_model = AsyncMock()
    mock_model.complete.return_value = ModelResponse(
        text="pgvector provides HNSW indexing [1].",
        model="llama-3.3-70b-versatile",
        usage=ModelUsage(input_tokens=100, output_tokens=20, total_tokens=120),
    )

    service = RagService(mock_retriever, mock_model)

    req = QueryRequest(
        query="What indexing does pgvector provide?",
        workspace_id=uuid4(),
        user_id=uuid4(),
        knowledge_base_ids=(uuid4(),),
    )

    answer = await service.answer_query(req)

    assert answer.status == AnswerStatus.ANSWERED
    assert "HNSW indexing" in answer.text
    assert len(answer.citations) == 1
    assert answer.citations[0].chunk_id == chunk_id
    assert answer.citations[0].document_id == doc_id
    assert answer.confidence >= 0.8


@pytest.mark.asyncio
async def test_rag_service_abstains_when_no_chunks_found() -> None:
    mock_retriever = AsyncMock()
    mock_retriever.retrieve.return_value = RetrievalResult(
        strategy=RetrievalStrategy.HYBRID,
        chunks=(),
    )

    mock_model = AsyncMock()
    service = RagService(mock_retriever, mock_model)

    req = QueryRequest(
        query="What is the meaning of life?",
        workspace_id=uuid4(),
        user_id=uuid4(),
        knowledge_base_ids=(uuid4(),),
    )

    answer = await service.answer_query(req)

    assert answer.status == AnswerStatus.ABSTAINED
    assert len(answer.citations) == 0
    assert "no_chunks_retrieved" in answer.diagnostic_codes
    mock_model.complete.assert_not_called()


@pytest.mark.asyncio
async def test_rag_service_abstains_on_uncited_response() -> None:
    mock_retriever = AsyncMock()
    mock_retriever.retrieve.return_value = RetrievalResult(
        strategy=RetrievalStrategy.HYBRID,
        chunks=(
            RetrievedChunk(
                chunk_id=uuid4(),
                document_id=uuid4(),
                document_version_id=uuid4(),
                content="Some facts here.",
                rank=1,
            ),
        ),
    )

    mock_model = AsyncMock()
    mock_model.complete.return_value = ModelResponse(
        text="I am not sure about this information.",
        model="llama-3.3-70b-versatile",
    )

    service = RagService(mock_retriever, mock_model)

    req = QueryRequest(
        query="Question?",
        workspace_id=uuid4(),
        user_id=uuid4(),
        knowledge_base_ids=(uuid4(),),
    )

    answer = await service.answer_query(req)

    assert answer.status == AnswerStatus.ABSTAINED
    assert len(answer.citations) == 0
    assert "uncited_answer" in answer.diagnostic_codes

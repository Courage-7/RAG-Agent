import re
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field

from rag_core.models.contracts import ChatMessage, ChatModelPort, ModelRequest
from rag_core.models.profiles import ModelPurpose
from rag_core.retrieval.models import (
    AnswerStatus,
    Citation,
    GroundedAnswer,
    RetrievalQuery,
    RetrievedChunk,
)
from rag_core.retrieval.ports import RerankerPort, RetrieverPort
from rag_core.retrieval.query_transform import condense_query

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are a precise, grounded assistant.
Answer the user's question using ONLY the provided evidence sources below.
Rules:
1. Every factual statement must be supported by the provided evidence.
2. When referencing evidence, include the source citation in square brackets, e.g. [1] or [2].
3. If the provided evidence does not contain sufficient information to answer the question, state:
   "I do not have sufficient evidence in the knowledge base to answer this question."
4. Do NOT hallucinate or speculate beyond the provided context.
"""


class QueryRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1, max_length=10_000)
    workspace_id: UUID
    user_id: UUID
    knowledge_base_ids: tuple[UUID, ...] = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=50)
    chat_history: tuple[ChatMessage, ...] = ()


class RagService:
    """Orchestrates query retrieval, cross-encoder reranking, and citation extraction."""

    def __init__(
        self,
        retriever: RetrieverPort,
        model_provider: ChatModelPort,
        *,
        reranker: RerankerPort | None = None,
        model_alias: str = ModelPurpose.QUALITY.value,
        fast_model_alias: str = ModelPurpose.FAST_STRUCTURED.value,
    ) -> None:
        self._retriever = retriever
        self._model = model_provider
        self._reranker = reranker
        self._model_alias = model_alias
        self._fast_model_alias = fast_model_alias

    @staticmethod
    def _format_context(
        chunks: tuple[RetrievedChunk, ...],
    ) -> tuple[str, dict[int, RetrievedChunk]]:
        chunk_map: dict[int, RetrievedChunk] = {}
        context_parts: list[str] = []
        for i, chunk in enumerate(chunks, start=1):
            chunk_map[i] = chunk
            context_parts.append(f"[{i}] (Chunk ID: {chunk.chunk_id}):\n{chunk.content}")
        return "\n\n".join(context_parts), chunk_map

    @staticmethod
    def _extract_citations(
        text: str,
        chunk_map: dict[int, RetrievedChunk],
    ) -> tuple[Citation, ...]:
        # Find citations like [1], [2], etc.
        cited_ordinals = {int(m) for m in re.findall(r"\[(\d+)\]", text) if int(m) in chunk_map}
        citations: list[Citation] = []
        for ordinal in sorted(cited_ordinals):
            chunk = chunk_map[ordinal]
            citations.append(
                Citation(
                    ordinal=ordinal,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    source_label=f"Source Chunk {ordinal}",
                )
            )
        return tuple(citations)

    async def answer_query(self, request: QueryRequest) -> GroundedAnswer:
        """Retrieve evidence and generate a verified grounded answer."""
        effective_query = request.query
        if request.chat_history:
            effective_query = await condense_query(
                self._model,
                request.chat_history,
                request.query,
                model_alias=self._fast_model_alias,
            )

        fetch_k = max(request.top_k * 2, 20) if self._reranker is not None else request.top_k
        retrieval_query = RetrievalQuery(
            text=effective_query,
            workspace_id=request.workspace_id,
            user_id=request.user_id,
            knowledge_base_ids=request.knowledge_base_ids,
            top_k=fetch_k,
        )

        result = await self._retriever.retrieve(retrieval_query)
        if not result.chunks:
            return GroundedAnswer(
                status=AnswerStatus.ABSTAINED,
                text=(
                    "I do not have sufficient evidence in the knowledge base "
                    "to answer this question."
                ),
                citations=(),
                confidence=0.0,
                diagnostic_codes=("no_chunks_retrieved",),
            )

        chunks_to_use = result.chunks
        if self._reranker is not None:
            reranked = await self._reranker.rerank(
                request.query,
                result.chunks,
                top_k=request.top_k,
            )
            chunks_to_use = tuple(reranked)
        else:
            chunks_to_use = result.chunks[: request.top_k]

        context_text, chunk_map = self._format_context(chunks_to_use)
        user_message_content = (
            f"Evidence Sources:\n{context_text}\n\nUser Question: {request.query}"
        )

        model_req = ModelRequest(
            profile_alias=self._model_alias,
            messages=(
                ChatMessage(role="system", content=SYSTEM_PROMPT),
                ChatMessage(role="user", content=user_message_content),
            ),
        )

        response = await self._model.complete(model_req)
        citations = self._extract_citations(response.text, chunk_map)

        if not citations:
            # Model did not cite sources or abstained
            return GroundedAnswer(
                status=AnswerStatus.ABSTAINED,
                text=response.text,
                citations=(),
                confidence=0.1,
                diagnostic_codes=("uncited_answer",),
            )

        return GroundedAnswer(
            status=AnswerStatus.ANSWERED,
            text=response.text,
            citations=citations,
            confidence=0.9,
            diagnostic_codes=(),
        )

    async def answer_query_stream(
        self,
        request: QueryRequest,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream retrieved evidence, generated tokens, and verified citations."""
        effective_query = request.query
        if request.chat_history:
            effective_query = await condense_query(
                self._model,
                request.chat_history,
                request.query,
                model_alias=self._fast_model_alias,
            )

        fetch_k = max(request.top_k * 2, 20) if self._reranker is not None else request.top_k
        retrieval_query = RetrievalQuery(
            text=effective_query,
            workspace_id=request.workspace_id,
            user_id=request.user_id,
            knowledge_base_ids=request.knowledge_base_ids,
            top_k=fetch_k,
        )

        result = await self._retriever.retrieve(retrieval_query)
        if not result.chunks:
            yield {
                "event": "token",
                "data": {
                    "text": (
                        "I do not have sufficient evidence in the knowledge base "
                        "to answer this question."
                    )
                },
            }
            yield {
                "event": "done",
                "data": {
                    "status": "abstained",
                    "citations": [],
                    "confidence": 0.0,
                    "diagnostic_codes": ["no_chunks_retrieved"],
                },
            }
            return

        chunks_to_use = result.chunks
        if self._reranker is not None:
            reranked = await self._reranker.rerank(
                request.query,
                result.chunks,
                top_k=request.top_k,
            )
            chunks_to_use = tuple(reranked)
        else:
            chunks_to_use = result.chunks[: request.top_k]

        context_text, chunk_map = self._format_context(chunks_to_use)
        evidence_items = [
            {
                "ordinal": ordinal,
                "chunk_id": str(chunk.chunk_id),
                "document_id": str(chunk.document_id),
                "source_label": f"Source Chunk {ordinal}",
            }
            for ordinal, chunk in chunk_map.items()
        ]
        yield {"event": "evidence", "data": {"items": evidence_items}}

        user_message_content = (
            f"Evidence Sources:\n{context_text}\n\nUser Question: {request.query}"
        )
        model_req = ModelRequest(
            profile_alias=self._model_alias,
            messages=(
                ChatMessage(role="system", content=SYSTEM_PROMPT),
                ChatMessage(role="user", content=user_message_content),
            ),
        )

        full_text_parts: list[str] = []
        async for chunk in self._model.stream(model_req):
            if chunk.text:
                full_text_parts.append(chunk.text)
                yield {"event": "token", "data": {"text": chunk.text}}

        complete_text = "".join(full_text_parts)
        citations = self._extract_citations(complete_text, chunk_map)

        if not citations:
            yield {
                "event": "done",
                "data": {
                    "status": "abstained",
                    "citations": [],
                    "confidence": 0.1,
                    "diagnostic_codes": ["uncited_answer"],
                },
            }
            return

        yield {
            "event": "done",
            "data": {
                "status": "answered",
                "citations": [
                    {
                        "ordinal": c.ordinal,
                        "chunk_id": str(c.chunk_id),
                        "document_id": str(c.document_id),
                        "source_label": c.source_label,
                    }
                    for c in citations
                ],
                "confidence": 0.9,
                "diagnostic_codes": [],
            },
        }

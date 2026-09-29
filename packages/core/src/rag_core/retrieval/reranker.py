"""Fast CPU-optimized Cross-Encoder Reranker using FlashRank (ONNX)."""

from collections.abc import Sequence
from typing import Any

import anyio
import structlog
from flashrank import Ranker, RerankRequest  # type: ignore[import-untyped]

from rag_core.retrieval.models import RetrievedChunk
from rag_core.retrieval.ports import RerankerPort

logger = structlog.get_logger(__name__)


class FlashRankReranker(RerankerPort):
    """Reranks retrieved candidate chunks using an ONNX Cross-Encoder model on CPU."""

    def __init__(self, model_name: str = "ms-marco-TinyBERT-L-2-v2") -> None:
        self._ranker = Ranker(model_name=model_name)

    async def rerank(
        self,
        query: str,
        chunks: Sequence[RetrievedChunk],
        *,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Rescore candidate chunks with query-passage cross-attention."""
        if not chunks:
            return []

        passages = [{"id": str(chunk.chunk_id), "text": chunk.content} for chunk in chunks]
        chunk_map = {str(c.chunk_id): c for c in chunks}

        def _execute_rerank() -> list[dict[str, Any]]:
            request = RerankRequest(query=query, passages=passages)
            return self._ranker.rerank(request)  # type: ignore[no-any-return]

        reranked_results = await anyio.to_thread.run_sync(_execute_rerank)

        scored_chunks: list[RetrievedChunk] = []
        for new_rank, item in enumerate(reranked_results, start=1):
            chunk_id = str(item["id"])
            original_chunk = chunk_map[chunk_id]
            score = float(item["score"])

            updated = RetrievedChunk(
                chunk_id=original_chunk.chunk_id,
                document_id=original_chunk.document_id,
                document_version_id=original_chunk.document_version_id,
                content=original_chunk.content,
                rank=new_rank,
                fused_score=original_chunk.fused_score,
                dense_score=original_chunk.dense_score,
                lexical_score=original_chunk.lexical_score,
                reranker_score=score,
            )
            scored_chunks.append(updated)

        if top_k is not None:
            scored_chunks = scored_chunks[:top_k]

        logger.info(
            "reranking_completed",
            input_count=len(chunks),
            output_count=len(scored_chunks),
            top_score=scored_chunks[0].reranker_score if scored_chunks else None,
        )
        return scored_chunks

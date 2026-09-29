"""Hybrid dense and lexical retriever implementation with Reciprocal Rank Fusion."""

from typing import Any

import structlog
from pgvector import Vector
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from rag_core.errors import RetrievalExecutionError
from rag_core.retrieval.embeddings import EmbeddingPort
from rag_core.retrieval.models import (
    RetrievalQuery,
    RetrievalResult,
    RetrievalStrategy,
    RetrievedChunk,
)

logger = structlog.get_logger(__name__)


class HybridRetriever:
    """Production hybrid retriever combining dense and lexical search via RRF."""

    def __init__(
        self,
        pool: AsyncConnectionPool,
        embedder: EmbeddingPort,
        *,
        rrf_k: int = 60,
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._rrf_k = rrf_k

    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """Execute hybrid search using the database RPC function."""
        # 1. Generate query embedding
        try:
            query_vector = await self._embedder.embed_query(query.text)
        except Exception as exc:
            logger.error("query_embedding_failed", error=str(exc))
            raise RetrievalExecutionError("Failed to generate embedding for query") from exc

        # 2. Execute SQL RPC function
        sql = """
            select
              chunk_id,
              document_id,
              document_version_id,
              content,
              source_label,
              fused_score,
              dense_score,
              lexical_score,
              rank
            from public.match_chunks_hybrid(
              query_text => %(text)s,
              query_embedding => %(embedding)s,
              match_count => %(top_k)s,
              filter_workspace_id => %(workspace_id)s,
              filter_knowledge_base_ids => %(kb_ids)s,
              rrf_k => %(rrf_k)s
            );
        """
        params: dict[str, Any] = {
            "text": query.text,
            "embedding": Vector(query_vector),
            "top_k": query.top_k,
            "workspace_id": query.workspace_id,
            "kb_ids": list(query.knowledge_base_ids),
            "rrf_k": self._rrf_k,
        }

        try:
            async with (
                self._pool.connection() as conn,
                conn.cursor(row_factory=dict_row) as cursor,
            ):
                await cursor.execute(sql, params)
                rows = await cursor.fetchall()
        except Exception as exc:
            logger.error("hybrid_retrieval_query_failed", error=str(exc))
            raise RetrievalExecutionError("Hybrid retrieval database query failed") from exc

        # 3. Construct strongly-typed RetrievedChunk objects
        chunks = tuple(
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                document_version_id=row["document_version_id"],
                content=row["content"],
                rank=row["rank"],
                fused_score=row["fused_score"],
                dense_score=row["dense_score"],
                lexical_score=row["lexical_score"],
            )
            for row in rows
        )

        return RetrievalResult(
            strategy=RetrievalStrategy.HYBRID,
            chunks=chunks,
            degraded=False,
            diagnostic_codes=(),
        )

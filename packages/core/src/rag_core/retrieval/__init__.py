"""Provider-neutral retrieval contracts, embeddings, and hybrid search implementation."""

from rag_core.retrieval.embeddings import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingPort,
    FastEmbedProvider,
)
from rag_core.retrieval.hybrid import HybridRetriever, RetrievalExecutionError
from rag_core.retrieval.models import (
    AnswerStatus,
    Citation,
    GroundedAnswer,
    RetrievalQuery,
    RetrievalResult,
    RetrievalStrategy,
    RetrievedChunk,
)
from rag_core.retrieval.ports import RerankerPort, RetrieverPort
from rag_core.retrieval.reranker import FlashRankReranker
from rag_core.retrieval.service import QueryRequest, RagService

__all__ = [
    "DEFAULT_EMBEDDING_DIMENSIONS",
    "DEFAULT_EMBEDDING_MODEL",
    "AnswerStatus",
    "Citation",
    "EmbeddingPort",
    "FastEmbedProvider",
    "FlashRankReranker",
    "GroundedAnswer",
    "HybridRetriever",
    "QueryRequest",
    "RagService",
    "RerankerPort",
    "RetrievalExecutionError",
    "RetrievalQuery",
    "RetrievalResult",
    "RetrievalStrategy",
    "RetrievedChunk",
    "RetrieverPort",
]

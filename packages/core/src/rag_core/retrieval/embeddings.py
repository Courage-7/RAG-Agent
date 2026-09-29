"""Provider-neutral embedding port and FastEmbed ONNX implementation."""

from typing import Protocol

import anyio
import structlog
from fastembed import TextEmbedding

logger = structlog.get_logger(__name__)

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_EMBEDDING_DIMENSIONS = 384


class EmbeddingPort(Protocol):
    """Protocol for dense embedding generation."""

    async def embed_query(self, text: str) -> list[float]: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedProvider:
    """CPU-optimized local dense embedding provider using ONNX Runtime."""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)

    def _sync_embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._model.embed(texts)
        return [e.tolist() for e in embeddings]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string in an executor thread without blocking the event loop."""
        results = await anyio.to_thread.run_sync(self._sync_embed, [text])
        if not results:
            raise RuntimeError("Embedding model produced empty output")
        return results[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document chunk texts without blocking the event loop."""
        if not texts:
            return []
        return await anyio.to_thread.run_sync(self._sync_embed, texts)

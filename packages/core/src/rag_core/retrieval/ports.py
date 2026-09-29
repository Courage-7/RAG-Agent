from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from rag_core.retrieval.models import RetrievalQuery, RetrievalResult, RetrievedChunk


class RetrieverPort(Protocol):
    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult: ...


class RerankerPort(Protocol):
    async def rerank(
        self,
        query: str,
        chunks: Sequence[RetrievedChunk],
        *,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]: ...


class WebSearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    content: str


class WebSearchPort(Protocol):
    async def search(self, query: str, *, max_results: int = 5) -> list[WebSearchResult]: ...

"""Retrieval strategy port implemented by baseline and experimental retrievers."""

from typing import Protocol

from rag_core.retrieval.models import RetrievalQuery, RetrievalResult


class RetrieverPort(Protocol):
    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult: ...

"""Stable inputs and outputs for retrieval and grounded answer construction."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RetrievalStrategy(StrEnum):
    HYBRID = "hybrid"
    WEB_FALLBACK = "web_fallback"
    MULTI_QUERY = "multi_query"
    DECOMPOSITION = "decomposition"


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    PARTIAL = "partial"
    ABSTAINED = "abstained"


class RetrievalQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1, max_length=10_000)
    workspace_id: UUID
    user_id: UUID
    knowledge_base_ids: tuple[UUID, ...] = Field(min_length=1, max_length=50)
    top_k: int = Field(default=12, ge=1, le=100)


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    content: str = Field(min_length=1)
    rank: int = Field(ge=1)
    fused_score: float | None = None
    dense_score: float | None = None
    lexical_score: float | None = None
    reranker_score: float | None = None


class RetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy: RetrievalStrategy
    chunks: tuple[RetrievedChunk, ...]
    degraded: bool = False
    diagnostic_codes: tuple[str, ...] = ()


class Citation(BaseModel):
    model_config = ConfigDict(frozen=True)

    ordinal: int = Field(ge=1)
    chunk_id: UUID
    document_id: UUID
    source_label: str = Field(min_length=1, max_length=300)


class GroundedAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: AnswerStatus
    text: str = Field(min_length=1)
    citations: tuple[Citation, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    diagnostic_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def answered_responses_require_evidence(self) -> "GroundedAnswer":
        if self.status is AnswerStatus.ANSWERED and not self.citations:
            raise ValueError("answered responses require at least one citation")
        return self

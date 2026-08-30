"""Provider-neutral job envelopes and state-machine rules."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rag_core.errors import InvalidJobTransitionError


class JobOperation(StrEnum):
    DOCUMENT_INGESTION = "document_ingestion"
    EMBEDDING_BATCH = "embedding_batch"
    MAINTENANCE = "maintenance"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD_LETTER = "dead_letter"


class JobStage(StrEnum):
    QUEUED = "queued"
    VALIDATING = "validating"
    PARSING = "parsing"
    NORMALIZING = "normalizing"
    CHUNKING = "chunking"
    ENRICHING = "enriching"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    VERIFYING = "verifying"
    COMPLETED = "completed"


ALLOWED_STATUS_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.RETRY_SCHEDULED,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.DEAD_LETTER,
        }
    ),
    JobStatus.RETRY_SCHEDULED: frozenset(
        {JobStatus.RUNNING, JobStatus.CANCELLED, JobStatus.DEAD_LETTER}
    ),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
    JobStatus.DEAD_LETTER: frozenset(),
}


def ensure_status_transition(current: JobStatus, target: JobStatus) -> None:
    if target not in ALLOWED_STATUS_TRANSITIONS[current]:
        raise InvalidJobTransitionError(current.value, target.value)


class JobEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(default=1, ge=1, le=1)
    job_id: UUID
    operation: JobOperation
    idempotency_key: str = Field(min_length=8, max_length=200)
    traceparent: str | None = Field(default=None, max_length=512)
    enqueued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("enqueued_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("enqueued_at must be timezone-aware")
        return value


class DispatchReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: UUID
    transport_message_id: str = Field(min_length=1, max_length=200)
    queue_name: str = Field(min_length=1, max_length=100)

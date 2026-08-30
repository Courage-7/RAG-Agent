from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from rag_core.errors import InvalidJobTransitionError
from rag_core.jobs.models import (
    JobEnvelope,
    JobOperation,
    JobStatus,
    ensure_status_transition,
)


def test_job_envelope_round_trips_as_transport_json() -> None:
    envelope = JobEnvelope(
        job_id=uuid4(),
        operation=JobOperation.DOCUMENT_INGESTION,
        idempotency_key="document-version:pipeline-v1",
    )

    restored = JobEnvelope.model_validate(envelope.model_dump(mode="json"))

    assert restored == envelope
    assert restored.enqueued_at.tzinfo is not None


def test_job_envelope_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        JobEnvelope(
            job_id=uuid4(),
            operation=JobOperation.MAINTENANCE,
            idempotency_key="maintenance:cleanup-v1",
            enqueued_at=datetime(2026, 8, 29),
        )


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (JobStatus.QUEUED, JobStatus.RUNNING),
        (JobStatus.RUNNING, JobStatus.RETRY_SCHEDULED),
        (JobStatus.RETRY_SCHEDULED, JobStatus.RUNNING),
        (JobStatus.RUNNING, JobStatus.COMPLETED),
    ],
)
def test_valid_job_status_transitions(current: JobStatus, target: JobStatus) -> None:
    ensure_status_transition(current, target)


def test_terminal_job_status_cannot_restart() -> None:
    with pytest.raises(InvalidJobTransitionError):
        ensure_status_transition(JobStatus.COMPLETED, JobStatus.RUNNING)

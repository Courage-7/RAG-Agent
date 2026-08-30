"""Foundation actor used to prove the worker transport boundary."""

from typing import Any

import dramatiq
from pydantic import ValidationError
from rag_core.jobs.models import JobEnvelope


@dramatiq.actor(
    actor_name="demo_job",
    queue_name="maintenance",
    max_retries=3,
    min_backoff=15_000,
    max_backoff=300_000,
    time_limit=30_000,
    throws=(ValidationError,),
)
def demo_job(payload: dict[str, Any]) -> None:
    """Validate the transport envelope without treating Redis as job state."""

    JobEnvelope.model_validate(payload)

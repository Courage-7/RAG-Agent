from typing import Any
from uuid import uuid4

import pytest
from pytest import MonkeyPatch
from rag_core.errors import QueueDispatchError
from rag_core.jobs.models import JobEnvelope, JobOperation
from rag_worker.infrastructure.dramatiq_queue import DramatiqJobQueue


class FakeMessage:
    message_id = "message-123"


class FakeActor:
    actor_name = "document_ingestion"
    queue_name = "ingestion"

    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None

    def send(self, payload: dict[str, Any]) -> FakeMessage:
        self.payload = payload
        return FakeMessage()


@pytest.fixture(autouse=True)
def run_actor_inline(monkeypatch: MonkeyPatch) -> None:
    """Keep the unit test independent of operating-system thread-pool behavior."""

    async def run_sync(function: Any, *args: Any) -> Any:
        return function(*args)

    monkeypatch.setattr("anyio.to_thread.run_sync", run_sync)


@pytest.mark.asyncio
async def test_dramatiq_adapter_dispatches_only_small_envelope() -> None:
    actor = FakeActor()
    queue = DramatiqJobQueue({JobOperation.DOCUMENT_INGESTION: actor})
    envelope = JobEnvelope(
        job_id=uuid4(),
        operation=JobOperation.DOCUMENT_INGESTION,
        idempotency_key="document-version:pipeline-v1",
    )

    receipt = await queue.enqueue(envelope)

    assert receipt.job_id == envelope.job_id
    assert receipt.transport_message_id == "message-123"
    assert actor.payload is not None
    assert set(actor.payload) == {
        "schema_version",
        "job_id",
        "operation",
        "idempotency_key",
        "traceparent",
        "enqueued_at",
    }


@pytest.mark.asyncio
async def test_dramatiq_adapter_rejects_unregistered_operation() -> None:
    queue = DramatiqJobQueue({})
    envelope = JobEnvelope(
        job_id=uuid4(),
        operation=JobOperation.MAINTENANCE,
        idempotency_key="maintenance:cleanup-v1",
    )

    with pytest.raises(QueueDispatchError, match="No actor"):
        await queue.enqueue(envelope)

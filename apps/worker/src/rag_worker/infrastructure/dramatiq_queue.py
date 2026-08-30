"""Dramatiq implementation of the core job queue port."""

from collections.abc import Mapping
from typing import Any, Protocol

import anyio
from rag_core.errors import QueueDispatchError
from rag_core.jobs.models import DispatchReceipt, JobEnvelope, JobOperation


class ActorSender(Protocol):
    actor_name: str
    queue_name: str

    def send(self, payload: dict[str, Any]) -> Any: ...


class DramatiqJobQueue:
    """Dispatch small job envelopes to an operation-specific Dramatiq actor."""

    def __init__(self, actors: Mapping[JobOperation, ActorSender]) -> None:
        self._actors = dict(actors)

    async def enqueue(self, envelope: JobEnvelope) -> DispatchReceipt:
        actor = self._actors.get(envelope.operation)
        if actor is None:
            raise QueueDispatchError(f"No actor is registered for {envelope.operation.value}")

        try:
            message = await anyio.to_thread.run_sync(
                actor.send,
                envelope.model_dump(mode="json"),
            )
        except Exception as exc:
            raise QueueDispatchError("The job broker rejected the dispatch") from exc

        message_id = getattr(message, "message_id", None)
        if not isinstance(message_id, str) or not message_id:
            raise QueueDispatchError("The job broker returned an invalid message identifier")

        return DispatchReceipt(
            job_id=envelope.job_id,
            transport_message_id=message_id,
            queue_name=actor.queue_name,
        )

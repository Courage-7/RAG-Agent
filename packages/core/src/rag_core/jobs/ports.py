"""Ports for dispatching durable application jobs to transient infrastructure."""

from typing import Protocol

from rag_core.jobs.models import DispatchReceipt, JobEnvelope


class JobQueue(Protocol):
    async def enqueue(self, envelope: JobEnvelope) -> DispatchReceipt: ...

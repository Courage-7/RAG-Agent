"""Transactional outbox event models and dispatcher reconciler implementation."""

from typing import Any
from uuid import UUID

import structlog
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, ConfigDict, Field

from rag_core.jobs.models import JobEnvelope, JobOperation
from rag_core.jobs.ports import JobQueue

logger = structlog.get_logger(__name__)


class OutboxEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    event_id: UUID
    job_id: UUID
    operation: JobOperation
    payload: dict[str, Any]
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(gt=0)


class OutboxDispatcher:
    """Dispatches pending outbox events to transient broker infrastructure (Redis/Dramatiq)."""

    def __init__(
        self,
        pool: AsyncConnectionPool,
        queue: JobQueue,
        *,
        worker_id: str = "outbox-dispatcher",
    ) -> None:
        self._pool = pool
        self._queue = queue
        self._worker_id = worker_id

    async def claim_pending(self, limit: int = 10) -> list[OutboxEvent]:
        """Claim pending or stale outbox events using FOR UPDATE SKIP LOCKED."""
        claim_sql = """
            with candidate as (
              select id
              from private.job_dispatch_outbox
              where dispatched_at is null
                and available_at <= now()
                and (claimed_at is null or claimed_at < now() - interval '60 seconds')
              order by id
              limit %(limit)s
              for update skip locked
            )
            update private.job_dispatch_outbox o
            set claimed_at = now(),
                claimed_by = %(worker_id)s,
                attempt_count = attempt_count + 1,
                updated_at = now()
            from candidate
            where o.id = candidate.id
            returning
              o.id,
              o.event_id,
              o.job_id,
              o.operation,
              o.payload,
              o.attempt_count,
              o.max_attempts;
        """
        async with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(claim_sql, {"limit": limit, "worker_id": self._worker_id})
            rows = await cursor.fetchall()
            return [
                OutboxEvent(
                    id=row["id"],
                    event_id=row["event_id"],
                    job_id=row["job_id"],
                    operation=JobOperation(row["operation"]),
                    payload=row["payload"],
                    attempt_count=row["attempt_count"],
                    max_attempts=row["max_attempts"],
                )
                for row in rows
            ]

    async def mark_dispatched(self, event_id: UUID, transport_message_id: str) -> None:
        """Mark outbox row as successfully delivered to the broker."""
        sql = """
            update private.job_dispatch_outbox
            set dispatched_at = now(),
                transport_message_id = %(transport_message_id)s,
                updated_at = now()
            where event_id = %(event_id)s;
        """
        async with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(
                sql,
                {"event_id": event_id, "transport_message_id": transport_message_id},
            )

    async def mark_failed(
        self,
        event_id: UUID,
        error: str,
        retry_delay_seconds: int = 10,
    ) -> None:
        """Release claim and schedule retry with backoff on dispatch failure."""
        sql = """
            update private.job_dispatch_outbox
            set last_error = %(error)s,
                available_at = now() + (%(delay)s * interval '1 second'),
                claimed_at = null,
                claimed_by = null,
                updated_at = now()
            where event_id = %(event_id)s;
        """
        async with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(
                sql,
                {
                    "event_id": event_id,
                    "error": error[:500],
                    "delay": retry_delay_seconds,
                },
            )

    async def dispatch_next_batch(self, limit: int = 10) -> int:
        """Claim a batch of pending events and dispatch each through the JobQueue port."""
        events = await self.claim_pending(limit=limit)
        if not events:
            return 0

        dispatched_count = 0
        for event in events:
            try:
                idempotency_key = str(
                    event.payload.get("idempotency_key", f"outbox-{event.event_id}")
                )
                envelope = JobEnvelope(
                    job_id=event.job_id,
                    operation=event.operation,
                    idempotency_key=idempotency_key,
                )
                receipt = await self._queue.enqueue(envelope)
                await self.mark_dispatched(event.event_id, receipt.transport_message_id)
                dispatched_count += 1
                logger.info(
                    "outbox_event_dispatched",
                    event_id=str(event.event_id),
                    job_id=str(event.job_id),
                    transport_message_id=receipt.transport_message_id,
                )
            except Exception as exc:
                logger.error(
                    "outbox_event_dispatch_failed",
                    event_id=str(event.event_id),
                    job_id=str(event.job_id),
                    error=str(exc),
                )
                await self.mark_failed(event.event_id, str(exc))

        return dispatched_count

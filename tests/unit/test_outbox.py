"""Unit tests for the Transactional Outbox Dispatcher."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from rag_core.jobs.models import DispatchReceipt, JobOperation
from rag_core.jobs.outbox import OutboxDispatcher, OutboxEvent
from rag_core.jobs.ports import JobQueue


def _create_mock_pool(mock_cursor: MagicMock) -> MagicMock:
    """Helper to mock AsyncConnectionPool context managers."""
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_conn.cursor = MagicMock()
    mock_conn.cursor.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_pool


@pytest.mark.asyncio
async def test_claim_pending_fetches_and_parses_events() -> None:
    mock_cursor = MagicMock()
    event_id = uuid4()
    job_id = uuid4()

    mock_cursor.execute = AsyncMock()
    mock_cursor.fetchall = AsyncMock(
        return_value=[
            {
                "id": 1,
                "event_id": event_id,
                "job_id": job_id,
                "operation": "document_ingestion",
                "payload": {"version_id": str(uuid4())},
                "attempt_count": 1,
                "max_attempts": 5,
            }
        ]
    )

    mock_pool = _create_mock_pool(mock_cursor)
    mock_queue = AsyncMock(spec=JobQueue)
    dispatcher = OutboxDispatcher(pool=mock_pool, queue=mock_queue)

    events = await dispatcher.claim_pending(limit=5)

    assert len(events) == 1
    event = events[0]
    assert event.id == 1
    assert event.event_id == event_id
    assert event.job_id == job_id
    assert event.operation == JobOperation.DOCUMENT_INGESTION
    assert event.attempt_count == 1
    assert event.max_attempts == 5

    mock_cursor.execute.assert_awaited_once()
    assert "for update skip locked" in mock_cursor.execute.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_mark_dispatched_executes_update() -> None:
    mock_cursor = MagicMock()
    mock_cursor.execute = AsyncMock()
    mock_pool = _create_mock_pool(mock_cursor)
    mock_queue = AsyncMock(spec=JobQueue)
    dispatcher = OutboxDispatcher(pool=mock_pool, queue=mock_queue)

    event_id = uuid4()
    await dispatcher.mark_dispatched(event_id, transport_message_id="msg-1234")

    mock_cursor.execute.assert_awaited_once()
    call_args = mock_cursor.execute.call_args
    assert "dispatched_at = now()" in call_args[0][0].lower()
    assert call_args[0][1]["event_id"] == event_id
    assert call_args[0][1]["transport_message_id"] == "msg-1234"


@pytest.mark.asyncio
async def test_mark_failed_reschedules_with_backoff() -> None:
    mock_cursor = MagicMock()
    mock_cursor.execute = AsyncMock()
    mock_pool = _create_mock_pool(mock_cursor)
    mock_queue = AsyncMock(spec=JobQueue)
    dispatcher = OutboxDispatcher(pool=mock_pool, queue=mock_queue)

    event_id = uuid4()
    await dispatcher.mark_failed(event_id, error="Broker unreachable", retry_delay_seconds=30)

    mock_cursor.execute.assert_awaited_once()
    call_args = mock_cursor.execute.call_args
    assert "claimed_at = null" in call_args[0][0].lower()
    assert call_args[0][1]["event_id"] == event_id
    assert call_args[0][1]["error"] == "Broker unreachable"
    assert call_args[0][1]["delay"] == 30


@pytest.mark.asyncio
async def test_dispatch_next_batch_success() -> None:
    mock_cursor = MagicMock()
    mock_cursor.execute = AsyncMock()
    mock_pool = _create_mock_pool(mock_cursor)
    mock_queue = AsyncMock(spec=JobQueue)

    mock_queue.enqueue.return_value = DispatchReceipt(
        job_id=uuid4(),
        queue_name="default",
        transport_message_id="trans-xyz",
    )

    dispatcher = OutboxDispatcher(pool=mock_pool, queue=mock_queue)

    e1 = OutboxEvent(
        id=1,
        event_id=uuid4(),
        job_id=uuid4(),
        operation=JobOperation.DOCUMENT_INGESTION,
        payload={"idempotency_key": "idempotency-key-1"},
        attempt_count=1,
        max_attempts=3,
    )
    e2 = OutboxEvent(
        id=2,
        event_id=uuid4(),
        job_id=uuid4(),
        operation=JobOperation.DOCUMENT_INGESTION,
        payload={},
        attempt_count=1,
        max_attempts=3,
    )

    dispatcher.claim_pending = AsyncMock(return_value=[e1, e2])  # type: ignore[method-assign]
    dispatcher.mark_dispatched = AsyncMock()  # type: ignore[method-assign]
    dispatcher.mark_failed = AsyncMock()  # type: ignore[method-assign]

    dispatched = await dispatcher.dispatch_next_batch(limit=10)

    assert dispatched == 2
    assert mock_queue.enqueue.await_count == 2
    assert dispatcher.mark_dispatched.await_count == 2
    dispatcher.mark_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_next_batch_handles_broker_error() -> None:
    mock_pool = MagicMock()
    mock_queue = AsyncMock(spec=JobQueue)
    mock_queue.enqueue.side_effect = ConnectionError("Redis is down")

    dispatcher = OutboxDispatcher(pool=mock_pool, queue=mock_queue)

    event = OutboxEvent(
        id=1,
        event_id=uuid4(),
        job_id=uuid4(),
        operation=JobOperation.DOCUMENT_INGESTION,
        payload={},
        attempt_count=1,
        max_attempts=3,
    )

    dispatcher.claim_pending = AsyncMock(return_value=[event])  # type: ignore[method-assign]
    dispatcher.mark_dispatched = AsyncMock()  # type: ignore[method-assign]
    dispatcher.mark_failed = AsyncMock()  # type: ignore[method-assign]

    dispatched = await dispatcher.dispatch_next_batch(limit=10)

    assert dispatched == 0
    mock_queue.enqueue.assert_awaited_once()
    dispatcher.mark_dispatched.assert_not_awaited()
    dispatcher.mark_failed.assert_awaited_once_with(event.event_id, "Redis is down")


@pytest.mark.asyncio
async def test_dispatch_next_batch_empty() -> None:
    mock_pool = MagicMock()
    mock_queue = AsyncMock(spec=JobQueue)
    dispatcher = OutboxDispatcher(pool=mock_pool, queue=mock_queue)
    dispatcher.claim_pending = AsyncMock(return_value=[])  # type: ignore[method-assign]

    dispatched = await dispatcher.dispatch_next_batch()

    assert dispatched == 0
    mock_queue.enqueue.assert_not_awaited()

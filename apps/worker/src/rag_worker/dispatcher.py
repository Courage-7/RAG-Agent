"""Transactional outbox poller and dispatcher runner for background jobs."""

import sys

import anyio
import structlog
from rag_core.config import get_settings
from rag_core.database.connection import create_async_pool
from rag_core.jobs.models import JobOperation
from rag_core.jobs.outbox import OutboxDispatcher

from rag_worker.app import document_ingestion
from rag_worker.infrastructure.dramatiq_queue import DramatiqJobQueue

logger = structlog.get_logger(__name__)


async def run_dispatcher(
    poll_interval_seconds: float = 2.0,
    batch_size: int = 20,
    max_loops: int | None = None,
) -> None:
    """Continuously poll pending outbox events and dispatch to Dramatiq/Redis."""
    settings = get_settings()
    pool = create_async_pool(settings.database_url)
    queue = DramatiqJobQueue({JobOperation.DOCUMENT_INGESTION: document_ingestion})
    dispatcher = OutboxDispatcher(pool=pool, queue=queue)

    logger.info("outbox_dispatcher_started", interval=poll_interval_seconds, batch_size=batch_size)

    loops = 0
    async with pool:
        while max_loops is None or loops < max_loops:
            try:
                dispatched = await dispatcher.dispatch_next_batch(limit=batch_size)
                if dispatched > 0:
                    logger.info("dispatched_outbox_batch", count=dispatched)
                    if dispatched >= batch_size:
                        continue
            except Exception as exc:
                logger.error("outbox_dispatcher_loop_error", error=str(exc))

            loops += 1
            await anyio.sleep(poll_interval_seconds)


def main() -> None:
    """CLI entrypoint for running the outbox dispatcher process."""
    try:
        anyio.run(run_dispatcher)
    except (KeyboardInterrupt, SystemExit):
        logger.info("outbox_dispatcher_stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()

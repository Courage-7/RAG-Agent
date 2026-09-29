from unittest.mock import AsyncMock, patch

import pytest
from rag_worker.dispatcher import run_dispatcher


@pytest.mark.asyncio
async def test_run_dispatcher_executes_configured_loops() -> None:
    mock_pool = AsyncMock()
    mock_pool.__aenter__ = AsyncMock(return_value=mock_pool)
    mock_pool.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("rag_worker.dispatcher.create_async_pool", return_value=mock_pool),
        patch("rag_worker.dispatcher.OutboxDispatcher") as mock_dispatcher_cls,
    ):
        mock_dispatcher = AsyncMock()
        mock_dispatcher.dispatch_next_batch = AsyncMock(return_value=2)
        mock_dispatcher_cls.return_value = mock_dispatcher

        await run_dispatcher(poll_interval_seconds=0.001, batch_size=10, max_loops=2)

        assert mock_dispatcher.dispatch_next_batch.await_count == 2

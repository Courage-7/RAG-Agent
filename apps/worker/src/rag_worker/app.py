"""Dramatiq worker entrypoint.

Run with: ``uv run --package rag-worker dramatiq rag_worker.app``.
"""

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from rag_core.config import get_settings

settings = get_settings()
broker = RedisBroker(url=settings.redis_broker_url, namespace="rag-agent")
dramatiq.set_broker(broker)

# Actor modules must be imported after the broker is configured.
from rag_worker.tasks.demo import demo_job  # noqa: E402

__all__ = ["broker", "demo_job"]

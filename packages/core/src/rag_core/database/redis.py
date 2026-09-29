import contextlib

import anyio
import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)


async def check_redis_health(redis_url: str, *, timeout_seconds: float = 1.0) -> bool:
    """Actively ping Redis with a strict timeout to verify broker readiness."""
    if not redis_url:
        return False
    client: aioredis.Redis | None = None
    try:
        with anyio.fail_after(timeout_seconds):
            client = aioredis.from_url(
                redis_url,
                socket_connect_timeout=timeout_seconds,
                socket_timeout=timeout_seconds,
            )
            pong = await client.ping()
            return bool(pong)
    except Exception as exc:
        logger.warning("redis_health_check_failed", error=str(exc))
        return False
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()

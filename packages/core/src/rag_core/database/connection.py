from typing import Any

import anyio
import psycopg
import structlog
from pgvector.psycopg import register_vector_async
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger(__name__)


async def configure_connection(conn: AsyncConnection[Any]) -> None:
    """Register extension adapters such as pgvector on new connections."""
    try:
        await register_vector_async(conn)
    except psycopg.ProgrammingError:
        # pgvector extension might not be installed in current database schema yet
        logger.debug("pgvector extension not present during connection configure")


def create_async_pool(
    database_url: str,
    *,
    min_size: int = 1,
    max_size: int = 10,
    timeout: float = 30.0,
) -> AsyncConnectionPool:
    """Create an asynchronous connection pool with dictionary rows and pgvector support."""
    return AsyncConnectionPool(
        conninfo=database_url,
        min_size=min_size,
        max_size=max_size,
        timeout=timeout,
        configure=configure_connection,
        kwargs={"row_factory": dict_row},
        open=False,
    )


async def check_database_health(database_url: str, *, timeout_seconds: float = 1.0) -> bool:
    """Actively execute SELECT 1 with a strict timeout to verify database readiness."""
    if not database_url:
        return False
    try:
        with anyio.fail_after(timeout_seconds):
            async with await AsyncConnection.connect(
                conninfo=database_url,
                connect_timeout=max(int(timeout_seconds), 1),
            ) as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT 1")
                    row = await cursor.fetchone()
                    return row is not None and row[0] == 1
    except Exception as exc:
        logger.warning("database_health_check_failed", error=str(exc))
        return False

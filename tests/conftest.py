"""Pytest global fixtures for real local infrastructure testing."""

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from rag_core.config import AppSettings, get_settings
from rag_core.database.connection import create_async_pool

# Ensure psycopg async functions properly on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "live: marks tests requiring live external services (e.g. Groq)"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests requiring real local services (Postgres, Redis)"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    has_groq = bool(os.getenv("GROQ_API_KEY") or os.getenv("RAG_GROQ_API_KEY"))
    skip_live = pytest.mark.skip(
        reason="GROQ_API_KEY is not set. Set GROQ_API_KEY in .env to run live tests."
    )
    for item in items:
        if "live" in item.keywords and not has_groq:
            item.add_marker(skip_live)


@pytest.fixture(scope="session")
def settings() -> AppSettings:
    return get_settings()


@pytest.fixture
async def real_db_pool(settings: AppSettings) -> AsyncIterator[AsyncConnectionPool]:
    """Provide an open AsyncConnectionPool connected to the real local PostgreSQL instance."""
    pool = create_async_pool(settings.database_url, min_size=1, max_size=5)
    await pool.open()
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
async def test_workspace(
    real_db_pool: AsyncConnectionPool,
) -> AsyncIterator[tuple[UUID, UUID]]:
    """Create an isolated test workspace and knowledge base in PostgreSQL and clean up after."""
    workspace_id = uuid4()
    kb_id = uuid4()
    workspace_slug = f"test-ws-{workspace_id.hex[:8]}"

    async with real_db_pool.connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(
            """
            insert into public.workspaces (id, name, slug)
            values (%(id)s, %(name)s, %(slug)s);
            """,
            {"id": workspace_id, "name": "Test Workspace", "slug": workspace_slug},
        )
        await cursor.execute(
            """
            insert into public.knowledge_bases (id, workspace_id, name, description)
            values (%(id)s, %(ws_id)s, 'Test KB', 'Temporary test knowledge base');
            """,
            {"id": kb_id, "ws_id": workspace_id},
        )

    try:
        yield workspace_id, kb_id
    finally:
        async with real_db_pool.connection() as conn, conn.cursor() as cursor:
            await cursor.execute(
                "delete from public.workspaces where id = %(id)s;",
                {"id": workspace_id},
            )

import time
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import jwt
import pytest
from pydantic import SecretStr
from rag_api.main import create_app
from rag_core.config import AppSettings
from rag_core.retrieval.models import AnswerStatus, Citation, GroundedAnswer
from rag_core.retrieval.service import RagService

JWT_SECRET = "super-secret-jwt-token-with-at-least-32-characters-long"


def create_token(user_id: str, workspace_ids: list[str], role: str = "authenticated") -> str:
    return jwt.encode(
        {
            "sub": user_id,
            "email": "user@example.com",
            "role": role,
            "aud": "authenticated",
            "exp": time.time() + 3600,
            "app_metadata": {"workspace_ids": workspace_ids},
        },
        JWT_SECRET,
        algorithm="HS256",
    )


@pytest.mark.asyncio
async def test_endpoint_rejects_missing_token_when_auth_enforced() -> None:
    settings = AppSettings(
        _env_file=None,  # type: ignore[call-arg]
        auth_enabled=True,
        supabase_jwt_secret=SecretStr(JWT_SECRET),
    )
    app = create_app(settings)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/query",
            json={
                "query": "Test query",
                "workspace_id": str(uuid4()),
                "user_id": str(uuid4()),
                "knowledge_base_ids": [str(uuid4())],
            },
        )

    assert res.status_code == 401
    assert "Missing or invalid authentication token" in res.json()["detail"]


@pytest.mark.asyncio
async def test_endpoint_rejects_invalid_token() -> None:
    settings = AppSettings(
        _env_file=None,  # type: ignore[call-arg]
        auth_enabled=True,
        supabase_jwt_secret=SecretStr(JWT_SECRET),
    )
    app = create_app(settings)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/query",
            headers={"Authorization": "Bearer bad.token.here"},
            json={
                "query": "Test query",
                "workspace_id": str(uuid4()),
                "user_id": str(uuid4()),
                "knowledge_base_ids": [str(uuid4())],
            },
        )

    assert res.status_code == 401
    assert "Invalid authentication token" in res.json()["detail"]


@pytest.mark.asyncio
async def test_endpoint_blocks_workspace_mismatch() -> None:
    settings = AppSettings(
        _env_file=None,  # type: ignore[call-arg]
        auth_enabled=True,
        supabase_jwt_secret=SecretStr(JWT_SECRET),
    )
    app = create_app(settings)

    user_ws = str(uuid4())
    other_ws = str(uuid4())
    token = create_token(str(uuid4()), [user_ws])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/query",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": "Test query",
                "workspace_id": other_ws,
                "user_id": str(uuid4()),
                "knowledge_base_ids": [str(uuid4())],
            },
        )

    assert res.status_code == 403
    assert "not a member of workspace" in res.json()["detail"]


@pytest.mark.asyncio
async def test_endpoint_allows_matching_workspace() -> None:
    mock_service = AsyncMock(spec=RagService)
    doc_id = uuid4()
    mock_service.answer_query.return_value = GroundedAnswer(
        status=AnswerStatus.ANSWERED,
        text="Authorized response",
        citations=(
            Citation(ordinal=1, chunk_id=uuid4(), document_id=doc_id, source_label="Doc 1"),
        ),
        confidence=1.0,
    )

    settings = AppSettings(
        _env_file=None,  # type: ignore[call-arg]
        auth_enabled=True,
        supabase_jwt_secret=SecretStr(JWT_SECRET),
    )
    app = create_app(settings, rag_service=mock_service)

    user_id = str(uuid4())
    ws_id = str(uuid4())
    token = create_token(user_id, [ws_id])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/query",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": "Test query",
                "workspace_id": ws_id,
                "user_id": user_id,
                "knowledge_base_ids": [str(uuid4())],
            },
        )

    assert res.status_code == 200
    assert res.json()["text"] == "Authorized response"


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file() -> None:
    mock_pool = AsyncMock()
    app = create_app(
        AppSettings(_env_file=None, database_url="postgresql://user:pass@localhost:5432/db"),  # type: ignore[call-arg]
        pool=mock_pool,
    )

    ws_id = str(uuid4())
    kb_id = str(uuid4())
    # Create 21MB content (exceeds 20MB limit)
    oversized = b"A" * (21 * 1024 * 1024)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/documents/upload",
            data={"workspace_id": ws_id, "knowledge_base_id": kb_id},
            files={"file": ("large.txt", oversized, "text/plain")},
        )

    assert res.status_code == 413
    assert "exceeds maximum allowed size" in res.json()["detail"]

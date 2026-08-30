import httpx
import pytest
from pydantic import SecretStr
from rag_api.main import create_app
from rag_core.config import AppSettings


async def request(app: object, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_liveness_is_independent_of_external_services() -> None:
    settings = AppSettings(
        _env_file=None,  # type: ignore[call-arg]  # Pydantic Settings runtime option.
        groq_api_key=None,
    )

    response = await request(create_app(settings), "/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_reports_missing_required_configuration() -> None:
    settings = AppSettings(
        _env_file=None,  # type: ignore[call-arg]  # Pydantic Settings runtime option.
        groq_api_key=None,
    )

    response = await request(create_app(settings), "/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["groq_configured"] is False


@pytest.mark.asyncio
async def test_readiness_accepts_complete_foundation_configuration() -> None:
    settings = AppSettings(
        _env_file=None,  # type: ignore[call-arg]  # Pydantic Settings runtime option.
        groq_api_key=SecretStr("test-key"),
    )

    response = await request(create_app(settings), "/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from pydantic import BaseModel, ConfigDict, SecretStr
from rag_core.errors import ModelConfigurationError, ModelProviderError
from rag_core.models.contracts import ChatMessage, ModelRequest
from rag_core.models.groq import GroqChatModelProvider
from rag_core.models.profiles import default_groq_profiles


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: str
    reason: str


class FakeStructuredModel:
    async def ainvoke(self, _: Any) -> dict[str, str]:
        return {"route": "rag", "reason": "The query asks about internal documents."}


class InvalidStructuredModel:
    async def ainvoke(self, _: Any) -> dict[str, str]:
        return {"unexpected": "shape"}


class FakeChatModel:
    def __init__(self) -> None:
        self.structured_arguments: dict[str, Any] | None = None

    async def ainvoke(self, _: Any) -> AIMessage:
        return AIMessage(
            content="Grounded answer",
            usage_metadata={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
            response_metadata={
                "finish_reason": "stop",
                "model_name": "openai/gpt-oss-120b",
                "x_groq": {"id": "req_test"},
            },
        )

    async def astream(self, _: Any) -> AsyncIterator[AIMessageChunk]:
        yield AIMessageChunk(content="Grounded ")
        yield AIMessageChunk(content="answer", response_metadata={"finish_reason": "stop"})

    def with_structured_output(self, _: Any, /, **kwargs: Any) -> Any:
        self.structured_arguments = kwargs
        return FakeStructuredModel()


class RateLimitFailure(Exception):
    status_code = 429


class RateLimitedChatModel(FakeChatModel):
    async def ainvoke(self, _: Any) -> AIMessage:
        raise RateLimitFailure("rate limit reached")


class InvalidStructuredChatModel(FakeChatModel):
    def with_structured_output(self, _: Any, /, **kwargs: Any) -> Any:
        self.structured_arguments = kwargs
        return InvalidStructuredModel()


def make_request(alias: str) -> ModelRequest:
    return ModelRequest(
        profile_alias=alias,
        messages=(ChatMessage(role="user", content="Where is the evidence?"),),
    )


def make_provider(fake_model: FakeChatModel) -> GroqChatModelProvider:
    profiles = default_groq_profiles(
        fast_model="openai/gpt-oss-20b",
        quality_model="openai/gpt-oss-120b",
        agent_model="openai/gpt-oss-120b",
    )
    return GroqChatModelProvider(
        api_key=SecretStr("test-key"),
        profiles=profiles,
        model_factory=lambda _profile, _api_key: fake_model,
    )


@pytest.mark.asyncio
async def test_complete_normalizes_groq_metadata() -> None:
    provider = make_provider(FakeChatModel())

    result = await provider.complete(make_request("quality"))

    assert result.text == "Grounded answer"
    assert result.provider_request_id == "req_test"
    assert result.usage.total_tokens == 15


@pytest.mark.asyncio
async def test_structured_completion_requires_strict_json_schema() -> None:
    fake_model = FakeChatModel()
    provider = make_provider(fake_model)

    result = await provider.complete_structured(
        make_request("fast_structured"),
        RouteDecision,
    )

    assert result.route == "rag"
    assert fake_model.structured_arguments == {"method": "json_schema", "strict": True}


@pytest.mark.asyncio
async def test_stream_yields_normalized_chunks() -> None:
    provider = make_provider(FakeChatModel())

    chunks = [chunk async for chunk in provider.stream(make_request("quality"))]

    assert "".join(chunk.text for chunk in chunks) == "Grounded answer"
    assert chunks[-1].finish_reason == "stop"


def test_provider_rejects_missing_api_key() -> None:
    with pytest.raises(ModelConfigurationError, match="GROQ_API_KEY"):
        GroqChatModelProvider(api_key=None, profiles={})


@pytest.mark.asyncio
async def test_rate_limit_is_exposed_as_retryable_provider_error() -> None:
    provider = make_provider(RateLimitedChatModel())

    with pytest.raises(ModelProviderError) as error:
        await provider.complete(make_request("quality"))

    assert error.value.retryable is True


@pytest.mark.asyncio
async def test_malformed_structured_output_is_a_typed_provider_error() -> None:
    provider = make_provider(InvalidStructuredChatModel())

    with pytest.raises(ModelProviderError) as error:
        await provider.complete_structured(make_request("fast_structured"), RouteDecision)

    assert error.value.retryable is False

"""Groq implementation of the provider-neutral chat model port."""

from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any, Protocol, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, SecretStr

from rag_core.errors import ModelConfigurationError, ModelProviderError
from rag_core.models.contracts import (
    ChatMessage,
    ModelRequest,
    ModelResponse,
    ModelStreamChunk,
    ModelUsage,
    SchemaT,
)
from rag_core.models.profiles import ModelProfile


class ChatModelRuntime(Protocol):
    async def ainvoke(self, input: Any, /) -> Any: ...

    def astream(self, input: Any, /) -> AsyncIterator[Any]: ...

    def with_structured_output(self, schema: Any, /, **kwargs: Any) -> Any: ...


ModelFactory = Callable[[ModelProfile, SecretStr], ChatModelRuntime]


def _default_model_factory(profile: ModelProfile, api_key: SecretStr) -> ChatModelRuntime:
    return cast(
        ChatModelRuntime,
        ChatGroq(
            api_key=api_key,
            model=profile.model,
            temperature=profile.temperature,
            max_tokens=profile.max_tokens,
            timeout=profile.timeout_seconds,
            max_retries=profile.max_retries,
        ),
    )


def _to_langchain_message(message: ChatMessage) -> BaseMessage:
    if message.role == "system":
        return SystemMessage(content=message.content)
    if message.role == "user":
        return HumanMessage(content=message.content)
    if message.role == "assistant":
        return AIMessage(content=message.content)
    if not message.tool_call_id:
        raise ModelConfigurationError("Tool messages require a tool_call_id")
    return ToolMessage(content=message.content, tool_call_id=message.tool_call_id)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return str(content) if content is not None else ""


def _usage_from_message(message: Any) -> ModelUsage:
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict):
        return ModelUsage(
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            total_tokens=int(usage.get("total_tokens", 0)),
        )

    metadata = getattr(message, "response_metadata", {})
    token_usage = metadata.get("token_usage", {}) if isinstance(metadata, dict) else {}
    return ModelUsage(
        input_tokens=int(token_usage.get("prompt_tokens", 0)),
        output_tokens=int(token_usage.get("completion_tokens", 0)),
        total_tokens=int(token_usage.get("total_tokens", 0)),
    )


def _is_retryable(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code in {408, 409, 425, 429} or status_code >= 500
    error_name = type(exc).__name__.lower()
    return "timeout" in error_name or "connection" in error_name


class GroqChatModelProvider:
    def __init__(
        self,
        *,
        api_key: SecretStr | None,
        profiles: Mapping[str, ModelProfile],
        model_factory: ModelFactory = _default_model_factory,
    ) -> None:
        if api_key is None or not api_key.get_secret_value():
            raise ModelConfigurationError("GROQ_API_KEY is required for Groq inference")
        self._api_key = api_key
        self._profiles = dict(profiles)
        self._model_factory = model_factory
        self._models: dict[str, ChatModelRuntime] = {}

    def _profile(self, alias: str) -> ModelProfile:
        profile = self._profiles.get(alias)
        if profile is None:
            raise ModelConfigurationError(f"Unknown model profile: {alias}")
        if profile.provider != "groq":
            raise ModelConfigurationError(f"Profile {alias} is not configured for Groq")
        return profile

    def _model(self, profile: ModelProfile) -> ChatModelRuntime:
        cached = self._models.get(profile.alias.value)
        if cached is None:
            cached = self._model_factory(profile, self._api_key)
            self._models[profile.alias.value] = cached
        return cached

    @staticmethod
    def _messages(request: ModelRequest) -> list[BaseMessage]:
        return [_to_langchain_message(message) for message in request.messages]

    async def complete(self, request: ModelRequest) -> ModelResponse:
        profile = self._profile(request.profile_alias)
        try:
            message = await self._model(profile).ainvoke(self._messages(request))
        except Exception as exc:
            raise ModelProviderError(
                "Groq inference failed",
                retryable=_is_retryable(exc),
            ) from exc

        metadata = message.response_metadata if isinstance(message.response_metadata, dict) else {}
        groq_metadata = metadata.get("x_groq", {})
        request_id = groq_metadata.get("id") if isinstance(groq_metadata, dict) else None
        return ModelResponse(
            text=_content_text(message.content),
            model=str(metadata.get("model_name", profile.model)),
            finish_reason=metadata.get("finish_reason"),
            provider_request_id=request_id if isinstance(request_id, str) else None,
            usage=_usage_from_message(message),
        )

    async def complete_structured(
        self,
        request: ModelRequest,
        schema: type[SchemaT],
    ) -> SchemaT:
        profile = self._profile(request.profile_alias)
        if not profile.supports_strict_structured_output:
            raise ModelConfigurationError(
                f"Profile {profile.alias.value} does not allow strict structured output"
            )

        structured_model = self._model(profile).with_structured_output(
            schema,
            method="json_schema",
            strict=True,
        )
        try:
            result = await structured_model.ainvoke(self._messages(request))
            return result if isinstance(result, schema) else schema.model_validate(result)
        except Exception as exc:
            raise ModelProviderError(
                "Groq structured inference failed",
                retryable=_is_retryable(exc),
            ) from exc

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamChunk]:
        profile = self._profile(request.profile_alias)
        if not profile.supports_streaming:
            raise ModelConfigurationError(f"Profile {profile.alias.value} does not allow streaming")
        try:
            async for chunk in self._model(profile).astream(self._messages(request)):
                metadata = (
                    chunk.response_metadata if isinstance(chunk.response_metadata, dict) else {}
                )
                yield ModelStreamChunk(
                    text=_content_text(chunk.content),
                    finish_reason=metadata.get("finish_reason"),
                    usage=_usage_from_message(chunk),
                )
        except Exception as exc:
            raise ModelProviderError(
                "Groq streaming inference failed",
                retryable=_is_retryable(exc),
            ) from exc

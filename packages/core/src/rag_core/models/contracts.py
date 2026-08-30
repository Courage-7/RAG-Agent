"""Provider-neutral chat model request and response contracts."""

from collections.abc import AsyncIterator
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1)
    tool_call_id: str | None = None


class ModelRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_alias: str = Field(min_length=1, max_length=100)
    messages: tuple[ChatMessage, ...] = Field(min_length=1)


class ModelUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ModelResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    model: str
    finish_reason: str | None = None
    provider_request_id: str | None = None
    usage: ModelUsage = Field(default_factory=ModelUsage)


class ModelStreamChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = ""
    finish_reason: str | None = None
    usage: ModelUsage | None = None


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class ChatModelPort(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse: ...

    async def complete_structured(
        self,
        request: ModelRequest,
        schema: type[SchemaT],
    ) -> SchemaT: ...

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamChunk]: ...


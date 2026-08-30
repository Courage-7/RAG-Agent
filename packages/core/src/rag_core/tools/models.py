"""Security boundaries for Composio and other connected tools."""

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class ToolEffect(StrEnum):
    READ_ONLY = "read_only"
    SIDE_EFFECT = "side_effect"


def tool_arguments_digest(arguments: dict[str, JsonValue]) -> str:
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class ToolCallIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    invocation_id: UUID
    workspace_id: UUID
    user_id: UUID
    connector: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=200)
    effect: ToolEffect
    arguments: dict[str, JsonValue]
    idempotency_key: str = Field(min_length=8, max_length=200)

    @property
    def arguments_sha256(self) -> str:
        return tool_arguments_digest(self.arguments)


class ApprovalGrant(BaseModel):
    model_config = ConfigDict(frozen=True)

    approval_id: UUID
    invocation_id: UUID
    workspace_id: UUID
    user_id: UUID
    arguments_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        return value

    def authorizes(self, intent: ToolCallIntent, *, at: datetime) -> bool:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("authorization time must be timezone-aware")
        return (
            intent.effect is ToolEffect.SIDE_EFFECT
            and self.expires_at > at
            and self.invocation_id == intent.invocation_id
            and self.workspace_id == intent.workspace_id
            and self.user_id == intent.user_id
            and self.arguments_sha256 == intent.arguments_sha256
        )


class ToolPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_tool_calls: int = Field(default=6, ge=0, le=50)
    max_steps: int = Field(default=10, ge=1, le=100)
    max_elapsed_seconds: int = Field(default=120, ge=1, le=900)
    require_write_approval: bool = True

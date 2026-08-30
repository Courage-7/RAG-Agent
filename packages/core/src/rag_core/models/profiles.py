"""Capability-aware LLM profiles selected by purpose rather than vendor string."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelPurpose(StrEnum):
    FAST_STRUCTURED = "fast_structured"
    QUALITY = "quality"
    AGENT = "agent"


class ModelProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    alias: ModelPurpose
    provider: Literal["groq"] = "groq"
    model: str = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    max_tokens: int = Field(gt=0)
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=300.0)
    max_retries: int = Field(default=2, ge=0, le=5)
    supports_streaming: bool = True
    supports_tool_calling: bool = False
    supports_strict_structured_output: bool = False


def default_groq_profiles(
    *,
    fast_model: str,
    quality_model: str,
    agent_model: str,
) -> dict[str, ModelProfile]:
    profiles = (
        ModelProfile(
            alias=ModelPurpose.FAST_STRUCTURED,
            model=fast_model,
            max_tokens=2_048,
            supports_strict_structured_output=True,
        ),
        ModelProfile(
            alias=ModelPurpose.QUALITY,
            model=quality_model,
            max_tokens=8_192,
        ),
        ModelProfile(
            alias=ModelPurpose.AGENT,
            model=agent_model,
            max_tokens=4_096,
            supports_tool_calling=True,
        ),
    )
    return {profile.alias.value: profile for profile in profiles}


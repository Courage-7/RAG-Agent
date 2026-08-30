"""Typed environment configuration shared by API and worker processes."""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from rag_core.models.profiles import ModelProfile, default_groq_profiles


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="RAG_",
        extra="ignore",
    )

    service_name: str = "rag-api"
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    json_logs: bool = False

    groq_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GROQ_API_KEY", "RAG_GROQ_API_KEY"),
    )
    groq_fast_model: str = "openai/gpt-oss-20b"
    groq_quality_model: str = "openai/gpt-oss-120b"
    groq_agent_model: str = "openai/gpt-oss-120b"

    redis_broker_url: str = "redis://127.0.0.1:6379/0"
    database_url: str = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    supabase_url: str = "http://127.0.0.1:54321"
    supabase_publishable_key: SecretStr | None = None

    def model_profiles(self) -> dict[str, ModelProfile]:
        return default_groq_profiles(
            fast_model=self.groq_fast_model,
            quality_model=self.groq_quality_model,
            agent_model=self.groq_agent_model,
        )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()

"""User identity, credentials, and tenant authorization models."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    email: str = Field(min_length=3)
    roles: tuple[str, ...] = ("authenticated",)
    workspace_ids: tuple[UUID, ...] = ()

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CreateFavoriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str
    source_session_id: Optional[str] = None
    source_id: str
    member_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class PatchFavoriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    tags: Optional[list[str]] = None


class BatchDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    favorite_ids: list[str]

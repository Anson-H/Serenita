from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CreateFavoriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_type: str
    source_session_id: Optional[str] = None
    source_id: str = Field(min_length=1)
    member_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class PatchFavoriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Optional[str] = Field(default=None, min_length=1)
    tags: Optional[list[str]] = None


class BatchDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    favorite_ids: list[str]

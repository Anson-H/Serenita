"""Append commands for fixed episodes, complete revisions and membership."""
from typing import Annotated

from pydantic import AfterValidator, Field

from backend.app.schemas.memory.values import (
    MemoryModel, Text, canonical_uuid,
)

Identifier = Annotated[str, AfterValidator(canonical_uuid)]


class EpisodeInput(MemoryModel):
    episode_id: Identifier
    scope: Text = Field(description="事项范围，说明稳定主体及持续目标、活动范围或状态维度；创建后固定，用于判断事件归属。")


class EpisodeMembershipInput(MemoryModel):
    event_id: Identifier
    episode_id: Identifier
    reason: Text


class EpisodeRevisionInput(MemoryModel):
    episode_id: Identifier
    version: int = Field(ge=1)
    trigger_event_id: Identifier
    summary: Text
    state: Text
    reason: Text


EPISODE_APPEND_FIELDS = {
    "episodes": EpisodeInput, "episode_revisions": EpisodeRevisionInput,
    "episode_memberships": EpisodeMembershipInput,
}


class EpisodeRevisionGenerationInput(MemoryModel):
    """Host-supplied provenance; never included in a model output schema."""
    episode_id: Identifier
    version: int = Field(ge=1)
    attempt_id: Identifier
    request_entry_id: Identifier
    result_entry_id: Identifier
    fixed_input: dict
    draft_scope: Identifier | None = None

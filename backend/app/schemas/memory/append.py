"""Append commands and query parameters for member memory."""
from __future__ import annotations
from backend.app.schemas.memory.evidence import EventEvidenceInput
from typing import Literal
from pydantic import Field, field_validator, model_validator, model_serializer
from backend.app.schemas.memory.values import MemoryModel, Text, SourceCategory, SOURCE_CATEGORIES, ObjectType, OBJECT_TYPES, canonical_uuid, stable_memory_id, local_time_value, TimeBound, MemoryTime, EventTime, memory_time_bounds, occurrence_time_bounds, MemoryReference
from backend.app.schemas.memory.coverage import ReadCoverage














class EventInput(MemoryModel):
    event_id: Text
    title: Text
    summary: Text = Field(description="模型生成的事件摘要，必填且必须有实际文字；保留核心事实及必要限定。")
    content: Text
    category: Text = Field(description="事件分类，必须由提取模型根据内容填写。")
    priority: Literal["HIGH", "MEDIUM", "LOW"] = Field(description="事件重要程度，必须填写高、中或低。")
    occurrence_time: EventTime | None = Field(default=None, description="事件实际发生时间，可省略；没有有据的发生时间时保存 null。")
    _id = field_validator("event_id")(canonical_uuid)







class ProcessingAttemptInput(MemoryModel):
    attempt_id: Text
    source_account_id: str | None = None
    source_database: Text | None = None
    change_id: Text | None = None
    change_sequence: int | None = Field(default=None, ge=1)
    previous_attempt_id: str | None = None
    task_kind: Literal["intake_review", "event_formation", "memory_query", "relation_review", "vector_index"]
    purpose: Text
    input_sequence: int = Field(ge=0)
    target_time: MemoryTime = Field(default_factory=MemoryTime)
    coverage: list[ReadCoverage] = Field(default_factory=list)
    input_references: list[MemoryReference] = Field(default_factory=list)
    _ids = field_validator("attempt_id", "source_account_id", "previous_attempt_id")(lambda v: canonical_uuid(v) if v is not None else None)

    @model_validator(mode="after")
    def delivery_identity(self):
        fields = (self.source_account_id, self.source_database, self.change_id, self.change_sequence)
        if any(value is not None for value in fields) and not all(value is not None for value in fields):
            raise ValueError("交付尝试必须同时提供来源账号、业务库、变化标识与序号。")
        return self


class AttemptUpdateInput(MemoryModel):
    attempt_id: Text
    expected_updated_commit_id: str | None = None
    resume: bool = False
    model_id: Text | None = None
    result_references: list[MemoryReference] = Field(default_factory=list)
    outcome_reason: Text | None = None
    error_code: Text | None = None
    error_message: Text | None = None
    retry_after: str | None = None
    gaps: list[str] = Field(default_factory=list)
    processing_status: Literal["pending", "running", "completed", "failed", "cancelled"]
    _ids = field_validator("attempt_id", "expected_updated_commit_id")(lambda v: canonical_uuid(v) if v is not None else None)
    _retry = field_validator("retry_after")(lambda v: local_time_value(v) if v is not None else None)

    @model_validator(mode="after")
    def genuine_failure(self):
        if self.processing_status == "failed" and (not self.error_code or not self.error_message):
            raise ValueError("计算失败必须提供真实错误。")
        if self.processing_status != "failed" and (self.error_code is not None or self.error_message is not None):
            raise ValueError("非失败状态不能携带失败错误。")
        if self.retry_after is not None and self.processing_status != "failed":
            raise ValueError("只有失败的计算尝试可以登记重试时间。")
        return self


class AccessRestrictionInput(MemoryModel):
    restriction_id: Text
    source_id: str | None = None
    restricted_actor_account_id: str | None = None
    grant_reference: str | None = None
    trigger_resource_type: Text
    trigger_resource_id: Text
    restriction_kind: Literal["source_deleted", "member_deleted", "grant_revoked", "source_access_revoked"]
    reason: Text
    effective_at: Text
    _ids = field_validator("restriction_id", "source_id", "restricted_actor_account_id")(lambda v: canonical_uuid(v) if v is not None else None)
    _time = field_validator("effective_at")(local_time_value)

    @model_validator(mode="after")
    def scope_matches_kind(self):
        if self.restriction_kind in {"source_deleted", "source_access_revoked"} and self.source_id is None:
            raise ValueError("来源限制必须提供来源标识。")
        if self.restriction_kind == "member_deleted" and self.source_id is not None:
            raise ValueError("成员删除限制不指向单一来源。")
        if self.restriction_kind == "grant_revoked" and (self.restricted_actor_account_id is None or not self.grant_reference):
            raise ValueError("授权撤销必须指明账号和授权身份。")
        return self


class MemorySettingInput(MemoryModel):
    setting_id: Text
    previous_setting_id: str | None = None
    embedding_model_id: str | None = None
    source_categories: list[SourceCategory] = Field(default_factory=list)
    reason: Text
    formation_state: Literal["disabled", "enabled", "paused"]
    effective_at: Text
    _ids = field_validator("setting_id", "previous_setting_id")(lambda v: canonical_uuid(v) if v is not None else None)
    _time = field_validator("effective_at")(local_time_value)

    @model_validator(mode="after")
    def valid_categories(self):
        if len(set(self.source_categories)) != len(self.source_categories):
            raise ValueError("来源类别不能重复。")
        if self.formation_state == "enabled" and not self.source_categories:
            raise ValueError("开启记忆形成必须选择来源类别。")
        return self


from backend.app.schemas.memory.index import (EntityInput, EntityNameInput, EventEntityInput, VectorSpaceInput, VectorBindingInput, VectorStatusInput, VectorRequestInput)


from backend.app.schemas.memory.relations import EventRelationInput


from backend.app.schemas.memory.episodes import (EpisodeInput, EpisodeRevisionInput, EpisodeMembershipInput, EpisodeRevisionGenerationInput)


from backend.app.schemas.memory.execution import MemoryExecutionEntryInput, MemoryProcessingStepInput






from backend.app.schemas.memory.chunk_index import ChunkVectorBindingInput, ChunkVectorStatusInput
from backend.app.schemas.memory.semantic_index import SemanticVectorBindingInput, SemanticVectorStatusInput


class MemoryWrite(MemoryModel):
    processing_steps: list[MemoryProcessingStepInput] = Field(default_factory=list)
    chunk_vector_bindings: list[ChunkVectorBindingInput] = Field(default_factory=list)
    chunk_vector_statuses: list[ChunkVectorStatusInput] = Field(default_factory=list)
    semantic_vector_bindings: list[SemanticVectorBindingInput] = Field(default_factory=list)
    semantic_vector_statuses: list[SemanticVectorStatusInput] = Field(default_factory=list)
    execution_entries: list[MemoryExecutionEntryInput] = Field(default_factory=list)
    events: list[EventInput] = Field(default_factory=list)
    event_evidence: list[EventEvidenceInput] = Field(default_factory=list)
    attempts: list[ProcessingAttemptInput] = Field(default_factory=list)
    attempt_updates: list[AttemptUpdateInput] = Field(default_factory=list)
    restrictions: list[AccessRestrictionInput] = Field(default_factory=list)
    settings: list[MemorySettingInput] = Field(default_factory=list)
    entities: list[EntityInput] = Field(default_factory=list)
    entity_names: list[EntityNameInput] = Field(default_factory=list)
    event_entities: list[EventEntityInput] = Field(default_factory=list)
    vector_spaces: list[VectorSpaceInput] = Field(default_factory=list)
    vector_bindings: list[VectorBindingInput] = Field(default_factory=list)
    vector_statuses: list[VectorStatusInput] = Field(default_factory=list)
    vector_request_parameters: list[VectorRequestInput] = Field(default_factory=list)

    event_relations: list[EventRelationInput] = Field(default_factory=list)

    episode_revisions: list[EpisodeRevisionInput] = Field(default_factory=list)
    episode_revision_inputs: list[EpisodeRevisionGenerationInput] = Field(default_factory=list)
    episodes: list[EpisodeInput] = Field(default_factory=list)
    episode_memberships: list[EpisodeMembershipInput] = Field(default_factory=list)

    @model_serializer(mode='wrap')
    def optional_chunk_section(self, handler):
        """The optional fragment-index section belongs only to fragment writes."""
        result = handler(self)
        if not self.chunk_vector_bindings and not self.chunk_vector_statuses:
            result.pop('chunk_vector_bindings', None)
            result.pop('chunk_vector_statuses', None)
        return result

    @model_validator(mode="after")
    def nonempty(self):
        count = sum(len(getattr(self, name)) for name in type(self).model_fields)
        if count < 1:
            raise ValueError("追加批次必须包含明确对象或关联。")
        return self


class MemoryQuery(MemoryModel):
    record_cutoff: int | None = Field(default=None, ge=0)
    target_time: MemoryTime | None = None
    view: Literal["current", "historical_saved", "historical_reconstruction"] = "current"
    object_types: list[ObjectType] = Field(default_factory=lambda: ["event"])
    source_categories: list[SourceCategory] = Field(default_factory=list)
    query: str = ""
    cursor: str | None = Field(default=None, min_length=1, max_length=8192)
    limit: int = Field(default=24, ge=1, le=100)

    @model_validator(mode="after")
    def valid_unique(self):
        for name in ("object_types", "source_categories"):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError("查询条件不能重复。")
        if not self.object_types:
            raise ValueError("必须指定读取对象类型。")
        if self.view == "historical_saved" and self.record_cutoff is None:
            raise ValueError("读取实际历史内容必须指定记录截点。")
        return self

"""Immutable SAG descriptions, entity evidence and vector commit metadata."""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID
from backend.app.schemas.memory.values import MemoryTime
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


def _text(value):
    if not value.strip():
        raise ValueError("文本不能为空白。")
    return value


def _uuid(value):
    if str(UUID(value)) != value:
        raise ValueError("记忆标识必须为规范 UUID。")
    return value


Text = Annotated[str, Field(min_length=1), AfterValidator(_text)]
Identifier = Annotated[str, AfterValidator(_uuid)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class IndexModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EntityInput(IndexModel):
    """实体创建时的身份、名称与依据。"""

    entity_id: Identifier
    event_id: Identifier
    entity_type: Text
    canonical_name: Text
    formal_resource_type: Text | None = None
    formal_resource_id: Text | None = None

    @model_validator(mode="after")
    def paired_resource(self):
        if (self.formal_resource_type is None) != (self.formal_resource_id is None):
            raise ValueError("正式业务身份必须同时提供类型和标识。")
        return self


class EntityNameInput(IndexModel):
    """同一实体的其他名称及其依据。"""

    entity_id: Identifier
    name_id: Identifier
    event_id: Identifier
    name: Text


class EventEntityInput(IndexModel):
    event_id: Identifier
    entity_id: Identifier
    description: Text


class VectorSpaceInput(IndexModel):
    space_id: Identifier
    model_id: Text
    provider_id: Text
    remote_model_id: Text
    model_signature: Digest
    dimensions: int = Field(ge=1, le=65536)
    protocol: Text


class VectorBindingInput(IndexModel):
    binding_id: Identifier
    event_id: Identifier
    space_id: Identifier
    vector_id: Identifier


class VectorStatusInput(IndexModel):
    binding_id: Identifier
    status_id: Identifier
    previous_status_id: Identifier | None = None
    vector_hash: Digest | None = None
    error_code: Text | None = None
    error_message: Text | None = None
    state: Literal["pending", "confirmed", "failed"]

    @model_validator(mode="after")
    def result_fields(self):
        if (self.state == "confirmed") != (self.vector_hash is not None):
            raise ValueError("仅确认状态必须保存实际向量校验值。")
        if self.state == "failed":
            if self.error_code is None or self.error_message is None:
                raise ValueError("失败状态必须保存错误信息。")
        elif self.error_code is not None or self.error_message is not None:
            raise ValueError("非失败状态不能保存错误信息。")
        return self


class VectorRequestInput(IndexModel):
    attempt_id: Identifier
    event_id: Identifier
    operation_id: Text
    requested_model_id: Text | None = None
    requested_dimensions: int | None = Field(default=None, ge=1, le=65536)


class IndexSearchInput(IndexModel):
    query: Text
    space_id: Identifier | None = None
    record_cutoff: int | None = Field(default=None, ge=0)
    continuation: str | None = None
    target_time: MemoryTime | None = None



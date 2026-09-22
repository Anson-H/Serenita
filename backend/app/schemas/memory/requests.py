"""HTTP commands for member memory; storage metadata stays server-owned."""

from typing import Literal

from pydantic import Field, field_validator, model_validator
from backend.app.schemas.memory.evidence import ChangeReference

from backend.app.schemas.memory.append import (
    MemoryModel, MemoryQuery, MemoryReference, SourceCategory, canonical_uuid,
)


class MemorySettingsSave(MemoryModel):
    operation_id: str = Field(min_length=1, max_length=200)
    formation_state: Literal["disabled", "enabled", "paused"]
    source_categories: list[SourceCategory]
    previous_setting_id: str | None = None
    reason: str = Field(default="健康档案所有者保存记忆形成设置。", min_length=1, max_length=2000)

    @field_validator("operation_id", "reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("操作标识和设置理由不能为空白。")
        return value

    @field_validator("previous_setting_id")
    @classmethod
    def setting_id(cls, value):
        return canonical_uuid(value) if value is not None else None


class MemoryReadRequest(MemoryQuery):
    references: list[MemoryReference] = Field(default_factory=list, max_length=100)
    business_changes: list[ChangeReference] = Field(default_factory=list, max_length=50,
        description='读取事件 evidence 中的实际业务变更引用；返回变更字段与记录时间。field_path 为空读取整条。与对象引用和目录筛选互斥。')

    @model_validator(mode='after')
    def one_read_scope(self):
        if self.business_changes:
            defaults=MemoryQuery().model_dump()
            if self.references or any(getattr(self,key)!=value for key,value in defaults.items()):
                raise ValueError('业务变更读取须单独提供 business_changes，不同时提供对象引用、截点或目录筛选。')
        return self



class MemoryProcessingRetry(MemoryModel):
    operation_id: str = Field(min_length=1, max_length=200)

    @field_validator('operation_id')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('重试操作标识不能为空白。')
        return value


class MemoryChangeSummaries(MemoryModel):
    references: list[ChangeReference] = Field(min_length=1, max_length=100,
        description='已加载变更记录的来源引用；按当前权限返回仍可读取的处理状态。')


class MemoryProcessingResume(MemoryModel):
    operation_id: str = Field(min_length=1, max_length=200)

    @field_validator('operation_id')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('继续处理操作标识不能为空白。')
        return value

"""Complete-population event, experience and source counts."""
from typing import Annotated, Literal
from pydantic import AfterValidator, Field, model_validator

from backend.app.schemas.memory.values import MemoryModel, MemoryTime, Text, SourceCategory, canonical_uuid

Identifier = Annotated[str, AfterValidator(canonical_uuid)]


class MemoryStatisticsRequest(MemoryModel):
    record_cutoff: int | None = Field(default=None, ge=0, description="成功提交的记忆截点，默认当前；完整母体固定在该截点，实时权限始终重新核对。")
    target_time: MemoryTime | None = Field(default=None, description="按发生时期可能相交筛选，省略不限制；未知时间保留在可能范围并单独报告，不能当作明确落在范围。")
    source_categories: list[SourceCategory] = Field(default_factory=list, description="实际来源类别筛选，不重复；默认全部当前可读类别，不改变各来源的授权。")
    event_ids: list[Identifier] = Field(default_factory=list, max_length=1000, description="明确统计的Event集合，默认整个筛选范围；只能来自实际对象目录，不能传入语义搜索topK后宣称全范围。")
    entity_ids: list[Identifier] = Field(default_factory=list, max_length=100, description="正式Entity身份筛选，默认不限；不同标识不按相似名称合并，至少匹配所选一个实体。")
    query: str = Field(default="", max_length=2000, description="对事件表述执行明确的文字包含筛选，默认空字符串；它是完整母体筛选，不能代替语义关联判断。")
    cursor: Text | None = Field(default=None, description="前一页返回的next_cursor，绑定成员、筛选及截点；默认从头读取。分页只控制原始对象，汇总始终使用完整母体。")
    limit: int = Field(default=100, ge=1, le=500, description="每页最多返回的Event数，默认100；汇总不受此值或页数限制。")

    @model_validator(mode="after")
    def unique_filters(self):
        for name in ("source_categories", "event_ids", "entity_ids"):
            value = getattr(self, name)
            if len(value) != len(set(value)):
                raise ValueError("统计筛选项不能重复。")
        return self

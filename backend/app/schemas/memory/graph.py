"""Read-only graph projection parameters; graphs have no separate storage."""
from pydantic import Field, field_validator, model_validator

from backend.app.schemas.memory.append import ObjectType, canonical_uuid
from backend.app.schemas.memory.requests import MemoryReadRequest
from backend.app.schemas.memory.values import OBJECT_TYPES


class MemoryGraphRead(MemoryReadRequest):
    episode_id: str | None = Field(default=None, description='已读取的 Episode UUID；提供时读取该事项的 Event Graph，省略时读取成员 Memory Graph。不能与 references 同时提供。')
    object_types: list[ObjectType] = Field(default_factory=lambda: list(OBJECT_TYPES), description='Memory Graph 的对象类型范围，默认全部实际支持类型，不重复；Episode 模式按实际归属读取 Event。')
    edge_limit: int = Field(default=100, ge=1, le=500, description='本页至多返回的关系或存储引用数量，默认100，范围1至500；超出时明确返回未读范围和继续读取参数。')
    edge_cursor: str | None = Field(default=None,max_length=4096,description='上次读取返回的 next_edge_cursor，用于继续同一对象页内尚未读取的边；默认省略从该页首项边开始。继续时保持原 cursor、limit、过滤条件及 record_cutoff，不使用对象下一页游标替换当前 cursor；边上限可调整。当前对象页或权限范围变化时须重新读取。')
    _episode = field_validator('episode_id')(lambda value: canonical_uuid(value) if value is not None else None)

    @model_validator(mode='after')
    def graph_scope(self):
        if self.episode_id and self.references:
            raise ValueError('事项图与明确对象引用不能同时选择。')
        if self.references and self.cursor:
            raise ValueError('明确对象引用读取不使用目录分页游标。')
        if self.edge_cursor and self.record_cutoff is None:
            raise ValueError('边续读必须保留实际读取结果的记录截点。')
        return self

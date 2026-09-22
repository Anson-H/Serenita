"""Direct references to immutable business changes; no copied source content."""
from pydantic import Field, field_validator
from backend.app.schemas.memory.values import MemoryModel, Text, canonical_uuid
from backend.app.domain.memory.sources import BUSINESS_SOURCE_DATABASES


class ChangeReference(MemoryModel):
    source_database: Text = Field(description="业务变更目录或事件 evidence 返回的已登记业务数据库文件名；不接受路径，不跨账号读取。")
    change_id: Text = Field(description="业务变更目录或事件 evidence 返回的实际业务变更规范 UUID；不能用业务条目 ID 代替。")
    field_path: str | None = Field(default='', description='该变更实际保存的字段 JSON Pointer，须精确匹配；省略、null 或空字符串读取整条变更。')

    _id = field_validator('change_id')(canonical_uuid)

    @field_validator('source_database')
    @classmethod
    def database(cls, value):
        if value not in BUSINESS_SOURCE_DATABASES:
            raise ValueError('来源数据库必须取自已登记的业务库。')
        return value

    @field_validator('field_path', mode='before')
    @classmethod
    def pointer(cls, value):
        import re
        if value is None:
            return ''
        if not isinstance(value, str) or value and (not value.startswith('/') or re.search(r'~(?![01])', value)):
            raise ValueError('字段位置须为业务变更中的 JSON Pointer；整条引用使用空值。')
        return value


class EventEvidenceInput(ChangeReference):
    event_id: Text
    _event = field_validator('event_id')(canonical_uuid)


def source_key(reference):
    import json
    return json.dumps([reference['source_database'], reference['change_id'], reference.get('field_path') or ''], separators=(',', ':'))

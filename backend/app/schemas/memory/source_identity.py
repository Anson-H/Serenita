"""The single canonical identity for one member's actual source lifecycle."""
import json

from backend.app.schemas.memory.values import canonical_uuid, stable_memory_id


def memory_source_id(member_id: str, *, source_account_id: str, source_database: str,
                     resource_type: str, resource_id: str, source_generation: str) -> str:
    canonical_uuid(source_account_id)
    parts = [source_account_id, source_database, resource_type, resource_id, source_generation]
    if any(not isinstance(value, str) or not value.strip() for value in parts):
        raise ValueError('来源身份的账号、业务库、类型、资源及生命周期必须是明确的非空字符串。')
    identity = json.dumps(parts, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return stable_memory_id(member_id, 'source-identity', 'source', identity)


from pydantic import field_validator
from backend.app.schemas.memory.values import MemoryModel, Text, SourceCategory


class BusinessResourceIdentity(MemoryModel):
    source_id: Text
    source_account_id: Text
    source_member_id: str | None = None
    source_category: SourceCategory
    resource_type: Text
    resource_id: Text
    source_database: Text
    source_generation: Text
    title: Text
    _ids = field_validator("source_id", "source_account_id", "source_member_id")(lambda v: canonical_uuid(v) if v is not None else None)

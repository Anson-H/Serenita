"""Shared strict values for immutable memory objects and references."""
from __future__ import annotations

from datetime import date, datetime
from backend.app.core.time import local_iso, parse_local_datetime, local_timezone, local_timezone_name
import re
import json
import calendar
from typing import Annotated, Literal
from uuid import UUID, uuid5, NAMESPACE_URL

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


class MemoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def nonblank_text(value):
    if not value.strip():
        raise ValueError("文本不能为空白。")
    return value


Text = Annotated[str, Field(min_length=1), AfterValidator(nonblank_text)]
SourceCategory = Literal["member_profile", "medical_report", "medical_log", "medication", "body_metric"]
SOURCE_CATEGORIES = ("member_profile", "medical_report", "medical_log", "medication", "body_metric")
ObjectType = Literal["event", "processing_attempt", "access_restriction", "memory_setting", "entity", "entity_name", "vector_space", "vector_binding", "vector_status", "event_relation", "episode", "episode_revision", "episode_membership", "memory_execution_entry"]
OBJECT_TYPES = ("event", "processing_attempt", "access_restriction", "memory_setting", "entity", "entity_name", "vector_space", "vector_binding", "vector_status", "event_relation", "episode", "episode_revision", "episode_membership", "memory_execution_entry")


def canonical_uuid(value: str) -> str:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("记忆标识必须为规范 UUID。") from exc
    if str(parsed) != value:
        raise ValueError("记忆标识必须为规范 UUID。")
    return value


def stable_memory_id(member_id: str, operation_id: str, object_type: str, label: str) -> str:
    """Derive a retry-stable server identity without including audit time."""
    canonical_uuid(member_id)
    if not operation_id.strip() or not label.strip():
        raise ValueError("操作标识与对象标签不能为空。")
    return str(uuid5(NAMESPACE_URL, json.dumps(["serenita:memory", member_id, operation_id, object_type, label], ensure_ascii=False, separators=(",", ":"))))


def local_time_value(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]+)?)?(?:Z|[+-][0-9]{2}:[0-9]{2})?", value):
        raise ValueError("时间必须为本地 ISO 8601 日期时间。")
    return local_iso(value)


class TimeBound(MemoryModel):
    value: Text
    precision: Literal["year", "month", "day", "instant"]

    @model_validator(mode="after")
    def valid_value(self):
        if self.precision == "instant":
            self.value = local_time_value(self.value)
        else:
            pattern = {"year": r"\d{4}", "month": r"\d{4}-\d{2}", "day": r"\d{4}-\d{2}-\d{2}"}[self.precision]
            if not re.fullmatch(pattern, self.value):
                raise ValueError("时间值与声明精度不符。")
            date.fromisoformat(self.value + {"year": "-01-01", "month": "-01", "day": ""}[self.precision])
        return self


class MemoryTime(MemoryModel):
    start: TimeBound | None = None
    end: TimeBound | None = None
    original_text: str | None = None
    timezone: str = Field(default_factory=local_timezone_name)
    anchor_time: str | None = None
    uncertainty: Literal["exact", "approximate", "unknown"] = "unknown"
    unknown: list[str] = Field(default_factory=lambda: ["时间未知"])

    @field_validator("anchor_time")
    @classmethod
    def valid_anchor(cls, value):
        return local_time_value(value) if value is not None else None

    @field_validator("timezone", mode="before")
    @classmethod
    def valid_zone(cls, value):
        return local_timezone_name()

    @model_validator(mode="after")
    def valid_range(self):
        if self.start is None and self.end is None and (self.uncertainty != "unknown" or not any(v.strip() for v in self.unknown)):
            raise ValueError("时间全部未知时必须保留未知说明。")
        if self.start and self.end:
            lower, upper = memory_time_bounds(self)
            if lower > upper:
                raise ValueError("时间下界不能晚于上界。")
        return self


class EventTime(MemoryTime):
    uncertainty: Literal["exact", "approximate"] = "exact"
    unknown: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def has_occurrence(self):
        if self.start is None and self.end is None:
            raise ValueError("未提供事件发生时间时使用 null，不保存空的时间结构。")
        return self

def memory_time_bounds(value):
    """Compute possible bounds without changing source values or precision."""
    if value is None:
        return None, None
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    def edge(raw, latest):
        if raw is None:
            return None
        text, precision = raw["value"], raw["precision"]
        if precision == "instant":
            return parse_local_datetime(text).timestamp()
        if precision == "year":
            year, month, day = int(text), (12 if latest else 1), (31 if latest else 1)
        elif precision == "month":
            year, month = map(int, text.split("-"))
            day = calendar.monthrange(year, month)[1] if latest else 1
        else:
            parsed = date.fromisoformat(text)
            year, month, day = parsed.year, parsed.month, parsed.day
        zone = local_timezone()
        return datetime(year, month, day, 23 if latest else 0, 59 if latest else 0, 59 if latest else 0, 999999 if latest else 0, tzinfo=zone).timestamp()
    return edge(value.get("start"), False), edge(value.get("end"), True)


def occurrence_time_bounds(value):
    """Possible occurrence range; a lone start retains its original precision.

    This read-only projection does not assert an end or continued validity.
    """
    if value is None:
        return None, None
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    if value.get('start') is not None and value.get('end') is None:
        value = {**value, 'end': value['start']}
    return memory_time_bounds(value)


class MemoryReference(MemoryModel):
    object_type: ObjectType
    object_id: Text
    version: int | None = Field(default=None, ge=1)
    item_id: str | None = None
    _id = field_validator("object_id")(canonical_uuid)

    @model_validator(mode="after")
    def valid_detail(self):
        if (self.object_type in {"episode_revision"}) != (self.version is not None):
            raise ValueError("事项版本引用必须提供实际整数 version，其它对象不接受 version。")
        if self.object_type in {"memory_setting", "entity_name", "vector_status", "memory_execution_entry"} and self.item_id is None:
            raise ValueError("父对象明细引用必须提供 item_id。")
        if self.item_id is not None:
            if self.object_type not in {"memory_setting", "entity_name", "vector_status", "memory_execution_entry"}:
                raise ValueError("该对象类型没有父对象明细。")
            canonical_uuid(self.item_id)
        return self



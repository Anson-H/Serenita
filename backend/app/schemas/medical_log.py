import re
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def calendar_date(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("日期必须为 YYYY-MM-DD。")
    date.fromisoformat(value)
    return value


class MedicalLogUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    recorded_on: str | None = None
    title: str | None = None
    content: str | None = None

    @field_validator("recorded_on")
    @classmethod
    def validate_date(cls, value):
        if value is None:
            raise ValueError("记录日期不能为空。")
        return calendar_date(value)

    @field_validator("title", "content")
    @classmethod
    def required_text(cls, value):
        if value is None or not value.strip():
            raise ValueError("标题和正文不能空白。")
        return value.strip()

    @model_validator(mode="after")
    def nonempty_update(self):
        if not self.model_fields_set:
            raise ValueError("至少提交一个可编辑字段。")
        return self


class MedicalLogCreate(MedicalLogUpdate):
    recorded_on: str
    title: str
    content: str


class MedicalLogQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    after_date: str | None = None
    before_date: str | None = None
    query: str = ""
    cursor: str | None = Field(default=None, min_length=1, max_length=4096)
    limit: int = Field(default=24, ge=1, le=100)

    @field_validator("after_date", "before_date")
    @classmethod
    def validate_date(cls, value):
        return calendar_date(value)

    @model_validator(mode="after")
    def valid_range(self):
        if self.after_date and self.before_date and self.after_date > self.before_date:
            raise ValueError("日期下界不能晚于上界。")
        return self


class MedicalLogReadQuery(MedicalLogQuery):
    medical_log_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("medical_log_ids")
    @classmethod
    def validate_ids(cls, value):
        if value is None or any(not item.strip() for item in value) or len(value) != len(set(value)):
            raise ValueError("日记标识必须为非空、不重复的数组。")
        return sorted(value)

    @field_validator("after_date", "before_date", "cursor", mode="before")
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("可选查询条件应省略，不能为 null。")
        return value

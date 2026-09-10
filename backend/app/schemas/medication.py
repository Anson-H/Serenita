"""The medication wire contract; partial writes are validated after merging."""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)


class Identity(StrictModel):
    generic_name: str = Field(min_length=1, description='药品通用名，创建必填，忠于已确认的用户表述或已读取材料；不接受 null、空字符串或纯空白，未知时先取证或询问；更新时省略保持原值。')
    brand_name: str | None = Field(default=None, min_length=1, description='药品商品名，忠于已确认的用户表述或已读取材料；未知为 null，省略默认 null；填写时不可为空白，更新时省略保持原值。')
    strength: str | None = None
    package_specification: str | None = None



class DoseTime(StrictModel):
    time: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')


class Schedule(StrictModel):
    kind: Literal['daily', 'weekly', 'every_n_days', 'as_needed']
    times: list[DoseTime] = Field(default_factory=list)
    times_per_day: int | None = Field(default=None, gt=0, le=96)
    weekdays: list[int] = Field(default_factory=list)
    interval_days: int | None = Field(default=None, gt=0)
    anchor_date: str | None = None

    @model_validator(mode='after')
    def valid(self):
        if len({t.time for t in self.times}) != len(self.times):
            raise ValueError('用药时间不能重复。')
        self.times.sort(key=lambda t: t.time)
        allowed = {
            'daily': {'times', 'times_per_day'}, 'weekly': {'times', 'weekdays'},
            'every_n_days': {'times', 'interval_days', 'anchor_date'},
            'as_needed': set(),
        }[self.kind]
        for key in ('times', 'times_per_day', 'weekdays', 'interval_days', 'anchor_date'):
            if getattr(self, key) not in (None, []) and key not in allowed:
                raise ValueError(f'{self.kind} 不接受 {key}。')
        if self.times and self.times_per_day is not None:
            raise ValueError('具体时间与每日次数不能同时提交。')
        if self.kind == 'weekly' and (not self.weekdays or len(set(self.weekdays)) != len(self.weekdays) or any(d < 1 or d > 7 for d in self.weekdays)):
            raise ValueError('每周用药须选择不重复的星期一至星期日。')
        if self.kind == 'every_n_days':
            if not self.interval_days or not self.anchor_date: raise ValueError('间隔天数和锚定日期必填。')
            calendar(self.anchor_date)
        return self


def calendar(value):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value): raise ValueError('日期须为 YYYY-MM-DD。')
    return date.fromisoformat(value)


def instant(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None: raise ValueError('时间必须包含时区偏移。')
    return parsed


def end_instant(value):
    return None if value is None or value == 'long_term' else instant(value)


def check_time(value, precision, zone):
    if (value is None) != (precision is None): raise ValueError('时间与时间精度须同时填写或清空。')
    if value is not None:
        parsed = instant(value)
        local = parsed.astimezone(ZoneInfo(zone))
        if precision == 'date' and (local.hour or local.minute or local.second or local.microsecond):
            raise ValueError('日期精度须使用所选时区的日边界。')


class Medication(Identity):
    prescription_type: Literal['prescription', 'nonprescription', 'unknown'] = 'unknown'
    notes: str | None = None
    leaflet_url: str | None = None

    @field_validator('leaflet_url')
    @classmethod
    def url(cls, value):
        if value and not re.match(r'^https?://[^/\s]+', value): raise ValueError('说明书链接必须为 HTTP 或 HTTPS 地址。')
        return value


class Plan(StrictModel):
    medication_id: str = Field(min_length=1, description='当前成员健康档案所有者账号药品目录中的已有药品的稳定标识，取自药品目录或读取工具结果；创建必填，切换药品时提交，更新省略保持原引用，不接受 null、空白、其它账号目录或已删除的药品。药品信息每次读取时从目录读取，不接受手工填写。')

    starts_at: str = Field(description='保存用药计划时必填的用药计划开始时间，须有明确日期，采用带时区偏移的 ISO 时间；日期精度取所选时区的日边界，不接受未知或空值。')
    ends_at: str | None = Field(default=None, description='结束边界：具体日期采用带时区偏移的 ISO 时间，边界不含该时刻；long_term 表示已明确长期使用，null 表示结束日期未知，省略默认为 null。')
    start_precision: Literal['date', 'minute'] = Field(description='保存用药计划时必填，date 表示精确到日，minute 表示精确到分钟，与用药计划开始时间一同提供。')
    end_precision: Literal['date', 'minute'] | None = Field(default=None, description='结束边界为具体时间时必填，date 表示日边界，minute 表示精确到分钟；结束边界为 long_term 或 null 时必须为 null，默认 null。')
    timezone: str = 'Asia/Shanghai'
    dose_text: str | None = Field(default=None, description='每次用药的完整剂量及单位，适用于本计划所有用药时间；未知为 null。')
    route: str | None = None
    schedule: Schedule | None = None
    usage_status: Literal['taking', 'paused', 'stopped', 'completed', 'unknown'] = 'unknown'

    notes: str | None = None


    @model_validator(mode='after')
    def valid(self):
        try: ZoneInfo(self.timezone)
        except (KeyError, ValueError): raise ValueError('时区必须为有效 IANA 标识。')
        check_time(self.starts_at, self.start_precision, self.timezone)
        check_time(None if self.ends_at == 'long_term' else self.ends_at, self.end_precision, self.timezone)
        end = end_instant(self.ends_at)
        if self.starts_at and end is not None and instant(self.starts_at) >= end:
            raise ValueError('用药计划结束必须晚于开始。')
        if self.usage_status in ('paused', 'stopped', 'completed') and self.schedule is not None:
            raise ValueError('暂停或结束用药计划不能设置排程。')
        return self



class Batch(StrictModel):
    quantity: str = Field(description='准确十进制数量文本，必须大于等于零。')
    expires_on: str | None = None
    notes: str | None = None

    @model_validator(mode='after')
    def valid(self):
        if not re.fullmatch(r'\d+(?:\.\d+)?', self.quantity) or len(self.quantity) > 120:
            raise ValueError('库存数量须为不超过 120 字符的非负十进制文本。')
        try: quantity = Decimal(self.quantity)
        except InvalidOperation: raise ValueError('库存数量必须为十进制数。')
        if not quantity.is_finite() or quantity < 0: raise ValueError('库存数量必须大于等于零。')
        self.quantity = format(quantity, 'f')
        if '.' in self.quantity: self.quantity = self.quantity.rstrip('0').rstrip('.')
        if self.expires_on is not None: calendar(self.expires_on)
        return self


MODELS = {'medication': Medication, 'plan': Plan, 'batch': Batch}
IDS = {'medication': 'medication_id', 'plan': 'medication_plan_id', 'batch': 'medication_batch_id'}
TABLES = {'medication': 'medications', 'plan': 'medication_plans', 'batch': 'medication_inventory'}


def validate_request_id(request_id: object) -> None:
    if (
        not isinstance(request_id, str)
        or not request_id.strip()
        or len(request_id) > 200
    ):
        raise ValueError("请求标识须为 1 至 200 字符且不能全部为空白。")

"""Body metric records: a shared envelope and strictly typed domain content."""
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field, model_validator

# code, display name, unit, category, aggregation
METRICS = [
    ('height','身高','cm','body','latest'),('weight','体重','kg','body','latest'),
    ('bmi','BMI','kg/m²','body','latest'),('waist','腰围','cm','body','latest'),
    ('body_fat','体脂率','%','body','latest'),('fat_mass','脂肪量','kg','body','latest'),
    ('bone_mass','骨量','kg','body','latest'),('body_water','体水分量','kg','body','latest'),
    ('protein_mass','蛋白质量','kg','body','latest'),('subcutaneous_fat','皮下脂肪','%','body','latest'),
    ('visceral_fat','内脏脂肪','等级','body','latest'),
    ('heart_rate','心率','次/分','heart','range'),('resting_heart_rate','静息心率','次/分','heart','mean'),
    ('night_heart_rate','夜间心率','次/分','heart','mean'),('hrv','心率变异性','ms','heart','mean'),
    ('blood_pressure','血压','mmHg','blood_pressure','mean'),('blood_oxygen','血氧','%','blood_oxygen','range'),
    ('blood_glucose','血糖','mmol/L','blood_glucose','range'),('temperature','体温','°C','temperature','mean'),
    ('steps','步数','步','steps','sum'),('active_energy','活动能量','kcal','active_energy','sum'),
    ('stand_hours','站立小时数','小时','stand_hours','sum'),('exercise_minutes','锻炼时长','min','exercise_minutes','sum'),
]
CATALOG = {r[0]: dict(zip(('metric','label','unit','category','aggregation'), r)) for r in METRICS}
MEALS = {'breakfast':'早餐','morning_snack':'早加餐','lunch':'午餐','afternoon_snack':'午加餐','dinner':'晚餐','evening_snack':'晚加餐'}
STAGES = {'awake':'清醒','rem':'快速眼动','light':'浅睡','deep':'深睡','unknown':'未知睡眠阶段','in_bed':'卧床'}

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)

class Nutrition(Strict):
    energy: float | None = Field(default=None, ge=0)
    carbohydrate: float | None = Field(default=None, ge=0)
    protein: float | None = Field(default=None, ge=0)
    fat: float | None = Field(default=None, ge=0)

class Food(Nutrition):
    food_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    amount: float | None = Field(default=None, gt=0)
    amount_unit: str = 'g'
    basis: str = ''

class Meal(Nutrition):
    meal_type: Literal['breakfast','morning_snack','lunch','afternoon_snack','dinner','evening_snack'] | None = None
    foods: list[Food] = Field(default_factory=list, max_length=100)
    estimated: bool = False
    basis: str = ''
    @model_validator(mode='after')
    def totals(self):
        if len({f.food_id for f in self.foods}) != len(self.foods): raise ValueError('食物标识重复。')
        if self.foods:
            for key in ('energy','carbohydrate','protein','fat'):
                values = [getattr(f,key) for f in self.foods]
                setattr(self,key,round(sum(values),4) if all(v is not None for v in values) else None)
        return self

class Stage(Strict):
    stage_id: str = Field(min_length=1, max_length=200)
    stage: Literal['awake','rem','light','deep','unknown','in_bed']
    starts_at: str
    ends_at: str
    original_stage: str = ''

class Sleep(Strict):
    score: float | None = Field(default=None, ge=0)
    score_max: float | None = Field(default=None, gt=0)
    score_basis: str = ''
    score_stale: bool = False
    duration_minutes: float | None = Field(default=None, ge=0)
    stages: list[Stage] = Field(default_factory=list, max_length=10000)
    @model_validator(mode='after')
    def scores(self):
        if self.score is not None and (self.score_max is None or self.score > self.score_max): raise ValueError('睡眠评分必须提供有效满分。')
        return self

class Workout(Strict):
    activity: str = Field(min_length=1, max_length=100)
    duration_minutes: float = Field(ge=0)
    distance_km: float | None = Field(default=None, ge=0)
    energy: float | None = Field(default=None, ge=0)

class Measurement(Strict):
    value: float = Field(ge=0)
    unit: str = Field(min_length=1, max_length=32)
    secondary_value: float | None = Field(default=None, ge=0)
    pulse: float | None = Field(default=None, ge=0)
    method: str = Field(default='', max_length=100)
    context: str = Field(default='', max_length=200)
    basis: str = Field(default='', max_length=1000)

DATA_MODELS = {'measurement': Measurement, 'meal': Meal, 'sleep': Sleep, 'workout': Workout}

def instant(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None: raise ValueError('日期时间必须包含时区偏移。')
    return result

class BodyRecord(Strict):
    kind: Literal['measurement','meal','sleep','workout']
    metric: str = ''
    starts_at: str
    ends_at: str | None = None
    timezone: str = 'Asia/Shanghai'
    precision: Literal['instant','interval','day'] = 'instant'
    source: str = Field(default='手工记录', min_length=1, max_length=200)
    device: str = Field(default='', max_length=200)
    origin: Literal['manual','apple_health','standard','image','demo'] = 'manual'
    external_id: str | None = Field(default=None, min_length=1, max_length=300)
    notes: str = Field(default='', max_length=4000)
    data: dict

    @model_validator(mode='after')
    def validate_record(self):
        ZoneInfo(self.timezone)
        start = instant(self.starts_at)
        end = instant(self.ends_at) if self.ends_at else None
        if end and (end-start).days > 366: raise ValueError('单条记录区间不能超过 366 天。')
        if end and end <= start: raise ValueError('结束时间必须晚于开始时间。')
        if (self.precision != 'instant' or self.kind in ('sleep','workout')) and end is None: raise ValueError('区间记录必须提供结束时间。')
        if self.kind == 'measurement':
            if self.metric not in CATALOG: raise ValueError('未知身体指标。')
        elif self.metric: raise ValueError('仅测量记录填写 metric。')
        parsed = DATA_MODELS[self.kind].model_validate(self.data)
        if self.kind == 'measurement':
            if self.metric == 'blood_pressure' and parsed.secondary_value is None: raise ValueError('血压需同时记录收缩压和舒张压。')
            if self.metric != 'blood_pressure' and (parsed.secondary_value is not None or parsed.pulse is not None): raise ValueError('成组血压字段仅用于血压。')
            allowed = {CATALOG[self.metric]['unit']}
            if self.metric in ('subcutaneous_fat','visceral_fat'): allowed |= {'%','kg','等级','cm²'}
            conversions = {('weight','lb'):('kg',0.45359237),('height','m'):('cm',100),('waist','m'):('cm',100),('blood_glucose','mg/dL'):('mmol/L',1/18.0182),('active_energy','kJ'):('kcal',1/4.184),('exercise_minutes','s'):('min',1/60)}
            if (self.metric,parsed.unit) in conversions:
                parsed.unit, factor = conversions[(self.metric,parsed.unit)]; parsed.value *= factor
            if parsed.unit not in allowed: raise ValueError(f'不支持该单位：{parsed.unit}。')
            if parsed.unit == '%' and parsed.value > 100: raise ValueError('百分比必须在 0 至 100 之间。')
            if self.metric == 'hrv' and not parsed.method: parsed.method = 'unknown'
        if self.kind == 'sleep':
            ids=set(); previous=None; sleeping=0
            for stage in sorted(parsed.stages,key=lambda s:instant(s.starts_at)):
                a,b=instant(stage.starts_at),instant(stage.ends_at)
                if stage.stage_id in ids: raise ValueError('睡眠阶段标识重复。')
                ids.add(stage.stage_id)
                if b <= a or a < start or b > end: raise ValueError('睡眠阶段必须位于主睡眠区间内，且结束晚于开始。')
                if previous and a < previous: raise ValueError('睡眠阶段存在冲突重叠，请核对起止时间。')
                previous=b
                if stage.stage not in ('awake','in_bed'): sleeping += (b-a).total_seconds()/60
            if parsed.stages: parsed.duration_minutes=round(sleeping,4)
        if self.kind in ('sleep','workout') and parsed.duration_minutes is not None and parsed.duration_minutes > (end-start).total_seconds()/60 + .001: raise ValueError('实际时长不能超过记录起止区间。')
        self.starts_at = start.astimezone(timezone.utc).isoformat(timespec='microseconds')
        self.ends_at = end.astimezone(timezone.utc).isoformat(timespec='microseconds') if end else None
        if self.kind == 'sleep':
            for stage in parsed.stages:
                stage.starts_at = instant(stage.starts_at).astimezone(timezone.utc).isoformat(timespec='microseconds')
                stage.ends_at = instant(stage.ends_at).astimezone(timezone.utc).isoformat(timespec='microseconds')
        self.data=parsed.model_dump()
        return self

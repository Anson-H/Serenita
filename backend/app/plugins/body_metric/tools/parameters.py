"""Parameter structures for body metric tools."""

from backend.app.agent_runtime.tools.parameters import model_parameters
from backend.app.schemas.body_metric import BodyRecord, DATA_MODELS

FIELD_DOCS = {
    "kind": "记录类型：measurement 测量、meal 饮食、sleep 睡眠、workout 运动，必填。",
    "metric": "测量必填，取自身体指标分类目录 metric；其它记录为空字符串。",
    "starts_at": "发生或开始日期时间，必填带时区偏移的 ISO 8601 字符串；不可用上传时间代替进食时间。",
    "ends_at": "结束日期时间，带时区偏移且晚于开始；区间、日汇总、睡眠和运动必填，其它可为 null。",
    "timezone": "有效 IANA 时区，省略为 Asia/Shanghai。",
    "precision": "instant 单次、interval 区间、day 日汇总；省略为 instant；区间和日汇总需要结束时间。",
    "source": "来源名称，非空，省略为手工记录；图片识别填写图片识别并说明估算依据。",
    "device": "来源设备名称，未知为空字符串，省略为空。",
    "origin": "manual 手工、apple_health 苹果、standard 标准文件、image 图片、demo 虚构演示，省略为 manual；忠于实际输入。",
    "external_id": "外部稳定标识，仅有来源提供时填写；默认 null，不得虚构设备标识。",
    "notes": "记录备注，默认空字符串。",
    "data": "与 kind 对应的完整业务结构；字段含义见各子参数。",
    "value": "测量非负数值，必填；血压为收缩压。",
    "unit": "测量单位，必填，取自分类目录；内脏/皮下脂肪还可使用 kg、%、等级或 cm²；百分比为 0–100。",
    "secondary_value": "同次舒张压，血压必填，其它类型不接受；默认 null。",
    "pulse": "同次血压测量的脉搏，非负；仅血压可填，未知 null。",
    "method": "测量方法；HRV 需注明 SDNN、RMSSD 或 unknown；默认空字符串。",
    "context": "测量背景，如空腹、餐后或设备条件，未知为空。",
    "basis": "数值依据、实际读取的标签或估算假设，默认空字符串。",
    "energy": "实际摄入或运动能量，单位 kcal，非负，未知 null；有食物明细时饮食总量由明细计算。",
    "carbohydrate": "实际摄入碳水化合物克数，非负，未知 null；有食物明细时按明细计算。",
    "protein": "实际摄入蛋白质克数，非负，未知 null；有食物明细时按明细计算。",
    "fat": "实际摄入脂肪克数，非负，未知 null；有食物明细时按明细计算。",
    "meal_type": "早餐 breakfast、早加餐 morning_snack、午餐 lunch、午加餐 afternoon_snack、晚餐 dinner、晚加餐 evening_snack；未确认可为 null。",
    "foods": "食物明细，默认空数组；有明细时各营养总量完全按明细计算，任一未知则该营养总量未知；最多 100 项。",
    "food_id": "当前饮食记录内唯一的食物标识，添加时自行生成稳定标识，更新取自已读取记录。",
    "name": "食物名称，必填非空字符串。",
    "amount": "实际摄入份量，正数，未知 null。",
    "amount_unit": "份量单位，默认 g。",
    "estimated": "是否包含照片推算或其它估算，默认 false；照片推算为 true，必须说明 basis。",
    "score": "来源睡眠评分，非负；填写时需同时填写 score_max，未知 null。",
    "score_max": "该评分量表满分，正数且不小于评分，未知 null。",
    "score_basis": "评分来源与算法说明，未知为空。",
    "score_stale": "已有评分是否对应更新前区间，默认 false；更新睡眠时由服务端维护。",
    "duration_minutes": "实际睡眠或运动时长，非负分钟数；睡眠有阶段时由阶段计算，未知可空；运动必填。",
    "stages": "逐段睡眠明细，默认空数组；每段必须在主区间内且不重叠，不能从总时长推测阶段。",
    "stage_id": "父睡眠记录内唯一阶段标识，添加时自行生成，更新取自已读取记录。",
    "stage": "awake 清醒、rem 快速眼动、light 浅睡、deep 深睡、unknown 未知睡眠阶段、in_bed 卧床。",
    "original_stage": "原始阶段名称，未提供为空字符串。",
    "activity": "运动名称，必填非空字符串。",
    "distance_km": "运动距离，非负公里数，未知 null。",
}


def expand_schema(model):
    return model_parameters(model, describe=lambda name, prop: FIELD_DOCS[name])


def record_schema():
    branches = []
    for kind, model in DATA_MODELS.items():
        branch = expand_schema(BodyRecord)
        branch["properties"]["kind"] = {
            "type": "string",
            "const": kind,
            "description": FIELD_DOCS["kind"],
        }
        branch["properties"]["data"] = expand_schema(model)
        branch["properties"]["data"]["description"] = FIELD_DOCS["data"]
        branches.append(branch)
    return {
        "type": "object",
        "oneOf": branches,
        "description": "完整记录，kind 决定 data 结构；创建字段省略使用明确默认值，不接受未知字段。",
    }


def string(desc):
    return {"type": "string", "minLength": 1, "description": desc}


ID = string(
    "当前成员记录稳定标识，取自记录目录、读取或创建工具结果；不接受路径、其它成员或已删除记录。"
)
FILTERS = {
    "after": string("包含的开始日期 YYYY-MM-DD，省略无下界。"),
    "before": string("包含的结束日期 YYYY-MM-DD，不早于 after，省略无上界。"),
    "category": string(
        "分类：body、nutrition、sleep、heart、blood_pressure、blood_oxygen、blood_glucose、temperature、steps、workouts、active_energy、stand_hours、exercise_minutes；省略查全部。"
    ),
    "timezone": string("统计日界使用的 IANA 时区，省略 Asia/Shanghai。"),
    "source": string(
        "精确来源名称，取自统计 sources 或记录 source，省略保留全部来源且分别统计。"
    ),
}


def build_parameters():
    def schema(props, required=()):
        return {
            "type": "object",
            "properties": props,
            "required": list(required),
            "additionalProperties": False,
        }

    full = record_schema()
    changes = expand_schema(BodyRecord)
    changes["properties"] = {
        k: v
        for k, v in changes["properties"].items()
        if k
        in ("metric", "starts_at", "ends_at", "timezone", "precision", "notes", "data")
    }
    changes.pop("required")
    changes["minProperties"] = 1
    changes["description"] = (
        "只提交要更新的业务字段，省略保持原值；data 按对应 kind 结构合并，foods/stages 提交时整组替换，更新前读取记录。"
    )
    partial_data = []
    for model in DATA_MODELS.values():
        branch = expand_schema(model)
        branch.pop("required", None)
        partial_data.append(branch)
    changes["properties"]["data"] = {
        "type": "object",
        "anyOf": partial_data,
        "description": "对应记录 kind 的局部业务字段，省略保持原值；合并后按完整记录校验。foods 和 stages 提交时须提供完整数组及完整明细。",
    }
    specs = {
        "read_body_metric_catalog": schema({}),
        "read_body_record_catalog": schema(dict(FILTERS)),
        "read_body_record": schema({"record_id": ID}, ["record_id"]),
        "read_body_statistics": schema(
            {
                **FILTERS,
                "series_id": string(
                    "汇总工具结果中的 series_id；省略返回全部匹配记录的汇总，提供时由 Harness 自动读取该序列的全部趋势页。"
                ),
                "view": {
                    "type": "string",
                    "enum": ["buckets", "points"],
                    "description": "提供 series_id 时可用，buckets 按日汇总，points 原始点；默认 buckets。",
                },
            }
        ),
        "create_body_record": schema(
            {
                "record": full,
                "request_id": string(
                    "当前创建操作的稳定请求标识，重试复用；同标识不同内容拒绝。"
                ),
            },
            ["record", "request_id"],
        ),
        "update_body_record": schema(
            {"record_id": ID, "changes": changes}, ["record_id", "changes"]
        ),
        "delete_body_record": schema({"record_id": ID}, ["record_id"]),
        "attach_body_record_file": schema(
            {
                "record_id": ID,
                "resource_id": string(
                    "当前会话已上传图片的 resource_id，取自附件元数据；服务端校验归属与文件完整性。"
                ),
            },
            ["record_id", "resource_id"],
        ),
        "detach_body_record_file": schema(
            {"record_id": ID, "file_id": string("取自饮食记录 files 的 file_id。")},
            ["record_id", "file_id"],
        ),
    }
    return specs

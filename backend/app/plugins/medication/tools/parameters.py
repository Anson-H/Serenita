"""Parameter structures for medication tools."""

from backend.app.agent_runtime.tools.parameters import model_parameters
from backend.app.plugins.medication.constants import LABELS
from backend.app.schemas.medication import IDS, Medication


PARAM_LABELS = {
    "generic_name": "通用名",
    "brand_name": "商品名",
    "strength": "浓度含量",
    "package_specification": "包装规格",
    "notes": "备注",
    "dose_text": "完整剂量及单位",
    "route": "给药途径",
    "leaflet_url": "说明书 HTTP 或 HTTPS 链接",
}


def string(description):
    return {"type": "string", "minLength": 1, "description": description}


def id_schema(label):
    if label == "药品资料":
        return string("当前成员健康档案所有者账号目录中的药品稳定标识，取自药品信息工具结果；不接受其它账号或已删除对象。")
    return string(
        f"当前成员{label}稳定标识，取自对应目录或先前工具结果；不接受其它成员或已删除对象。"
    )


def parameter_description(key, prop):
    desc = PARAM_LABELS.get(key, key)
    if key in ("strength", "package_specification", "leaflet_url", "notes"):
        desc += "；采用已确认文字或实际读取材料中的内容，未知为 null，创建时省略默认 null，更新时省略保留原值。"
    if key in ("starts_at", "ends_at"):
        desc = "带时区偏移的 ISO 时间；未知为 null。日期精度取所选时区的日边界，计划结束为不含该时刻。"
    elif key in ("start_precision", "end_precision"):
        desc = "date 表示精确到日，minute 表示精确到分钟；与对应时间同时有值或同时为 null。"
    elif key == "timezone":
        desc = "有效 IANA 时区，默认 Asia/Shanghai；日期和固定钟点按该时区解释。"
    elif key == "medication_id":
        desc = "当前成员健康档案所有者账号目录中的药品稳定标识，取自药品信息工具结果；必填且不可清空。"
    elif key == "usage_status":
        desc = "明确反馈的状态，taking 在用、paused 暂停、stopped 停用、completed 完成、unknown 未确认；默认未确认，暂停或结束计划 schedule 必须为 null。"
    elif key == "schedule":
        desc = "频率结构；未知可空。每日次数和具体时间互斥；固定时间不重复；按需不能设置固定时间。"
    elif key == "kind":
        desc = "as_needed 按需、daily 每日、every_n_days 每隔若干日、weekly 每周指定日；未记录时将整个 schedule 设为 null。"
    elif key == "times":
        desc = "不重复的固定时间列表，省略为空；每项只保存 HH:mm 格式的 time；所有时间共用用药安排的每次剂量。"
    elif key == "time":
        desc = "固定本地钟点，格式 HH:mm。"
    elif key == "times_per_day":
        desc = "每天次数，正整数，最大 96；仅 daily，不能与非空 times 同时提供。"
    elif key == "weekdays":
        desc = "仅 weekly，必填不重复的 1 至 7 数组，1 为星期一。"
    elif key == "interval_days":
        desc = "仅 every_n_days，必填正整数，与 anchor_date 同时提供。"
    elif key == "anchor_date":
        desc = "仅 every_n_days，必填合法 YYYY-MM-DD 锚定日期。"
    elif key == "expires_on":
        desc = "有效期截止日期，格式为合法日期 YYYY-MM-DD；未知为 null。"
    elif key == "prescription_type":
        desc = "prescription 处方药、nonprescription 非处方药、unknown 未知，默认 unknown；标签须有材料依据。"
    return desc


def model_schema(model, partial=False):
    return model_parameters(model, describe=parameter_description, partial=partial)


def object_parameters(properties, required):
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def identity_parameters(kind):
    key = IDS[kind]
    return object_parameters({key: id_schema(LABELS[kind])}, [key])


def create_parameters(kind, model):
    schema = model_schema(model)
    return object_parameters(
        {
            **schema["properties"],
            "request_id": string(
                "本次创建的稳定请求标识，1 至 200 字符且不得全部为空白；同一请求重试复用，相同标识不同内容失败。"
            ),
            **({"medication_id": id_schema("药品资料")} if kind == "batch" else {}),
            **({"sources": medication_source_list(creating=True)} if kind == "medication" else {}),
        },
        schema.get("required", []) + ["request_id"] + (["medication_id"] if kind == "batch" else []),
    )


def update_parameters(kind, model):
    key = IDS[kind]
    return object_parameters({**model_schema(model, partial=True)['properties'], key: id_schema(LABELS[kind])}, [key])


def catalog_properties():
    return {
        "query": {
            "type": "string",
            "description": "字面关键词；省略或空白不限制，与其它筛选共同生效。",
        },
        "status": {
            "type": "string",
            "description": "计划可选 upcoming、ongoing、ended、undated、taking、paused、stopped、completed、unknown；省略不限制。",
        },
        "after_date": string(
            "日期下界 YYYY-MM-DD，含当天，计划按区间相交筛选。"
        ),
        "before_date": string("日期上界 YYYY-MM-DD，含当天，不能早于下界。"),
        "undated": {
            "type": "boolean",
            "description": "是否仅查未知日期，默认 false。",
        },
    }


def medication_plan_parameters():
    return object_parameters({
        **catalog_properties(),
        IDS['plan']: {
            **string('当前成员用药计划的稳定标识，取自先前工具结果；省略不限制，与关键词、状态和日期筛选共同生效，不接受 null、空白、其它成员或已删除的计划。返回 items 中的完整计划内容和全部匹配数量 total；无匹配时 items 为空，Harness 自动读取全部匹配页。'),
            'pattern': r'\S',
        },
    }, [])


def medication_information_parameters():
    catalog = catalog_properties()
    return object_parameters({
        **{key: catalog[key] for key in ('query',)},
        'medication_id': string('当前成员健康档案所有者账号目录中的药品稳定标识，取自先前工具结果；省略不限制，与关键词共同筛选，不接受空值、空白、其它账号或已删除对象。'),
        'fields': {'type': 'array', 'uniqueItems': True,
            'items': {'type': 'string', 'enum': sorted(set(Medication.model_fields) | {'sources', 'created_at', 'updated_at'})},
            'description': '要读取的药品信息字段；省略或空数组返回全部药品资料与审计信息，不含来源和库存。药品和成员标识、通用名、商品名、浓度含量、包装规格及审计信息始终返回。选择 sources 时返回每项药品的全部来源元数据并将来源原文交给模型；没有来源时返回空数组。不接受 null。'},
    }, [])


def medication_source_list(*, creating=False):
    return {
        'type': 'array', 'minItems': 0 if creating else 1, 'maxItems': 20, 'uniqueItems': True,
        **({'default': []} if creating else {}),
        'description': (
            '随药品资料一同保存的原件；省略或空数组表示没有附件原件，不接受 null。资料和全部原件一次保存，任一资料或文件无效、重复或写入失败时整次失败，不保留药品或部分原件。'
            if creating else
            '需要补充的原件，至少一项且不可为空或 null；目标药品已有相同内容或整批中存在相同内容时整次失败，不产生部分写入。'
        ) + '每项必须来自当前会话可见附件，同一文件不可重复提交，最多 20 项。支持 JPEG、PNG、HEIC、PDF、UTF-8 纯文本，每份非空且不超过 20 MB，整批不超过 100 MB。保存需要当前成员健康档案所有者账号权限。服务端读取并校验原文件，保存后返回独立的药品原件标识，原件独立于聊天存续；保留已有主来源，尚无原件时首项为主来源。',
        'items': object_parameters({
            'resource_id': string('当前会话线性视图中可见附件的稳定标识，取自附件元数据；必填，不接受空白、其它会话、已过期或内容校验失败的附件，不接受文件路径或模型生成的正文。'),
            'purpose': {'type': 'string', 'enum': ['package', 'label', 'leaflet'],
                'description': '原件用途，package 为药品包装，label 为标签，leaflet 为说明书；按实际读取内容选择，必填且无默认值，不接受 null。'},
        }, ['resource_id', 'purpose']),
    }


def medication_sources_parameters():
    return object_parameters({
        'medication_id': id_schema('药品资料'),
        'sources': medication_source_list(),
        'request_id': {**string('本次补充原件的稳定请求标识，1 至 200 字符且不得全部为空白；同一请求重试复用，相同标识不同内容失败。'), 'maxLength': 200},
    }, ['medication_id', 'sources', 'request_id'])

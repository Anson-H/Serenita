"""Shared meanings for memory model fields and query schemas."""

DESCRIPTIONS = {
    "MemoryTime": {
        "start": "有据起点，未知或省略为 null；与 end 独立保留原精度，不得用提交时间补齐。来源只给发生时点时填写 start，省略 end，不将同一时点复制为结束。",
        "end": "有据终点，未知或省略为 null；不能推定一直持续。不能确定地早于 start。",
        "original_text": "来源中的原始时间表述，未知或省略为 null；保留昨天、持续十分钟等原话。",
        "timezone": "系统本地时区，由程序提供，省略即使用本地设置。",
        "anchor_time": "仅用于解释昨天、三天后等相对时间的来源锚点，本地 ISO 日期时间；明确日期和时刻无需此参数，省略。来源接收或记忆保存时刻不能充当来源时间锚点。",
        "uncertainty": "exact 表示有据精确、approximate 表示约略、unknown 表示未知，默认 unknown。",
        "unknown": "时间仍未知的部分与原因，默认包含时间未知；起止均为空时必须保留非空说明。",
    },
    "TimeBound": {"value": "合法年 YYYY、年月 YYYY-MM、日期 YYYY-MM-DD 或本地 ISO 日期时间，与 precision 相符。",
                  "precision": "year/month/day/instant 分别表示年、月、日和真实明确时刻，不提升来源精度。"},
    "MemoryReference": {"object_type": "当前实际支持的记忆对象类型，取自工具结果。", "object_id": "实际对象的规范 UUID。",
        "version": "episode_revision 必填实际读取的摘要与状态整数版本；其它对象类型省略此参数。", "item_id": "memory_setting、entity_name、vector_status 和 memory_execution_entry 必填实际明细 UUID；其它类型省略此参数。"},
}


def describe(schema):
    for name, fields in DESCRIPTIONS.items():
        definition = schema.get("$defs", {}).get(name)
        if definition:
            for field, description in fields.items():
                definition["properties"][field]["description"] = description
    return schema



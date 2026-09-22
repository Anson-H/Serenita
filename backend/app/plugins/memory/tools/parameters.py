"""Model-facing schemas derived from the validated formation commands."""

from backend.app.agent_runtime.tools.parameters import schema_parameters
from backend.app.schemas.memory.requests import MemoryReadRequest


from backend.app.schemas.memory.descriptions import describe


def memory_parameters(schema):
    """Optional model arguments use omission; supplied values keep one type."""
    schema = schema_parameters(schema)

    def visit(value, *, optional=False):
        if not isinstance(value, dict):
            return [visit(item) for item in value] if isinstance(value, list) else value
        value = dict(value)
        if optional:
            choices = value.get("anyOf", [])
            actual = [item for item in choices if item != {"type": "null"}]
            if len(choices) == 2 and len(actual) == 1:
                branch = actual[0]
                value = {**branch, **{key: item for key, item in value.items() if key != "anyOf"}}
            types = value.get("type")
            if isinstance(types, list) and "null" in types:
                actual_types = [item for item in types if item != "null"]
                value["type"] = actual_types[0] if len(actual_types) == 1 else actual_types
            if isinstance(value.get("enum"), list):
                value["enum"] = [item for item in value["enum"] if item is not None]
            if value.get("default", object()) is None:
                value.pop("default")
            if value.get("description"):
                description = value["description"]
                for original, replacement in (
                    ("未知或省略为 null", "未知时省略"),
                    ("省略或 null", "省略"),
                    ("省略为 null", "省略"),
                    ("默认 null", "默认省略"),
                ):
                    description = description.replace(original, replacement)
                value["description"] = description.replace("null", "省略该参数")
        required = set(value.get("required", []))
        result = {}
        for key, item in value.items():
            if key == "properties":
                result[key] = {name: visit(prop, optional=name not in required) for name, prop in item.items()}
            else:
                result[key] = visit(item)
        return result

    result = visit(schema)
    result["description"] = (result.get("description", "") +
        " 可选参数用省略表示未提供；提供时使用 Schema 指定的实际类型，不接收空值。").strip()
    return result


def build_parameters():
    read = MemoryReadRequest.model_json_schema()
    descriptions = {
        "record_cutoff": "成功提交的记录截点，省略或 null 为当前；从实际读取结果取得，不得猜测历史截点。",
        "target_time": "按有据发生时期筛选，省略或 null 不限制；完整时间精度与未知规则见 MemoryTime。",
        "view": "current 当前读取、historical_saved 当时实际保存、historical_reconstruction 当前证据重建历史，默认 current；historical_saved 必须指定 record_cutoff。",
        "object_types": "不重复的实际对象类型，默认只读 event，至少一项；支持列表仅列当前实现。",
        "source_categories": "按实际来源类别筛选，不重复，默认空数组表示不限。",
        "query": "当前基础读取中的文本包含筛选，默认空字符串；不代表完成语义向量检索。",
        "cursor": "上次同一范围返回的 next_cursor，默认 null；绑定成员、当前权限、筛选与截点，不得跨范围复用。",
        "limit": "默认每页 24 个对象，范围 1 至 100；分页只限制返回量，不改变总匹配数。",
        "references": "直接读取实际对象引用，最多 100 项；默认空数组执行目录查询，非空执行明确引用读取并仍执行截点和实时权限。",
    }
    for name, description in descriptions.items():
        read["properties"][name]["description"] = description
    return {name: memory_parameters(describe(schema)) for name, schema in {
        "read_memory": read,
    }.items()}

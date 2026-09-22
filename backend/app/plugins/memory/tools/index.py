"""Expose the independent memory query service to conversations."""
from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.domain.memory.read_results import readable_result
from backend.app.schemas.memory.index import IndexSearchInput
from backend.app.plugins.memory.tools.parameters import describe, memory_parameters


INDEX_DESCRIPTIONS = {
    "search_memory": "搜索当前成员的长期记忆，返回有关事件、联系和证据入口。",
}


def index_parameters():
    search = IndexSearchInput.model_json_schema()
    meanings = {
        "query": "本次明确的问题或对象线索，非空文本；Entity 名称匹配与描述向量共同定位，不构成事件取证。",
        "space_id": "从实际索引结果取得的固定向量空间 UUID；省略或 null 时使用当前记忆向量模型对应的已有空间，缺失时保留文字检索并明确向量缺口。",
        "record_cutoff": "真实提交截点，省略或 null 为当前；继续检索必须沿用前次返回的截点，不能跨时间混用游标。",
        "target_time": "有据发生时期，省略或 null 不限制；保留原时间精度和未知，不把记录时间当作发生时间。",
        "continuation": "本次相同账号、成员、查询、时间与记录截点返回的继续检索值，省略或 null 从首批开始；不能跨范围复用。",
    }
    for key, meaning in meanings.items():
        search["properties"][key]["description"] = meaning
    return {"search_memory": memory_parameters(describe(search))}


class MemoryIndexTool(Tool):
    def __init__(self, context, formation, service, name, schema):
        self.context, self.formation, self.service = context, formation, service
        self.name, self.description, self.input_schema = name, INDEX_DESCRIPTIONS[name], schema

    def bind_runtime_arguments(self, arguments, *, context, observations):
        return {**arguments, "_memory_binding": self.formation.bind(conversation_scope(context, self.context), observations)}

    def run(self, arguments):
        values = dict(arguments)
        binding = values.pop("_memory_binding", None)
        self.formation.require_binding(self.context.account_id, self.context.member_id, binding)
        output = self.service.search(self.context.account_id, self.context.member_id, values)
        evidence = output.get("evidence")
        if evidence and evidence.get("objects"):
            self.formation.receipts(evidence, binding)
        resources = (evidence or {}).get("model_resource_refs", [])
        return ToolResult(name=self.name, output=readable_result(output),
            effects={"model_resource_refs": resources} if resources else {})


def create_index_tools(runtime_context, reads):
    return [MemoryIndexTool(runtime_context, reads.evidence, reads.search, name, schema) for name, schema in index_parameters().items()]

from backend.app.plugins.memory.evidence_scope import conversation_scope

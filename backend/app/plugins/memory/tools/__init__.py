"""The four read capabilities exposed to conversations."""

from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.domain.memory.read_results import readable_result
from backend.app.application.memory.capabilities import MemoryConversationReads
from backend.app.application.memory.service import MemoryService
from backend.app.plugins.memory.tools.parameters import build_parameters
from backend.app.plugins.memory.tools.index import create_index_tools
from backend.app.plugins.memory.tools.statistics import create_statistics_tools
from backend.app.plugins.memory.tools.graph import MemoryGraphTool


DESCRIPTIONS = {
    "read_memory": "读取当前成员的记忆对象、经过与依据，返回指定范围的内容。",
}


class MemoryTool(Tool):
    def __init__(self, context, service, name, schema):
        self.context, self.service = context, service
        self.name, self.description, self.input_schema = name, DESCRIPTIONS[name], schema

    def bind_runtime_arguments(self, arguments, *, context, observations):
        return {**arguments, "_memory_binding": self.service.bind(conversation_scope(context, self.context), observations)}

    def run(self, arguments):
        values = dict(arguments)
        binding = values.pop("_memory_binding", None)
        capability = self.service.read
        result = capability(self.context.account_id, self.context.member_id, values, binding=binding)
        return ToolResult(name=self.name, output=readable_result(result),
            effects={"model_resource_refs": result["model_resource_refs"]} if result.get("model_resource_refs") else {})


def create_tools(*, runtime_context):
    if runtime_context.member_id is None:
        return []
    reads = MemoryConversationReads(runtime_context.service("memory", MemoryService),
        cancellation_token=runtime_context.cancellation_token,deadline=runtime_context.deadline)
    service = reads.evidence
    tools = [MemoryGraphTool(runtime_context, reads),
        MemoryTool(runtime_context, service, 'read_memory', build_parameters()['read_memory']),
        *create_index_tools(runtime_context, reads), *create_statistics_tools(runtime_context, reads)]
    for tool in tools:
        tool.model_exposure = 'direct'
    return tools

from backend.app.plugins.memory.evidence_scope import conversation_scope

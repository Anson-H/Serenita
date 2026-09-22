"""The model chooses the complete statistics scope and reads returned evidence."""
from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.domain.memory.read_results import readable_result
from backend.app.plugins.memory.tools.parameters import describe, memory_parameters
from backend.app.schemas.memory.statistics import MemoryStatisticsRequest


class MemoryStatisticsTool(Tool):
    name = "read_memory_statistics"
    description = "读取当前成员的记忆统计，返回计数、计算口径和覆盖范围。"
    input_schema = memory_parameters(describe(MemoryStatisticsRequest.model_json_schema()))

    def __init__(self, runtime_context, reads):
        self.context, self.formation = runtime_context, reads.evidence
        self.service = reads.statistics

    def bind_runtime_arguments(self, arguments, *, context, observations):
        return {**arguments, "_memory_binding": self.formation.bind(conversation_scope(context, self.context), observations)}

    def run(self, arguments):
        values = dict(arguments)
        binding = values.pop("_memory_binding", None)
        result = self.service.read(self.context.account_id, self.context.member_id, values, binding=binding)
        return ToolResult(name=self.name, output=readable_result(result))


def create_statistics_tools(runtime_context, reads):
    return [MemoryStatisticsTool(runtime_context, reads)] if runtime_context.member_id else []

from backend.app.plugins.memory.evidence_scope import conversation_scope

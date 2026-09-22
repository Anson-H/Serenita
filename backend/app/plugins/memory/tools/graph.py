"""Read an existing graph projection through the shared evidence issuer."""
from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.domain.memory.read_results import readable_result
from backend.app.plugins.memory.tools.parameters import build_parameters, describe, memory_parameters
from backend.app.schemas.memory.graph import MemoryGraphRead


class MemoryGraphTool(Tool):
    name = 'read_memory_graph'
    description = '读取当前成员的记忆对象与关联结构，返回事项经过或指定范围的记忆图。'

    def __init__(self, context, reads):
        self.context, self.formation = context, reads.evidence
        self.service = reads.graph
        self.input_schema = memory_parameters(describe(MemoryGraphRead.model_json_schema()))
        shared = build_parameters()['read_memory']['properties']
        for field, schema in self.input_schema['properties'].items():
            if not schema.get('description') and field in shared and shared[field].get('description'):
                schema['description'] = shared[field]['description']

    def bind_runtime_arguments(self, arguments, *, context, observations):
        return {**arguments, '_memory_binding': self.formation.bind(conversation_scope(context, self.context), observations)}

    def run(self, arguments):
        values = dict(arguments)
        binding = values.pop('_memory_binding', None)
        result = self.service.read(self.context.account_id, self.context.member_id, values, binding=binding)
        return ToolResult(name=self.name, output=readable_result(result),
                          effects={'model_resource_refs': result['model_resource_refs']} if result.get('model_resource_refs') else {})

from backend.app.plugins.memory.evidence_scope import conversation_scope

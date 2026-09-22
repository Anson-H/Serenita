"""Expose memory queries directly to conversations."""
from backend.app.plugins.memory.tools import create_tools

PLUGIN_ID = "memory"


QUERY_TOOLS = frozenset({'search_memory', 'read_memory', 'read_memory_graph', 'read_memory_statistics'})


def build_tools(*, runtime_context):
    return create_tools(runtime_context=runtime_context)



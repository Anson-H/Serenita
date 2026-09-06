"""Composable tools and model drivers for Harness behavior tests."""

import json
from backend.app.agent_runtime.context import AgentContext
from backend.app.agent_runtime.model_types import AssistantModelOutput, ToolCall
from backend.app.agent_runtime.runtime import AgentHarnessRuntime
from backend.app.agent_runtime.skills.base import SkillDocument, Skill
from backend.app.agent_runtime.skills.registry import SkillRegistry
from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.agent_runtime.tools.registry import ToolRegistry


class FakeSkill(Skill):
    def __init__(self, name: str, tools: set[str] | None = None):
        self.name = name
        self.description = f"{name} capability"
        self._tools = frozenset(tools or set())

    def read(self, context: AgentContext) -> SkillDocument:
        return SkillDocument(
            name=self.name,
            content="Use observed evidence only.",
            allowed_tools=self._tools,
        )


class EchoTool(Tool):
    name = "echo"
    description = "Echo one value."
    input_schema = {
        "type": "object",
        "required": ["value"],
        "properties": {"value": {"type": "string"}},
        "additionalProperties": False,
    }

    def run(self, arguments):
        assert arguments["account_id"] == "alice"
        return ToolResult(
            name=self.name,
            output={"value": arguments["value"]},
            effects={"created_entities": []},
        )


class DirectEchoTool(EchoTool):
    name = "direct_echo"
    model_exposure = "direct"


class FailingTool(EchoTool):
    name = "failing"

    def run(self, arguments):
        raise RuntimeError("temporary failure")


class BatchTool(Tool):
    name = "batch"
    description = "Accept a structured batch."
    input_schema = {
        "type": "object",
        "oneOf": [
            {
                "type": "object",
                "required": ["operation", "items"],
                "properties": {
                    "operation": {"type": "string", "enum": ["store"]},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["value"],
                            "properties": {"value": {"type": "string"}},
                            "additionalProperties": False,
                        },
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "additionalProperties": False,
            },
            {
                "type": "object",
                "required": ["operation", "item_name_zh"],
                "properties": {
                    "operation": {"type": "string", "enum": ["read"]},
                    "item_name_zh": {"type": "string"},
                },
                "additionalProperties": False,
            },
        ],
    }

    def run(self, arguments):
        assert arguments["items"] == [{"value": "x"}]
        assert arguments["limit"] == 24
        return ToolResult(
            name=self.name,
            output={"stored": arguments["items"], "limit": arguments["limit"]},
        )


class TableTool(Tool):
    name = "table"
    description = "Return same-shape rows."
    input_schema = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def run(self, arguments):
        return ToolResult(
            name=self.name,
            output={
                "rows": [
                    {"item": "甲", "value": 1},
                    {"item": "乙", "value": 2},
                ]
            },
        )


class LogicalPagesTool(Tool):
    name = "logical_pages"
    description = "Return three internal logical pages."
    model_exposure = "direct"
    input_schema = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def __init__(self):
        self.calls = 0

    def run(self, arguments):
        self.calls += 1
        return ToolResult(
            name=self.name,
            output={"total": 3, "rows": []},
            logical_pages=(
                {"rows": [{"position": 1, "value": "甲"}]},
                {"rows": [{"position": 2, "value": "乙"}]},
                {"rows": [{"position": 3, "value": "丙"}]},
            ),
        )


def runtime(*, skills=(), tools=(), max_actions=12) -> AgentHarnessRuntime:
    skill_registry = SkillRegistry()
    for skill in skills:
        skill_registry.register(skill)
    tool_registry = ToolRegistry()
    for tool in tools:
        tool_registry.register(tool)
    return AgentHarnessRuntime(
        skill_registry=skill_registry,
        tool_registry=tool_registry,
        max_actions=max_actions,
    )


class HarnessDriver:
    """Small event-log projection used by runtime unit tests."""

    def __init__(self, *outputs: AssistantModelOutput):
        self.outputs = list(outputs)
        self.messages = [{"role": "user", "content": "test request"}]
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return self.outputs.pop(0)

    def derive(self):
        return [dict(item) for item in self.messages]

    def record(self, event):
        payload = event.payload
        if event.type == "assistant_tool_calls":
            self.messages.append(
                {
                    "role": "assistant",
                    "content": payload.get("content"),
                    "tool_calls": payload["tool_calls"],
                }
            )
        elif event.type in {"tool_result", "tool_error"}:
            body = payload.get("output")
            if event.type == "tool_error":
                body = {"error": payload.get("error"), "status": "failed"}
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": payload["tool_call_id"],
                    "name": payload["tool"],
                    "content": (
                        body
                        if isinstance(body, str)
                        else json.dumps(body, ensure_ascii=False)
                    ),
                }
            )
        elif event.type == "assistant_intermediate":
            self.messages.append(
                {"role": "assistant", "content": payload.get("content", "")}
            )
        elif event.type == "harness_observation":
            self.messages.append(
                {
                    "role": "user",
                    "content": "HARNESS_OBSERVATION\n"
                    + json.dumps(payload, ensure_ascii=False),
                }
            )


def call(call_id: str, tool_name: str, **arguments) -> AssistantModelOutput:
    return AssistantModelOutput(
        tool_calls=(ToolCall(id=call_id, name=tool_name, arguments=arguments),),
        stop_reason="tool_calls",
    )


def assert_native_pairs(messages, *, pending_ids=()):
    """Independent protocol assertion, so success does not rely on the validator."""
    pending = set()
    for message in messages:
        if message["role"] == "assistant":
            assert not pending
            ids = [call["id"] for call in message.get("tool_calls", [])]
            assert len(ids) == len(set(ids))
            pending.update(ids)
        elif message["role"] == "tool":
            assert message["tool_call_id"] in pending
            pending.remove(message["tool_call_id"])
        else:
            assert not pending
    assert pending == set(pending_ids)

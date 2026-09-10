"""Real plugin registration and skill loading through the Harness."""

import pytest

from backend.app.agent_runtime.context import AgentContext
from backend.app.agent_runtime.model_types import AssistantModelOutput
from backend.app.agent_runtime.runtime import AgentHarnessRuntime
from backend.app.agent_runtime.tools.registry import ToolRegistry
from backend.app.plugins.registry import build_available_tools, build_builtin_skills
from backend.app.plugins.runtime_context import PluginRuntimeContext
from tests.agent_support import HarnessDriver, call


class InMemoryService:
    def for_runtime(self, *args, **kwargs):
        return self


@pytest.mark.parametrize("skill", build_builtin_skills(), ids=lambda skill: skill.name)
def test_registered_skill_exposes_its_tools_after_successful_loading(skill):
    plugin_context = PluginRuntimeContext(
        account_id="account",
        member_id="member",
        event_recorder=lambda _event: None,
        service_factory=lambda _name: InMemoryService(),
    )
    registered = build_available_tools(runtime_context=plugin_context)
    tools = ToolRegistry()
    for tool in registered:
        tools.register(tool)
    harness = AgentHarnessRuntime(tool_registry=tools)
    context = AgentContext(
        account_id="account", member_id="member", task_type="conversation"
    )
    driver = HarnessDriver(
        call("load", "load_skill", name=skill.name),
        AssistantModelOutput(content="已读取技能。"),
    )

    result = harness.execute(
        context,
        derive_messages=driver.derive,
        complete_model=driver.complete,
        on_event=driver.record,
    )

    assert result.output["status"] == "completed"
    assert len(driver.requests) == 2
    loaded = skill.read(context)
    skill_result = next(message for message in driver.messages if message["role"] == "tool")
    assert skill_result["content"] == loaded.content
    first_tools = {tool.name for tool in driver.requests[0].tools}
    next_tools = {tool.name: tool for tool in driver.requests[1].tools}
    assert first_tools == {
        "load_skill", "update_plan", "read_history",
        "update_history", "web_search", "web_read",
    }
    assert set(next_tools) == first_tools | loaded.allowed_tools
    for tool in registered:
        if tool.name in loaded.allowed_tools:
            assert next_tools[tool.name].parameters == tool.input_schema_for_context(context)


MEDICATION_CAPABILITIES = {
    "medication-catalog": {"create_medication", "add_medication_sources"},
    "medication-query": {
        "read_medication_information", "read_medication_inventory", "read_medication_batch",
        "read_medication_plan",
    },
    "medication-inventory": {"create_medication_batch", "update_medication_batch", "delete_medication_batch"},
    "medication-plan": {"create_medication_plan", "update_medication_plan", "delete_medication_plan"},
}


@pytest.mark.parametrize(
    "first,second",
    [(first, second) for first in MEDICATION_CAPABILITIES for second in MEDICATION_CAPABILITIES if first != second],
)
def test_medication_skills_expose_only_their_capabilities_and_compose(first, second):
    from backend.app.plugins.medication.registry import build_skills, build_tools
    plugin_context = PluginRuntimeContext(
        account_id="account", member_id="member",
        event_recorder=lambda _event: None,
        service_factory=lambda _name: InMemoryService(),
    )
    assert {skill.name for skill in build_skills()} == set(MEDICATION_CAPABILITIES)
    medication_tools = {tool.name for tool in build_tools(runtime_context=plugin_context)}
    assert medication_tools == set().union(*MEDICATION_CAPABILITIES.values())
    assert {name for name in medication_tools if name.startswith("read_")} == MEDICATION_CAPABILITIES["medication-query"]
    tools = ToolRegistry()
    for tool in build_available_tools(runtime_context=plugin_context):
        tools.register(tool)
    harness = AgentHarnessRuntime(tool_registry=tools)
    context = AgentContext(account_id="account", member_id="member", task_type="conversation")
    driver = HarnessDriver(
        call("first", "load_skill", name=first),
        call("second", "load_skill", name=second),
        AssistantModelOutput(content="Skills loaded."),
    )
    result = harness.execute(
        context, derive_messages=driver.derive,
        complete_model=driver.complete, on_event=driver.record,
    )
    assert result.output["status"] == "completed"
    initial, isolated, combined = [{tool.name for tool in request.tools} for request in driver.requests]
    assert not medication_tools & initial
    assert isolated == initial | MEDICATION_CAPABILITIES[first]
    assert combined == isolated | MEDICATION_CAPABILITIES[second]

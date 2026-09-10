from copy import deepcopy
from dataclasses import replace
import json
import pytest
from backend.app.agent_runtime.context import AgentContext
from backend.app.agent_runtime.model_types import AssistantModelOutput, PromptContextSection, ToolCall
from backend.app.agent_runtime.tools.base import ToolResult
from backend.app.core.tabular_json import decode_tabular_json
from backend.app.providers.errors import ProviderChatCompletionError
from tests.agent_support import DirectEchoTool, EchoTool, FakeSkill, HarnessDriver, LogicalPagesTool, call, runtime


def execute(harness, driver, **kwargs):
    return harness.execute(
        AgentContext(account_id="alice", member_id="alice-member", task_type="conversation"),
        derive_messages=driver.derive,
        complete_model=driver.complete,
        on_event=driver.record,
        **kwargs,
    )


def overflow():
    error = ProviderChatCompletionError("context is full")
    error.code = "CONTEXT_WINDOW_EXCEEDED"
    return error


class ErrorDriver(HarnessDriver):
    def complete(self, request):
        output = super().complete(request)
        if isinstance(output, Exception):
            raise output
        return output


def assert_paired(messages):
    pending = set()
    for message in messages:
        if message.get("tool_calls"):
            assert not pending
            pending = {item["id"] for item in message["tool_calls"]}
        elif message["role"] == "tool":
            assert message["tool_call_id"] in pending
            pending.remove(message["tool_call_id"])
        else:
            assert not pending
    assert not pending


def test_preparation_uses_current_skills_and_revokes_tools_before_model_call():
    driver = HarnessDriver(
        call("revoked", "echo", value="must not execute"),
        AssistantModelOutput(content="done"),
    )
    names = ["worker"]
    order = []
    prepared = []

    def derive_skills():
        order.append("skills")
        return iter(names)

    def prepare(request, rebuild, force):
        order.append("prepare")
        assert force is False
        if not prepared:
            assert "echo" in {item.name for item in request.tools}
            names.clear()
        else:
            assert "echo" not in {item.name for item in request.tools}
        request = replace(
            request, tools=tuple(item for item in request.tools if item.name != "echo")
        )
        prepared.append(request)
        return request

    result = execute(
        runtime(skills=[FakeSkill("worker", {"echo"})], tools=[EchoTool()]),
        driver,
        before_model_request=lambda: order.append("before"),
        derive_skill_names=derive_skills,
        prepare_request=prepare,
    )

    assert order == ["before", "skills", "prepare"] * 2
    assert all(sent is ready for sent, ready in zip(driver.requests, prepared))
    assert result.output["tool_results"] == []
    error = next(event for event in result.events if event.type == "tool_error")
    assert error.payload["error"]["code"] == "TOOL_NOT_ALLOWED"
    assert_paired(driver.messages)


def test_skill_projection_replaces_initial_and_in_memory_loaded_skills():
    driver = HarnessDriver(
        call("load", "load_skill", name="worker"),
        AssistantModelOutput(content="done"),
    )
    result = execute(
        runtime(skills=[FakeSkill("worker", {"echo"})], tools=[EchoTool()]),
        driver,
        initial_skill_names=["worker"],
        derive_skill_names=lambda: [],
    )
    assert all("echo" not in {tool.name for tool in req.tools} for req in driver.requests)
    assert any(event.type == "tool_result" for event in result.events)
    assert_paired(driver.messages)


def test_request_rebuilder_uses_history_skill_visibility_without_inferring_suspension():
    driver = HarnessDriver(AssistantModelOutput(content="done"))
    rebuilt = []

    def prepare(request, rebuild, force):
        assert "echo" not in {tool.name for tool in request.tools}
        visible = rebuild(messages=driver.derive(), skill_names=["worker"])
        assert "echo" in {tool.name for tool in visible.tools}
        hidden = rebuild(messages=driver.derive(), skill_names=[])
        assert "echo" not in {tool.name for tool in hidden.tools}
        rebuilt.extend([visible, hidden])
        return hidden

    execute(
        runtime(skills=[FakeSkill("worker", {"echo"})], tools=[EchoTool()]),
        driver,
        prepare_request=prepare,
    )
    assert driver.requests == [rebuilt[-1]]


def test_request_rebuilder_preserves_tool_suspension_after_skill_visibility_changes():
    driver = HarnessDriver(
        *(call(f"invalid-{index}", "echo", value=index) for index in range(3)),
        AssistantModelOutput(content="done"),
    )

    def prepare(request, rebuild, force):
        return rebuild(messages=driver.derive(), skill_names=["alternate"])

    result = execute(
        runtime(
            skills=[FakeSkill("worker", {"echo"}), FakeSkill("alternate", {"echo"})],
            tools=[EchoTool()],
        ),
        driver,
        initial_skill_names=["worker"],
        prepare_request=prepare,
    )
    assert "echo" in {tool.name for tool in driver.requests[0].tools}
    assert "echo" not in {tool.name for tool in driver.requests[-1].tools}
    assert result.output["tool_results"] == []
    assert [event.payload["error"]["code"] for event in result.events if event.type == "tool_error"] == [
        "TOOL_ARGUMENTS_INVALID", "TOOL_ARGUMENTS_INVALID", "REPEATED_INVALID_TOOL_ARGUMENTS"
    ]


def test_pending_skill_result_survives_each_rebuild_once_and_activates_after_success():
    driver = HarnessDriver(
        call("load", "load_skill", name="worker"),
        call("echo", "echo", value="ok"),
        AssistantModelOutput(content="done"),
    )
    candidates = []

    def before_result(request, rebuild):
        driver.messages[0] = {"role": "user", "content": "summary"}
        for _ in range(2):
            candidate = rebuild(messages=driver.derive(), skill_names=[])
            assert "echo" in {tool.name for tool in candidate.tools}
            assert [message.get("tool_call_id") for message in candidate.messages if message["role"] == "tool"] == ["load"]
            assert_paired(candidate.messages)
            candidates.append(candidate)
        return candidate

    result = execute(
        runtime(skills=[FakeSkill("worker", {"echo"})], tools=[EchoTool()]),
        driver,
        before_tool_result=before_result,
        estimate_request_tokens=lambda request: 100 if request.messages[0]["content"] != "summary" else 20,
        context_window_tokens=90,
        reserved_output_tokens=10,
    )
    assert len(candidates) == 2
    assert result.output["tool_results"][0]["output"] == {"value": "ok"}
    assert [message.get("tool_call_id") for message in driver.messages if message["role"] == "tool"] == ["load", "echo"]
    assert_paired(driver.messages)


def test_skill_projection_restores_surviving_skills_from_events():
    driver = HarnessDriver(
        call("load", "load_skill", name="worker"),
        call("echo", "echo", value="ok"),
        AssistantModelOutput(content="done"),
    )

    def derive_skills():
        return (
            ["worker", "worker", "", "missing"]
            if any(item.get("name") == "load_skill" for item in driver.messages)
            else []
        )

    result = execute(
        runtime(skills=[FakeSkill("worker", {"echo"})], tools=[EchoTool()]),
        driver,
        derive_skill_names=derive_skills,
    )
    assert "echo" not in {item.name for item in driver.requests[0].tools}
    assert "echo" in {item.name for item in driver.requests[1].tools}
    assert result.output["tool_results"][0]["output"] == {"value": "ok"}
    assert_paired(driver.messages)


@pytest.mark.parametrize("overflow_before_tool", [True, False])
def test_overflow_retries_only_model_call_and_never_reexecutes_tools(overflow_before_tool):
    tool = LogicalPagesTool()
    output = call("pages", tool.name)
    driver = ErrorDriver(
        *([overflow(), output] if overflow_before_tool else [output, overflow()]),
        AssistantModelOutput(content="done"),
    )
    calls = []
    forced = []

    def prepare(request, rebuild, force):
        calls.append(force)
        if force:
            forced.append(request)
            # Simulate a Service checkpoint which replaces older history only.
            driver.messages[0] = {"role": "user", "content": "summary"}
            return replace(request, messages=tuple(driver.derive()))
        return request

    result = execute(runtime(tools=[tool], max_actions=2), driver, prepare_request=prepare)

    assert calls == ([False, True, False] if overflow_before_tool else [False, False, True])
    assert len(driver.requests) == 3
    assert len(forced) == 1
    assert tool.calls == 1
    assert len(result.output["tool_results"]) == 1
    assert sum(event.type == "assistant_tool_calls" for event in result.events) == 1
    for request in driver.requests:
        assert_paired(request.messages)
    assert_paired(driver.messages)


def test_forced_preparation_tools_authorize_retry_output():
    tool = LogicalPagesTool()
    driver = ErrorDriver(
        overflow(), call("denied", tool.name), AssistantModelOutput(content="done")
    )

    def prepare(request, rebuild, force):
        return replace(request, tools=()) if force else request

    result = execute(runtime(tools=[tool]), driver, prepare_request=prepare)
    assert driver.requests[1].tools == ()
    assert tool.calls == 0
    error = next(event for event in result.events if event.type == "tool_error")
    assert error.payload["error"]["code"] == "TOOL_NOT_ALLOWED"
    assert_paired(driver.messages)


def test_second_overflow_propagates_without_another_compaction_or_action():
    first, second = overflow(), overflow()
    driver = ErrorDriver(first, second)
    calls = []

    def prepare(request, rebuild, force):
        calls.append(force)
        return replace(request, messages=()) if force else request

    with pytest.raises(ProviderChatCompletionError) as caught:
        execute(runtime(), driver, prepare_request=prepare)
    assert caught.value is second
    assert calls == [False, True]
    assert len(driver.requests) == 2
    assert len(driver.messages) == 1


def test_service_no_progress_error_stops_retry():
    driver = ErrorDriver(overflow())
    failure = RuntimeError("compaction made no progress")

    def prepare(request, rebuild, force):
        if force:
            raise failure
        return request

    with pytest.raises(RuntimeError) as caught:
        execute(runtime(), driver, prepare_request=prepare)
    assert caught.value is failure
    assert len(driver.requests) == 1


@pytest.mark.parametrize("code", [None, "RATE_LIMIT_EXCEEDED"])
def test_other_provider_errors_do_not_force_compaction(code):
    failure = ProviderChatCompletionError("provider failed")
    if code:
        failure.code = code
    driver = ErrorDriver(failure)
    calls = []

    def prepare(request, rebuild, force):
        calls.append(force)
        return request

    with pytest.raises(ProviderChatCompletionError) as caught:
        execute(runtime(), driver, prepare_request=prepare)
    assert caught.value is failure
    assert calls == [False]
    assert len(driver.requests) == 1


def test_overflow_without_callbacks_preserves_provider_error():
    failure = overflow()
    driver = ErrorDriver(failure)
    with pytest.raises(ProviderChatCompletionError) as caught:
        execute(runtime(), driver)
    assert caught.value is failure
    assert len(driver.requests) == 1


def page_tokens(request):
    tokens = 10 if request.system == "compacted" else 100
    for message in request.messages:
        if message["role"] == "tool" and message.get("name") == "logical_pages":
            observation = json.loads(message["content"])
            output = decode_tabular_json(observation.get("output", {}))
            tokens += 20 * len(output.get("rows", []))
    return tokens


@pytest.mark.parametrize("available_tokens, fitted_pages", [(70, None), (55, 2)])
def test_tool_candidate_is_complete_and_reestimated_with_rebuilt_system_and_tools(
    available_tokens, fitted_pages
):
    tool = LogicalPagesTool()
    driver = HarnessDriver(call("pages", tool.name), AssistantModelOutput(content="done"))
    candidates = []
    estimates = []
    section = PromptContextSection("system_prompt", "Prepared", "prepared")

    def prepare(request, rebuild, force):
        assert force is False
        return replace(
            request,
            system=section.content,
            context_sections=(section,),
            tool_choice="required",
            model_config={"purpose": "agent_action", "temperature": 0.2},
            transport_mode="text",
        )

    def before_result(candidate, rebuild):
        candidates.append(candidate)
        assert candidate.system == "prepared"
        assert candidate.context_sections == (section,)
        assert candidate.tools == driver.requests[0].tools
        assert candidate.tool_choice == "required"
        assert candidate.model_config == driver.requests[0].model_config
        assert candidate.transport_mode == "text"
        assert not any(message["role"] == "tool" for message in driver.messages)
        assert_paired(candidate.messages)
        output = decode_tabular_json(json.loads(candidate.messages[-1]["content"])["output"])
        assert [row["position"] for row in output["rows"]] == [1, 2, 3]
        rebuilt_section = PromptContextSection("system_prompt", "Compacted", "compacted")
        return replace(
            candidate,
            system="compacted",
            context_sections=(rebuilt_section,),
            tools=(),
            messages=(
                {"role": "user", "content": "summary"},
                *candidate.messages[1:],
                {"role": "user", "content": "resource context"},
            ),
        )

    def estimate(request):
        estimates.append(request)
        return page_tokens(request)

    result = execute(
        runtime(tools=[tool]),
        driver,
        prepare_request=prepare,
        before_tool_result=before_result,
        estimate_request_tokens=estimate,
        context_window_tokens=available_tokens + 10,
        reserved_output_tokens=10,
    )
    assert tool.calls == 1
    assert len(candidates) == 1
    assert estimates[0] is candidates[0]
    for request in estimates[1:]:
        assert request.system == "compacted"
        assert request.tools == ()
        assert request.messages[0]["content"] == "summary"
        assert request.messages[-1]["content"] == "resource context"
        assert_paired(request.messages)
    if fitted_pages is None:
        assert len(result.output["tool_results"]) == 1
        assert len(estimates) == 2
    else:
        assert len(result.output["tool_results"]) == 1
        assert len(result.output["tool_results"][0]["output"]["rows"]) == 3
        error = next(event for event in result.events if event.type == "tool_error")
        assert error.payload["error"]["details"] == {
            "tool_name": tool.name,
            "logical_total_pages": 3,
            "fitted_pages": fitted_pages,
            "estimated_required_tokens": 70,
            "available_tokens": available_tokens,
            "context_window_tokens": available_tokens + 10,
            "reserved_output_tokens": 10,
            "execution_completed": True,
            "effects": {},
        }
        assert "甲" not in json.dumps(error.payload["error"], ensure_ascii=False)
    assert_paired(driver.messages)


def test_candidate_does_not_mutate_derived_history_or_compact_below_threshold():
    tool = LogicalPagesTool()
    driver = HarnessDriver(call("pages", tool.name), AssistantModelOutput(content="done"))

    def before_result(_request, rebuild):
        pytest.fail("a result below the threshold must not trigger compaction")

    result = runtime(tools=[tool]).execute(
        AgentContext(account_id="alice", member_id="alice-member", task_type="conversation"),
        derive_messages=lambda: driver.messages,
        complete_model=driver.complete,
        on_event=driver.record,
        before_tool_result=before_result,
        estimate_request_tokens=lambda _request: 50,
        context_window_tokens=80,
        reserved_output_tokens=10,
    )
    assert len(result.output["tool_results"]) == 1
    assert_paired(driver.messages)


def test_batched_candidates_include_prior_results_once_after_checkpoint():
    tool = LogicalPagesTool()
    driver = HarnessDriver(
        AssistantModelOutput(tool_calls=(
            ToolCall("first", tool.name, {}), ToolCall("second", tool.name, {})
        )),
        AssistantModelOutput(content="done"),
    )
    candidates = []

    def before_result(candidate, rebuild):
        candidates.append(candidate)
        driver.messages[0] = {"role": "user", "content": "summary"}
        return rebuild(messages=driver.derive(), skill_names=[])

    def estimate(request):
        return 100 if request.messages[0]["content"] != "summary" else 20

    result = execute(
        runtime(tools=[tool]), driver, before_tool_result=before_result,
        estimate_request_tokens=estimate, context_window_tokens=90,
        reserved_output_tokens=10,
    )
    assert len(candidates) == 1
    assert tool.calls == 2
    assert len(result.output["tool_results"]) == 2
    assert [message.get("tool_call_id") for message in driver.messages if message["role"] == "tool"] == ["first", "second"]
    assert_paired(driver.requests[-1].messages)
    assert_paired(driver.messages)


class WritingTool(LogicalPagesTool):
    def run(self, arguments):
        super().run(arguments)
        return ToolResult(
            name=self.name,
            output={"saved_payload": "large-result-" * 1000},
            effects={"affected_resource_refs": [{"resource_type": "report", "resource_id": "r1"}]},
        )


class InspectEffectsTool(DirectEchoTool):
    def bind_runtime_arguments(self, arguments, *, context, observations):
        self.observations = deepcopy(observations)
        return super().bind_runtime_arguments(arguments, context=context, observations=observations)


@pytest.mark.parametrize("with_compaction", [True, False])
def test_oversized_write_retains_effects_and_raw_result_without_duplicate_reply(with_compaction):
    writer, reader = WritingTool(), InspectEffectsTool()
    driver = HarnessDriver(
        call("write", writer.name),
        call("inspect", reader.name, value="ok"),
        AssistantModelOutput(content="done"),
    )
    callbacks = {"before_tool_result": lambda request, rebuild: request} if with_compaction else {}
    result = execute(
        runtime(tools=[writer, reader]), driver,
        estimate_request_tokens=lambda request: (
            100 if "large-result-" in request.messages[-1]["content"] else 10
        ),
        context_window_tokens=90, reserved_output_tokens=10, **callbacks,
    )
    assert writer.calls == 1
    actual = result.output["tool_results"][0]
    assert actual["output"]["saved_payload"] == "large-result-" * 1000
    assert reader.observations == [actual]
    error = next(event for event in result.events if event.type == "tool_error")
    details = error.payload["error"]["details"]
    assert details["execution_completed"] is True
    assert details["effects"] == actual["effects"]
    assert "large-result-" not in json.dumps(error.payload["error"])
    assert error.payload["output"]["output"] == actual["output"]
    assert "large-result-" not in json.dumps(driver.requests[-1].messages)
    assert not any(
        event.type == "tool_result" and event.payload["call_id"] == "write"
        for event in result.events
    )
    assert_paired(driver.messages)


def test_tool_compaction_failure_keeps_completed_effects_in_paired_error():
    writer = WritingTool()
    driver = HarnessDriver(call("write", writer.name))
    failure = RuntimeError("compaction made no progress")

    def before_result(_candidate, rebuild):
        raise failure

    with pytest.raises(RuntimeError) as caught:
        execute(
            runtime(tools=[writer]), driver, before_tool_result=before_result,
            estimate_request_tokens=lambda _request: 100,
            context_window_tokens=90, reserved_output_tokens=10,
        )
    assert caught.value is failure
    assert writer.calls == 1
    error = json.loads(driver.messages[-1]["content"])["error"]
    assert error["details"]["execution_completed"] is True
    assert error["details"]["effects"]["affected_resource_refs"][0]["resource_id"] == "r1"
    assert "large-result-" not in json.dumps(driver.messages)
    assert_paired(driver.messages)

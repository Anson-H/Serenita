from tests.agent_support import BatchTool, DirectEchoTool, EchoTool, FailingTool, FakeSkill, HarnessDriver, LogicalPagesTool, TableTool, call, runtime
import json
from datetime import datetime, timedelta, timezone
import pytest
from backend.app.agent_runtime.context import AgentContext
from backend.app.agent_runtime.model_types import AssistantModelOutput, ModelRequest, PromptContextSection, ToolCall
from backend.app.agent_runtime.prompts import SYSTEM_PROMPT
from backend.app.agent_runtime.runtime import AgentHarnessRuntime
from backend.app.core.tabular_json import decode_tabular_json
from backend.app.providers.errors import ProviderChatCompletionError
from backend.app.plugins.medical_report.tools.import_tools import CreateReportTool


def test_runtime_context_includes_current_time_without_attachments(monkeypatch):
    frozen_now = datetime(2026, 8, 19, 2, 30, 0, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr("backend.app.agent_runtime.runtime.local_now", lambda: frozen_now)
    driver = HarnessDriver(AssistantModelOutput(content="完成。"))

    result = runtime().execute(
        AgentContext(account_id="alice", task_type="conversation", memory={}, member_id="alice-member"),
        derive_messages=driver.derive,
        complete_model=driver.complete,
        on_event=driver.record,
    )

    assert result.output["status"] == "completed"
    request = driver.requests[0]
    runtime_metadata = next(
        section
        for section in request.context_sections
        if section.context_type == "runtime_context"
    )
    assert runtime_metadata.label == "运行时元数据"
    assert "current_time" in request.system
    assert '"current_time":"2026-08-19T02:30:00+08:00"' in request.system
    assert "current_date" not in request.system
    assert '"visible_attachments":[]' in request.system
    assert request.system.startswith(SYSTEM_PROMPT + "\n\n")


def test_context_sections_must_exactly_match_the_model_system_prompt():
    section = PromptContextSection(
        context_type="system_prompt",
        label="系统提示词",
        content="truthful prompt",
    )

    request = ModelRequest.build(
        system="truthful prompt",
        messages=[],
        context_sections=[section],
    )
    assert request.context_sections == (section,)

    with pytest.raises(ValueError, match="exactly reconstruct"):
        ModelRequest.build(
            system="different prompt",
            messages=[],
            context_sections=[section],
        )


def execute(runtime_instance, driver):
    return runtime_instance.execute(
        AgentContext(account_id="alice", task_type="conversation", input_text="test", member_id="alice-member"),
        derive_messages=driver.derive,
        complete_model=driver.complete,
        on_event=driver.record,
    )


def _logical_page_request_tokens(request):
    row_count = 0
    for message in request.messages:
        if message.get("role") != "tool" or message.get("name") != "logical_pages":
            continue
        content = message.get("content")
        payload = json.loads(content) if isinstance(content, str) else content
        output = payload.get("output") if isinstance(payload, dict) else None
        decoded = decode_tabular_json(output)
        if isinstance(decoded, dict) and isinstance(decoded.get("rows"), list):
            row_count += len(decoded["rows"])
    return 50 + (row_count * 10)


def test_logical_pages_are_assembled_once_in_order_at_exact_budget_boundary():
    tool = LogicalPagesTool()
    driver = HarnessDriver(
        call("page-call", "logical_pages"),
        AssistantModelOutput(content="已读取完整结果。"),
    )

    result = runtime(tools=[tool]).execute(
        AgentContext(account_id="alice", task_type="conversation", input_text="test", member_id="alice-member"),
        derive_messages=driver.derive,
        complete_model=driver.complete,
        on_event=driver.record,
        estimate_request_tokens=_logical_page_request_tokens,
        context_window_tokens=90,
        reserved_output_tokens=10,
    )

    assert tool.calls == 1
    assert [event.type for event in result.events].count("tool_call") == 1
    assert [event.type for event in result.events].count("tool_result") == 1
    assert result.output["tool_results"][0]["output"] == {
        "total": 3,
        "rows": [
            {"position": 1, "value": "甲"},
            {"position": 2, "value": "乙"},
            {"position": 3, "value": "丙"},
        ],
    }
    persisted = next(
        event.payload["output"]
        for event in result.events
        if event.type == "tool_result" and event.payload["tool"] == "logical_pages"
    )
    assert decode_tabular_json(persisted["output"]) == result.output["tool_results"][0]["output"]


def test_logical_pages_fail_without_partial_results_when_complete_result_is_too_large():
    tool = LogicalPagesTool()
    driver = HarnessDriver(
        call("page-call", "logical_pages"),
        AssistantModelOutput(content="结果过大，需缩小查询。"),
    )

    result = runtime(tools=[tool]).execute(
        AgentContext(account_id="alice", task_type="conversation", input_text="test", member_id="alice-member"),
        derive_messages=driver.derive,
        complete_model=driver.complete,
        on_event=driver.record,
        estimate_request_tokens=_logical_page_request_tokens,
        context_window_tokens=80,
        reserved_output_tokens=10,
    )

    assert tool.calls == 1
    assert len(result.output["tool_results"]) == 1
    assert len(result.output["tool_results"][0]["output"]["rows"]) == 3
    assert [event.type for event in result.events].count("tool_result") == 0
    errors = [event for event in result.events if event.type == "tool_error"]
    assert len(errors) == 1
    error = errors[0].payload["error"]
    assert error["code"] == "TOOL_RESULT_TOO_LARGE"
    assert error["details"] == {
        "tool_name": "logical_pages",
        "logical_total_pages": 3,
        "fitted_pages": 2,
        "estimated_required_tokens": 80,
        "available_tokens": 70,
        "context_window_tokens": 80,
        "reserved_output_tokens": 10,
        "execution_completed": True,
        "effects": {},
    }
    assert "甲" not in json.dumps(error, ensure_ascii=False)
    assert "甲" not in json.dumps(driver.requests[-1].messages, ensure_ascii=False)
    assert "甲" in json.dumps(errors[0].payload["output"], ensure_ascii=False)


def test_multiple_tool_calls_share_the_remaining_context_budget():
    tool = LogicalPagesTool()
    two_calls = AssistantModelOutput(
        tool_calls=(
            ToolCall(id="first", name="logical_pages", arguments={}),
            ToolCall(id="second", name="logical_pages", arguments={}),
        ),
        stop_reason="tool_calls",
    )
    driver = HarnessDriver(
        two_calls,
        AssistantModelOutput(content="第二个完整结果超出共享预算。"),
    )

    result = runtime(tools=[tool]).execute(
        AgentContext(account_id="alice", task_type="conversation", input_text="test", member_id="alice-member"),
        derive_messages=driver.derive,
        complete_model=driver.complete,
        on_event=driver.record,
        estimate_request_tokens=_logical_page_request_tokens,
        context_window_tokens=119,
        reserved_output_tokens=10,
    )

    assert tool.calls == 2
    assert len(result.output["tool_results"]) == 2
    errors = [event for event in result.events if event.type == "tool_error"]
    assert len(errors) == 1
    assert errors[0].payload["error"]["code"] == "TOOL_RESULT_TOO_LARGE"


def test_missing_context_window_uses_the_128k_safety_default():
    tool = LogicalPagesTool()
    driver = HarnessDriver(
        call("page-call", "logical_pages"),
        AssistantModelOutput(content="结果过大。"),
    )

    result = runtime(tools=[tool]).execute(
        AgentContext(account_id="alice", task_type="conversation", input_text="test", member_id="alice-member"),
        derive_messages=driver.derive,
        complete_model=driver.complete,
        on_event=driver.record,
        estimate_request_tokens=lambda _request: 127_000,
        context_window_tokens=None,
        reserved_output_tokens=4096,
    )

    error = next(event for event in result.events if event.type == "tool_error")
    assert error.payload["error"]["code"] == "TOOL_RESULT_TOO_LARGE"
    assert error.payload["error"]["details"]["context_window_tokens"] == 131_072
    assert error.payload["error"]["details"]["available_tokens"] == 126_976


@pytest.mark.parametrize(
    "payload",
    [
        {
            "goal": "x",
            "open_questions": [],
            "milestones": [],
            "completion_criteria": ["done"],
            "intent": "report",
        },
        {
            "goal": "x",
            "open_questions": [],
            "milestones": [],
            "completion_criteria": ["done"],
            "skills": ["report-query"],
        },
    ],
)
def test_update_plan_schema_rejects_capability_bound_shapes(payload):
    driver = HarnessDriver(
        call("p1", "update_plan", **payload),
        AssistantModelOutput(content="计划参数无效，但仍可继续。"),
    )

    result = execute(runtime(), driver)

    assert "TOOL_ARGUMENTS_INVALID" in json.dumps(
        driver.requests[1].messages, ensure_ascii=False
    )
    assert result.output["status"] == "completed"


def test_initial_request_only_exposes_control_tools_and_direct_answer_is_terminal():
    driver = HarnessDriver(AssistantModelOutput(content="你好"))
    harness = runtime(skills=[FakeSkill("worker")])
    assert harness.skill_registry.catalog() == [
        {"name": "worker", "description": "worker capability"}
    ]
    result = execute(harness, driver)
    assert [item.name for item in driver.requests[0].tools] == [
        "load_skill",
        "update_plan",
    ]
    skill_schema = driver.requests[0].tools[0].parameters
    assert skill_schema["required"] == ["name"]
    assert set(skill_schema["properties"]) == {"name"}
    assert skill_schema["properties"]["name"]["enum"] == ["worker"]
    assert skill_schema["properties"]["name"]["description"] == (
        "技能目录中要读取的技能名称。"
    )
    assert skill_schema["additionalProperties"] is False
    assert "TASK_PLAN_CONTEXT" not in driver.requests[0].system
    assert "loaded_skill_names" not in result.output
    assert result.output["terminal_action"]["content"] == "你好"


def test_direct_tools_are_visible_from_first_step_without_changing_skill_catalog():
    driver = HarnessDriver(AssistantModelOutput(content="done"))
    execute(
        runtime(
            skills=[FakeSkill("worker", {"echo"})],
            tools=[EchoTool(), DirectEchoTool()],
        ),
        driver,
    )

    assert [item.name for item in driver.requests[0].tools] == [
        "load_skill",
        "update_plan",
        "direct_echo",
    ]
    skill_catalog = next(
        section
        for section in driver.requests[0].context_sections
        if section.context_type == "skill_catalog"
    )
    assert skill_catalog.label == "1 个可用技能"
    assert "direct_echo" not in skill_catalog.content


def test_initial_skill_names_restore_application_tools_on_first_request():
    driver = HarnessDriver(AssistantModelOutput(content="done"))
    restored_runtime = runtime(
        skills=[FakeSkill("worker", {"echo"})],
        tools=[EchoTool()],
    )

    result = restored_runtime.execute(
        AgentContext(account_id="alice", task_type="conversation", input_text="test", member_id="alice-member"),
        initial_skill_names=["worker"],
        derive_messages=driver.derive,
        complete_model=driver.complete,
        on_event=driver.record,
    )

    assert [item.name for item in driver.requests[0].tools] == [
        "load_skill",
        "update_plan",
        "echo",
    ]
    assert result.output["terminal_action"]["content"] == "done"


def test_skill_read_changes_next_step_tool_union_and_plain_content_can_finish():
    driver = HarnessDriver(
        call("a1", "load_skill", name="one"),
        call("a2", "load_skill", name="two"),
        AssistantModelOutput(content="需要用户补充信息。"),
    )
    result = execute(
        runtime(
            skills=[FakeSkill("one", {"echo"}), FakeSkill("two", {"failing"})],
            tools=[EchoTool(), FailingTool()],
        ),
        driver,
    )
    assert "echo" in {item.name for item in driver.requests[1].tools}
    skill_schema_after_first_read = next(
        item for item in driver.requests[1].tools if item.name == "load_skill"
    )
    assert skill_schema_after_first_read.parameters["properties"]["name"]["enum"] == [
        "one",
        "two",
    ]
    assert {"echo", "failing"}.issubset(
        {item.name for item in driver.requests[2].tools}
    )
    skill_schema_after_second_read = next(
        item for item in driver.requests[2].tools if item.name == "load_skill"
    )
    assert skill_schema_after_second_read.parameters["properties"]["name"]["enum"] == [
        "one",
        "two",
    ]
    assert result.output["terminal_action"]["content"] == "需要用户补充信息。"


def test_load_skill_tool_outputs_only_the_complete_instruction_text():
    driver = HarnessDriver(
        call("a1", "load_skill", name="worker"),
        AssistantModelOutput(content="已读取完整能力。"),
    )

    execute(
        runtime(skills=[FakeSkill("worker", {"echo"})], tools=[EchoTool()]),
        driver,
    )

    read_output = next(
        message["content"]
        for message in driver.messages
        if message.get("role") == "tool"
        and message.get("name") == "load_skill"
    )
    assert read_output == "Use observed evidence only."
    next_load_skill = next(
        item for item in driver.requests[1].tools if item.name == "load_skill"
    )
    assert next_load_skill.parameters["properties"]["name"]["enum"] == ["worker"]
    next_request_read_output = next(
        message["content"]
        for message in driver.requests[1].messages
        if message.get("role") == "tool" and message.get("name") == "load_skill"
    )
    assert next_request_read_output == read_output


def test_harness_does_not_hide_or_block_an_already_read_skill():
    driver = HarnessDriver(
        call("a1", "load_skill", name="worker"),
        call("a2", "load_skill", name="worker"),
        AssistantModelOutput(content="done"),
    )

    execute(
        runtime(skills=[FakeSkill("worker", {"echo"})], tools=[EchoTool()]),
        driver,
    )

    assert all(
        next(item for item in request.tools if item.name == "load_skill")
        .parameters["properties"]["name"]["enum"] == ["worker"]
        for request in driver.requests
    )
    repeated_outputs = [
        message["content"]
        for message in driver.messages
        if message.get("role") == "tool" and message.get("name") == "load_skill"
    ]
    assert repeated_outputs == [
        "Use observed evidence only.",
        "Use observed evidence only.",
    ]


def test_tool_schema_strictly_rejects_provider_encoded_nested_json_and_numbers():
    driver = HarnessDriver(
        call("a1", "load_skill", name="worker"),
        call(
            "a2",
            "batch",
            operation="store",
            items=json.dumps([{"value": "x"}]),
            limit="24",
        ),
        call(
            "a3",
            "batch",
            operation="store",
            items=[{"value": "x"}],
            limit=24,
        ),
        AssistantModelOutput(content="done"),
    )

    result = execute(
        runtime(
            skills=[FakeSkill("worker", {"batch"})],
            tools=[BatchTool()],
        ),
        driver,
    )

    assistant_calls = [
        message["tool_calls"][0]["function"]["arguments"]
        for message in driver.messages
        if message.get("tool_calls")
        and message["tool_calls"][0]["function"]["name"] == "batch"
    ]
    assert json.loads(assistant_calls[0])["items"] == '[{"value": "x"}]'
    assert json.loads(assistant_calls[0])["limit"] == "24"
    assert "TOOL_ARGUMENTS_INVALID" in json.dumps(
        driver.requests[2].messages, ensure_ascii=False
    )
    assert result.output["tool_results"][0]["output"] == {
        "stored": [{"value": "x"}],
        "limit": 24,
    }


def test_one_of_validation_reports_the_selected_operation_field_error():
    with pytest.raises(ValueError, match=r"arguments\.items 必须是数组"):
        AgentHarnessRuntime._validate_schema(
            {"operation": "store", "items": "not-json"},
            BatchTool.input_schema,
            label="arguments",
        )


def test_tool_results_and_errors_are_observations_in_the_next_request():
    driver = HarnessDriver(
        call("a1", "load_skill", name="worker"),
        call("a2", "echo"),
        call("a3", "failing", value="x"),
        call("a4", "echo", value="recovered", account_id="mallory"),
        call("a5", "echo", value="recovered"),
        AssistantModelOutput(content="recovered"),
    )
    result = execute(
        runtime(
            skills=[FakeSkill("worker", {"failing", "echo"})],
            tools=[FailingTool(), EchoTool()],
        ),
        driver,
    )
    serialized = json.dumps(driver.requests[-1].messages, ensure_ascii=False)
    assert "TOOL_ARGUMENTS_INVALID" in serialized
    assert "temporary failure" in serialized
    assert "SERVER_BOUND_ARGUMENT_REJECTED" in serialized
    assert result.output["tool_results"][-1]["output"]["value"] == "recovered"
    successful_echo = next(
        json.loads(message["content"])
        for message in driver.requests[-1].messages
        if message.get("role") == "tool"
        and message.get("name") == "echo"
        and "recovered" in message.get("content", "")
    )
    assert successful_echo["call_id"] == "a5"


def test_tabular_tool_output_is_encoded_on_the_wire_and_raw_in_turn():
    events = []
    driver = HarnessDriver(
        call("a1", "load_skill", name="worker"),
        call("a2", "table"),
        AssistantModelOutput(content="done"),
    )
    result = runtime(
        skills=[FakeSkill("worker", {"table"})],
        tools=[TableTool()],
    ).execute(
        AgentContext(account_id="alice", task_type="conversation", input_text="test", member_id="alice-member"),
        derive_messages=driver.derive,
        complete_model=driver.complete,
        on_event=lambda event: (events.append(event), driver.record(event)),
    )

    emitted = next(
        event
        for event in events
        if event.type == "tool_result" and event.payload.get("tool") == "table"
    )
    envelope = emitted.payload["output"]
    assert envelope["output"] == {
        "rows": {
            "$keys": ["item", "value"],
            "$rows": [["甲", 1], ["乙", 2]],
        }
    }
    assert result.output["tool_results"][-1]["output"] == {
        "rows": [{"item": "甲", "value": 1}, {"item": "乙", "value": 2}]
    }
    wire = json.loads(driver.messages[-1]["content"])
    assert wire["output"] == envelope["output"]


def test_update_plan_is_an_ordinary_tool_result():
    created = {
        "goal": "等待用户补充",
        "open_questions": ["目标日期是什么？"],
        "milestones": ["读取日期"],
        "completion_criteria": ["日期明确"],
    }
    events = []
    driver = HarnessDriver(
        call("p1", "update_plan", **created),
        AssistantModelOutput(content="目标日期是什么？"),
    )
    result = runtime().execute(
        AgentContext(account_id="alice", task_type="conversation", input_text="test", member_id="alice-member"),
        derive_messages=driver.derive,
        complete_model=driver.complete,
        on_event=lambda event: (events.append(event), driver.record(event)),
    )

    update_events = [
        event
        for event in events
        if event.payload.get("tool") == "update_plan"
    ]
    assert [event.type for event in update_events] == ["tool_call", "tool_result"]
    assert update_events[1].payload["output"]["output"] == created
    assert result.output["tool_results"][-1]["output"] == created
    assert "task_plan" not in result.output
    assert not any(
        event.type in {"plan_created", "plan_updated"}
        for event in events
    )
    assert all(
        "TASK_PLAN_CONTEXT" not in request.system
        for request in driver.requests
    )
    assert all(
        section.context_type != "task_plan_context"
        for request in driver.requests
        for section in request.context_sections
    )
    observation = json.loads(
        next(
            message["content"]
            for message in driver.requests[1].messages
            if message.get("role") == "tool"
            and message.get("name") == "update_plan"
        )
    )
    assert observation == update_events[1].payload["output"]
    assert observation["type"] == "tool_result"
    assert result.output["terminal_action"]["content"] == "目标日期是什么？"


def test_invalid_update_plan_is_an_observation_and_does_not_fail_the_turn():
    driver = HarnessDriver(
        call("p1", "update_plan", goal="缺少其它字段"),
        AssistantModelOutput(content="我无法建立计划，但仍可直接说明当前结果。"),
    )

    result = execute(runtime(), driver)

    assert "task_plan" not in result.output
    assert "TOOL_ARGUMENTS_INVALID" in json.dumps(
        driver.requests[1].messages, ensure_ascii=False
    )
    assert result.output["status"] == "completed"


def test_repeated_update_plan_calls_are_independent_ordinary_tool_results():
    first = {
        "goal": "先读取资料",
        "open_questions": [],
        "milestones": ["读取资料"],
        "completion_criteria": ["资料完整"],
    }
    revised = {
        "goal": "说明资料不可用",
        "open_questions": ["是否稍后重试？"],
        "milestones": [],
        "completion_criteria": ["如实说明限制"],
    }
    events = []
    driver = HarnessDriver(
        call("p1", "update_plan", **first),
        call("p2", "update_plan", **revised),
        AssistantModelOutput(content="当前资料不可用，因此这次无法执行。"),
    )

    result = runtime().execute(
        AgentContext(account_id="alice", task_type="conversation", input_text="test", member_id="alice-member"),
        derive_messages=driver.derive,
        complete_model=driver.complete,
        on_event=lambda event: (events.append(event), driver.record(event)),
    )

    update_events = [
        event
        for event in events
        if event.payload.get("tool") == "update_plan"
    ]
    assert [event.type for event in update_events] == [
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
    ]
    assert [item["output"] for item in result.output["tool_results"]] == [
        first,
        revised,
    ]
    assert "task_plan" not in result.output
    assert result.output["status"] == "completed"
    assert result.output["terminal_action"]["content"].endswith("无法执行。")


def test_repeated_identical_tool_calls_become_observations_and_hit_action_budget():
    outputs = [
        call("a1", "load_skill", name="worker"),
        call("a2", "echo", value="x"),
        call("a3", "echo", value="x"),
        call("a4", "echo", value="x"),
    ]
    driver = HarnessDriver(*outputs)
    with pytest.raises(RuntimeError, match="最大行动次数"):
        execute(
            runtime(
                skills=[FakeSkill("worker", {"echo"})],
                tools=[EchoTool()],
                max_actions=len(outputs),
            ),
            driver,
        )
    assert "REPEATED_TOOL_CALL_LIMIT" in json.dumps(driver.messages, ensure_ascii=False)


def test_repeated_schema_failures_suspend_the_tool_instead_of_consuming_the_turn():
    driver = HarnessDriver(
        call("a1", "load_skill", name="worker"),
        call("a2", "echo"),
        call("a3", "echo"),
        call("a4", "echo"),
        AssistantModelOutput(content="参数始终无效，已停止调用。"),
    )

    result = execute(
        runtime(
            skills=[FakeSkill("worker", {"echo"})],
            tools=[EchoTool()],
        ),
        driver,
    )

    assert "REPEATED_INVALID_TOOL_ARGUMENTS" in json.dumps(
        driver.messages, ensure_ascii=False
    )
    assert "echo" not in {item.name for item in driver.requests[4].tools}
    assert result.output["status"] == "completed"


def test_attachment_resource_is_explicit_in_tool_schema_and_guesses_are_rejected():
    report = {
        "report_type": "其它医疗报告",
        "report_name": "测试医疗报告",
        "report_time": "2026-08-01",
        "source_kind": "unknown",
        "institution_name": None,
        "lab_test_results": [],
        "examination_report": None,
        "pathology_report": None,
        "surgery_report": None,
        "other_report": {"report_body": "内容"},
    }
    driver = HarnessDriver(
        call("a1", "load_skill", name="worker"),
        call(
            "a2",
            "create_report",
            sources=[{'source_type': 'conversation_attachment', 'resource_id': 'attachment_1'}], report=report,
        ),
        AssistantModelOutput(content="附件标识无效，已停止导入。"),
    )
    instance = runtime(
        skills=[FakeSkill("worker", {"create_report"})],
        tools=[CreateReportTool(account_id="alice", service=object(), member_id="alice-member")],
    )
    result = instance.execute(
        AgentContext(
            account_id="alice",
            task_type="conversation",
            input_text="导入附件",
            session_id="session",
            resources=[{"resource_type": "file", "resource_id": "actual-resource"}],
            memory={
                "visible_attachments": {
                    "actual-resource": {
                        "resource_id": "actual-resource",
                        "original_filename": "检验报告.jpg",
                        "mime_type": "image/jpeg",
                        "path": "/trusted/report.jpg",
                        "sha256": "digest",
                    }
                }
            }, member_id="alice-member"),
        derive_messages=driver.derive,
        complete_model=driver.complete,
        on_event=driver.record,
    )

    validate_schema = next(
        item for item in driver.requests[1].tools if item.name == "create_report"
    )
    sources_schema = validate_schema.parameters
    source_union = sources_schema["properties"]["sources"]["items"]["oneOf"]
    assert source_union[1]["properties"]["resource_id"]["enum"] == ["actual-resource"]
    runtime_metadata = next(
        section
        for section in driver.requests[1].context_sections
        if section.context_type == "runtime_context"
    )
    assert runtime_metadata.label == "运行时元数据"
    assert "actual-resource" in driver.requests[1].system
    assert "检验报告.jpg" in driver.requests[1].system
    assert "TOOL_ARGUMENTS_INVALID" in json.dumps(
        driver.requests[2].messages, ensure_ascii=False
    )
    assert result.output["status"] == "completed"


def test_single_attachment_cannot_omit_resource_id_at_runtime():
    report = {
        "report_type": "其它医疗报告",
        "report_name": "测试医疗报告",
        "report_time": "2026-08-01",
        "source_kind": "unknown",
        "institution_name": None,
        "lab_test_results": [],
        "examination_report": None,
        "pathology_report": None,
        "surgery_report": None,
        "other_report": {"report_body": "内容"},
    }
    driver = HarnessDriver(
        call("a1", "load_skill", name="worker"),
        call(
            "a2",
            "create_report",
            sources=[{'source_type': 'conversation_attachment'}], report=report,
        ),
        AssistantModelOutput(content="缺少明确附件标识，未执行导入。"),
    )
    instance = runtime(
        skills=[FakeSkill("worker", {"create_report"})],
        tools=[CreateReportTool(account_id="alice", service=object(), member_id="alice-member")],
    )
    result = instance.execute(
        AgentContext(
            account_id="alice",
            task_type="conversation",
            session_id="session",
            memory={
                "visible_attachments": {
                    "only-resource": {
                        "resource_id": "only-resource",
                        "original_filename": "only.jpg",
                        "mime_type": "image/jpeg",
                    }
                }
            }, member_id="alice-member"),
        derive_messages=driver.derive,
        complete_model=driver.complete,
        on_event=driver.record,
    )

    assert "TOOL_ARGUMENTS_INVALID" in json.dumps(
        driver.requests[2].messages, ensure_ascii=False
    )
    assert result.output["status"] == "completed"


def test_text_tool_protocol_failure_is_observed_without_automatic_repair():
    driver = HarnessDriver()
    attempts = 0

    def invalid(_request):
        nonlocal attempts
        attempts += 1
        raise ProviderChatCompletionError("文本工具协议返回的内容不是有效 JSON")

    with pytest.raises(ProviderChatCompletionError, match="文本工具协议"):
        runtime(max_actions=4).execute(
            AgentContext(account_id="alice", task_type="conversation", member_id="alice-member"),
            derive_messages=driver.derive,
            complete_model=invalid,
            on_event=driver.record,
        )
    assert attempts == 1
    assert json.dumps(driver.messages, ensure_ascii=False).count(
        "TEXT_TOOL_PROTOCOL_INVALID"
    ) == 1

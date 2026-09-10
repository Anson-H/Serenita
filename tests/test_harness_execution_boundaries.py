"""Regression coverage for model conversion and executed-tool boundaries."""
import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from backend.app.agent_runtime.context import AgentContext
from backend.app.agent_runtime.model_types import AssistantModelOutput, ModelRequest, ModelStreamChunk, ToolCall, ToolCallDelta, ToolSchema
from backend.app.agent_runtime.skills.base import SkillDocument
from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.application.conversations.model_calls import ModelCallRecorder
from backend.app.application.model_provider_service import ModelProviderService
from backend.app.core.cancellation import OperationCancelledError
from backend.app.providers.errors import ProviderChatCompletionError
from backend.app.domain.conversations.events import make_event
from tests.agent_support import DirectEchoTool, FakeSkill, HarnessDriver, assert_native_pairs, call, runtime
from tests.test_runtime_cancellation import session, run_harness


def execute(harness, driver, **kwargs):
    return harness.execute(AgentContext(account_id="alice", task_type="conversation"),
        derive_messages=driver.derive, complete_model=driver.complete,
        on_event=driver.record, **kwargs)


@pytest.mark.parametrize("control", ["load_skill", "update_plan"])
def test_control_result_uses_budget_and_does_not_activate_failed_skill(control):
    class LargeSkill(FakeSkill):
        def read(self, context):
            return SkillDocument(self.name, "large evidence " * 2000, frozenset({"echo"}))

    args = {"name": "worker"} if control == "load_skill" else {
        "goal": "goal", "open_questions": ["q" * 500] * 16,
        "milestones": [], "completion_criteria": ["done"],
    }
    from tests.agent_support import EchoTool
    driver = HarnessDriver(call("control", control, **args), AssistantModelOutput(content="done"))
    compactions = []
    result = execute(runtime(skills=[LargeSkill("worker", {"echo"})], tools=[EchoTool()]), driver,
        context_window_tokens=2000, reserved_output_tokens=100,
        estimate_request_tokens=lambda request: len(json.dumps(request.messages)),
        before_tool_result=lambda request, rebuild: compactions.append(request) or request)
    failure = next(event for event in result.events if event.type == "tool_error")
    assert failure.payload["error"]["code"] == "TOOL_RESULT_TOO_LARGE"
    assert failure.payload["error"]["details"]["execution_completed"] is True
    assert compactions
    assert "echo" not in {tool.name for tool in driver.requests[-1].tools}
    assert "large evidence" not in json.dumps(driver.requests[-1].messages)


@pytest.mark.parametrize("same_batch", [False, True])
def test_call_identity_conflicts_are_rejected_before_business_execution(same_batch):
    class Save(DirectEchoTool):
        def __init__(self): self.writes = []
        def run(self, arguments):
            self.writes.append(arguments["value"])
            return super().run(arguments)
    tool = Save()
    calls = [ToolCall("same", tool.name, {"value": value}) for value in ["first", "second"]]
    actions = [AssistantModelOutput(tool_calls=tuple(calls))] if same_batch else [AssistantModelOutput(tool_calls=(item,)) for item in calls]
    driver = HarnessDriver(*actions, AssistantModelOutput(content="done"))
    result = execute(runtime(tools=[tool]), driver)
    assert tool.writes == ([] if same_batch else ["first"])
    assert_native_pairs(driver.requests[-1].messages)
    assert "second" in json.dumps(driver.requests[-1].messages)
    assert any(event.type == "harness_observation" and event.payload["error"]["code"] == "TOOL_CALL_ID_CONFLICT" for event in result.events)


@pytest.mark.parametrize("reason", ["length", "max_tokens", "incomplete", "content_filter"])
def test_incomplete_content_returns_to_action_loop(reason):
    driver = HarnessDriver(AssistantModelOutput(content="partial evidence", stop_reason=reason), AssistantModelOutput(content="complete answer"))
    result = execute(runtime(), driver)
    assert len(driver.requests) == 2
    assert "partial evidence" in json.dumps(driver.requests[1].messages)
    assert "MODEL_OUTPUT_INCOMPLETE" in json.dumps(driver.requests[1].messages)
    assert [event.payload["content"] for event in result.events if event.type == "final_response"] == ["complete answer"]


def test_text_transport_keeps_assistant_content_with_calls():
    request = ModelRequest.build(system="fixture", messages=[{
        "role": "assistant", "content": "Evidence uncertainty must remain visible.",
        "tool_calls": [ToolCall("call", "lookup", {}).as_dict()],
    }], tools=[ToolSchema("lookup")])
    wire = ModelProviderService.prepare_transport_request({"supports_tool_calling": False}, request, "default")
    translated = json.loads(wire.messages[0]["content"])
    assert translated["content"] == request.messages[0]["content"]
    assert translated["calls"] == request.messages[0]["tool_calls"]


class MemoryEvents:
    def __init__(self): self.events = []
    def new_id(self): return "memory-call"
    def append_session_event(self, account_id, session_id, event_type, data, **kwargs):
        self.events.append(make_event(event_type, len(self.events), data, **kwargs))
    def append_session_events(self, account_id, session_id, specifications, **kwargs):
        for spec in specifications:
            self.append_session_event(account_id, session_id, spec["type"], spec["data"], **{key: value for key, value in spec.items() if key not in {"type", "data"}})


def record_model(monkeypatch, chunks, *, text_tool=False):
    monkeypatch.setattr("backend.app.application.conversations.model_calls.member_lifecycle_guard", lambda **kwargs: nullcontext())
    repository = MemoryEvents()
    catalog = SimpleNamespace(
        prepare_stream_chat_for_account=lambda **kwargs: SimpleNamespace(
            provider_payload={"model": "fixture", "messages": [{"role": "user", "content": "fixture"}], "stream": True},
            transport_mode="text_tool" if text_tool else "native"),
        stream_prepared_chat_for_account=lambda **kwargs: ModelProviderService._stream_text_tool_result(iter(chunks)) if text_tool else iter(chunks),
    )
    recorder = ModelCallRecorder(repository, catalog, None,
        SimpleNamespace(session_lock=lambda *args: nullcontext()),
        ensure_active=lambda *args: None, next_model_step=lambda *args: 1)
    with pytest.raises(ProviderChatCompletionError):
        recorder.complete_chat_with_events(account_id="memory", turn={"session_id": "session", "turn_id": "turn"},
            user_message={"message_id": "user"}, model={"model_id": "fixture"},
            model_request=ModelRequest.build(system="", messages=[]), thinking_mode="default", purpose="agent_action")
    return repository.events


def test_invalid_text_protocol_still_records_provider_usage(monkeypatch):
    events = record_model(monkeypatch, [ModelStreamChunk(content_delta="invalid protocol"),
        ModelStreamChunk(usage={"prompt_tokens": 123, "completion_tokens": 7, "total_tokens": 130}, stop_reason="stop")], text_tool=True)
    result = next(event for event in events if event.type == "model/result")
    assert result.data["status"] == "failed"
    assert result.data["result"]["usage"]["total_tokens"] == 130
    assert result.data["result"]["raw_content"] == "invalid protocol"


@pytest.mark.parametrize("arguments", ["{", "[]", "null", "42"])
def test_stream_finalization_records_parameter_failure_once(monkeypatch, arguments):
    events = record_model(monkeypatch, [ModelStreamChunk(
        tool_call_deltas=(ToolCallDelta(0, "call", "lookup", arguments),),
        usage={"total_tokens": 5}, stop_reason="tool_calls")])
    results = [event for event in events if event.type == "model/result"]
    assert len(results) == 1
    assert results[0].data["status"] == "failed"
    assert results[0].data["result"]["usage"] == {"total_tokens": 5}
    assert [event.data["status"] for event in events if event.type == "step/end"] == ["failed"]


class ResourceTool(Tool):
    name = "source"
    model_exposure = "direct"
    def __init__(self): self.executions = 0
    def run(self, arguments):
        self.executions += 1
        return ToolResult(self.name, {"read": "complete", "raw": "audit evidence"}, {
            "model_resource_refs": [{"resource_type": "fixture", "resource_id": "source"}],
        })


@pytest.mark.parametrize("failure", ["unsupported", "bad_pdf"])
def test_resource_preparation_failure_is_observed_after_single_execution(session, monkeypatch, failure):
    tool = ResourceTool()
    mime = "application/pdf" if failure == "bad_pdf" else "image/png"
    monkeypatch.setattr("backend.app.application.conversations.model_resources.resolve_plugin_model_resource_refs", lambda **kwargs: [{"resource_type": "fixture", "resource_id": "source", "mime_type": mime, "content_bytes": b"fixture"}])
    monkeypatch.setattr(session.service.inputs, "model_can_forward_attachment", lambda model, value: failure == "bad_pdf" and value == "image/jpeg")
    monkeypatch.setattr(session.service.model_catalog, "default_model_for_account", lambda *args: None)
    monkeypatch.setattr("backend.app.application.conversations.attachment_rendering.model_file_parts", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("PDF 文件无法读取或已损坏")))
    requests = []
    def complete(**kwargs):
        requests.append(kwargs["model_request"])
        return call("source-call", "source") if len(requests) == 1 else AssistantModelOutput(content="Cannot read this source; please provide another format.")
    result = run_harness(session, monkeypatch, tool, complete)
    assert result["status"] == "completed"
    assert tool.executions == 1 and len(requests) == 2
    outcome = next(event for event in session.events() if event.type == "tool/result")
    assert outcome.data["status"] == "failed"
    assert outcome.data["result"]["output"]["raw"] == "audit evidence"
    assert outcome.data["error"]["details"]["execution_completed"] is True
    assert "audit evidence" not in json.dumps(requests[1].messages)
    assert ("MODEL_FILE_UNSUPPORTED" if failure == "unsupported" else "PDF 文件无法读取") in json.dumps(requests[1].messages, ensure_ascii=False)


def test_resource_permission_failure_still_stops_execution(session, monkeypatch):
    tool = ResourceTool()
    monkeypatch.setattr("backend.app.application.conversations.model_resources.resolve_plugin_model_resource_refs", lambda **kwargs: (_ for _ in ()).throw(PermissionError("access revoked")))
    calls = []
    def complete(**kwargs):
        calls.append(kwargs)
        return call("source-call", "source")
    with pytest.raises(PermissionError): run_harness(session, monkeypatch, tool, complete)
    assert len(calls) == 1 and tool.executions == 1
    outcome = next(event for event in session.events() if event.type == "tool/result")
    assert outcome.data["error"]["details"]["execution_completed"] is True


def test_rejected_resource_budget_rolls_back_model_input(session, monkeypatch):
    tool = ResourceTool()
    monkeypatch.setattr("backend.app.application.conversations.model_resources.resolve_plugin_model_resource_refs", lambda **kwargs: [{"resource_type": "fixture", "resource_id": "source", "mime_type": "image/png", "content_bytes": b"large snapshot" * 100000}])
    monkeypatch.setattr(session.service.inputs, "model_can_forward_attachment", lambda *args: True)
    monkeypatch.setattr(session.service.model_catalog, "default_model_for_account", lambda *args: None)
    requests = []
    def complete(**kwargs):
        requests.append(kwargs["model_request"])
        return call("source-call", "source") if len(requests) == 1 else AssistantModelOutput(content="The full result cannot fit.")
    run_harness(session, monkeypatch, tool, complete)
    assert tool.executions == 1 and len(requests) == 2
    outcome = next(event for event in session.events() if event.type == "tool/result")
    assert outcome.data["error"]["code"] == "TOOL_RESULT_TOO_LARGE"
    assert "data_base64" not in json.dumps(requests[1].messages)
    assert "TOOL_RESOURCE_OBSERVATION" not in json.dumps(requests[1].messages)


def test_pending_skill_schemas_survive_compaction_budget_rebuild(session, monkeypatch):
    from tests.agent_support import EchoTool
    class WideTool(EchoTool):
        input_schema = {"type": "object", "properties": {"value": {"type": "string", "description": "large schema " * 4000}}}
    monkeypatch.setattr("backend.app.agent_runtime.runtime.build_builtin_skills", lambda: [FakeSkill("worker", {"echo"})])
    rebuilt = []
    def compact(**kwargs):
        if kwargs["reason"] == "tool_result":
            rebuilt.append(kwargs["rebuild_request"](session.events()))
            return rebuilt[-1]
        return kwargs["model_request"]
    monkeypatch.setattr(session.service.compaction, "compact_model_request_if_needed", compact)
    monkeypatch.setattr(session.service.compaction, "estimate_model_request_tokens", lambda request: len(json.dumps([tool.as_dict() for tool in request.tools])))
    requests = []
    def complete(**kwargs):
        requests.append(kwargs["model_request"])
        return call("skill-call", "load_skill", name="worker") if len(requests) == 1 else AssistantModelOutput(content="The complete skill cannot fit.")
    run_harness(session, monkeypatch, WideTool(), complete)
    assert rebuilt and "echo" in {tool.name for tool in rebuilt[0].tools}
    for request in rebuilt:
        assert [message.get("tool_call_id") for message in request.messages if message.get("role") == "tool"] == ["skill-call"]
        assert_native_pairs(request.messages)
    assert "echo" not in {tool.name for tool in requests[1].tools}
    assert "TOOL_RESULT_TOO_LARGE" in json.dumps(requests[1].messages)


def test_compaction_never_reintroduces_audit_only_retention(monkeypatch):
    from backend.app.application.conversations.compaction import ConversationCompaction
    from backend.app.domain.conversations.model_history import derive_model_messages
    monkeypatch.setattr("backend.app.application.conversations.compaction.member_lifecycle_guard", lambda **kwargs: nullcontext())
    repository = MemoryEvents()
    repository.session_events = lambda *args, **kwargs: list(repository.events)
    def add(kind, data): repository.append_session_event("memory", "session", kind, data)
    add("turn/start", {"turn_id": "old", "user_message_id": "user", "stream_id": "stream"})
    add("user/message", {"turn_id": "old", "message_id": "old-user", "parent_message_id": None, "content": "history " * 5000})
    add("assistant/message", {"turn_id": "old", "message_id": "call-message", "parent_message_id": "old-user", "content": None, "tool_calls": [ToolCall("parse", "parse", {}).as_dict()]})
    effects = {"context_retention": {"collection_field": "reports", "index_field": "report_index"}}
    add("tool/result", {"turn_id": "old", "call_id": "parse", "tool_call_id": "parse", "name": "parse", "status": "failed", "error": {"code": "TOOL_RESULT_TOO_LARGE", "details": {"execution_completed": True, "effects": effects}}, "result": {"type": "tool_result", "output": {"reports": [{"report_index": 0, "text": "AUDIT_ONLY_SENTINEL"}]}, "effects": effects}})
    add("assistant/message", {"turn_id": "old", "message_id": "old-answer", "parent_message_id": "old-user", "content": "The result could not fit."})
    add("turn/start", {"turn_id": "new", "user_message_id": "user", "stream_id": "stream"})
    add("user/message", {"turn_id": "new", "message_id": "current", "parent_message_id": "old-answer", "content": "continue"})
    compaction = ConversationCompaction(repository, SimpleNamespace(default_model_for_account=lambda *args: None), None,
        SimpleNamespace(session_lock=lambda *args: nullcontext()),
        complete_model=lambda **kwargs: AssistantModelOutput(content="## 目标\n继续核对。"),
        ensure_active=lambda *args: None, thinking_mode_for_model=lambda *args: "default")
    request = ModelRequest.build(system="fixture", messages=derive_model_messages(repository.events), model_config={"purpose": "agent_action", "max_output_tokens": 100})
    rebuilt = compaction.compact_model_request_if_needed(account_id="memory", turn={"session_id": "session", "turn_id": "new"},
        user_message={"message_id": "current"}, model={"context_window_tokens": 5000, "max_output_tokens": 100},
        model_request=request, thinking_mode="default", force=True)
    assert any(event.type == "compaction/checkpoint" for event in repository.events)
    assert "AUDIT_ONLY_SENTINEL" not in json.dumps(rebuilt.messages)


def test_report_source_selection_delivers_original_content_to_model(tmp_path):
    from backend.app.application.conversations.model_resources import ConversationModelResources
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    from backend.app.plugins.medical_report.tools.query_tools import ReadReportInformationTool
    from backend.app.plugins.medical_report.resources import resolve_model_resource

    original = tmp_path / 'report.txt'
    original.write_text('医疗报告原文：检验结果 5.2', encoding='utf-8')
    def query(member, **arguments):
        value = {'report_id': 'report'}
        if 'sources' in arguments.get('fields', []):
            value['sources'] = [{'resource_id': 'source'}]
        return {'reports': [value]}
    service = SimpleNamespace(query_evidence=query,
        validate_report_context=lambda *args: {'resource_type': 'report', 'resource_id': 'report'},
        source_download=lambda *args: (original, 'report.txt', 'text/plain'))
    tool = ReadReportInformationTool(account_id='actor', member_id='member', service=service)
    assert 'model_resource_refs' not in tool.run({}).effects
    result = tool.run({'report_ids': ['report'], 'fields': ['sources']})
    refs = result.effects['model_resource_refs']
    assert refs == [{'resource_type': 'report_source', 'resource_id': 'source', 'report_id': 'report', 'member_id': 'member'}]
    context = PluginRuntimeContext(account_id='actor', member_id='member', event_recorder=lambda event: None, services={'medical_report': service})
    preparer = ConversationModelResources(account_id='actor', runtime_context=context,
        inputs=SimpleNamespace(model_can_forward_attachment=lambda *args: False),
        model_catalog=SimpleNamespace(default_model_for_account=lambda *args: None))
    _, parts = preparer.prepare(refs, {'model_id': 'model'},
        resolved_resources=[resolve_model_resource(runtime_context=context, reference=ref) for ref in refs])
    assert parts[0]['text'] == '医疗报告原文：检验结果 5.2'
    assert 'path' not in parts[0]['model_resource_ref']


def test_medication_model_preparation_reuses_single_authorized_read():
    import base64
    from backend.app.application.conversations.model_resources import ConversationModelResources
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    from backend.app.plugins.medication.registry import build_tools, resolve_model_resource
    reads = []
    def read(*args):
        reads.append(args)
        return {"mime_type": "image/png", "original_filename": "box.png"}, b"verified snapshot"
    metadata = {'medication_id': 'medication', 'member_id': 'member', 'generic_name': '药品', 'created_at': 'now', 'updated_at': 'now', 'sources': [{'resource_id': 'source'}]}
    service = SimpleNamespace(source=read, read_information=lambda *args, **kwargs: {"items": [metadata], "total": 1, "next_cursor": None}, read=lambda *args: metadata, members=SimpleNamespace(access_guard=lambda *args: nullcontext()))
    context = PluginRuntimeContext(account_id="actor", member_id="member", event_recorder=lambda event: None, services={"medication": service})
    tool = next(tool for tool in build_tools(runtime_context=context) if tool.name == "read_medication_information")
    result = tool.run({"medication_id": "medication", "fields": ["sources"]})
    ref = result.effects["model_resource_refs"][0]
    resource = resolve_model_resource(runtime_context=context, reference=ref)
    preparer = ConversationModelResources(account_id="actor", runtime_context=context,
        inputs=SimpleNamespace(model_can_forward_attachment=lambda model, mime: mime == "image/png"),
        model_catalog=SimpleNamespace(default_model_for_account=lambda *args: None))
    _, parts = preparer.prepare([ref], {"model_id": "model"}, resolved_resources=[resource])
    assert len(reads) == 1
    assert base64.b64decode(parts[0]["data_base64"]) == b"verified snapshot"
    assert "content_bytes" not in parts[0]["model_resource_ref"]
    assert "path" not in resource
    assert context.model_resource_cache == {}


@pytest.mark.parametrize("cancel", [True, False])
def test_web_reading_stops_on_cancel_or_total_deadline(monkeypatch, cancel):
    import httpx
    from backend.app.core.cancellation import CancellationToken
    from backend.app.plugins.web.adapters import ExaAdapter
    from backend.app.plugins.web.errors import WebAccessError
    token = CancellationToken()
    clock = [100.0]
    monkeypatch.setattr("backend.app.plugins.web.adapters.time.monotonic", lambda: clock[0])
    class Stream(httpx.SyncByteStream):
        closed = False
        def __iter__(self):
            yield b"{"
            if cancel: token.cancel()
            else: clock[0] = 102.0
            yield b"}"
        def close(self): self.closed = True
    stream = Stream()
    adapter = ExaAdapter(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))).for_execution(token, 101.0)
    with pytest.raises(OperationCancelledError if cancel else WebAccessError) as caught:
        adapter._request_json(endpoint="https://example.test/read", api_key="fixture", payload={}, timeout=45)
    if not cancel: assert caught.value.code == "WEB_TIMEOUT"
    assert stream.closed


def test_web_cancel_closes_response_while_read_is_blocked():
    import httpx
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from backend.app.core.cancellation import CancellationToken
    from backend.app.plugins.web.adapters import ExaAdapter
    entered, closed = Event(), Event()
    token = CancellationToken()
    class BlockedStream(httpx.SyncByteStream):
        def __iter__(self):
            entered.set()
            assert closed.wait(2), "cancellation did not close the blocked response"
            raise httpx.ReadError("closed")
            yield b""
        def close(self): closed.set()
    adapter = ExaAdapter(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=BlockedStream()))).for_execution(token, None)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(adapter._request_json, endpoint="https://example.test/read", api_key="fixture", payload={}, timeout=45)
        assert entered.wait(1)
        token.cancel()
        with pytest.raises(OperationCancelledError): pending.result(timeout=1)
    assert closed.is_set()

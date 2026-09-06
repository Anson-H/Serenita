"""Executed tool outcomes survive cancellation through the real Service sink."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace
import json
import pytest
from backend.app.core.errors import SerenitaError
from member_support import account_id as account_id_for
from backend.app.agent_runtime.compaction import CompactionError
from backend.app.agent_runtime.model_types import AssistantModelOutput, ToolCall
from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.application.conversation_service import ConversationService
from backend.app.conversation_timeline import records_from_events
from backend.app.model_history import derive_model_messages
from backend.app.core.cancellation import CancellationToken, OperationCancelledError
from backend.app.core.time import local_now_iso
from backend.app.repositories.conversation_repository import ConversationRepository
from tests.agent_support import assert_native_pairs


@pytest.fixture
def session(monkeypatch):
    account = account_id_for("cancel-audit")
    repository = ConversationRepository()
    session_id = repository.ensure_session(account, member_id=None)
    turn = {"session_id": session_id, "turn_id": "turn", "stream_id": "stream"}
    user = {"message_id": "user", "parent_message_id": None, "content": "save", "context_resources": []}
    repository.append_session_events(account, session_id, [
        {"type": "turn/start", "data": {"turn_id": "turn", "user_message_id": "user"}},
        {"type": "user/message", "data": {**user, "turn_id": "turn"}, "surface_op": "append"},
    ])
    now = local_now_iso()
    repository.insert_turn(account, session_id, "turn", "user", "final", "stream", "streaming", None, None, now, now)
    service = ConversationService(repository=repository)
    model = {"model_id": "fake", "supports_tool_calling": True, "thinking_modes": ["default"], "context_window_tokens": 10000, "max_output_tokens": 100}
    monkeypatch.setattr(service, "_validate_model", lambda *args: model)
    token = CancellationToken()
    value = SimpleNamespace(account=account, repository=repository, service=service, turn=turn, user=user, token=token)
    value.events = lambda: repository.session_events(account, session_id, repair=False)
    value.persist = lambda payload, failed=False: service._persist_runtime_tool_result(account, turn, payload, failed=failed)
    return value


class SaveTool(Tool):
    name = "save"
    model_exposure = "direct"
    description = "Save a test object."
    input_schema = {"type": "object", "properties": {}, "additionalProperties": False}

    def __init__(self, after_write=lambda: None, *, empty_effects=False):
        self.writes = []
        self.after_write = after_write
        self.empty_effects = empty_effects

    def run(self, arguments):
        self.writes.append("report-1")
        self.after_write()
        return ToolResult(
            self.name,
            {"report_id": "report-1", "evidence": "AUDIT_ONLY" * 10000},
            {} if self.empty_effects else {"affected_resource_refs": [{"resource_type": "report", "resource_id": "report-1"}]},
        )


def run_harness(session, monkeypatch, tool, complete):
    monkeypatch.setattr("backend.app.plugins.build_available_tools", lambda **kwargs: [tool])
    monkeypatch.setattr(session.service.model_calls, "complete_chat_with_events", complete)
    return session.service._execute_agent_harness(
        session.account, session.turn, session.user,
        on_workflow_event=lambda event: None, cancellation_token=session.token,
    )


@pytest.mark.parametrize("stage", ["tool", "candidate", "emit"])
@pytest.mark.parametrize("cancel_turn", [False, True])
@pytest.mark.parametrize("empty_effects", [False, True])
def test_cancelled_tool_outcome_is_durable_and_stops_actions(session, monkeypatch, stage, cancel_turn, empty_effects):
    def cancel():
        session.token.cancel()
        if cancel_turn:
            session.service.cancel_turn(session.account, session.turn["session_id"], "turn")

    tool = SaveTool(after_write=cancel if stage == "tool" else lambda: None, empty_effects=empty_effects)
    model_calls = []

    def complete(**kwargs):
        model_calls.append(kwargs)
        assert len(model_calls) == 1
        return AssistantModelOutput(tool_calls=(ToolCall("save-call", "save", {}),))

    def prepare(**kwargs):
        if kwargs.get("reason") == "tool_result":
            assert stage == "candidate"
            cancel()
            session.token.raise_if_cancelled()
        return kwargs["model_request"]

    def estimate(request):
        if request.messages and request.messages[-1].get("role") == "tool":
            if stage == "emit":
                cancel()
                return 1
            return 20000
        return 1

    monkeypatch.setattr(session.service.compaction, "compact_model_request_if_needed", prepare)
    monkeypatch.setattr(session.service.compaction, "estimate_model_request_tokens", estimate)
    with pytest.raises(OperationCancelledError):
        run_harness(session, monkeypatch, tool, complete)

    results = [event for event in session.events() if event.type == "tool/result"]
    actual = results[-1]
    assert tool.writes == ["report-1"]
    assert len(model_calls) == 1
    assert actual.data["result"]["output"]["report_id"] == "report-1"
    assert actual.data["result"]["output"]["evidence"] == "AUDIT_ONLY" * 10000
    if empty_effects:
        assert actual.data["result"]["effects"] == {}
    else:
        assert actual.data["result"]["effects"]["affected_resource_refs"][0]["resource_id"] == "report-1"
    assert actual.data["status"] == ("completed" if stage == "emit" else "failed")
    if stage != "emit":
        assert actual.data["error"]["details"]["execution_completed"] is True
        assert "AUDIT_ONLY" not in json.dumps(actual.data["error"])
    if cancel_turn:
        assert len(results) == 2
        assert results[0].data["status"] == "interrupted"
        assert actual.source_event_seqs == (results[0].seq,)
        assert actual.surface_op == {"op": "replace", "start": results[0].seq, "end": results[0].seq + 1}
        assert session.repository.turn_row(session.account, session.turn["session_id"], "turn")["status"] == "cancelled"
    else:
        assert len(results) == 1
    messages = derive_model_messages(session.events())
    assert_native_pairs(messages)
    assert len([message for message in messages if message["role"] == "tool"]) == 1
    if stage != "emit":
        assert "AUDIT_ONLY" not in json.dumps(messages)
    record = next(item for item in records_from_events(session.events()) if item.get("kind") == "tool")
    assert record["result"] == actual.data["result"]
    assert record["status"] == actual.data["status"]


@pytest.mark.parametrize("empty_effects", [False, True])
def test_oversized_result_keeps_full_audit_but_only_error_in_model_context(session, monkeypatch, empty_effects):
    tool = SaveTool(empty_effects=empty_effects)
    requests = []

    def complete(**kwargs):
        requests.append(kwargs["model_request"])
        if len(requests) == 1:
            return AssistantModelOutput(tool_calls=(ToolCall("save-call", "save", {}),))
        return AssistantModelOutput(content="saved")

    def prepare(**kwargs):
        if kwargs.get("reason") == "tool_result":
            raise CompactionError("cannot compact candidate")
        return kwargs["model_request"]

    monkeypatch.setattr(session.service.compaction, "compact_model_request_if_needed", prepare)
    result = run_harness(session, monkeypatch, tool, complete)
    event = next(event for event in session.events() if event.type == "tool/result")
    assert event.data["status"] == "failed"
    assert event.data["error"]["code"] == "TOOL_RESULT_TOO_LARGE"
    assert event.data["error"]["message"].startswith("工具已执行")
    assert event.data["error"]["details"]["execution_completed"] is True
    assert event.data["error"]["details"]["effects"] == event.data["result"]["effects"]
    assert event.data["result"]["output"] == result["tool_results"][0]["output"]
    assert "AUDIT_ONLY" not in json.dumps(requests[-1].canonical_dict())
    assert_native_pairs(requests[-1].messages)
    assert tool.writes == ["report-1"]


@pytest.mark.parametrize("cancel_turn", [False, True])
def test_unexecuted_argument_error_is_not_saved_after_cancellation(session, monkeypatch, cancel_turn):
    tool = SaveTool()
    original = session.service._persist_runtime_tool_result

    def cancel_before_error(account, turn, payload, **kwargs):
        assert payload["error"]["code"] == "TOOL_ARGUMENTS_INVALID"
        session.token.cancel()
        if cancel_turn:
            session.service.cancel_turn(account, turn["session_id"], turn["turn_id"])
        return original(account, turn, payload, **kwargs)

    monkeypatch.setattr(session.service, "_persist_runtime_tool_result", cancel_before_error)
    monkeypatch.setattr(session.service.compaction, "compact_model_request_if_needed", lambda **kwargs: kwargs["model_request"])
    with pytest.raises(OperationCancelledError):
        run_harness(
            session, monkeypatch, tool,
            lambda **kwargs: AssistantModelOutput(tool_calls=(ToolCall("invalid", "save", {"unexpected": True}),)),
        )
    assert tool.writes == []
    results = [event for event in session.events() if event.type == "tool/result"]
    assert len(results) == int(cancel_turn)
    assert all(event.data["status"] == "interrupted" for event in results)


def test_next_tool_can_resolve_completed_failed_result_from_durable_audit(session, monkeypatch):
    writer = SaveTool()
    requests = []
    observed = []

    class ReadAuditTool(Tool):
        name = "read_audit"
        model_exposure = "direct"
        description = "Read the test audit."

        def run(self, arguments):
            actual = self.resolve(
                call_id="save-call", allowed_tools={"save"},
                session_id=session.turn["session_id"], visible_message_ids={"user"},
            )
            observed.append(actual)
            return ToolResult(self.name, {"report_id": actual["output"]["report_id"]})

    reader = ReadAuditTool()

    def tools(**kwargs):
        reader.resolve = kwargs["runtime_context"].observation_resolver
        return [writer, reader]

    def complete(**kwargs):
        requests.append(kwargs["model_request"])
        if len(requests) <= 2:
            name = "save" if len(requests) == 1 else "read_audit"
            return AssistantModelOutput(tool_calls=(ToolCall(name + "-call", name, {}),))
        return AssistantModelOutput(content="done")

    monkeypatch.setattr("backend.app.plugins.build_available_tools", tools)
    monkeypatch.setattr(session.service.model_calls, "complete_chat_with_events", complete)
    monkeypatch.setattr(session.service.compaction, "compact_model_request_if_needed", lambda **kwargs: kwargs["model_request"])
    session.service._execute_agent_harness(
        session.account, session.turn, session.user, on_workflow_event=lambda event: None,
    )
    assert observed[0]["output"]["report_id"] == "report-1"
    assert observed[0]["output"]["evidence"] == "AUDIT_ONLY" * 10000
    assert "AUDIT_ONLY" not in json.dumps(requests[-1].canonical_dict())
    assert_native_pairs(requests[-1].messages)
    assert writer.writes == ["report-1"]


def seed_call(session):
    session.repository.append_session_events(session.account, session.turn["session_id"], [
        {"type": "assistant/message", "data": {"turn_id": "turn", "message_id": "action", "parent_message_id": "user", "content": None, "branch_addressable": False, "tool_calls": [ToolCall("save-call", "save", {}).as_dict()]}, "surface_op": "append"},
        {"type": "tool/call", "data": {"turn_id": "turn", "step": 3, "call_id": "save-call", "tool_call_id": "save-call", "name": "save", "arguments": {}}},
    ])
    return {
        "call_id": "save-call", "tool_call_id": "save-call", "tool": "save",
        "output": {"type": "tool_result", "output": {"report_id": "report-1"}, "effects": {}},
    }


@pytest.mark.parametrize("cancel_first", [False, True])
def test_result_finalization_is_idempotent_under_concurrent_delivery(session, cancel_first):
    payload = seed_call(session)
    if cancel_first:
        session.service.cancel_turn(session.account, session.turn["session_id"], "turn")
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(lambda _: session.persist(payload), range(8)))
    assert sum(outcomes) == 1
    events = session.events()
    assert len([event for event in events if event.type == "tool/result"]) == (2 if cancel_first else 1)
    assert_native_pairs(derive_model_messages(events))
    altered = deepcopy(payload)
    altered["output"]["output"]["report_id"] = "different"
    with pytest.raises(SerenitaError) as caught:
        session.persist(altered)
    assert caught.value.detail["code"] == "TOOL_RESULT_CONFLICT"
    assert session.events() == events


@pytest.mark.parametrize("field", ["call_id", "tool_call_id", "tool", "turn_id", "session_id", "account_id"])
def test_finalization_requires_session_ownership_and_exact_existing_call(session, field):
    payload = seed_call(session)
    account, turn = session.account, dict(session.turn)
    if field == "account_id":
        account = account_id_for("other-audit-account")
    elif field == "session_id":
        turn[field] = session.repository.ensure_session(account, member_id=None)
    elif field == "turn_id":
        turn[field] = "other-turn"
    else:
        payload[field] = "wrong"
    before = session.events()
    with pytest.raises(SerenitaError):
        session.service._persist_runtime_tool_result(account, turn, payload, failed=False)
    assert session.events() == before


def test_late_result_invalidates_summary_of_unknown_outcome_without_orphan_reply(session):
    payload = seed_call(session)
    session.service.cancel_turn(session.account, session.turn["session_id"], "turn")
    events = session.events()
    sources = [event.seq for event in events if event.type in {"assistant/message", "tool/result"} and event.data.get("message_id") != "final"]
    checkpoint_data = {
        "turn_id": "turn", "compaction_id": "compaction_test",
        "estimated_tokens_before": 1000, "estimated_tokens_after": 100,
        "target_tokens": 600, "replaced_turn_ids": ["turn"],
    }
    checkpoint = session.repository.append_session_event(
        session.account, session.turn["session_id"], "compaction/checkpoint",
        {**checkpoint_data, "message_id": "summary", "content": "<compacted-summary>\noutcome unknown\n</compacted-summary>", "summary": "outcome unknown"},
        source_event_seqs=sources, surface_op={"op": "replace", "start": min(sources), "end": max(sources) + 1},
    )
    session.repository.append_session_event(
        session.account, session.turn["session_id"], "compaction/checkpoint",
        {**checkpoint_data, "compaction_id": "compaction_test2", "message_id": "summary2", "content": "<compacted-summary>\nstill unknown\n</compacted-summary>", "summary": "still unknown"},
        source_event_seqs=[checkpoint.seq], surface_op={"op": "replace", "start": min(sources), "end": max(sources) + 1},
    )
    assert session.persist(payload)
    messages = derive_model_messages(session.events(), include_surface_metadata=True)
    assert_native_pairs(messages)
    assert "unknown" not in json.dumps(messages)
    assert "report-1" in json.dumps(messages)
    reply = next(message for message in messages if message["role"] == "tool")
    assert reply["_source_seq"] == session.events()[-1].seq
    assert reply["_surface_seq"] in sources

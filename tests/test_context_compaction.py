from backend.app.application.conversation_compaction import ConversationCompaction
"""Compaction boundaries and checkpoints through the real conversation Service."""

from tests.agent_support import assert_native_pairs
from copy import deepcopy
from dataclasses import dataclass, field, replace
import json
import math
import re
import pytest
from member_support import account_id as account_id_for, member_id
from backend.app.agent_runtime.compaction import CompactionError, ContextBudget, public_message, select_history, summarize_history, validate_tool_pairs
from backend.app.agent_runtime.model_types import AssistantModelOutput, ModelRequest, ModelStreamChunk, PromptContextSection, ToolCall, ToolCallDelta, ToolSchema
from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.agent_runtime.skills.base import Skill, SkillDocument
from backend.app.agent_runtime.runtime import AgentHarnessRuntime
from backend.app.application.conversation_service import ConversationService
from backend.app.model_history import derive_model_messages, visible_loaded_skill_names
from backend.app.core.cancellation import CancellationToken, OperationCancelledError
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.session_events import make_event
from backend.app.storage.session_persistence import JsonlSessionPersistence
from tests.model_support import CompactCatalog


CURRENT_TURN = "current"
CURRENT_USER = "current-user"
CURRENT_CONTENT = "请继续核对来源，保留尚未解决的问题。"
ESTIMATE = ConversationCompaction.estimate_model_request_tokens
INVALID_OUTPUTS = [
    pytest.param(AssistantModelOutput(content=""), id="empty"),
    pytest.param(AssistantModelOutput(content=" \n\t"), id="whitespace"),
    *[
        pytest.param(AssistantModelOutput(content="unfinished", stop_reason=reason), id=reason)
        for reason in ("length", "max_tokens", "max_output_tokens", "incomplete")
    ],
    pytest.param(
        AssistantModelOutput(
            content="cannot be a summary",
            tool_calls=(ToolCall(id="unexpected", name="lookup", arguments={}),),
        ),
        id="tool-call",
    ),
]


def group_specifications(name, *, size=0, completed=True):
    """Two parallel calls, with results deliberately arriving in reverse order."""
    calls = [ToolCall(id=f"{name}-{index}", name="lookup", arguments={"index": index}) for index in range(2)]
    specs = [{
        "type": "assistant/message",
        "data": {
            "turn_id": CURRENT_TURN, "message_id": f"assistant-{name}",
            "parent_message_id": CURRENT_USER, "content": None,
            "branch_addressable": False, "tool_calls": [call.as_dict() for call in calls],
        },
        "surface_op": "append",
    }]
    if completed:
        for call in reversed(calls):
            specs.append({
                "type": "tool/result",
                "data": {
                    "turn_id": CURRENT_TURN, "call_id": call.id,
                    "tool_call_id": call.id, "name": call.name, "status": "completed",
                    "result": {"source": call.id, "fact": "ALT 45 U/L, 2026-01-01", "evidence": "x" * size},
                },
                "surface_op": "append",
            })
    return specs


def initial_specifications():
    return [
        {"type": "turn/start", "data": {"turn_id": CURRENT_TURN}},
        {"type": "user/message", "data": {
            "turn_id": CURRENT_TURN, "message_id": CURRENT_USER,
            "parent_message_id": None, "content": CURRENT_CONTENT,
        }, "surface_op": "append"},
    ]


def project_specs(specs):
    events = [
        make_event(spec["type"], seq, spec["data"], surface_op=spec.get("surface_op"))
        for seq, spec in enumerate(specs)
    ]
    return derive_model_messages(events, current_turn_ids=[CURRENT_TURN], include_surface_metadata=True)


def test_context_budget_reserves_output_before_applying_thresholds():
    budget = ContextBudget(window=10000, output=2000)
    assert (budget.available, budget.trigger, budget.target) == (8000, 6400, 4800)


@pytest.mark.parametrize("window,output", [(100, 100), (100, 101)])
def test_context_budget_rejects_no_input_capacity(window, output):
    with pytest.raises(CompactionError):
        _ = ContextBudget(window, output).available


@pytest.mark.parametrize("force,available,selected_groups", [
    (False, 2000, {"old"}),
    (False, 1000, {"old", "middle"}),
    (True, 2000, {"old", "middle"}),
])
def test_select_history_keeps_current_and_whole_recent_parallel_groups(force, available, selected_groups):
    specs = initial_specifications()
    for name in ("old", "middle", "last"):
        specs.extend(group_specifications(name))
    surface = project_specs(specs)
    original = deepcopy(surface)
    selected = select_history(
        surface, current_user_seq=1, available_tokens=available,
        estimate_messages=lambda messages: 50 * len(messages), force=force,
    )
    assert surface == original
    expected_sources = {
        seq for seq, spec in enumerate(specs)
        if any(spec["data"].get("message_id") == f"assistant-{name}" or
               str(spec["data"].get("tool_call_id", "")).startswith(f"{name}-")
               for name in selected_groups)
    }
    assert {item["_source_seq"] for item in selected} == expected_sources
    assert {item["_turn_id"] for item in selected} == {CURRENT_TURN}
    kept = [public_message(item) for item in surface if item["_source_seq"] not in expected_sources]
    assert kept[0] == {"role": "user", "content": CURRENT_CONTENT}
    assert_native_pairs(kept)
    assert_native_pairs([public_message(item) for item in selected])
    assert all(not key.startswith("_") for item in kept for key in item)


def test_select_history_pins_pending_group_and_last_complete_action():
    surface = project_specs([
        *initial_specifications(), *group_specifications("old"),
        *group_specifications("last"), *group_specifications("pending", completed=False),
    ])
    selected = select_history(
        surface, current_user_seq=1, available_tokens=1000,
        estimate_messages=lambda messages: len(messages), force=True,
    )
    assert {item["_source_seq"] for item in selected} == {2, 3, 4}
    kept = [public_message(item) for item in surface if item not in selected]
    assert_native_pairs(kept, pending_ids={"pending-0", "pending-1"})
    validate_tool_pairs(kept, allow_pending=True)
    with pytest.raises(CompactionError):
        validate_tool_pairs(kept)


def test_select_history_pins_group_whose_execution_outcome_is_still_unknown():
    surface = project_specs([
        *initial_specifications(), *group_specifications("old"),
        *group_specifications("uncertain"), *group_specifications("last"),
    ])
    surface[5]["_pending_execution"] = True
    selected = select_history(
        surface, current_user_seq=1, available_tokens=1000,
        estimate_messages=lambda messages: len(messages), force=True,
    )
    assert {item["_source_seq"] for item in selected} == {2, 3, 4}


@pytest.mark.parametrize("messages", [
    [{"role": "tool", "tool_call_id": "orphan", "content": "result"}],
    [{"role": "assistant", "tool_calls": [{"id": "duplicate"}, {"id": "duplicate"}]}],
    [{"role": "assistant", "tool_calls": [{"id": ""}]}],
    [{"role": "assistant", "tool_calls": [{"id": "missing"}]}, {"role": "assistant", "content": "done"}],
    [{"role": "assistant", "tool_calls": [{"id": "a"}]},
     {"role": "tool", "tool_call_id": "a"}, {"role": "tool", "tool_call_id": "a"}],
])
@pytest.mark.parametrize("allow_pending", [False, True])
def test_validate_tool_pairs_rejects_invalid_groups_even_when_pending_is_allowed(messages, allow_pending):
    with pytest.raises(CompactionError):
        validate_tool_pairs(messages, allow_pending=allow_pending)


def test_summary_chunks_fit_model_window_and_fold_all_history_without_loss():
    records = [{"seq": 5, "message": {"role": "tool", "tool_call_id": "call-1", "content": "数值45，单位U/L。" * 3000}}]
    original = deepcopy(records)
    budget = ContextBudget(window=2048, output=256)
    calls = []

    def complete(request):
        assert ESTIMATE(request) + request.model_config["max_tokens"] <= budget.window
        assert not request.tools and request.tool_choice is None
        assert request.model_config["purpose"] == "context_compaction"
        assert [item["role"] for item in request.messages] == ["user"]
        data = json.loads(request.messages[0]["content"])
        assert data["previous_summary"] == (f"summary-{len(calls)}" if calls else "previous facts")
        assert data["history_fragment"]
        calls.append(data)
        return AssistantModelOutput(content=f"summary-{len(calls)}")

    result = summarize_history(records, previous_summary="previous facts", budget=budget, estimate=ESTIMATE, complete=complete)
    assert len(calls) >= 3
    assert result == f"summary-{len(calls)}"
    assert "".join(item["history_fragment"] for item in calls) == json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    assert records == original


@pytest.mark.parametrize("output", INVALID_OUTPUTS)
def test_summarize_history_rejects_invalid_summary(output):
    with pytest.raises(CompactionError):
        summarize_history(
            [{"fact": "ALT 45 U/L"}], previous_summary="", budget=ContextBudget(2048, 256),
            estimate=ESTIMATE, complete=lambda _request: output,
        )


def test_summary_budget_exhaustion_stops_before_calling_model():
    def unexpected(_request):
        pytest.fail("The summary request already exceeds its input budget")

    with pytest.raises(CompactionError):
        summarize_history(
            [{"fact": "value"}], previous_summary="x" * 20000,
            budget=ContextBudget(2048, 256), estimate=ESTIMATE, complete=unexpected,
        )


class RecordingCompactCatalog(CompactCatalog):
    def __init__(self, model):
        super().__init__(model)
        self.outputs = []
        self.output_override = None
        self.on_complete = None

    def stream_prepared_chat_for_account(self, **_kwargs):
        index = len(self.outputs) + 1
        output = self.output_override or AssistantModelOutput(content=f"摘要{index}：ALT 45 U/L，来源明确，仍需核对。", stop_reason="stop")
        self.outputs.append(output)
        if self.on_complete is not None:
            self.on_complete()
        if output.content:
            yield ModelStreamChunk(content_delta=output.content)
        if output.tool_calls:
            yield ModelStreamChunk(tool_call_deltas=tuple(
                ToolCallDelta(index=index, id=call.id, name_delta=call.name, arguments_delta=json.dumps(call.arguments))
                for index, call in enumerate(output.tool_calls)
            ))
        yield ModelStreamChunk(stop_reason=output.stop_reason)


@dataclass
class CompactionSession:
    repository: ConversationRepository
    account_id: str
    session_id: str
    model: dict
    catalog: RecordingCompactCatalog
    service: ConversationService
    candidate_snapshots: list = field(default_factory=list)

    def events(self):
        return self.repository.session_events(self.account_id, self.session_id, repair=False)

    def append(self, specs):
        return self.repository.append_session_events(self.account_id, self.session_id, specs)

    def add_group(self, name, **kwargs):
        return self.append(group_specifications(name, **kwargs))

    def request(self, events=None):
        return ModelRequest.build(
            system="system",
            messages=derive_model_messages(self.events() if events is None else events, current_turn_ids=[CURRENT_TURN]),
            tools=[ToolSchema(name="lookup", parameters={"type": "object", "properties": {}})],
            context_sections=[PromptContextSection(context_type="system", label="system", content="system")],
            model_config={"purpose": "agent_action", "max_output_tokens": self.model["max_output_tokens"]},
        )

    def rebuild(self, events):
        self.candidate_snapshots.append(events)
        return self.request(events)

    def compact(self, *, request=None, **kwargs):
        return self.service.compaction.compact_model_request_if_needed(
            account_id=self.account_id, turn={"session_id": self.session_id, "turn_id": CURRENT_TURN},
            user_message={"message_id": CURRENT_USER, "parent_message_id": None, "context_resources": []},
            model=self.model, model_request=self.request() if request is None else request,
            thinking_mode="default",
            rebuild_request=kwargs.pop("rebuild_request", self.rebuild), **kwargs,
        )

    def checkpoints(self):
        return [event for event in self.events() if event.type == "compaction/checkpoint"]


@pytest.fixture
def session():
    repository = ConversationRepository(JsonlSessionPersistence())
    account = account_id_for("compaction-user")
    session_id = repository.ensure_session(account, member_id=member_id("compaction-user"))
    model = {
        "model_id": "action", "provider_id": "fake", "remote_model_id": "fake-action",
        "thinking_modes": ["default"], "supports_tool_calling": True,
        "context_window_tokens": 6000, "max_output_tokens": 500,
    }
    catalog = RecordingCompactCatalog({**model, "model_id": "compact", "remote_model_id": "fake-compact", "context_window_tokens": 2048, "max_output_tokens": 256})
    service = ConversationService(repository=repository, model_catalog=catalog)
    value = CompactionSession(repository, account, session_id, model, catalog, service)
    specs = initial_specifications()
    for index in range(4):
        specs.extend(group_specifications(f"history-{index}", size=3600))
    specs.extend(group_specifications("last"))
    value.append(specs)
    return value


def test_service_three_compactions_replace_previous_summary_and_keep_current_and_last_group(session):
    previous_checkpoint = None
    previous_summary = ""
    last_name = "last"
    for round_index in range(3):
        if round_index:
            session.add_group(f"history-round-{round_index}", size=3600)
            last_name = f"last-round-{round_index}"
            session.add_group(last_name)
        before = session.events()
        surface = derive_model_messages(before, current_turn_ids=[CURRENT_TURN], include_surface_metadata=True)
        visible_sources = {item["_source_seq"] for item in surface}
        first_request_index = len(session.catalog.requests)
        original = session.request()
        rebuilt = session.compact(request=original, force=True)
        checkpoints = session.checkpoints()
        assert len(checkpoints) == round_index + 1
        checkpoint = checkpoints[-1]
        assert set(checkpoint.source_event_seqs) <= visible_sources
        assert 1 not in checkpoint.source_event_seqs  # Current user message.
        assert checkpoint.data["replaced_turn_ids"] == [CURRENT_TURN]
        if previous_checkpoint is not None:
            assert previous_checkpoint.seq in checkpoint.source_event_seqs
            assert not set(previous_checkpoint.source_event_seqs) & set(checkpoint.source_event_seqs)
        first_summary_input = json.loads(session.catalog.requests[first_request_index].messages[0]["content"])
        assert first_summary_input["previous_summary"] == previous_summary
        inputs = [json.loads(request.messages[0]["content"])
                  for request in session.catalog.requests[first_request_index:]]
        assert any(item["summary_kind"] == "turn_prefix" for item in inputs)
        records = []
        for kind in ("history", "turn_prefix"):
            fragments = "".join(item["history_fragment"] for item in inputs if item["summary_kind"] == kind)
            if fragments:
                records.extend(item for item in json.loads(fragments)
                               if not item.get("preserved_original_request"))
        selected_events = {event.seq: event for event in before}
        assert {record["seq"] for record in records} == {
            seq for seq in checkpoint.source_event_seqs
            if selected_events[seq].type != "compaction/checkpoint"
        }
        for record in records:
            assert record["time"] == selected_events[record["seq"]].time
            assert all(not key.startswith("_") for key in record["message"])
        summary_messages = [item for item in rebuilt.messages if str(item.get("content", "")).startswith("<compacted-summary>")]
        assert len(summary_messages) == 1
        assert summary_messages[0]["content"].count("<compacted-summary>") == 1
        assert summary_messages[0]["content"] == checkpoint.data["content"]
        assert checkpoint.data["summary"].count("# 轮次前半段摘要") == 1
        assert checkpoint.data["summary"].count("# 历史摘要") == int(round_index > 0)
        assert rebuilt.messages[0] == {"role": "user", "content": CURRENT_CONTENT}
        assert {item["tool_call_id"] for item in rebuilt.messages if item["role"] == "tool"} == {f"{last_name}-0", f"{last_name}-1"}
        assert list(rebuilt.messages[-3:]) == [public_message(item) for item in surface[-3:]]
        assert_native_pairs(rebuilt.messages)
        validate_tool_pairs(rebuilt.messages)
        assert rebuilt.canonical_dict() == session.request().canonical_dict()
        assert rebuilt.tools == original.tools and rebuilt.context_sections == original.context_sections
        assert rebuilt.model_config == original.model_config
        assert ESTIMATE(rebuilt) <= ContextBudget(session.model["context_window_tokens"], session.model["max_output_tokens"]).target
        assert ESTIMATE(rebuilt) < ESTIMATE(original)
        assert [event.to_record() for event in session.events()[:len(before)]] == [event.to_record() for event in before]
        assert all(not key.startswith("_") for item in rebuilt.messages for key in item)
        previous_checkpoint, previous_summary = checkpoint, checkpoint.data["summary"]

    assert len(session.catalog.requests) > 3
    for request in session.catalog.requests:
        assert ESTIMATE(request) + request.model_config["max_tokens"] <= session.catalog.model["context_window_tokens"]
        assert request.model_config["max_tokens"] == 256
        assert not request.tools and request.tool_choice is None
    assert session.candidate_snapshots
    assert all(events[-1].type == "compaction/checkpoint" for events in session.candidate_snapshots)


@pytest.mark.parametrize("output", INVALID_OUTPUTS)
def test_service_second_layer_failure_keeps_previous_checkpoint(session, output):
    session.compact(force=True)
    original_checkpoint = session.checkpoints()[0]
    session.add_group("new-early", size=3600)
    session.add_group("new-last")
    original_request = session.request()

    def after_history():
        if session.catalog.requests[-1].model_config["summary_kind"] == "history":
            session.catalog.output_override = output

    session.catalog.on_complete = after_history
    with pytest.raises(CompactionError):
        session.compact(force=True)
    assert session.checkpoints() == [original_checkpoint]
    assert session.request().messages == original_request.messages
    assert session.events()[-1].data["status"] == "failed"


def test_service_layer_labels_survive_projection_and_response(session):
    from backend.app.conversation_timeline import records_from_events
    from backend.app.application.conversation_presenter import record_response

    session.compact(force=True)
    session.add_group("next-early", size=3600)
    session.add_group("next-last")
    session.compact(force=True)
    rows = [record_response(record) for record in records_from_events(session.events())
            if record.get("kind") == "model" and record.get("purpose") == "context_compaction"]
    assert {row["summary_kind"] for row in rows} == {"history", "turn_prefix"}
    assert all(row["summary_kind"] in {"history", "turn_prefix"} for row in rows)

@pytest.mark.parametrize("output", INVALID_OUTPUTS)
def test_service_invalid_summary_never_writes_checkpoint(session, output):
    session.catalog.output_override = output
    before = session.request().canonical_dict()
    with pytest.raises(CompactionError):
        session.compact(force=True)
    assert session.catalog.requests
    assert not session.checkpoints()
    assert session.request().canonical_dict() == before


def test_service_invalid_later_summary_chunk_does_not_commit_partial_summary(session):
    def fail_next_chunk():
        session.catalog.output_override = AssistantModelOutput(content="")
        session.catalog.on_complete = None

    session.catalog.on_complete = fail_next_chunk
    before = session.request().canonical_dict()
    with pytest.raises(CompactionError):
        session.compact(force=True)
    assert len(session.catalog.outputs) == 2
    assert session.catalog.outputs[0].content
    assert not session.catalog.outputs[1].content
    assert not session.checkpoints()
    assert session.request().canonical_dict() == before


@pytest.mark.parametrize("during_summary", [False, True])
def test_service_cancellation_never_writes_checkpoint(session, during_summary):
    token = CancellationToken()
    before = session.request().canonical_dict()
    if during_summary:
        session.catalog.on_complete = token.cancel
    else:
        token.cancel()
    with pytest.raises(OperationCancelledError):
        session.compact(force=True, cancellation_token=token)
    assert bool(session.catalog.requests) is during_summary
    assert not session.checkpoints()
    assert session.request().canonical_dict() == before


def test_service_single_concurrent_message_update_reassesses_before_checkpoint(session):
    def edit_current_message():
        session.catalog.on_complete = None
        assert not session.checkpoints()
        session.append([{"type": "user/message-update", "data": {"message_id": CURRENT_USER, "patch": {"content": "changed while summarizing"}}}])

    session.catalog.on_complete = edit_current_message
    rebuilt = session.compact(force=True)
    assert len(session.checkpoints()) == 1
    statuses = [event.data["status"] for event in session.events() if event.type == "compaction/status"]
    assert statuses == ["running", "failed", "running", "completed"]
    assert session.request().messages[0]["content"] == "changed while summarizing"
    assert rebuilt.canonical_dict() == session.request().canonical_dict()
    assert_native_pairs(rebuilt.messages)


@pytest.mark.parametrize("snapshot_retries", [0, 1])
def test_service_persistent_snapshot_conflict_stops_without_checkpoint(session, snapshot_retries):
    def edit_current_message():
        assert not session.checkpoints()
        session.append([{"type": "user/message-update", "data": {
            "message_id": CURRENT_USER,
            "patch": {"content": f"concurrent update {len(session.catalog.outputs)}"},
        }}])

    session.catalog.on_complete = edit_current_message
    with pytest.raises(CompactionError) as caught:
        session.compact(force=True, snapshot_retries=snapshot_retries)
    assert not session.checkpoints()
    statuses = [event.data["status"] for event in session.events() if event.type == "compaction/status"]
    assert statuses == ["running", "failed"] * (snapshot_retries + 1)
    assert_native_pairs(session.request().messages)
    assert caught.value.code == "CONTEXT_COMPACTION_STALE"


def test_service_final_rebuild_detects_changed_tool_permissions(session):
    rebuild_count = 0

    def rebuild(events):
        nonlocal rebuild_count
        rebuild_count += 1
        request = session.rebuild(events)
        return replace(request, tools=()) if rebuild_count >= 3 else request

    rebuilt = session.compact(force=True, rebuild_request=rebuild)
    assert rebuild_count >= 6
    assert not rebuilt.tools
    assert len(session.checkpoints()) == 1
    statuses = [event.data["status"] for event in session.events() if event.type == "compaction/status"]
    assert statuses == ["running", "failed", "running", "completed"]


def test_service_strict_target_rejects_large_retained_current_input_without_checkpoint(session):
    session.append([{"type": "user/message-update", "data": {
        "message_id": CURRENT_USER, "patch": {"content": "current input " + "x" * 15000},
    }}])
    original = session.request().canonical_dict()
    with pytest.raises(CompactionError, match="目标预算"):
        session.compact(force=True)
    assert not session.catalog.requests
    assert not session.checkpoints()
    assert session.request().canonical_dict() == original


def test_service_threshold_compacts_to_sixty_percent(session):
    request = session.request()
    budget = ContextBudget(session.model["context_window_tokens"], session.model["max_output_tokens"])
    assert ESTIMATE(request) >= budget.trigger
    rebuilt = session.compact(request=request)
    assert len(session.checkpoints()) == 1
    assert session.checkpoints()[0].data["target_tokens"] == int(budget.available * 0.6)
    assert ESTIMATE(rebuilt) <= budget.target
    assert_native_pairs(rebuilt.messages)


def test_service_force_compacts_below_normal_threshold(session):
    session.model["context_window_tokens"] = 50000
    original = session.request()
    assert session.compact(request=original) is original
    assert not session.catalog.requests and not session.checkpoints()
    rebuilt = session.compact(request=original, force=True)
    assert len(session.checkpoints()) == 1
    assert ESTIMATE(rebuilt) < ESTIMATE(original)


@pytest.mark.parametrize("allow_pending", [False, True])
def test_service_invalid_source_tool_history_is_not_hidden_by_compaction(session, allow_pending):
    session.append([{"type": "tool/result", "data": {
        "turn_id": CURRENT_TURN, "call_id": "orphan", "tool_call_id": "orphan",
        "name": "lookup", "status": "completed", "result": {"fact": "unpaired"},
    }, "surface_op": "append"}])
    session.add_group("newest")
    original = session.request().canonical_dict()
    with pytest.raises(CompactionError):
        session.compact(force=True, allow_pending=allow_pending)
    assert not session.catalog.requests
    assert not session.checkpoints()
    assert session.request().canonical_dict() == original


def test_failed_compaction_is_not_repeated_when_only_request_clock_advances(session):
    def request_at(clock):
        content = 'RUNTIME_CONTEXT\n' + json.dumps({"current_time": clock, "current_date": "2026-09-06"})
        return replace(
            session.request(), system=content,
            context_sections=(PromptContextSection(
                context_type="runtime_context", label="运行时元数据", content=content,
            ),),
        )
    original = request_at("2026-09-06T12:00:00+08:00")
    session.model["context_window_tokens"] = math.ceil(ESTIMATE(original) / 0.9) + session.model["max_output_tokens"]
    session.catalog.output_override = AssistantModelOutput(content="")
    failed = set()
    session.compact(request=original, failed_fingerprints=failed)
    attempts = len(session.catalog.requests)
    assert attempts > 0
    changed = request_at("2026-09-06T12:00:01+08:00")
    assert session.compact(request=changed, failed_fingerprints=failed) is changed
    assert len(session.catalog.requests) == attempts


def test_service_failed_fingerprint_skips_same_soft_failure_but_force_retries(session):
    original = session.request()
    estimated = ESTIMATE(original)
    session.model["context_window_tokens"] = math.ceil(estimated / 0.9) + session.model["max_output_tokens"]
    budget = ContextBudget(session.model["context_window_tokens"], session.model["max_output_tokens"])
    assert budget.trigger <= estimated < budget.available
    session.catalog.output_override = AssistantModelOutput(content="")
    failed = set()
    assert session.compact(request=original, failed_fingerprints=failed) is original
    assert len(failed) == 1
    attempts = len(session.catalog.requests)
    assert attempts > 0
    assert session.compact(request=original, failed_fingerprints=failed) is original
    assert len(session.catalog.requests) == attempts
    with pytest.raises(CompactionError):
        session.compact(request=original, force=True, failed_fingerprints=failed)
    assert len(session.catalog.requests) > attempts
    assert not session.checkpoints()
    session.append([{"type": "user/message-update", "data": {
        "message_id": CURRENT_USER, "patch": {"content": CURRENT_CONTENT + "更新后的限制。"},
    }}])
    changed = session.request()
    attempts = len(session.catalog.requests)
    assert session.compact(request=changed, failed_fingerprints=failed) is changed
    assert len(session.catalog.requests) > attempts
    assert len(failed) == 2


@pytest.mark.parametrize("allow_pending", [False, True])
def test_service_pending_group_is_preserved_and_requires_allow_pending(session, allow_pending):
    session.add_group("pending", completed=False)
    if allow_pending:
        request = session.compact(force=True, allow_pending=True)
        assert len(session.checkpoints()) == 1
        assert_native_pairs(request.messages, pending_ids={"pending-0", "pending-1"})
        validate_tool_pairs(request.messages, allow_pending=True)
        assert {item["tool_call_id"] for item in request.messages if item["role"] == "tool"} == {"last-0", "last-1"}
    else:
        with pytest.raises(CompactionError):
            session.compact(force=True)
        assert not session.checkpoints()


def test_service_harness_returns_tool_result_too_large_when_full_candidate_cannot_compact(session, monkeypatch):
    class OversizedTool(Tool):
        name = "oversized"
        description = "Return a large test observation."
        model_exposure = "direct"
        input_schema = {"type": "object", "properties": {}, "additionalProperties": False}

        def __init__(self):
            self.calls = 0

        def run(self, arguments):
            self.calls += 1
            return ToolResult(name=self.name, output={"complete_evidence": "OVERSIZED_ONLY" * 20000})

    class HarnessCatalog(RecordingCompactCatalog):
        def default_model_for_account(self, account, purpose="chat"):
            return session.model if purpose == "chat" else super().default_model_for_account(account, purpose)

        def stream_prepared_chat_for_account(self, **kwargs):
            request = self.requests[-1]
            if request.model_config.get("purpose") == "context_compaction":
                yield from super().stream_prepared_chat_for_account(**kwargs)
                return
            actions = [item for item in self.requests if item.model_config.get("purpose") == "agent_action"]
            if len(actions) == 1:
                yield ModelStreamChunk(tool_call_deltas=(ToolCallDelta(index=0, id="oversized-call", name_delta="oversized", arguments_delta="{}"),))
                yield ModelStreamChunk(stop_reason="tool_calls")
            else:
                assert len(actions) == 2
                yield ModelStreamChunk(content_delta="完整结果过大，请缩小查询范围。")
                yield ModelStreamChunk(stop_reason="stop")

    session.model["context_window_tokens"] = 30000
    tool = OversizedTool()
    catalog = HarnessCatalog(session.catalog.model)
    session.service.model_catalog = catalog
    session.service.model_calls.model_catalog = catalog
    session.service.compaction.model_catalog = catalog
    session.service.titles.model_catalog = catalog
    monkeypatch.setattr("backend.app.plugins.build_available_tools", lambda **_kwargs: [tool])
    result = session.service._execute_agent_harness(
        session.account_id, {"session_id": session.session_id, "turn_id": CURRENT_TURN},
        {"message_id": CURRENT_USER, "parent_message_id": None, "content": CURRENT_CONTENT,
         "context_resources": [], "thinking_mode": "default"},
        on_workflow_event=lambda _event: None,
    )
    assert tool.calls == 1
    assert len(result["tool_results"]) == 1
    assert result["tool_results"][0]["output"]["complete_evidence"] == "OVERSIZED_ONLY" * 20000
    assert not session.checkpoints()
    failures = [event for event in session.events() if event.type == "tool/result" and event.data.get("tool_call_id") == "oversized-call"]
    assert len(failures) == 1
    assert failures[0].data["status"] == "failed"
    assert failures[0].data["error"]["code"] == "TOOL_RESULT_TOO_LARGE"
    actions = [request for request in catalog.requests if request.model_config.get("purpose") == "agent_action"]
    assert len(actions) == 2
    for request in actions:
        assert_native_pairs(request.messages)
    assert "TOOL_RESULT_TOO_LARGE" in actions[-1].messages[-1]["content"]
    assert "OVERSIZED_ONLY" not in json.dumps(actions[-1].canonical_dict())
    assert not any(request.model_config.get("purpose") == "context_compaction" for request in catalog.requests)


def test_service_harness_rebuilds_visible_skills_during_repeated_automatic_and_tool_candidate_compaction(session, monkeypatch):
    """Exercise Service's actual prepare/rebuild closures, with only I/O faked."""
    session.model["context_window_tokens"] = 12000
    budget = ContextBudget(12000, session.model["max_output_tokens"])
    assemblies = []
    rebuilds = []
    original_assembly = AgentHarnessRuntime.assemble_request_context
    original_compact = session.service.compaction.compact_model_request_if_needed

    def record_compact(**kwargs):
        rebuild = kwargs["rebuild_request"]

        def record_rebuild(events):
            request = rebuild(events)
            if events[-1].type == "compaction/checkpoint" and events[-1].data.get("summary"):
                rebuilds.append((events[-1].seq, request.canonical_dict()))
            return request

        return original_compact(**{**kwargs, "rebuild_request": record_rebuild})

    def record_assembly(runtime, **kwargs):
        assembly = original_assembly(runtime, **kwargs)
        assemblies.append({
            "read_skills": set(kwargs["read_skills"]),
            "live_skills": set(visible_loaded_skill_names(session.events(), current_turn_ids=[CURRENT_TURN])),
            "tools": {tool.name for tool in assembly.tools},
        })
        return assembly

    class EvidenceSkill(Skill):
        name = "evidence"
        description = "Read test evidence."

        def read(self, context):
            return SkillDocument(name=self.name, content="Check the recorded units and source identifiers.", allowed_tools=frozenset({"protected_lookup"}))

    class EvidenceTool(Tool):
        name = "protected_lookup"
        description = "Return one evidence identifier."
        input_schema = {"type": "object", "properties": {"round": {"type": "integer"}}, "required": ["round"], "additionalProperties": False}

        def __init__(self):
            self.calls = []

        def run(self, arguments):
            self.calls.append(arguments["round"])
            return ToolResult(name=self.name, output={"fact": "ALT 45 U/L", "source": f"report-{arguments['round']}"})

    class GrowHistoryTool(Tool):
        name = "grow_history"
        description = "Return a complete test evidence block."
        model_exposure = "direct"
        input_schema = {"type": "object", "properties": {"round": {"type": "integer"}, "phase": {"type": "string", "enum": ["fill", "burst"]}}, "required": ["round", "phase"], "additionalProperties": False}

        def __init__(self):
            self.calls = []

        def run(self, arguments):
            self.calls.append((arguments["round"], arguments["phase"]))
            if arguments["phase"] == "fill":
                # Leave the next action under the trigger; its following burst
                # then exercises the complete, not-yet-persisted tool candidate.
                tokens = max(1, budget.trigger - 450 - ESTIMATE(catalog.requests[-1]))
            else:
                tokens = 2800
            return ToolResult(name=self.name, output={"round": arguments["round"], "phase": arguments["phase"], "evidence": "z" * (tokens * 4)})

    class HarnessCatalog(RecordingCompactCatalog):
        def __init__(self, model):
            super().__init__(model)
            self.actions = []

        def default_model_for_account(self, account, purpose="chat"):
            return session.model if purpose == "chat" else super().default_model_for_account(account, purpose)

        def stream_prepared_chat_for_account(self, **kwargs):
            request = self.requests[-1]
            if request.model_config.get("purpose") == "context_compaction":
                yield from super().stream_prepared_chat_for_account(**kwargs)
                return
            index = len(self.actions)
            self.actions.append(request)
            assert index <= 12
            assert_native_pairs(request.messages)
            assert request.messages[0]["content"] == CURRENT_CONTENT
            assert sum(str(item.get("content", "")).startswith("<compacted-summary>") for item in request.messages) == 1
            tool_names = {item.name for item in request.tools}
            round_index, phase = divmod(index, 4)
            if phase == 0:
                assert "protected_lookup" not in tool_names, json.dumps({
                    "action_index": index,
                    "action_estimates": [ESTIMATE(item) for item in self.actions],
                    "statuses": [event.data for event in session.events() if event.type == "compaction/status"],
                    "last_tool_error": json.loads(request.messages[-1]["content"]).get("error") if request.messages[-1]["role"] == "tool" else None,
                }, ensure_ascii=False)
            else:
                assert "protected_lookup" in tool_names
            if index == 12:
                yield ModelStreamChunk(content_delta="三次结果均已核对。")
                yield ModelStreamChunk(stop_reason="stop")
                return
            if phase == 0:
                name, arguments = "load_skill", {"name": "evidence"}
            elif phase == 2:
                name, arguments = "protected_lookup", {"round": round_index}
            else:
                name, arguments = "grow_history", {"round": round_index, "phase": "fill" if phase == 1 else "burst"}
            yield ModelStreamChunk(tool_call_deltas=(ToolCallDelta(index=0, id=f"action-{index}", name_delta=name, arguments_delta=json.dumps(arguments)),))
            yield ModelStreamChunk(stop_reason="tool_calls")

    evidence, grow = EvidenceTool(), GrowHistoryTool()
    catalog = HarnessCatalog(session.catalog.model)
    session.service.model_catalog = catalog
    session.service.model_calls.model_catalog = catalog
    session.service.compaction.model_catalog = catalog
    session.service.titles.model_catalog = catalog
    monkeypatch.setattr("backend.app.plugins.build_available_tools", lambda **_kwargs: [evidence, grow])
    monkeypatch.setattr("backend.app.agent_runtime.runtime.build_builtin_skills", lambda: [EvidenceSkill()])
    monkeypatch.setattr(AgentHarnessRuntime, "assemble_request_context", record_assembly)
    monkeypatch.setattr(session.service.compaction, "compact_model_request_if_needed", record_compact)
    try:
        result = session.service._execute_agent_harness(
            session.account_id, {"session_id": session.session_id, "turn_id": CURRENT_TURN},
            {"message_id": CURRENT_USER, "parent_message_id": None, "content": CURRENT_CONTENT,
             "context_resources": [], "thinking_mode": "default"},
            on_workflow_event=lambda _event: None,
        )
    except CompactionError as exc:
        for (candidate_seq, candidate), (live_seq, live) in zip(rebuilds, rebuilds[1:]):
            if live_seq <= candidate_seq:
                continue
            changed_fields = [key for key in candidate if candidate[key] != live[key]]
            time_pattern = r'"current_time"\s*:\s*"([^"]+)"'
            candidate_time = re.search(time_pattern, candidate["system"])
            live_time = re.search(time_pattern, live["system"])
            same_system_except_time = re.sub(time_pattern, '"current_time":"<time>"', candidate["system"]) == re.sub(time_pattern, '"current_time":"<time>"', live["system"])
            exc.add_note(json.dumps({
                "candidate_seq": candidate_seq, "live_seq": live_seq,
                "changed_fields": changed_fields,
                "candidate_time": candidate_time.group(1) if candidate_time else None,
                "live_time": live_time.group(1) if live_time else None,
                "same_system_except_current_time": same_system_except_time,
            }, ensure_ascii=False))
        raise
    assert result["status"] == "completed"
    assert evidence.calls == [0, 1, 2]
    assert grow.calls == [(index, phase) for index in range(3) for phase in ("fill", "burst")]
    assert len(result["tool_results"]) == 9
    assert any(
        item["live_skills"] == {"evidence"} and not item["read_skills"]
        and "protected_lookup" not in item["tools"]
        for item in assemblies
    ), "Virtual checkpoint events must revoke the skill before that checkpoint is persisted"
    checkpoints = session.checkpoints()
    assert len(checkpoints) >= 4
    statuses = [event.data for event in session.events() if event.type == "compaction/status"]
    assert any(item["reason"] == "threshold" and item["status"] == "completed" for item in statuses)
    assert sum(item["reason"] == "tool_result" and item["status"] == "completed" for item in statuses) == 3
    assert not any(item["reason"] == "overflow" for item in statuses)
    for checkpoint in checkpoints:
        assert checkpoint.data["estimated_tokens_after"] <= budget.target
        prior_events = [event for event in session.events() if event.seq < checkpoint.seq]
        visible = derive_model_messages(prior_events, current_turn_ids=[CURRENT_TURN], include_surface_metadata=True)
        assert set(checkpoint.source_event_seqs) <= {item["_source_seq"] for item in visible}
        assert 1 not in checkpoint.source_event_seqs
    for request in catalog.requests:
        if request.model_config.get("purpose") == "context_compaction":
            assert ESTIMATE(request) + request.model_config["max_tokens"] <= catalog.model["context_window_tokens"]
    for index in range(3):
        after_burst = catalog.actions[(index + 1) * 4]
        assert after_burst.messages[-1]["tool_call_id"] == f"action-{index * 4 + 3}"
        assert len(json.loads(after_burst.messages[-1]["content"])["output"]["evidence"]) == 11200

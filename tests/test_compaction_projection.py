from copy import deepcopy
import pytest
from backend.app.domain.conversations.timeline import ConversationTimelineProjector, active_records, records_from_events
from backend.app.domain.conversations.model_history import derive_model_messages, visible_loaded_skill_names
from backend.app.domain.conversations.queries import messages_from_events
from backend.app.domain.conversations.events import SessionEvent, SessionEventCorruptionError, SessionHeader, make_event, validate_contiguous_events
from backend.app.storage.session_recovery import interrupted_turn_closers
from backend.app.application.conversations.presenter import record_response


def wrapped(summary):
    return f"<compacted-summary>\n{summary}\n</compacted-summary>"


class Log:
    def __init__(self):
        self.events = []

    def add(self, kind, data, **envelope):
        event = make_event(kind, len(self.events), data, timestamp=1000, **envelope)
        self.events.append(event)
        return event

    def start(self, turn="t", **data):
        return self.add("turn/start", {"turn_id": turn, "user_message_id": f"message-{len(self.events) + 1}", "stream_id": f"stream-{turn}", **data})

    def message(self, content, turn="t", role="user", **data):
        return self.add(
            f"{role}/message",
            {
                "turn_id": turn,
                "message_id": f"message-{len(self.events)}",
                "parent_message_id": None,
                "content": content,
                **data,
            },
        )

    def checkpoint(
        self,
        sources,
        summary="summary",
        turn="t",
        start=None,
        end=None,
        compaction_id=None,
    ):
        positions = [
            source.surface_op["start"]
            if source.type == "compaction/checkpoint"
            else source.seq
            for source in sources
        ]
        return self.add(
            "compaction/checkpoint",
            {
                "turn_id": turn,
                "message_id": f"checkpoint-{len(self.events)}",
                "compaction_id": compaction_id or f"compaction_{len(self.events)}",
                "summary": summary,
                "content": wrapped(summary),
                "estimated_tokens_before": 1000,
                "estimated_tokens_after": 500,
                "target_tokens": 600,
                "replaced_turn_ids": sorted(
                    {source.data["turn_id"] for source in sources}
                ),
            },
            source_event_seqs=[source.seq for source in sources],
            surface_op={
                "op": "replace",
                "start": min(positions) if start is None else start,
                "end": max(positions) + 1 if end is None else end,
            },
        )

    def end(self, turn="t"):
        return self.add("turn/end", {"turn_id": turn, "reason": {"kind": "completed"}})

    def projection(self, **options):
        validate_contiguous_events(self.events)
        return derive_model_messages(iter(self.events), **options)


def test_sparse_sources_preserve_unlisted_messages_and_original_details():
    log = Log()
    log.start()
    first = log.message("first")
    middle = log.message("keep middle", role="assistant")
    last = log.message("last")
    log.checkpoint([first, last])
    original = deepcopy([event.to_record() for event in log.events])

    assert log.projection() == [
        {"role": "user", "content": wrapped("summary")},
        {"role": "assistant", "content": "keep middle"},
    ]
    assert [event.to_record() for event in log.events] == original
    assert [message["content"] for message in messages_from_events(log.events)] == [
        "first",
        "keep middle",
        "last",
    ]
    records = active_records(records_from_events(log.events), log.events)
    assert {
        record["seq"] for record in records if record["kind"] in {"user", "assistant"}
    } == {first.seq, middle.seq, last.seq}


def test_three_compactions_absorb_checkpoint_by_source_seq_and_preserve_position():
    log = Log()
    log.start()
    original = log.message("original")
    retained = log.message("retained")
    first = log.checkpoint([original], "summary one")
    added = log.message("added", role="assistant")
    second = log.checkpoint([first, added], "summary two")
    third = log.checkpoint([second], "summary three")

    assert second.source_event_seqs == (first.seq, added.seq)
    assert third.source_event_seqs == (second.seq,)
    assert third.surface_op["end"] < second.seq
    assert log.projection(include_surface_metadata=True) == [
        {
            "role": "user",
            "content": wrapped("summary three"),
            "_source_seq": third.seq,
            "_surface_seq": original.seq,
            "_turn_id": "t",
        },
        {
            "role": "user",
            "content": "retained",
            "_source_seq": retained.seq,
            "_surface_seq": retained.seq,
            "_turn_id": "t",
        },
    ]


def test_independent_summaries_survive_until_explicitly_absorbed():
    log = Log()
    first_message = log.message("first")
    second_message = log.message("second")
    first = log.checkpoint([first_message], "first summary", start=0, end=2)
    second = log.checkpoint([second_message], "second summary", start=0, end=2)
    assert [item["content"] for item in log.projection()] == [
        wrapped("first summary"),
        wrapped("second summary"),
    ]
    log.checkpoint([first, second], "combined")
    assert log.projection() == [{"role": "user", "content": wrapped("combined")}]


def test_range_only_locates_summary_even_when_source_is_outside_it():
    log = Log()
    retained = log.message("retained")
    selected = log.message("selected")
    summary = log.checkpoint([selected], start=0, end=1)
    projected = log.projection(include_surface_metadata=True)
    assert [item["_source_seq"] for item in projected] == [retained.seq, summary.seq]
    assert [item["_surface_seq"] for item in projected] == [0, 0]


def test_partial_current_turn_compaction_preserves_unselected_tools_and_observations():
    log = Log()
    log.start()
    user = log.message("question")
    tool_call = {
        "id": "call",
        "type": "function",
        "function": {"name": "load_skill", "arguments": '{"name":"report-query"}'},
    }
    request = log.message(
        None, role="assistant", branch_addressable=False, tool_calls=[tool_call]
    )
    log.add(
        "tool/call",
        {
            "turn_id": "t",
            "call_id": "call",
            "tool_call_id": "call",
            "name": "load_skill",
            "arguments": {"name": "report-query"},
        },
    )
    result = log.add(
        "tool/result",
        {
            "turn_id": "t",
            "call_id": "call",
            "tool_call_id": "call",
            "name": "load_skill",
            "result": "skill instructions",
            "status": "completed",
        },
    )
    observation = log.add(
        "harness/observation",
        {"turn_id": "t", "step": 1, "observation": {"fact": 7}, "status": "completed"},
    )
    tail = log.message("continue", branch_addressable=False)
    first = log.checkpoint([user], end=tail.seq + 1)

    projected = log.projection(include_surface_metadata=True)
    assert [item["_source_seq"] for item in projected] == [
        first.seq,
        request.seq,
        result.seq,
        observation.seq,
        tail.seq,
    ]
    assert projected[1]["tool_calls"] == [tool_call]
    assert visible_loaded_skill_names(log.events) == ["report-query"]
    second = log.checkpoint([first, request, result, observation], "updated summary")
    assert [
        item["_source_seq"] for item in log.projection(include_surface_metadata=True)
    ] == [second.seq, tail.seq]
    assert visible_loaded_skill_names(log.events) == []


@pytest.mark.parametrize("include_user_context", [False, True])
@pytest.mark.parametrize("include_surface_metadata", [False, True])
def test_metadata_options_are_independent_and_preserve_patched_attachment_context(
    include_user_context, include_surface_metadata
):
    log = Log()
    user = log.message("before")
    resources = [{"resource_type": "file", "resource_id": "image"}]
    log.add(
        "user/message-update",
        {
            "message_id": user.data["message_id"],
            "patch": {"content": "after", "context_resources": resources},
        },
    )
    answer = log.add(
        "assistant/message",
        {
            "turn_id": "t",
            "message_id": "answer",
            "parent_message_id": user.data["message_id"],
            "content": "answer",
        },
        source_event_seqs=[user.seq],
    )
    expected = [
        {"role": "user", "content": "after"},
        {"role": "assistant", "content": "answer"},
    ]
    if include_user_context:
        expected[0].update(
            _message_id=user.data["message_id"], _context_resources=resources
        )
    if include_surface_metadata:
        for item, event in zip(expected, [user, answer]):
            item.update(_source_seq=event.seq, _surface_seq=event.seq, _turn_id="t")
    assert (
        log.projection(
            include_user_context=include_user_context,
            include_surface_metadata=include_surface_metadata,
        )
        == expected
    )


@pytest.mark.parametrize("retry", [False, True], ids=["edit", "retry"])
def test_superseded_checkpoint_owner_restores_shared_history_without_summary_leak(
    retry,
):
    log = Log()
    log.start("history")
    log.message("shared history", turn="history")
    log.end("history")
    log.start("old")
    old_user = log.message("old question", turn="old")
    old_answer = log.message("old answer", turn="old", role="assistant")
    log.checkpoint([old_user, old_answer], "old summary", turn="old")
    log.end("old")
    log.start(
        "new",
        supersedes_turn_id="old",
        user_message_id=old_user.data["message_id"] if retry else "edited-user",
    )
    if not retry:
        log.message("edited question", turn="new", message_id="edited-user")
    log.message("new answer", turn="new", role="assistant")

    assert [item["content"] for item in log.projection()] == [
        "shared history",
        "old question" if retry else "edited question",
        "new answer",
    ]


def test_invalid_source_branch_invalidates_entire_summary_chain_and_restores_shared_inputs():
    log = Log()
    log.start("history")
    shared = log.message("shared fact", turn="history")
    log.end("history")
    log.start("old")
    old = log.message("obsolete fact", turn="old")
    log.end("old")
    log.start("owner")
    first = log.checkpoint([shared, old], "mixed summary", turn="owner")
    retained = log.message("retained fact", turn="owner")
    log.checkpoint([first, retained], "derived mixed summary", turn="owner")
    log.end("owner")
    log.start("new", supersedes_turn_id="old")
    log.message("corrected fact", turn="new")
    assert [item["content"] for item in log.projection()] == [
        "shared fact",
        "retained fact",
        "corrected fact",
    ]


def test_checkpoint_from_inactive_owner_cannot_hide_still_active_sources():
    log = Log()
    log.start("history")
    shared = log.message("shared fact", turn="history")
    log.start("old")
    log.checkpoint([shared], "inactive summary", turn="old")
    log.start("new", supersedes_turn_id="old")
    assert log.projection() == [{"role": "user", "content": "shared fact"}]


def test_current_turn_ids_allow_checkpoint_before_its_turn_start_is_in_input():
    log = Log()
    log.start("history")
    shared = log.message("shared fact", turn="history")
    log.checkpoint([shared], turn="current")
    assert log.projection(current_turn_ids=iter(["current"])) == [
        {"role": "user", "content": wrapped("summary")}
    ]


def test_sources_must_be_current_surface_and_cannot_reconsume_hidden_originals():
    log = Log()
    original = log.message("original")
    log.checkpoint([original], "valid summary")
    retained = log.message("retained")
    log.checkpoint([original, retained], "stale selection")
    assert [item["content"] for item in log.projection()] == [
        wrapped("valid summary"),
        "retained",
    ]


def checkpoint_record():
    log = Log()
    source = log.message("source")
    log.message("retained")
    return log.checkpoint([source]).to_record()


@pytest.mark.parametrize(
    "sources", [None, [], [True], [-1], [2], [3], [0, 0], [0.0], ["0"], "0"]
)
def test_checkpoint_rejects_missing_empty_invalid_or_non_prior_sources(sources):
    record = checkpoint_record()
    record["sourceEventSeqs"] = sources
    with pytest.raises(SessionEventCorruptionError, match="sourceEventSeqs"):
        SessionEvent.from_record(record)


def test_checkpoint_rejects_absent_sources():
    record = checkpoint_record()
    del record["sourceEventSeqs"]
    with pytest.raises(SessionEventCorruptionError, match="sourceEventSeqs"):
        SessionEvent.from_record(record)


@pytest.mark.parametrize(
    "operation",
    [
        None,
        "append",
        {"op": "replace", "start": 0, "end": 3},
        {"op": "replace", "start": -1, "end": 1},
        {"op": "replace", "start": 1, "end": 1},
        {"op": "replace", "start": False, "end": 1},
    ],
)
def test_checkpoint_rejects_invalid_or_future_placement(operation):
    record = checkpoint_record()
    record["surfaceOp"] = operation
    with pytest.raises(SessionEventCorruptionError):
        SessionEvent.from_record(record)


@pytest.mark.parametrize("content", [None, "", "  ", {}, []])
def test_checkpoint_rejects_non_text_or_empty_summary(content):
    record = checkpoint_record()
    record["data"]["content"] = content
    with pytest.raises(SessionEventCorruptionError, match="content"):
        SessionEvent.from_record(record)


def test_full_event_validation_rejects_non_message_checkpoint_sources():
    log = Log()
    start = log.start()
    log.checkpoint([start])
    with pytest.raises(SessionEventCorruptionError, match="model message events"):
        validate_contiguous_events(log.events)


def test_incremental_validation_accepts_references_to_unavailable_prefix():
    event = SessionEvent.from_record(checkpoint_record())
    assert validate_contiguous_events([event], start_seq=event.seq) == [event]


def status_data(status="running", **extra):
    return {
        "turn_id": "t",
        "message_id": "compaction_operation",
        "status": status,
        "reason": "threshold",
        "estimated_tokens_before": 1000,
        "target_tokens": 600,
        **extra,
    }


@pytest.mark.parametrize(
    "status,extra",
    [
        ("completed", {"estimated_tokens_after": 500}),
        (
            "failed",
            {"error": {"code": "COMPACTION_FAILED", "message": "summary failed"}},
        ),
    ],
)
def test_status_updates_one_timeline_record_and_never_changes_model_context(
    status, extra
):
    log = Log()
    log.start()
    log.message("question")
    before = log.projection(include_surface_metadata=True, include_user_context=True)
    running = log.add("compaction/status", status_data())
    projector = ConversationTimelineProjector(log.events)
    initial_record = next(
        item for item in projector.records() if item["kind"] == "context"
    )
    assert initial_record["status"] == "running"
    terminal = log.add("compaction/status", status_data(status, **extra))
    changed = projector.apply_events([terminal])
    assert "compaction_operation" in changed
    projected = projector.records()
    assert projected == records_from_events(log.events)
    contexts = [item for item in projected if item["kind"] == "context"]
    assert len(contexts) == 1
    assert contexts[0] == {
        **status_data(status, **extra),
        "record_id": "compaction_operation",
        "call_id": "compaction_operation",
        "context_id": "compaction_operation",
        "kind": "context",
        "context_type": "compaction_status",
        "purpose": "context_compaction",
        "label": "上下文压缩",
        "seq": running.seq,
        "time": running.time,
        "source_event_seqs": [running.seq, terminal.seq],
    }
    assert (
        log.projection(include_surface_metadata=True, include_user_context=True)
        == before
    )
    assert visible_loaded_skill_names(log.events) == []


def test_status_round_trips_and_checkpoint_timeline_preserves_token_estimates():
    from backend.app.storage.session_persistence import JsonlSessionPersistence

    log = Log()
    log.start()
    source = log.message("question")
    running = log.add("compaction/status", status_data())
    checkpoint = log.add(
        "compaction/checkpoint",
        {
            "turn_id": "t",
            "message_id": "compaction_operation_summary",
            "compaction_id": "compaction_operation",
            "summary": "summary",
            "content": wrapped("summary"),
            "replaced_turn_ids": ["t"],
            "estimated_tokens_before": 1000,
            "estimated_tokens_after": 500,
            "target_tokens": 600,
        },
        source_event_seqs=[source.seq],
        surface_op={"op": "replace", "start": source.seq, "end": source.seq + 1},
    )
    log.add("compaction/status", status_data("completed", estimated_tokens_after=500))
    persistence = JsonlSessionPersistence()
    account = "00000000-0000-4000-8000-000000000001"
    header = SessionHeader(id="session", account_id=account, created_at=1000)
    persistence.create(header)
    persistence.append(
        account, "session", log.events[: running.seq + 1], created_at=1000
    )
    persistence.append(
        account, "session", log.events[running.seq + 1 :], created_at=1000
    )
    stored = persistence.load(account, "session", repair=False)
    assert list(stored.events) == log.events
    contexts = [
        item for item in records_from_events(stored.events) if item["kind"] == "context"
    ]
    assert [item["context_type"] for item in contexts] == [
        "compaction_status",
        "compacted_summary",
    ]
    for item in contexts:
        assert item["status"] == "completed"
        assert item["estimated_tokens_before"] == 1000
        assert item["estimated_tokens_after"] == 500
        assert item["target_tokens"] == 600
    assert contexts[1]["source_event_seqs"] == [source.seq, checkpoint.seq]
    assert derive_model_messages(stored.events) == [
        {"role": "user", "content": wrapped("summary")}
    ]


@pytest.mark.parametrize("reason", ["threshold", "overflow", "tool_result"])
def test_status_accepts_each_compaction_reason(reason):
    assert (
        make_event("compaction/status", 0, status_data(reason=reason)).surface_op
        is None
    )


@pytest.mark.parametrize(
    "field",
    [
        "turn_id",
        "message_id",
        "status",
        "reason",
        "estimated_tokens_before",
        "target_tokens",
    ],
)
def test_status_requires_all_base_fields(field):
    data = status_data()
    del data[field]
    with pytest.raises(SessionEventCorruptionError, match=field):
        make_event("compaction/status", 0, data)


@pytest.mark.parametrize(
    "patch",
    [
        {"turn_id": ""},
        {"turn_id": None},
        {"message_id": "wrong_prefix"},
        {"message_id": "compaction_"},
        {"message_id": 7},
        {"status": "unknown"},
        {"status": []},
        {"reason": "unknown"},
        {"reason": {}},
        {"estimated_tokens_before": -1},
        {"estimated_tokens_before": True},
        {"target_tokens": "600"},
        {"target_tokens": 1.5},
        {"estimated_tokens_after": 500},
        {"status": "completed"},
        {"status": "completed", "estimated_tokens_after": None},
        {"status": "completed", "estimated_tokens_after": False},
        {"status": "completed", "estimated_tokens_after": -1},
        {"status": "failed"},
        {"status": "failed", "error": "failed"},
        {"status": "failed", "error": {}},
        {"status": "failed", "error": {"code": "FAILED", "message": ""}},
        {"status": "failed", "error": {"code": 1, "message": "failed"}},
        {
            "status": "failed",
            "error": {"code": "FAILED", "message": "failed"},
            "estimated_tokens_after": 500,
        },
        {"error": None},
    ],
)
def test_status_rejects_invalid_fields_and_status_dependent_values(patch):
    with pytest.raises(SessionEventCorruptionError):
        make_event("compaction/status", 0, status_data(**patch))


@pytest.mark.parametrize(
    "operation", ["append", {"op": "replace", "start": 0, "end": 1}]
)
def test_status_cannot_carry_surface_operation(operation):
    with pytest.raises(SessionEventCorruptionError, match="cannot carry surfaceOp"):
        make_event("compaction/status", 1, status_data(), surface_op=operation)


def test_checkpoint_cannot_consume_status_events():
    log = Log()
    status = log.add("compaction/status", status_data())
    log.checkpoint([status])
    with pytest.raises(SessionEventCorruptionError, match="model message events"):
        validate_contiguous_events(log.events)


def test_status_records_follow_active_branch_and_keep_failed_details_durable():
    log = Log()
    log.start()
    log.add(
        "compaction/status",
        status_data("failed", error={"code": "FAILED", "message": "old failure"}),
    )
    log.start("retry", supersedes_turn_id="t")
    log.add(
        "compaction/status", status_data(turn_id="retry", message_id="compaction_retry")
    )
    records = records_from_events(log.events)
    assert len(records) == 2
    assert [item["record_id"] for item in active_records(records, log.events)] == [
        "compaction_retry"
    ]
    assert log.projection() == []


@pytest.mark.parametrize(
    "field", ["estimated_tokens_before", "estimated_tokens_after", "target_tokens"]
)
def test_checkpoint_rejects_invalid_token_estimates(field):
    record = checkpoint_record()
    record["data"][field] = -1
    with pytest.raises(SessionEventCorruptionError, match=field):
        SessionEvent.from_record(record)


@pytest.mark.parametrize(
    "field",
    [
        "compaction_id",
        "summary",
        "estimated_tokens_before",
        "estimated_tokens_after",
        "target_tokens",
    ],
)
def test_checkpoint_requires_complete_commit_contract(field):
    record = checkpoint_record()
    del record["data"][field]
    with pytest.raises(SessionEventCorruptionError, match=field):
        SessionEvent.from_record(record)


@pytest.mark.parametrize("summary", [None, "", " \n\t", 7, False, [], {}])
def test_checkpoint_rejects_empty_or_non_text_summary(summary):
    record = checkpoint_record()
    record["data"]["summary"] = summary
    with pytest.raises(
        SessionEventCorruptionError, match="summary must be non-empty text"
    ):
        SessionEvent.from_record(record)


@pytest.mark.parametrize(
    "content",
    [
        "summary",
        "<compacted-summary>\nsummary",
        "summary\n</compacted-summary>",
        wrapped("other summary"),
        wrapped(""),
        "prefix\n" + wrapped("summary"),
    ],
)
def test_checkpoint_rejects_content_not_completely_wrapping_exact_summary(content):
    record = checkpoint_record()
    record["data"]["content"] = content
    with pytest.raises(SessionEventCorruptionError, match="completely wrap summary"):
        SessionEvent.from_record(record)


def test_checkpoint_preserves_multiline_summary_and_appended_exact_evidence():
    record = checkpoint_record()
    summary = "ALT 45 U/L\n已导入医疗报告，待核对来源。"
    content = (
        wrapped(summary)
        + '\n<unresolved-context-observations>\n[{"value":45}]\n</unresolved-context-observations>'
    )
    record["data"].update(summary=summary, content=content)
    event = SessionEvent.from_record(record)
    assert event.data["summary"] == summary
    assert event.data["content"] == content


def unknown_tool_log():
    log = Log()
    log.start()
    log.message(
        None,
        role="assistant",
        branch_addressable=False,
        tool_calls=[
            {
                "id": "call",
                "type": "function",
                "function": {"name": "write_report", "arguments": "{}"},
            }
        ],
    )
    result = log.add(
        "tool/result",
        {
            "turn_id": "t",
            "call_id": "call",
            "tool_call_id": "call",
            "name": "write_report",
            "status": "interrupted",
            "result": None,
            "error": {"code": "TOOL_OUTCOME_UNKNOWN", "message": "outcome unknown"},
        },
    )
    return log, result


def resolved_tool_result(log, previous, status="completed"):
    return log.add(
        "tool/result",
        {
            "turn_id": "t",
            "call_id": "call",
            "tool_call_id": "call",
            "name": "write_report",
            "status": status,
            "result": {"completed_effect": True},
            **(
                {"error": {"code": "WRITE_FAILED", "message": "write failed"}}
                if status == "failed"
                else {}
            ),
        },
        source_event_seqs=[previous.seq],
        surface_op={"op": "replace", "start": previous.seq, "end": previous.seq + 1},
    )


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_pending_execution_metadata_is_private_and_cleared_by_exact_final_result(
    status,
):
    log, previous = unknown_tool_log()
    assert (
        log.projection(include_surface_metadata=True)[-1]["_pending_execution"] is True
    )
    assert "_pending_execution" not in log.projection()[-1]
    resolved = resolved_tool_result(log, previous, status)
    projected = log.projection(include_surface_metadata=True)
    assert [item["role"] for item in projected] == ["assistant", "tool"]
    assert projected[-1]["_source_seq"] == resolved.seq
    assert projected[-1]["_surface_seq"] == previous.seq
    assert "_pending_execution" not in projected[-1]
    assert log.events[previous.seq].data["status"] == "interrupted"


@pytest.mark.parametrize(
    "patch",
    [
        {"status": "failed"},
        {"error": {"code": "OTHER", "message": "interrupted"}},
    ],
)
def test_only_interrupted_unknown_outcomes_are_pending_execution(patch):
    log, previous = unknown_tool_log()
    record = previous.to_record()
    record["data"].update(patch)
    log.events[-1] = SessionEvent.from_record(record)
    assert "_pending_execution" not in log.projection(include_surface_metadata=True)[-1]


@pytest.mark.parametrize("sources", [None, [], [0, 1]])
def test_tool_result_replacement_requires_exactly_one_source(sources):
    log, previous = unknown_tool_log()
    record = resolved_tool_result(log, previous).to_record()
    record["sourceEventSeqs"] = sources
    with pytest.raises(SessionEventCorruptionError, match="exactly one earlier result"):
        SessionEvent.from_record(record)


def test_tool_result_replacement_requires_exact_source_position_and_final_status():
    log, previous = unknown_tool_log()
    record = resolved_tool_result(log, previous).to_record()
    record["surfaceOp"] = {"op": "replace", "start": 0, "end": 1}
    with pytest.raises(SessionEventCorruptionError, match="exact source"):
        SessionEvent.from_record(record)
    record = log.events[-1].to_record()
    record["data"].update(status="interrupted", error={"code": "TOOL_OUTCOME_UNKNOWN"})
    with pytest.raises(
        SessionEventCorruptionError, match="completed or failed outcome"
    ):
        SessionEvent.from_record(record)


@pytest.mark.parametrize("field", ["turn_id", "call_id", "tool_call_id", "name"])
def test_tool_result_replacement_must_resolve_same_call(field):
    log, previous = unknown_tool_log()
    record = resolved_tool_result(log, previous).to_record()
    record["data"][field] = "another"
    log.events[-1] = SessionEvent.from_record(record)
    with pytest.raises(
        SessionEventCorruptionError, match="same interrupted unknown call"
    ):
        validate_contiguous_events(log.events)
    # Projection must not append the rejected replacement as an orphan result.
    projected = derive_model_messages(log.events, include_surface_metadata=True)
    assert [item["_source_seq"] for item in projected if item["role"] == "tool"] == [
        previous.seq
    ]


@pytest.mark.parametrize(
    "patch",
    [
        {"status": "completed"},
        {"result": {"already_known": True}},
        {"error": {"code": "OTHER", "message": "other failure"}},
    ],
)
def test_tool_result_replacement_source_must_be_unknown_interruption(patch):
    log, previous = unknown_tool_log()
    record = previous.to_record()
    record["data"].update(patch)
    log.events[-1] = SessionEvent.from_record(record)
    resolved_tool_result(log, previous)
    with pytest.raises(
        SessionEventCorruptionError, match="same interrupted unknown call"
    ):
        validate_contiguous_events(log.events)


@pytest.mark.parametrize("compaction_id", [None, "", "other", "compaction_", 7, [], {}])
def test_checkpoint_requires_explicit_valid_compaction_id(compaction_id):
    record = checkpoint_record()
    record["data"]["compaction_id"] = compaction_id
    with pytest.raises(SessionEventCorruptionError, match="compaction_id"):
        SessionEvent.from_record(record)


def test_checkpoint_immediately_completes_matching_status_at_its_original_position():
    log = Log()
    log.start()
    source = log.message("evidence")
    running = log.add(
        "compaction/status",
        status_data(estimated_tokens_before=2000, target_tokens=900),
    )
    projector = ConversationTimelineProjector(log.events)
    checkpoint = log.checkpoint([source], compaction_id="compaction_operation")
    # The checkpoint message id deliberately has no status-id naming relation.
    assert checkpoint.data["message_id"] != "compaction_operation_summary"
    assert "compaction_operation" in projector.apply_events([checkpoint])
    record = next(
        item
        for item in projector.records()
        if item["record_id"] == "compaction_operation"
    )
    assert record["status"] == "completed"
    assert record["seq"] == running.seq
    assert record["time"] == running.time
    assert record["source_event_seqs"] == [running.seq, checkpoint.seq]
    assert (
        record["estimated_tokens_before"],
        record["estimated_tokens_after"],
        record["target_tokens"],
    ) == (1000, 500, 600)
    assert "error" not in record
    assert projector.records() == records_from_events(log.events)


@pytest.mark.parametrize(
    "later_status,extra",
    [
        ("running", {}),
        ("completed", {"estimated_tokens_after": 123}),
        ("failed", {"error": {"code": "INTERRUPTED", "message": "late failure"}}),
    ],
)
def test_committed_checkpoint_remains_authoritative_after_later_status_and_turn_end(
    later_status, extra
):
    log = Log()
    log.start()
    source = log.message("evidence")
    running = log.add("compaction/status", status_data())
    checkpoint = log.checkpoint([source], compaction_id="compaction_operation")
    projector = ConversationTimelineProjector(log.events)
    later = log.add("compaction/status", status_data(later_status, **extra))
    log.end()
    projector.apply_events(log.events[later.seq :])
    record = next(
        item
        for item in projector.records()
        if item["record_id"] == "compaction_operation"
    )
    assert record["status"] == "completed"
    assert record["estimated_tokens_after"] == 500
    assert record["source_event_seqs"] == [running.seq, checkpoint.seq, later.seq]
    assert "error" not in record
    assert projector.records() == records_from_events(log.events)


def test_checkpoint_completes_only_explicit_operation_in_same_turn():
    log = Log()
    log.start()
    source = log.message("evidence")
    log.add("compaction/status", status_data())
    log.add("compaction/status", status_data(message_id="compaction_other"))
    log.checkpoint([source], compaction_id="compaction_other")
    log.end()
    statuses = {
        item["record_id"]: item
        for item in records_from_events(log.events)
        if item.get("context_type") == "compaction_status"
    }
    assert statuses["compaction_operation"]["status"] == "failed"
    assert statuses["compaction_other"]["status"] == "completed"
    log.start("next")
    next_source = log.message("next", turn="next")
    log.checkpoint([next_source], turn="next", compaction_id="compaction_operation")
    statuses = {
        item["record_id"]: item
        for item in records_from_events(log.events)
        if item.get("context_type") == "compaction_status"
    }
    assert statuses["compaction_operation"]["status"] == "failed"


@pytest.mark.parametrize(
    "torn_event_type", ["compaction/checkpoint", "compaction/status"]
)
def test_torn_batch_recovery_uses_complete_checkpoint_as_commit(torn_event_type):
    from backend.app.storage.session_persistence import JsonlSessionPersistence

    log = Log()
    log.start()
    source = log.message("evidence")
    running = log.add("compaction/status", status_data())
    checkpoint = log.checkpoint(
        [source], "committed summary", compaction_id="compaction_operation"
    )
    completed = log.add(
        "compaction/status", status_data("completed", estimated_tokens_after=500)
    )
    torn = checkpoint if torn_event_type == "compaction/checkpoint" else completed
    account = "00000000-0000-4000-8000-000000000001"
    persistence = JsonlSessionPersistence()
    persistence.create(
        SessionHeader(id="recovery", account_id=account, created_at=1000)
    )
    persistence.append(account, "recovery", log.events[: torn.seq], created_at=1000)
    # Simulate a short final write in an isolated test artifact, then exercise
    # the actual JSONL torn-tail repair and interrupted-turn recovery.
    with persistence._path(account, "recovery").open("ab") as handle:
        handle.write(persistence._line(torn.to_record())[:30])
    recovered = persistence.load(account, "recovery", repair=True)
    assert recovered.events[-1].type == "turn/end"
    assert not any(
        event.type == "compaction/status" and event.data["status"] == "completed"
        for event in recovered.events
    )
    assert recovered.events[running.seq].data["status"] == "running"
    status = next(
        item
        for item in records_from_events(recovered.events)
        if item.get("context_type") == "compaction_status"
    )
    if torn_event_type == "compaction/status":
        assert status["status"] == "completed"
        assert status["estimated_tokens_after"] == 500
        assert "error" not in status
        assert status["source_event_seqs"] == [running.seq, checkpoint.seq]
        assert derive_model_messages(recovered.events) == [
            {"role": "user", "content": wrapped("committed summary")}
        ]
    else:
        assert status["status"] == "failed"
        assert "estimated_tokens_after" not in status
        assert status["source_event_seqs"] == [running.seq, recovered.events[-1].seq]
        assert derive_model_messages(recovered.events) == [
            {"role": "user", "content": "evidence"}
        ]
    assert persistence.load(account, "recovery", repair=True).events == recovered.events


@pytest.mark.parametrize(
    "reason", ["completed", "cancelled", "aborted", "interrupted", "steered", "failed"]
)
def test_turn_end_projects_running_compaction_as_failed_without_model_events(reason):
    log = Log()
    log.start()
    log.message("question")
    running = log.add("compaction/status", status_data())
    # Existing terminal statuses must retain their own outcome and error.
    log.add(
        "compaction/status",
        status_data(
            "completed", message_id="compaction_done", estimated_tokens_after=500
        ),
    )
    log.add(
        "compaction/status",
        status_data(
            "failed",
            message_id="compaction_failed",
            error={"code": "FAILED", "message": "original failure"},
        ),
    )
    before = log.projection()
    projector = ConversationTimelineProjector(log.events)
    end = log.add("turn/end", {"turn_id": "t", "reason": {"kind": reason}})
    raw_events = deepcopy([event.to_record() for event in log.events])
    assert "compaction_operation" in projector.apply_events([end])
    assert projector.records() == records_from_events(log.events)
    statuses = {
        item["record_id"]: item
        for item in projector.records()
        if item.get("context_type") == "compaction_status"
    }
    recovered = statuses["compaction_operation"]
    assert recovered["status"] == "failed"
    assert recovered["error"]["code"] == "CONTEXT_COMPACTION_INTERRUPTED"
    assert recovered["source_event_seqs"] == [running.seq, end.seq]
    assert "estimated_tokens_after" not in recovered
    assert statuses["compaction_done"]["status"] == "completed"
    assert statuses["compaction_failed"]["error"] == {
        "code": "FAILED",
        "message": "original failure",
    }
    assert log.projection() == before
    assert [event.to_record() for event in log.events] == raw_events


def test_crash_recovery_turn_closer_finishes_running_compaction_projection():
    log = Log()
    log.start()
    log.message("question")
    log.add("compaction/status", status_data())
    closers = interrupted_turn_closers(log.events)
    assert [event.type for event in closers] == ["turn/end"]
    log.events.extend(closers)
    records = records_from_events(log.events)
    status = next(
        item for item in records if item.get("context_type") == "compaction_status"
    )
    assert status["status"] == "failed"
    assert status["source_event_seqs"][-1] == closers[0].seq
    assert log.projection() == [{"role": "user", "content": "question"}]


def test_fork_prefix_preserves_checkpoint_identity_and_supports_further_compaction():
    from member_support import account_id, member_id
    from backend.app.application.conversations.service import ConversationService
    from backend.app.repositories.conversation_repository import ConversationRepository
    from backend.app.storage.session_persistence import JsonlSessionPersistence

    account = account_id("alice")
    repository = ConversationRepository(JsonlSessionPersistence())
    service = ConversationService(repository=repository)
    parent = repository.ensure_session(account, member_id=member_id(account))
    log = Log()
    log.start("first")
    original = log.message("original", turn="first")
    log.end("first")
    log.start("second")
    second_user = log.message("second question", turn="second")
    summary = log.checkpoint([original], turn="second")
    log.end("second")
    stable_prefix = list(log.events)
    log.start("open")
    log.message("unfinished parent content", turn="open")
    repository.append_session_events(
        account,
        parent,
        [
            {
                "type": event.type,
                "data": event.data,
                "source_event_seqs": event.source_event_seqs,
                "surface_op": event.surface_op,
            }
            for event in log.events
        ],
    )
    early_child = service.fork_conversation(account, parent, original.seq)["session"][
        "session_id"
    ]
    early_events = repository.session_events(account, early_child, repair=False)
    assert derive_model_messages(early_events) == [
        {"role": "user", "content": "original"}
    ]
    child = service.fork_conversation(account, parent, summary.seq)["session"][
        "session_id"
    ]
    child_events = repository.session_events(account, child, repair=False)
    assert [
        (event.seq, event.data, event.source_event_seqs, event.surface_op)
        for event in child_events
    ] == [
        (event.seq, event.data, event.source_event_seqs, event.surface_op)
        for event in stable_prefix
    ]
    assert [
        item["_source_seq"]
        for item in derive_model_messages(child_events, include_surface_metadata=True)
    ] == [summary.seq, second_user.seq]
    repository.append_session_events(
        account,
        child,
        [
            {"type": "turn/start", "data": {"turn_id": "child-turn", "user_message_id": "user", "stream_id": "stream"}},
            {
                "type": "compaction/checkpoint",
                "data": {
                    "turn_id": "child-turn",
                    "message_id": "child-summary",
                    "compaction_id": "compaction_child",
                    "summary": "child summary",
                    "content": wrapped("child summary"),
                    "estimated_tokens_before": 1000,
                    "estimated_tokens_after": 500,
                    "target_tokens": 600,
                    "replaced_turn_ids": ["second"],
                },
                "source_event_seqs": [summary.seq, second_user.seq],
                "surface_op": {
                    "op": "replace",
                    "start": original.seq,
                    "end": second_user.seq + 1,
                },
            },
            {
                "type": "turn/end",
                "data": {"turn_id": "child-turn", "reason": {"kind": "completed"}},
            },
        ],
    )
    grandchild = service.fork_conversation(account, child)["session"]["session_id"]
    assert derive_model_messages(
        repository.session_events(account, grandchild, repair=False)
    ) == [{"role": "user", "content": wrapped("child summary")}]
    assert derive_model_messages(
        repository.session_events(account, parent, repair=False)
    ) == [
        {"role": "user", "content": wrapped("summary")},
        {"role": "user", "content": "second question"},
        {"role": "user", "content": "unfinished parent content"},
    ]


@pytest.mark.parametrize("status", ["running", "completed", "failed"])
def test_saved_compaction_response_preserves_estimates_and_error(status):
    record = {
        "record_id": "compaction_demo", "kind": "context", "turn_id": "turn",
        "context_type": "compaction_status", "purpose": "context_compaction",
        "status": status, "estimated_tokens_before": 80000,
        "estimated_tokens_after": 52000 if status == "completed" else None,
        "target_tokens": 60000,
        "error": {"code": "CONTEXT_COMPACTION_FAILED", "message": "摘要为空"} if status == "failed" else None,
    }
    response = record_response(record)
    for key in ("status", "estimated_tokens_before", "estimated_tokens_after", "target_tokens", "error"):
        assert response[key] == record[key]

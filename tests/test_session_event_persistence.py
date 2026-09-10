from tests.model_support import ConversationModelCatalog, BlockingConversationModelCatalog
from member_support import account_id as account_id_for, member_id
from types import SimpleNamespace
from backend.app.api.conversations import stream_response
import asyncio
import json
import os
import threading
import time
import pytest
from backend.app.application.conversations.service import ConversationService
from backend.app.application.conversations import sse as conversation_sse_module
from backend.app.agent_runtime.model_types import ModelStreamChunk, ToolCallDelta
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.domain.conversations.events import SessionEventCorruptionError, SessionEventFormatError, SessionHeader, make_event
from backend.app.storage.paths import app_paths
from backend.app.storage.session_persistence import JsonlSessionPersistence, StoredSession


class CancellableBlockingConversationModelCatalog(ConversationModelCatalog):
    def __init__(self):
        self.blocked = threading.Event()
        self.released = threading.Event()

    def stream_prepared_chat_for_account(self, **kwargs):
        cancellation_token = kwargs["cancellation_token"]
        unregister = cancellation_token.register(self.released.set)
        try:
            self.blocked.set()
            if not self.released.wait(timeout=5):
                raise TimeoutError("test stream was not cancelled")
            cancellation_token.raise_if_cancelled()
            yield ModelStreamChunk(content_delta="不应持久化")
        finally:
            unregister()


class ToolRequestAfterContentCatalog(ConversationModelCatalog):
    """Stream content first, then block in the middle of tool request arguments."""

    def __init__(self):
        self.tool_request_started = threading.Event()
        self.release = threading.Event()
        self.blocked = False

    def stream_prepared_chat_for_account(self, **kwargs):
        model_request = kwargs["prepared_request"].transport_request
        if model_request.model_config.get("purpose") == "agent_action" and not self.blocked:
            self.blocked = True
            yield ModelStreamChunk(content_delta="先输出正文。")
            yield ModelStreamChunk(
                tool_call_deltas=(
                    ToolCallDelta(
                        index=0,
                        id="tool-1",
                        name_delta="load_skill",
                        arguments_delta='{"name": ',
                    ),
                )
            )
            self.tool_request_started.set()
            if not self.release.wait(timeout=5):
                raise TimeoutError("test did not release the blocked provider stream")
            yield ModelStreamChunk(
                tool_call_deltas=(
                    ToolCallDelta(
                        index=0,
                        id="",
                        name_delta="",
                        arguments_delta='"report-query"}',
                    ),
                )
            )
            yield ModelStreamChunk(stop_reason="tool_calls")
            return
        yield from super().stream_prepared_chat_for_account(**kwargs)


def _stable_seed():
    return [
        make_event(
            "turn/start",
            0,
            {
                "turn_id": "turn-shared",
                "user_message_id": "user-shared",
                "final_assistant_message_id": "assistant-shared",
                "stream_id": "stream-shared",
            },
            timestamp=100,
        ),
        make_event(
            "user/message",
            1,
            {
                "turn_id": "turn-shared",
                "message_id": "user-shared",
                "parent_message_id": None,
                "content": "继承的问题",
            },
            timestamp=101,
            surface_op="append",
        ),
        make_event(
            "assistant/message",
            2,
            {
                "turn_id": "turn-shared",
                "message_id": "assistant-shared",
                "parent_message_id": "user-shared",
                "content": "继承的回答",
            },
            timestamp=102,
            surface_op="append",
        ),
        make_event(
            "turn/end",
            3,
            {
                "turn_id": "turn-shared",
                "reason": {"kind": "completed"},
            },
            timestamp=103,
        ),
    ]


def test_cached_reads_are_isolated_and_follow_another_writers_append_and_replace(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    reader, writer = JsonlSessionPersistence(), JsonlSessionPersistence()
    account_id = account_id_for("alice")
    reader.create(SessionHeader(id="cached", account_id=account_id, created_at=200))
    seed = _stable_seed()
    reader.append(account_id, "cached", seed, created_at=200)
    seed[1].data["content"] = "调用方更新了追加参数"
    first = reader.load(account_id, "cached", repair=False)
    assert first.events[1].data["content"] == "继承的问题"
    first.events[1].data["content"] = "调用方更新了返回值"
    assert reader.load(account_id, "cached", repair=False).events[1].data["content"] == "继承的问题"

    added = make_event("user/message", 4, {
        "turn_id": "next", "message_id": "next-user", "parent_message_id": None, "content": "新输入"
    }, timestamp=201, surface_op="append")
    writer.append(account_id, "cached", [added], created_at=200, expected_seq=4)
    appended = reader.load(account_id, "cached", repair=False)
    assert len(appended.events) == 5
    assert appended.events[-1] == added
    assert appended.revision != first.revision

    writer.replace(account_id, "cached", _stable_seed(), expected_revision=appended.revision)
    replaced = reader.load(account_id, "cached", repair=False)
    assert len(replaced.events) == 4
    assert replaced.lineage != appended.lineage
    writer.delete(account_id, "cached")
    assert reader.load(account_id, "cached", repair=False) is None


def test_warm_snapshot_detects_same_size_edits_and_torn_tail(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    reader = JsonlSessionPersistence()
    account_id = account_id_for("alice")
    reader.create(SessionHeader(id="cached", account_id=account_id, created_at=200))
    reader.append(account_id, "cached", _stable_seed(), created_at=200)
    reader.load(account_id, "cached", repair=False)
    path = reader._path(account_id, "cached")
    before = path.stat()
    path.write_bytes(path.read_bytes().replace("继承的问题".encode(), "更新的问题".encode()))
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert reader.load(account_id, "cached", repair=False).events[1].data["content"] == "更新的问题"
    with path.open("ab") as handle:
        handle.write(b'{"type":')
    with pytest.raises(SessionEventCorruptionError, match="torn tail"):
        reader.load(account_id, "cached", repair=False)
    repaired = reader.load(account_id, "cached", repair=True)
    assert len(repaired.events) == 4
    assert reader.load(account_id, "cached", repair=False) == repaired


def test_seed_create_round_trips_lineage_and_exact_content(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "seed-create"))
    persistence = JsonlSessionPersistence()
    seed = _stable_seed()
    header = SessionHeader(
        id="child-session",
        account_id=account_id_for("alice"),
        created_at=200,
        parent_session_id="parent-session",
        seed_event_count=len(seed),
    )

    persistence.create(header, seed)
    stored = persistence.load(account_id_for("alice"), "child-session", repair=False)

    assert stored is not None
    assert stored.header == header
    assert list(stored.events) == seed
    assert persistence.list(account_id_for("alice")) == [header]
    assert all("session_id" not in event.data for event in stored.events)
    persistence.create(header, seed)

    changed_seed = [
        *seed[:2],
        make_event(
            "assistant/message",
            2,
            {
                "turn_id": "turn-shared",
                "message_id": "assistant-shared",
                "parent_message_id": "user-shared",
                "content": "同长度 seed 的不同内容",
            },
            timestamp=102,
            surface_op="append",
        ),
        seed[3],
    ]
    with pytest.raises(SessionEventCorruptionError):
        persistence.create(header, changed_seed)

    path = (
        app_paths().account_root(account_id_for("alice"))
        / "conversations"
        / "sessions"
        / "child-session.jsonl"
    )
    first_line = json.loads(path.read_text().splitlines()[0])
    assert first_line == {
        "type": "session",
        "version": 2,
        "id": "child-session",
        "accountId": account_id_for("alice"),
        "createdAt": 200,
        "parentSession": "parent-session",
        "seedEventCount": 4,
    }


def test_event_tail_reads_only_requested_sequence_and_tracks_revision(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "event-tail"))
    persistence = JsonlSessionPersistence()
    seed = _stable_seed()
    header = SessionHeader(
        id="tail-session",
        account_id=account_id_for("alice"),
        created_at=200,
        parent_session_id="parent-session",
        seed_event_count=len(seed),
    )
    persistence.create(header, seed)

    initial_tail = persistence.read_from(account_id_for("alice"), "tail-session", 2)
    assert initial_tail is not None
    assert list(initial_tail.events) == seed[2:]
    initial_revision = initial_tail.revision

    appended = make_event(
        "turn/start",
        4,
        {"turn_id": "turn-next", "user_message_id": "user", "stream_id": "stream"},
        timestamp=201,
    )
    persistence.append(
        account_id_for("alice"), "tail-session", [appended], created_at=header.created_at
    )
    appended_tail = persistence.read_from(account_id_for("alice"), "tail-session", 4)
    assert appended_tail is not None
    assert list(appended_tail.events) == [appended]
    assert appended_tail.revision != initial_revision
    assert appended_tail.lineage == initial_tail.lineage

    empty_tail = persistence.read_from(account_id_for("alice"), "tail-session", 5)
    assert empty_tail is not None
    assert list(empty_tail.events) == []
    assert empty_tail.revision == appended_tail.revision

    replacement_revision = persistence.revision(account_id_for("alice"), "tail-session")
    assert replacement_revision is not None
    persistence.replace(
        account_id_for("alice"),
        "tail-session",
        seed,
        expected_revision=replacement_revision,
    )
    replacement_tail = persistence.read_from(account_id_for("alice"), "tail-session", 2)
    assert replacement_tail is not None
    assert list(replacement_tail.events) == seed[2:]
    assert replacement_tail.lineage != appended_tail.lineage


def test_seed_create_rolls_back_or_rejects_invalid_header_and_old_format(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "old-format"))
    persistence = JsonlSessionPersistence()
    seed = _stable_seed()
    invalid = SessionHeader(
        id="invalid-child",
        account_id=account_id_for("alice"),
        created_at=200,
        parent_session_id="parent-session",
        seed_event_count=len(seed) - 1,
    )
    with pytest.raises(SessionEventCorruptionError):
        persistence.create(invalid, seed)
    assert persistence.load(account_id_for("alice"), "invalid-child", repair=False) is None

    current = SessionHeader(id="old-session", account_id=account_id_for("alice"), created_at=200)
    persistence.create(current)
    path = (
        app_paths().account_root(account_id_for("alice"))
        / "conversations"
        / "sessions"
        / "old-session.jsonl"
    )
    lines = path.read_text().splitlines()
    header = json.loads(lines[0])
    header["version"] = 0
    path.write_text(
        "\n".join([json.dumps(header, separators=(",", ":")), *lines[1:]])
        + "\n"
    )
    with pytest.raises(SessionEventFormatError):
        persistence.load(account_id_for("alice"), "old-session", repair=False)


def test_agent_turn_events_survive_repository_reload(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "repository-reload"))
    repository = ConversationRepository(JsonlSessionPersistence())
    service = ConversationService(
        repository=repository,
        model_catalog=ConversationModelCatalog(),
    )
    queued = service.send_message(
        account_id_for("alice"), None, "测试问题", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    service.start_turn_job(account_id_for("alice"), queued["session_id"], queued["stream_id"])
    service.wait_for_turn_job(
        account_id_for("alice"), queued["session_id"], queued["stream_id"], timeout=5
    )
    response = stream_response(queued["session_id"], queued["stream_id"], user=SimpleNamespace(account_id=account_id_for("alice")), service=service)

    async def read_stream() -> str:
        return "".join([str(chunk) async for chunk in response.body_iterator])

    stream = asyncio.run(read_stream())
    assert "event: record_delta" in stream
    assert '"kind": "plan"' not in stream
    assert '"kind": "model"' in stream
    assert "# 系统提示词" in stream
    assert '"provider_source"' in stream
    assert "event: turn_completed" in stream

    reloaded = ConversationRepository(JsonlSessionPersistence())
    messages = reloaded.message_payloads(account_id_for("alice"), queued["session_id"])
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == "核心结论：测试回答。"
    detail = ConversationService(
        repository=reloaded,
        model_catalog=ConversationModelCatalog(),
    ).get_conversation(account_id_for("alice"), queued["session_id"])
    assert not any(record["kind"] == "plan" for record in detail["records"])
    context_records = [record for record in detail["records"] if record["kind"] == "context"]
    assert any("# 系统提示词" in str(record["content"]) for record in context_records)
    assert context_records[0]["label"] == "系统提示词"
    tool_catalog = next(
        record for record in context_records if record["context_type"] == "tool_catalog"
    )
    assert tool_catalog["context_type"] == "tool_catalog"
    assert {
        item["function"]["name"] for item in tool_catalog["content"]
    } == {"load_skill", "update_plan", "web_search", "web_read", "read_history", "update_history"}
    assert all(
        item["function"].get("description")
        for item in tool_catalog["content"]
    )
    skill_catalog = next(
        record for record in context_records if record["context_type"] == "skill_catalog"
    )
    assert skill_catalog["context_type"] == "skill_catalog"
    catalog_lines = skill_catalog["content"].strip().splitlines()
    assert catalog_lines[0] == "SKILL_CATALOG"
    assert [line.partition(" ")[0] for line in catalog_lines[1:]] == [
        "body-metrics",
        "log",
        "medication-catalog",
        "medication-inventory",
        "medication-plan",
        "medication-query",
        "report-analysis",
        "report-import",
        "report-query",
        "report-update",
    ]
    assert all(line.partition(" ")[2] for line in catalog_lines[1:])
    assert context_records.index(tool_catalog) < context_records.index(skill_catalog)
    assert all(record.get("provider_source") for record in context_records)
    assert all(record.get("purpose") != "generate_title" for record in context_records)
    model_records = [record for record in detail["records"] if record["kind"] == "model"]
    assert any(
        record["channel"] == "content" and record["value"] == "核心结论：测试回答。"
        for record in model_records
    )
    model_input = next(record for record in model_records if record["channel"] == "input")
    assert all(record["context_window_tokens"] == 131_072 for record in model_records)
    assert not any(record["kind"] == "thinking" for record in detail["records"])
    assert all(record.get("purpose") != "generate_title" for record in model_records)
    events = reloaded.session_events(account_id_for("alice"), queued["session_id"])
    event_types = [event.type for event in events]
    assert "request/context" in event_types
    assert "workflow/trace" in event_types
    assert "turn/end" in event_types
    headers = [event for event in events if event.type == "request/header"]
    assert [event.data["step"] for event in headers] == [1]
    assert all("provider_payload" in event.data["header"] for event in headers)
    action_header = next(
        event.data["header"]
        for event in headers
        if event.data["purpose"] == "agent_action"
    )
    assert model_input["value"] == action_header["provider_payload"]
    assert action_header["transport_mode"] == "native"
    assert action_header["model"]["context_window_tokens"] == 131_072
    assert "normalized_request" not in action_header
    assert "system" not in action_header
    assert "messages" not in action_header
    assert "tools" not in action_header
    assert [
        item["function"]["name"]
        for item in action_header["provider_payload"]["tools"]
    ] == ["load_skill", "update_plan", "read_history", "update_history", "web_read", "web_search"]
    action_events = [
        event.type
        for event in events
        if event.data.get("call_id") == headers[0].data["call_id"]
        or (
            event.type == "step/start"
            and event.data.get("step") == headers[0].data["step"]
        )
    ]
    assert action_events[0] == "step/start"
    header_index = action_events.index("request/header")
    assert all(
        event_type == "request/context" for event_type in action_events[1:header_index]
    )


def test_sse_emits_persisted_model_delta_before_turn_completion(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "live-sse"))
    repository = ConversationRepository(JsonlSessionPersistence())
    model_catalog = BlockingConversationModelCatalog()
    service = ConversationService(
        repository=repository,
        model_catalog=model_catalog,
    )
    queued = service.send_message(
        account_id_for("alice"), None, "测试实时推送", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    service.start_turn_job(account_id_for("alice"), queued["session_id"], queued["stream_id"])
    assert model_catalog.first_chunk_persisted.wait(timeout=2)

    response = stream_response(queued["session_id"], queued["stream_id"], user=SimpleNamespace(account_id=account_id_for("alice")), service=service)

    async def read_until_model_delta() -> list[str]:
        received: list[str] = []
        try:
            for _index in range(24):
                chunk = await asyncio.wait_for(
                    response.body_iterator.__anext__(),
                    timeout=1,
                )
                received.append(str(chunk))
                if "event: record_delta" in str(chunk) and '"kind": "model"' in str(chunk):
                    break
        finally:
            await response.body_iterator.aclose()
        return received

    try:
        received = asyncio.run(read_until_model_delta())
        turn = repository.turn_by_stream_id(
            account_id_for("alice"), queued["session_id"], queued["stream_id"]
        )
        assert turn is not None
        assert turn["status"] == "streaming"
        assert received[0] == ": connected\n\n"
        assert any(
            "event: record_delta" in chunk and '"kind": "model"' in chunk
            for chunk in received
        )
    finally:
        model_catalog.release.set()
        service.wait_for_turn_job(
            account_id_for("alice"), queued["session_id"], queued["stream_id"], timeout=5
        )


def test_cancel_turn_interrupts_provider_and_prevents_post_cancel_events(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "cancel"))
    repository = ConversationRepository(JsonlSessionPersistence())
    model_catalog = CancellableBlockingConversationModelCatalog()
    service = ConversationService(
        repository=repository,
        model_catalog=model_catalog,
    )
    queued = service.send_message(
        account_id_for("alice"), None, "测试真正取消", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    service.start_turn_job(account_id_for("alice"), queued["session_id"], queued["stream_id"])
    assert model_catalog.blocked.wait(timeout=2)

    started_at = time.monotonic()
    cancelled = service.cancel_turn(
        account_id_for("alice"),
        queued["session_id"],
        queued["turn_id"],
        preserve_partial=False,
    )
    elapsed = time.monotonic() - started_at

    assert cancelled["status"] == "cancelled"
    assert elapsed < 1
    assert model_catalog.released.is_set()
    service.wait_for_turn_job(
        account_id_for("alice"), queued["session_id"], queued["stream_id"], timeout=1
    )
    job_key = (account_id_for("alice"), queued["session_id"], queued["stream_id"])
    assert job_key not in service.task_state.threads
    assert job_key not in service.task_state.cancellations

    events = repository.session_events(account_id_for("alice"), queued["session_id"], repair=False)
    turn_events = [
        event
        for event in events
        if str(event.data.get("turn_id") or "") == queued["turn_id"]
    ]
    assert not any(
        event.type == "assistant/chunk"
        and event.data.get("chunk", {}).get("delta") == "不应持久化"
        for event in turn_events
    )
    model_results = [
        event for event in turn_events if event.type == "model/result"
    ]
    assert [event.data["status"] for event in model_results] == ["interrupted"]
    assert any(
        event.type == "step/end" and event.data.get("status") == "interrupted"
        for event in turn_events
    )
    turn_end = next(event for event in turn_events if event.type == "turn/end")
    assert turn_end.data["reason"]["kind"] == "cancelled"
    event_count = len(events)
    time.sleep(0.05)
    assert len(
        repository.session_events(account_id_for("alice"), queued["session_id"], repair=False)
    ) == event_count


def test_connected_sse_wakes_immediately_after_persisted_event_append(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "live-notify"))
    monkeypatch.setattr(conversation_sse_module, "SSE_POLL_SECONDS", 5.0)
    repository = ConversationRepository(JsonlSessionPersistence())
    service = ConversationService(
        repository=repository,
        model_catalog=ConversationModelCatalog(),
    )
    queued = service.send_message(
        account_id_for("alice"), None, "测试持久化即时推送", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    response = stream_response(queued["session_id"], queued["stream_id"], user=SimpleNamespace(account_id=account_id_for("alice")), service=service)

    async def append_after_stream_connects() -> tuple[list[str], float]:
        connected = await asyncio.wait_for(
            response.body_iterator.__anext__(),
            timeout=1,
        )
        assert str(connected) == ": connected\n\n"
        next_chunk = asyncio.create_task(response.body_iterator.__anext__())
        await asyncio.sleep(0.05)
        started_at = asyncio.get_running_loop().time()
        repository.append_session_event(
            account_id_for("alice"),
            queued["session_id"],
            "assistant/chunk",
            {
                "turn_id": queued["turn_id"],
                "step": 1,
                "call_id": "live-call",
                "message_id": "model_live-call",
                "branch_addressable": False,
                "purpose": "agent_action",
                "parent_message_id": queued["user_message_id"],
                "model_id": "model_1",
                "duration_ms": 1,
                "created_at": queued["created_at"],
                "chunk": {
                    "type": "reasoning-delta",
                    "delta": "已持久化的实时增量",
                },
            },
        )
        streamed = [str(await asyncio.wait_for(next_chunk, timeout=0.5))]
        streamed.append(
            str(
                await asyncio.wait_for(
                    response.body_iterator.__anext__(),
                    timeout=0.5,
                )
            )
        )
        elapsed = asyncio.get_running_loop().time() - started_at
        await response.body_iterator.aclose()
        return streamed, elapsed

    streamed, elapsed = asyncio.run(append_after_stream_connects())
    assert "event: record_started" in streamed[0]
    assert '"kind": "model"' in streamed[0]
    assert '"channel": "reasoning"' in streamed[0]
    assert '"value": ""' in streamed[0]
    assert "event: record_delta" in streamed[1]
    assert '"delta": "已持久化的实时增量"' in streamed[1]
    assert elapsed < 0.5


def test_connected_sse_streams_each_persisted_tool_request_delta(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "live-tool-request-notify"))
    monkeypatch.setattr(conversation_sse_module, "SSE_POLL_SECONDS", 5.0)
    repository = ConversationRepository(JsonlSessionPersistence())
    service = ConversationService(
        repository=repository,
        model_catalog=ConversationModelCatalog(),
    )
    queued = service.send_message(
        account_id_for("alice"), None, "测试工具请求实时增量", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    response = stream_response(queued["session_id"], queued["stream_id"], user=SimpleNamespace(account_id=account_id_for("alice")), service=service)

    def append_tool_delta(*, name_delta: str = "", arguments_delta: str = "") -> None:
        repository.append_session_event(
            account_id_for("alice"),
            queued["session_id"],
            "assistant/chunk",
            {
                "turn_id": queued["turn_id"],
                "step": 1,
                "call_id": "live-tool-call",
                "message_id": "model_live-tool-call",
                "branch_addressable": False,
                "purpose": "agent_action",
                "parent_message_id": queued["user_message_id"],
                "model_id": "model_1",
                "duration_ms": 1,
                "created_at": queued["created_at"],
                "chunk": {
                    "type": "tool-call-delta",
                    "index": 0,
                    "id": "provider-tool-call" if name_delta else "",
                    "name_delta": name_delta,
                    "arguments_delta": arguments_delta,
                },
            },
        )

    async def stream_tool_deltas() -> tuple[str, str]:
        connected = await asyncio.wait_for(
            response.body_iterator.__anext__(),
            timeout=1,
        )
        assert str(connected) == ": connected\n\n"
        started_chunk = asyncio.create_task(response.body_iterator.__anext__())
        await asyncio.sleep(0.05)
        append_tool_delta(name_delta="web_search")
        started = str(await asyncio.wait_for(started_chunk, timeout=0.5))
        delta_chunk = asyncio.create_task(response.body_iterator.__anext__())
        await asyncio.sleep(0.05)
        append_tool_delta(arguments_delta='{"query":"test"}')
        delta = str(await asyncio.wait_for(delta_chunk, timeout=0.5))
        await response.body_iterator.aclose()
        return started, delta

    started, delta = asyncio.run(stream_tool_deltas())
    assert "event: record_started" in started
    assert '"channel": "tool_request"' in started
    assert '"name": "web_search"' in started
    assert "event: record_delta" in delta
    assert '"channel": "arguments"' in delta
    assert '\\"query\\":\\"test\\"' in delta


def test_idle_sse_revision_poll_does_not_read_or_reproject_event_tail(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "idle-sse"))
    monkeypatch.setattr(conversation_sse_module, "SSE_POLL_SECONDS", 0)
    repository = ConversationRepository(JsonlSessionPersistence())
    model_catalog = BlockingConversationModelCatalog()
    service = ConversationService(repository=repository, model_catalog=model_catalog)
    queued = service.send_message(
        account_id_for("alice"), None, "测试空闲轮询", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    service.start_turn_job(account_id_for("alice"), queued["session_id"], queued["stream_id"])
    assert model_catalog.first_chunk_persisted.wait(timeout=2)

    original_revision = repository.session_event_revision
    revision_calls = 0

    def same_revision_then_cancel(account: str, session_id: str):
        nonlocal revision_calls
        revision_calls += 1
        if revision_calls == 1:
            repository.update_turn_cancelled(
                account,
                session_id,
                queued["turn_id"],
                queued["final_assistant_message_id"],
                None,
            )
        return original_revision(account, session_id)

    monkeypatch.setattr(repository, "session_event_revision", same_revision_then_cancel)

    def unexpected_tail(*_args, **_kwargs):
        raise AssertionError("unchanged revision must not read the event tail")

    monkeypatch.setattr(repository, "session_event_tail", unexpected_tail)
    response = stream_response(queued["session_id"], queued["stream_id"], user=SimpleNamespace(account_id=account_id_for("alice")), service=service)

    async def read_until_cancelled() -> str:
        chunks: list[str] = []
        for _index in range(200):
            chunk = await asyncio.wait_for(response.body_iterator.__anext__(), timeout=1)
            chunks.append(str(chunk))
            if "event: turn_cancelled" in str(chunk):
                break
        return "".join(chunks)

    try:
        stream = asyncio.run(read_until_cancelled())
        assert "event: turn_cancelled" in stream
        assert revision_calls >= 1
    finally:
        model_catalog.release.set()
        service.wait_for_turn_job(
            account_id_for("alice"), queued["session_id"], queued["stream_id"], timeout=5
        )


def test_sse_rebuilds_projection_when_event_log_lineage_changes(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "sse-replacement"))
    monkeypatch.setattr(conversation_sse_module, "SSE_POLL_SECONDS", 0)
    repository = ConversationRepository(JsonlSessionPersistence())
    model_catalog = BlockingConversationModelCatalog()
    service = ConversationService(repository=repository, model_catalog=model_catalog)
    queued = service.send_message(
        account_id_for("alice"), None, "测试日志替换", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    service.start_turn_job(account_id_for("alice"), queued["session_id"], queued["stream_id"])
    assert model_catalog.first_chunk_persisted.wait(timeout=2)

    original_snapshot = repository.session_event_snapshot(
        account_id_for("alice"), queued["session_id"]
    )
    assert original_snapshot is not None
    original_snapshot_reader = repository.session_event_snapshot
    snapshot_calls = 0

    def counted_snapshot(account: str, session_id: str):
        nonlocal snapshot_calls
        snapshot_calls += 1
        return original_snapshot_reader(account, session_id)

    revision_calls = 0

    def replacement_revision(account: str, session_id: str):
        nonlocal revision_calls
        revision_calls += 1
        if revision_calls == 2:
            repository.update_turn_cancelled(
                account,
                session_id,
                queued["turn_id"],
                queued["final_assistant_message_id"],
                None,
            )
        return "replacement:1"

    fake_tail = StoredSession(
        header=original_snapshot.header,
        events=(
            make_event(
                "turn/start",
                len(original_snapshot.events),
                {"turn_id": "replacement-turn", "user_message_id": "user", "stream_id": "stream"},
            ),
        ),
        revision="replacement:1",
        lineage="replacement",
    )
    monkeypatch.setattr(repository, "session_event_snapshot", counted_snapshot)
    monkeypatch.setattr(repository, "session_event_revision", replacement_revision)
    monkeypatch.setattr(
        repository,
        "session_event_tail",
        lambda _account, _session_id, _from_seq: fake_tail,
    )
    response = stream_response(queued["session_id"], queued["stream_id"], user=SimpleNamespace(account_id=account_id_for("alice")), service=service)

    async def read_until_cancelled() -> str:
        chunks: list[str] = []
        for _index in range(200):
            chunk = await asyncio.wait_for(response.body_iterator.__anext__(), timeout=1)
            chunks.append(str(chunk))
            if "event: turn_cancelled" in str(chunk):
                break
        return "".join(chunks)

    try:
        stream = asyncio.run(read_until_cancelled())
        assert "event: turn_cancelled" in stream
        assert snapshot_calls >= 2
    finally:
        model_catalog.release.set()
        service.wait_for_turn_job(
            account_id_for("alice"), queued["session_id"], queued["stream_id"], timeout=5
        )


def test_sse_completes_content_record_while_tool_request_still_streams(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "live-sse-channel-end"))
    repository = ConversationRepository(JsonlSessionPersistence())
    model_catalog = ToolRequestAfterContentCatalog()
    service = ConversationService(
        repository=repository,
        model_catalog=model_catalog,
    )
    queued = service.send_message(
        account_id_for("alice"), None, "测试正文先行完成", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    service.start_turn_job(account_id_for("alice"), queued["session_id"], queued["stream_id"])
    assert model_catalog.tool_request_started.wait(timeout=2)

    response = stream_response(queued["session_id"], queued["stream_id"], user=SimpleNamespace(account_id=account_id_for("alice")), service=service)

    async def read_until_content_completed() -> list[str]:
        received: list[str] = []
        try:
            for _index in range(60):
                chunk = await asyncio.wait_for(
                    response.body_iterator.__anext__(),
                    timeout=1,
                )
                received.append(str(chunk))
                if (
                    "event: record_completed" in str(chunk)
                    and '"channel": "content"' in str(chunk)
                ):
                    break
        finally:
            await response.body_iterator.aclose()
        return received

    try:
        received = asyncio.run(read_until_content_completed())
        turn = repository.turn_by_stream_id(
            account_id_for("alice"), queued["session_id"], queued["stream_id"]
        )
        assert turn is not None
        assert turn["status"] == "streaming"
        completed = next(
            chunk
            for chunk in received
            if "event: record_completed" in chunk and '"channel": "content"' in chunk
        )
        assert '"status": "completed"' in completed
        assert not any(
            "event: record_completed" in chunk and '"channel": "tool_request"' in chunk
            for chunk in received
        )
        content_started = next(
            chunk
            for chunk in received
            if "event: record_started" in chunk and '"channel": "content"' in chunk
        )
        assert '"time":' in content_started
        assert not model_catalog.release.is_set()
        threading.Event().wait(0.12)
    finally:
        model_catalog.release.set()
        service.wait_for_turn_job(
            account_id_for("alice"), queued["session_id"], queued["stream_id"], timeout=5
        )

    turn = repository.turn_by_stream_id(
        account_id_for("alice"), queued["session_id"], queued["stream_id"]
    )
    assert turn is not None
    assert turn["status"] == "completed"
    tool_request = next(
        record
        for record in repository.timeline_records(account_id_for("alice"), queued["session_id"])
        if record.get("kind") == "model"
        and record.get("channel") == "tool_request"
    )
    assert tool_request["duration_ms"] >= 100


def test_same_session_inputs_queue_persist_restore_and_advance(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "durable-input-queue"))
    repository = ConversationRepository(JsonlSessionPersistence())
    catalog = BlockingConversationModelCatalog()
    service = ConversationService(repository=repository, model_catalog=catalog)

    first = service.send_message(
        account_id_for("alice"), None, "第一问", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    assert first["disposition"] == "started"
    service.start_turn_job(account_id_for("alice"), first["session_id"], first["stream_id"])
    assert catalog.first_chunk_persisted.wait(timeout=2)

    exact_second = "  第二问\n请保留空白  "
    second = service.send_message(
        account_id_for("alice"), first["session_id"], exact_second, "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    third = service.send_message(
        account_id_for("alice"), first["session_id"], "第三问", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    assert second["disposition"] == "queued"
    assert third["disposition"] == "queued"

    reloaded = ConversationService(
        repository=ConversationRepository(JsonlSessionPersistence()),
        model_catalog=catalog,
    )
    queued = reloaded.get_conversation(account_id_for("alice"), first["session_id"])["queued_inputs"]
    assert [item["content"] for item in queued] == [exact_second, "第三问"]
    assert [
        message["content"]
        for message in repository.message_payloads(account_id_for("alice"), first["session_id"])
        if message["role"] == "user"
    ] == ["第一问"]

    restored = reloaded.remove_queued_input(
        account_id_for("alice"),
        first["session_id"],
        second["queued_input"]["input_id"],
        restore_to_draft=True,
    )
    assert restored["queued_input"]["content"] == exact_second
    resubmitted = reloaded.send_message(
        account_id_for("alice"), first["session_id"], exact_second, "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    assert [item["content"] for item in resubmitted["queued_inputs"]] == [
        "第三问",
        exact_second,
    ]

    catalog.release.set()
    service.wait_for_all_jobs(timeout=5)
    detail = reloaded.get_conversation(account_id_for("alice"), first["session_id"])
    assert detail["queued_inputs"] == []
    assert [
        record["content"]
        for record in detail["records"]
        if record["kind"] == "user"
    ] == ["第一问", "第三问", exact_second]


def test_run_now_steers_current_turn_and_preserves_queue_order(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "run-now-queue"))
    repository = ConversationRepository(JsonlSessionPersistence())
    catalog = CancellableBlockingConversationModelCatalog()
    service = ConversationService(repository=repository, model_catalog=catalog)
    first = service.send_message(
        account_id_for("alice"), None, "原方向", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    service.start_turn_job(account_id_for("alice"), first["session_id"], first["stream_id"])
    assert catalog.blocked.wait(timeout=2)
    second = service.send_message(
        account_id_for("alice"), first["session_id"], "稍后执行", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    urgent = service.send_message(
        account_id_for("alice"), first["session_id"], "立即执行", "model_1", "default", [], member_id=member_id(account_id_for("alice")))

    service.queue.run_now(
        account_id_for("alice"), first["session_id"], urgent["queued_input"]["input_id"]
    )
    service.wait_for_all_jobs(timeout=5)
    detail = service.get_conversation(account_id_for("alice"), first["session_id"])
    assert [
        record["content"]
        for record in detail["records"]
        if record["kind"] == "user"
    ] == ["原方向", "立即执行", "稍后执行"]
    assert repository.turn_row(
        account_id_for("alice"), first["session_id"], first["turn_id"]
    )["error_code"] == "STEERED"
    assert second["queued_input"]["input_id"] not in {
        item["input_id"] for item in detail["queued_inputs"]
    }


@pytest.mark.parametrize("reason", ["cancelled", "steered"])
def test_cancellation_preserves_live_model_text_and_next_turn_context(reason, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / reason))
    partial = "已保存的正文🙂\n第二行  "

    class PartialCatalog(ConversationModelCatalog):
        def __init__(self):
            self.persisted = threading.Event()
            self.release = threading.Event()
            self.calls = 0
            self.payloads = []

        def stream_prepared_chat_for_account(self, **kwargs):
            request = kwargs["prepared_request"]
            if request.transport_request.model_config.get("purpose") != "agent_action":
                yield from super().stream_prepared_chat_for_account(**kwargs)
                return
            self.calls += 1
            self.payloads.append(request.provider_payload)
            if self.calls == 1:
                token = kwargs["cancellation_token"]
                unregister = token.register(self.release.set)
                try:
                    yield ModelStreamChunk(content_delta=partial)
                    self.persisted.set()
                    assert self.release.wait(timeout=5)
                    token.raise_if_cancelled()
                    yield ModelStreamChunk(content_delta="不应保存")
                finally:
                    unregister()
            else:
                yield ModelStreamChunk(content_delta="下一条完成")
                yield ModelStreamChunk(stop_reason="end_turn")

    catalog = PartialCatalog()
    repository = ConversationRepository(JsonlSessionPersistence())
    service = ConversationService(repository=repository, model_catalog=catalog)
    first = service.send_message(account_id_for("alice"), None, "第一条", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    service.start_turn_job(account_id_for("alice"), first["session_id"], first["stream_id"])
    assert catalog.persisted.wait(timeout=2)
    service.send_message(account_id_for("alice"), first["session_id"], "第二条", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    service.cancel_turn(account_id_for("alice"), first["session_id"], first["turn_id"], reason=reason)
    service.wait_for_all_jobs(timeout=5)
    detail = service.get_conversation(account_id_for("alice"), first["session_id"])
    assistant = next(r for r in detail["records"] if r["record_id"] == first["final_assistant_message_id"])
    assert assistant["content"] == partial
    assert assistant["status"] == "cancelled"
    assert assistant["stop_reason"] == reason
    assert not any(r["kind"] == "error" for r in detail["records"])
    assert repository.turn_row(account_id_for("alice"), first["session_id"], first["turn_id"])["status"] == "cancelled"
    assert detail["queued_inputs"] == []
    assert len(catalog.payloads) == 2
    assert partial in json.dumps(catalog.payloads[1], ensure_ascii=False).replace("\\n", "\n")
    assert "不应保存" not in json.dumps([e.data for e in repository.session_events(account_id_for("alice"), first["session_id"])], ensure_ascii=False)


def test_stream_delta_offsets_use_utf16_and_reconstruct_exact_text(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "utf16-stream"))
    content = "🙂" * 17 + "甲乙"

    class UnicodeCatalog(ConversationModelCatalog):
        def stream_prepared_chat_for_account(self, **kwargs):
            request = kwargs["prepared_request"].transport_request
            if request.model_config.get("purpose") != "agent_action":
                yield from super().stream_prepared_chat_for_account(**kwargs)
                return
            yield ModelStreamChunk(content_delta=content)
            yield ModelStreamChunk(stop_reason="end_turn")

    service = ConversationService(repository=ConversationRepository(JsonlSessionPersistence()), model_catalog=UnicodeCatalog())
    account = account_id_for("alice")
    queued = service.send_message(account, None, "测试", "model_1", "default", [], member_id=member_id(account))
    service.start_turn_job(account, queued["session_id"], queued["stream_id"])
    service.wait_for_turn_job(account, queued["session_id"], queued["stream_id"], timeout=5)
    events = list(service.stream_events(account, queued["session_id"], queued["stream_id"]))
    chunks = [json.loads(event.split("data: ", 1)[1]) for event in events if event.startswith("event: record_delta")]
    chunks = [chunk for chunk in chunks if chunk["kind"] == "assistant"]
    assert [chunk["offset"] for chunk in chunks] == [0, 32]
    assert "".join(chunk["delta"] for chunk in chunks) == content


def test_different_sessions_run_workers_concurrently(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "cross-session-concurrency"))

    class ConcurrentCatalog(ConversationModelCatalog):
        def __init__(self):
            self.lock = threading.Lock()
            self.entered = 0
            self.both_entered = threading.Event()
            self.release = threading.Event()

        def stream_prepared_chat_for_account(self, **kwargs):
            request = kwargs["prepared_request"].transport_request
            if request.model_config.get("purpose") != "agent_action":
                yield from super().stream_prepared_chat_for_account(**kwargs)
                return
            with self.lock:
                self.entered += 1
                if self.entered == 2:
                    self.both_entered.set()
            if not self.release.wait(timeout=5):
                raise TimeoutError("both session workers did not run concurrently")
            yield ModelStreamChunk(content_delta="并发完成")
            yield ModelStreamChunk(stop_reason="end_turn")

    catalog = ConcurrentCatalog()
    service = ConversationService(
        repository=ConversationRepository(JsonlSessionPersistence()),
        model_catalog=catalog,
    )
    first = service.send_message(account_id_for("alice"), None, "会话 A", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    second = service.send_message(account_id_for("alice"), None, "会话 B", "model_1", "default", [], member_id=member_id(account_id_for("alice")))
    service.start_turn_job(account_id_for("alice"), first["session_id"], first["stream_id"])
    service.start_turn_job(account_id_for("alice"), second["session_id"], second["stream_id"])
    assert catalog.both_entered.wait(timeout=2)
    catalog.release.set()
    service.wait_for_all_jobs(timeout=5)
    assert service.get_turn(
        account_id_for("alice"), first["session_id"], first["turn_id"]
    )["status"] == "completed"
    assert service.get_turn(
        account_id_for("alice"), second["session_id"], second["turn_id"]
    )["status"] == "completed"


@pytest.mark.parametrize("cancelled", [False, True])
def test_answer_keeps_actual_model_after_attachment_model_selection(cancelled, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "model-identity"))
    account = account_id_for("alice")
    catalog = BlockingConversationModelCatalog()
    actual_model = {**catalog.model, "model_id": "test:vision-model", "remote_model_id": "vision-model"}
    repository = ConversationRepository(JsonlSessionPersistence())
    service = ConversationService(repository=repository, model_catalog=catalog)
    monkeypatch.setattr(service.inputs, "model_and_attachment_parts", lambda *_: (actual_model, []))
    queued = service.send_message(account, None, "测试问题", "model_1", "default", [], member_id=member_id(account))
    service.start_turn_job(account, queued["session_id"], queued["stream_id"])
    assert catalog.first_chunk_persisted.wait(timeout=3)
    try:
        live = service.get_conversation(account, queued["session_id"])
        live_content = next(r for r in live["records"] if r["kind"] == "model" and r["channel"] == "content")
        assert live_content["model_id"] == actual_model["model_id"]
        if cancelled:
            service.cancel_turn(account, queued["session_id"], queued["turn_id"])
    finally:
        catalog.release.set()
    service.wait_for_turn_job(account, queued["session_id"], queued["stream_id"], timeout=5)
    # Read from disk with the selected model removed from the catalog.
    catalog.model = {**catalog.model, "model_id": "test:another-default"}
    reloaded = ConversationRepository(JsonlSessionPersistence())
    detail = ConversationService(repository=reloaded, model_catalog=catalog).get_conversation(account, queued["session_id"])
    answer = next(r for r in detail["records"] if r["record_id"] == queued["final_assistant_message_id"])
    assert answer["status"] == ("cancelled" if cancelled else "completed")
    assert answer["model_id"] == actual_model["model_id"]
    assert next(r for r in detail["records"] if r["kind"] == "user")["model_id"] == "model_1"
    stored = JsonlSessionPersistence().load(account, queued["session_id"])
    assert next(e.data for e in reversed(stored.events) if e.type == "assistant/message")["model_id"] == actual_model["model_id"]

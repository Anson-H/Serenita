from backend.app.api.errors import error_http_status
from member_support import account_id as account_id_for, member_id
from datetime import datetime, timedelta, timezone
import pytest
from backend.app.core.errors import SerenitaError
from backend.app.application.conversation_service import ConversationService
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.storage.paths import app_paths
from backend.app.storage.session_persistence import JsonlSessionPersistence


def _append_turn(
    repository: ConversationRepository,
    session_id: str,
    *,
    turn_id: str,
    user_id: str,
    assistant_id: str,
    question: str,
    answer: str,
    closed: bool = True,
) -> None:
    records = [
        {
            "type": "turn/start",
            "data": {
                "turn_id": turn_id,
                "user_message_id": user_id,
                "final_assistant_message_id": assistant_id,
                "stream_id": f"stream-{turn_id}",
            },
        },
        {
            "type": "user/message",
            "surface_op": "append",
            "data": {
                "turn_id": turn_id,
                "message_id": user_id,
                "parent_message_id": None,
                "content": question,
            },
        },
    ]
    if closed:
        records.extend(
            [
                {
                    "type": "assistant/message",
                    "surface_op": "append",
                    "data": {
                        "turn_id": turn_id,
                        "message_id": assistant_id,
                        "parent_message_id": user_id,
                        "content": answer,
                    },
                },
                {
                    "type": "turn/end",
                    "data": {
                        "turn_id": turn_id,
                        "reason": {"kind": "completed"},
                    },
                },
            ]
        )
    repository.append_session_events(account_id_for("alice"), session_id, records)
    repository.reconcile_session_indexes(account_id_for("alice"), session_id)


def test_fork_uses_precise_stable_prefix_and_can_be_forked_again(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "fork"))
    repository = ConversationRepository(JsonlSessionPersistence())
    service = ConversationService(repository=repository)
    parent = repository.ensure_session(account_id_for("alice"), member_id=member_id(account_id_for("alice")))

    _append_turn(
        repository,
        parent,
        turn_id="turn-one",
        user_id="user-one",
        assistant_id="assistant-one",
        question="第一轮",
        answer="第一轮回答",
    )
    repository.append_session_event(
        account_id_for("alice"),
        parent,
        "workflow/trace",
        {"turn_id": "turn-one", "payload": {"stable": True}},
    )
    _append_turn(
        repository,
        parent,
        turn_id="turn-open",
        user_id="user-open",
        assistant_id="assistant-open",
        question="正在执行的第二轮",
        answer="",
        closed=False,
    )

    parent_events = repository.session_events(account_id_for("alice"), parent, repair=False)
    assistant_anchor = next(
        event.seq
        for event in parent_events
        if event.type == "assistant/message"
        and event.data["message_id"] == "assistant-one"
    )
    open_anchor = next(
        event.seq
        for event in parent_events
        if event.type == "user/message" and event.data["message_id"] == "user-open"
    )
    stable_trace_anchor = next(
        event.seq
        for event in parent_events
        if event.type == "workflow/trace" and event.data["payload"] == {"stable": True}
    )

    with pytest.raises(SerenitaError) as error:
        service.fork_conversation(account_id_for("alice"), parent, open_anchor)
    assert error_http_status(error.value) == 409
    assert error.value.detail["code"] == "FORK_UNAVAILABLE"

    trace_child = service.fork_conversation(account_id_for("alice"), parent, stable_trace_anchor)[
        "session"
    ]["session_id"]
    assert len(repository.session_events(account_id_for("alice"), trace_child, repair=False)) == 5
    service.delete_conversation(account_id_for("alice"), trace_child)

    child_summary = service.fork_conversation(account_id_for("alice"), parent, assistant_anchor)[
        "session"
    ]
    child = child_summary["session_id"]
    child_events = repository.session_events(account_id_for("alice"), child, repair=False)
    assert child_summary["parent_session_id"] == parent
    assert child_summary["seed_event_count"] == len(child_events) == 5
    assert [event.type for event in child_events][-2:] == [
        "turn/end",
        "workflow/trace",
    ]
    assert all(event.data.get("turn_id") != "turn-open" for event in child_events)
    assert all("session_id" not in event.data for event in child_events)
    assert repository.turn_row(account_id_for("alice"), parent, "turn-one") is not None
    assert repository.turn_row(account_id_for("alice"), child, "turn-one") is not None
    assert repository.turn_row(account_id_for("alice"), child, "turn-open") is None

    child_detail = service.get_conversation(account_id_for("alice"), child)
    assert [
        record["content"]
        for record in child_detail["records"]
        if record.get("kind") == "user"
    ] == ["第一轮"]
    assert child_detail["parent_session_id"] == parent
    assert "active_path_message_ids" not in child_detail
    assert "all_records" not in child_detail

    grandchild_summary = service.fork_conversation(account_id_for("alice"), child)["session"]
    grandchild = grandchild_summary["session_id"]
    assert grandchild_summary["parent_session_id"] == child
    assert grandchild_summary["seed_event_count"] == len(child_events)
    assert grandchild_summary["title"].endswith("(2)")
    assert repository.turn_row(account_id_for("alice"), grandchild, "turn-one") is not None


def test_forked_attachment_survives_parent_deletion_until_last_reference(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "forked-attachment"))
    repository = ConversationRepository(JsonlSessionPersistence())
    service = ConversationService(repository=repository)
    parent = repository.ensure_session(account_id_for("alice"), member_id=member_id(account_id_for("alice")))
    resource_id = "shared-resource"
    relative_path = f"conversations/attachments/{parent}/{resource_id}"
    path = app_paths().account_root(account_id_for("alice")) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"immutable-shared-attachment")
    timestamp = datetime.now(timezone.utc).isoformat()
    repository.insert_ready_resource(
        account_id=account_id_for("alice"),
        session_id=parent,
        resource_id=resource_id,
        original_filename="evidence.jpg",
        mime_type="image/jpeg",
        size_bytes=path.stat().st_size,
        relative_path=relative_path,
        sha256="shared-sha",
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        timestamp=timestamp,
    )
    repository.attach_file_resources(
        account_id_for("alice"),
        parent,
        [{"resource_type": "file", "resource_id": resource_id}],
    )
    _append_turn(
        repository,
        parent,
        turn_id="turn-shared",
        user_id="user-shared",
        assistant_id="assistant-shared",
        question="查看附件",
        answer="附件已查看",
    )

    child = service.fork_conversation(account_id_for("alice"), parent)["session"]["session_id"]
    parent_resource = repository.resource_row(account_id_for("alice"), parent, resource_id)
    child_resource = repository.resource_row(account_id_for("alice"), child, resource_id)
    assert parent_resource is not None and child_resource is not None
    assert parent_resource["relative_path"] == child_resource["relative_path"]
    assert (
        parent_resource["original_filename"]
        == child_resource["original_filename"]
        == "evidence.jpg"
    )
    assert path.exists()

    service.delete_conversation(account_id_for("alice"), parent)
    assert repository.session_row(account_id_for("alice"), child) is not None
    assert repository.resource_row(account_id_for("alice"), child, resource_id) is not None
    assert path.exists()

    service.delete_conversation(account_id_for("alice"), child)
    assert not path.exists()
    assert repository.attachment_cleanup_jobs(account_id_for("alice")) == []


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("用药咨询", "用药咨询 (1)"),
        ("用药咨询 (1)", "用药咨询 (2)"),
        ("用药咨询（9）", "用药咨询（10）"),
    ],
)
def test_fork_title_increment_preserves_parenthesis_style(title, expected):
    assert ConversationService._increment_fork_title(title) == expected



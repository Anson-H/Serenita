from backend.app.api.errors import error_http_status
import multiprocessing
import os
import threading
import pytest
from backend.app.core.errors import SerenitaError
from member_support import account_id as account_id_for, member_id
from backend.app.core.time import local_now_iso as now_iso
from backend.app.application.conversations.service import ConversationService
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.domain.conversations.events import iso_to_epoch_ms
from backend.app.storage.session_persistence import JsonlSessionPersistence
from tests.model_support import ConversationModelCatalog


def _seed_terminal_conversation() -> tuple[str, str, str]:
    repository = ConversationRepository(JsonlSessionPersistence())
    session_id = repository.ensure_session(
        account_id_for("alice"),
        member_id=member_id(account_id_for("alice")),
    )
    timestamp = now_iso()
    event_time = iso_to_epoch_ms(timestamp)
    repository.append_session_events(
        account_id_for("alice"),
        session_id,
        [
            {
                "type": "turn/start",
                "timestamp": event_time,
                "data": {
                    "turn_id": "turn-original",
                    "user_message_id": "user-original",
                    "final_assistant_message_id": "assistant-original",
                    "stream_id": "stream-original",
                },
            },
            {
                "type": "user/message",
                "timestamp": event_time,
                "surface_op": "append",
                "data": {
                    "turn_id": "turn-original",
                    "message_id": "user-original",
                    "parent_message_id": None,
                    "model_id": "model_1",
                    "thinking_mode": "default",
                    "content": "原始问题",
                    "context_resources": [],
                    "created_at": timestamp,
                },
            },
            {
                "type": "assistant/message",
                "timestamp": event_time,
                "surface_op": "append",
                "data": {
                    "turn_id": "turn-original",
                    "message_id": "assistant-original",
                    "parent_message_id": "user-original",
                    "model_id": "model_1",
                    "content": "原始回答",
                    "created_at": timestamp,
                },
            },
            {
                "type": "turn/end",
                "timestamp": event_time,
                "data": {
                    "turn_id": "turn-original",
                    "reason": {"kind": "completed"},
                },
            },
        ],
    )
    repository.reconcile_session_indexes(account_id_for("alice"), session_id)
    return session_id, "user-original", "assistant-original"


def _run_operation(
    service: ConversationService,
    operation: str,
    session_id: str,
    user_message_id: str,
    final_assistant_message_id: str,
) -> dict:
    if operation == "regenerate":
        return service.regenerate_message(
            account_id_for("alice"),
            session_id,
            final_assistant_message_id,
            "model_1",
            "default",
        )
    return service.edit_message(
        account_id_for("alice"),
        session_id,
        user_message_id,
        "更新后的问题",
        "model_1",
        "default",
        [],
    )


def _process_operation(
    data_root: str,
    operation: str,
    session_id: str,
    user_message_id: str,
    final_assistant_message_id: str,
    barrier,
    results,
) -> None:
    os.environ["DATA_ROOT"] = data_root
    repository = ConversationRepository(JsonlSessionPersistence())
    service = ConversationService(
        repository=repository,
        model_catalog=ConversationModelCatalog(),
    )
    original_append = repository.append_session_events
    reached_conditional_append = False

    def append_with_barrier(*args, **kwargs):
        nonlocal reached_conditional_append
        if kwargs.get("expected_seq") is not None and not reached_conditional_append:
            reached_conditional_append = True
            barrier.wait(timeout=10)
        return original_append(*args, **kwargs)

    repository.append_session_events = append_with_barrier
    try:
        response = _run_operation(
            service,
            operation,
            session_id,
            user_message_id,
            final_assistant_message_id,
        )
        results.put(("success", response["turn_id"]))
    except SerenitaError as exc:
        results.put(("error", error_http_status(exc), exc.detail["code"]))
    except BaseException as exc:  # pragma: no cover - surfaced in the parent assertion.
        results.put(("unexpected", type(exc).__name__, str(exc)))


def _assert_single_winner(repository: ConversationRepository, session_id: str) -> None:
    events = repository.session_events(account_id_for("alice"), session_id, repair=False)
    starts = [event for event in events if event.type == "turn/start"]
    rows = repository.list_turn_rows(account_id_for("alice"), session_id)
    assert len(starts) == 2
    assert len(rows) == 2
    assert {event.data["turn_id"] for event in starts} == {
        row["turn_id"] for row in rows
    }
    assert len(repository.list_pending_turn_rows(account_id_for("alice"), session_id)) == 1


def test_ambiguous_event_append_does_not_duplicate_committed_turn(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "ambiguous"))
    session_id, _user_message_id, final_assistant_message_id = _seed_terminal_conversation()
    repository = ConversationRepository(JsonlSessionPersistence())
    service = ConversationService(
        repository=repository,
        model_catalog=ConversationModelCatalog(),
    )
    original_append = repository.append_session_events
    raised_after_commit = False

    def append_then_raise(*args, **kwargs):
        nonlocal raised_after_commit
        events = original_append(*args, **kwargs)
        if kwargs.get("expected_seq") is not None and not raised_after_commit:
            raised_after_commit = True
            raise OSError("simulated notification failure after durable append")
        return events

    repository.append_session_events = append_then_raise
    response = service.regenerate_message(
        account_id_for("alice"),
        session_id,
        final_assistant_message_id,
        "model_1",
        "default",
    )

    assert raised_after_commit is True
    assert repository.turn_row(account_id_for("alice"), session_id, response["turn_id"]) is not None
    _assert_single_winner(repository, session_id)


def test_turn_index_publish_retries_after_committed_event(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "index-retry"))
    session_id, _user_message_id, final_assistant_message_id = _seed_terminal_conversation()
    repository = ConversationRepository(JsonlSessionPersistence())
    service = ConversationService(
        repository=repository,
        model_catalog=ConversationModelCatalog(),
    )
    original_insert = repository.insert_turn
    attempts = 0

    def fail_first_insert(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("simulated transient index failure")
        return original_insert(**kwargs)

    repository.insert_turn = fail_first_insert
    response = service.regenerate_message(
        account_id_for("alice"),
        session_id,
        final_assistant_message_id,
        "model_1",
        "default",
    )

    assert attempts == 2
    assert repository.turn_row(account_id_for("alice"), session_id, response["turn_id"]) is not None
    _assert_single_winner(repository, session_id)


def test_event_append_failure_before_commit_leaves_no_turn_or_update(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "precommit"))
    session_id, _user_message_id, final_assistant_message_id = _seed_terminal_conversation()
    repository = ConversationRepository(JsonlSessionPersistence())
    service = ConversationService(
        repository=repository,
        model_catalog=ConversationModelCatalog(),
    )
    original_append = repository.append_session_events

    def fail_before_append(*args, **kwargs):
        if kwargs.get("expected_seq") is not None:
            raise OSError("simulated pre-commit failure")
        return original_append(*args, **kwargs)

    repository.append_session_events = fail_before_append
    with pytest.raises(OSError, match="pre-commit"):
        service.regenerate_message(
            account_id_for("alice"),
            session_id,
            final_assistant_message_id,
            "model_1",
            "default",
        )

    events = repository.session_events(account_id_for("alice"), session_id, repair=False)
    assert [event.type for event in events].count("turn/start") == 1
    assert [event.type for event in events].count("user/message-update") == 0
    assert len(repository.list_turn_rows(account_id_for("alice"), session_id)) == 1


def test_reconcile_rebuilds_missing_open_turn_as_queued_and_preserves_claim(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "reconcile"))
    session_id, _user_message_id, _final_assistant_message_id = _seed_terminal_conversation()
    repository = ConversationRepository(JsonlSessionPersistence())
    repository.append_session_event(
        account_id_for("alice"),
        session_id,
        "turn/start",
        {
            "turn_id": "turn-recovered",
            "user_message_id": "user-original",
            "final_assistant_message_id": "assistant-recovered",
            "stream_id": "stream-recovered",
        },
    )

    repository.reconcile_session_indexes(account_id_for("alice"), session_id)
    recovered = repository.turn_row(account_id_for("alice"), session_id, "turn-recovered")
    assert recovered["status"] == "queued"
    assert repository.claim_turn_job(account_id_for("alice"), session_id, "turn-recovered") is True
    repository.reconcile_session_indexes(account_id_for("alice"), session_id)
    claimed = repository.turn_row(account_id_for("alice"), session_id, "turn-recovered")
    assert claimed["status"] == "streaming"


def test_reconcile_does_not_replace_final_message_id_with_intermediate_assistant_message(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "reconcile-final-message"))
    session_id, _user_message_id, _final_assistant_message_id = _seed_terminal_conversation()
    repository = ConversationRepository(JsonlSessionPersistence())
    repository.append_session_events(
        account_id_for("alice"),
        session_id,
        [
            {
                "type": "turn/start",
                "data": {
                    "turn_id": "turn-with-tool-call",
                    "user_message_id": "user-original",
                    "final_assistant_message_id": "assistant-final",
                    "stream_id": "stream-with-tool-call",
                },
            },
            {
                "type": "assistant/message",
                "surface_op": "append",
                "data": {
                    "turn_id": "turn-with-tool-call",
                    "message_id": "assistant-intermediate",
                    "parent_message_id": "user-original",
                    "branch_addressable": False,
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "function": {"name": "load_skill", "arguments": "{}"},
                        }
                    ],
                },
            },
        ],
    )

    repository.reconcile_session_indexes(account_id_for("alice"), session_id)

    recovered = repository.turn_row(
        account_id_for("alice"), session_id, "turn-with-tool-call"
    )
    assert recovered["final_assistant_message_id"] == "assistant-final"


@pytest.mark.parametrize(
    ("first_operation", "second_operation"),
    [
        ("regenerate", "regenerate"),
        ("edit", "edit"),
        ("regenerate", "edit"),
    ],
)
def test_concurrent_turn_replacement_has_one_winner_in_threads(
    monkeypatch,
    tmp_path,
    first_operation,
    second_operation,
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "threads"))
    session_id, user_message_id, final_assistant_message_id = _seed_terminal_conversation()
    repository = ConversationRepository(JsonlSessionPersistence())
    service = ConversationService(
        repository=repository,
        model_catalog=ConversationModelCatalog(),
    )
    start = threading.Barrier(2)
    outcomes: list[tuple] = []

    def invoke(operation: str) -> None:
        start.wait(timeout=5)
        try:
            response = _run_operation(
                service,
                operation,
                session_id,
                user_message_id,
                final_assistant_message_id,
            )
            outcomes.append(("success", response["turn_id"]))
        except SerenitaError as exc:
            outcomes.append(("error", error_http_status(exc), exc.detail["code"]))

    threads = [
        threading.Thread(target=invoke, args=(first_operation,)),
        threading.Thread(target=invoke, args=(second_operation,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert [outcome[0] for outcome in outcomes].count("success") == 1
    failure = next(outcome for outcome in outcomes if outcome[0] == "error")
    assert failure[1] == 409
    assert failure[2] in {"TURN_IN_PROGRESS", "MESSAGE_NOT_LATEST"}
    _assert_single_winner(repository, session_id)


@pytest.mark.parametrize(
    ("first_operation", "second_operation"),
    [
        ("regenerate", "regenerate"),
        ("edit", "edit"),
        ("regenerate", "edit"),
    ],
)
def test_concurrent_turn_replacement_has_one_winner_across_processes(
    monkeypatch,
    tmp_path,
    first_operation,
    second_operation,
):
    data_root = str(tmp_path / "processes")
    monkeypatch.setenv("DATA_ROOT", data_root)
    session_id, user_message_id, final_assistant_message_id = _seed_terminal_conversation()
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    processes = [
        context.Process(
            target=_process_operation,
            args=(
                data_root,
                operation,
                session_id,
                user_message_id,
                final_assistant_message_id,
                barrier,
                results,
            ),
        )
        for operation in (first_operation, second_operation)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)
        assert not process.is_alive()
        assert process.exitcode == 0

    outcomes = [results.get(timeout=5), results.get(timeout=5)]
    assert [outcome[0] for outcome in outcomes].count("success") == 1, outcomes
    failure = next(outcome for outcome in outcomes if outcome[0] == "error")
    assert failure[1] == 409
    assert failure[2] in {"TURN_IN_PROGRESS", "MESSAGE_NOT_LATEST"}
    repository = ConversationRepository(JsonlSessionPersistence())
    _assert_single_winner(repository, session_id)

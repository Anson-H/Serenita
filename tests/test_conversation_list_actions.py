from __future__ import annotations
from backend.app.api.errors import error_http_status
from member_support import account_id as account_id_for, member_id
import threading
from types import SimpleNamespace
import pytest
from backend.app.core.errors import SerenitaError
from pydantic import ValidationError
from tests.api_client import TestClient
from backend.app.core.time import local_now_iso as now_iso
from backend.app.api.conversations import PatchConversationRequest
from backend.app.application.conversation_service import ConversationService
from backend.app.core.cancellation import CancellationToken, OperationCancelledError
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.storage.paths import app_paths
from backend.app.storage.session_persistence import JsonlSessionPersistence
from backend.app.storage.sqlite import connect


def _repository(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "conversations"))
    return ConversationRepository(JsonlSessionPersistence())


def _insert_indexed_turn(
    repository: ConversationRepository,
    account: str,
    session_id: str,
    *,
    turn_id: str,
    status: str,
) -> None:
    timestamp = now_iso()
    repository.insert_turn(
        account_id=account,
        session_id=session_id,
        turn_id=turn_id,
        user_message_id=f"user-{turn_id}",
        final_assistant_message_id=f"assistant-{turn_id}",
        stream_id=f"stream-{turn_id}",
        status=status,
        error_code=None,
        error_message=None,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _title_job_input(repository: ConversationRepository, account: str, session_id: str):
    raw_title = "请帮我看看最近的血压变化"
    assert repository.set_initial_session_title(account, session_id, raw_title)
    return (
        {"session_id": session_id, "turn_id": "turn-title"},
        {
            "content": raw_title,
            "context_resources": [],
            "generate_session_title": True,
            "initial_session_title": raw_title,
        },
    )


class ImmediateTitleCatalog:
    def __init__(self, title: str = "血压变化"):
        self.title = title
        self.calls = 0

    def default_model_for_account(self, _account: str, _purpose: str):
        return {"model_id": "title-model", "provider_id": "fake"}

    def complete_chat_for_account(self, **_kwargs):
        self.calls += 1
        return SimpleNamespace(content=self.title)


class BlockingCancellableTitleCatalog(ImmediateTitleCatalog):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.cancelled_upstream = threading.Event()
        self.release = threading.Event()

    def complete_chat_for_account(self, **kwargs):
        self.calls += 1
        cancellation_token = kwargs["cancellation_token"]
        unregister = cancellation_token.register(self._cancel_upstream)
        self.started.set()
        try:
            while not self.release.wait(0.01):
                cancellation_token.raise_if_cancelled()
            cancellation_token.raise_if_cancelled()
            return SimpleNamespace(content=self.title)
        finally:
            unregister()

    def _cancel_upstream(self):
        self.cancelled_upstream.set()
        self.release.set()


def test_pinned_sorting_batch_pin_and_pending_turn_summary(
    monkeypatch, tmp_path
):
    repository = _repository(monkeypatch, tmp_path)
    service = ConversationService(repository=repository)
    sessions = [repository.ensure_session(account_id_for("alice"), member_id=member_id(account_id_for("alice"))) for _ in range(3)]
    for index, session_id in enumerate(sessions):
        _insert_indexed_turn(
            repository,
            account_id_for("alice"),
            session_id,
            turn_id=f"turn-{index}",
            status=("completed", "queued", "streaming")[index],
        )
    with connect(app_paths().conversations_db(account_id_for("alice"))) as connection:
        for index, session_id in enumerate(sessions):
            connection.execute(
                "UPDATE conversations SET last_active_at = ? WHERE session_id = ?",
                (f"2026-08-0{index + 1}T10:00:00+08:00", session_id),
            )

    service.update_conversation(account_id_for("alice"), sessions[0], is_pinned=True)
    summaries = service.list_conversations(account_id_for("alice"))["sessions"]
    assert [item["session_id"] for item in summaries] == [sessions[0], sessions[2], sessions[1]]
    assert {item["session_id"]: item["pending_turn_status"] for item in summaries} == {
        sessions[0]: None,
        sessions[1]: "queued",
        sessions[2]: "streaming",
    }

    updated = service.batch_pin_conversations(account_id_for("alice"), [sessions[1], sessions[2]], True)
    assert all(item["is_pinned"] for item in updated["sessions"])
    unpinned = service.batch_pin_conversations(account_id_for("alice"), [sessions[0], sessions[1]], False)
    assert all(not item["is_pinned"] for item in unpinned["sessions"])


def test_manual_title_validation_persistence_and_account_isolation(monkeypatch, tmp_path):
    repository = _repository(monkeypatch, tmp_path)
    service = ConversationService(repository=repository)
    session_id = repository.ensure_session(account_id_for("alice"), member_id=member_id(account_id_for("alice")))
    repository.ensure_session(account_id_for("bob"), member_id=member_id(account_id_for("bob")))

    response = service.update_conversation(account_id_for("alice"), session_id, title="  血压   复查  ")
    assert response["session"]["title"] == "血压 复查"
    row = repository.session_row(account_id_for("alice"), session_id)
    assert row["title"] == "血压 复查"
    assert row["is_title_manual"] == 1
    assert not repository.replace_initial_session_title(
        account_id_for("alice"), session_id, "血压 复查", "迟到的自动标题"
    )

    with pytest.raises(SerenitaError) as blank_error:
        service.update_conversation(account_id_for("alice"), session_id, title="   ")
    assert error_http_status(blank_error.value) == 400
    with pytest.raises(ValidationError):
        PatchConversationRequest(title="一" * 15)
    with pytest.raises(SerenitaError) as isolation_error:
        service.batch_pin_conversations(account_id_for("bob"), [session_id], True)
    assert error_http_status(isolation_error.value) == 404


def test_batch_delete_returns_real_per_item_failures(monkeypatch, tmp_path):
    repository = _repository(monkeypatch, tmp_path)
    service = ConversationService(repository=repository)
    session_id = repository.ensure_session(account_id_for("alice"), member_id=member_id(account_id_for("alice")))

    result = service.batch_delete_conversations(account_id_for("alice"), [session_id, "missing", session_id])

    assert result["success"] is False
    assert result["deleted_ids"] == [session_id]
    assert result["failed"] == [
        {
            "session_id": "missing",
            "code": "NOT_FOUND",
            "message": "聊天不存在。",
        }
    ]
    assert repository.session_row(account_id_for("alice"), session_id) is None


def test_cancelled_before_title_request_never_reaches_provider(monkeypatch, tmp_path):
    repository = _repository(monkeypatch, tmp_path)
    catalog = ImmediateTitleCatalog()
    service = ConversationService(repository=repository, model_catalog=catalog)
    session_id = repository.ensure_session(account_id_for("alice"), member_id=member_id(account_id_for("alice")))
    turn, user_message = _title_job_input(repository, account_id_for("alice"), session_id)
    cancellation_token = CancellationToken()
    cancellation_token.cancel()

    with pytest.raises(OperationCancelledError):
        service.titles.generate(
            account_id_for("alice"), turn, user_message, cancellation_token=cancellation_token
        )
    assert catalog.calls == 0


def test_rename_cancels_blocking_title_request_and_cleans_registry(monkeypatch, tmp_path):
    repository = _repository(monkeypatch, tmp_path)
    catalog = BlockingCancellableTitleCatalog()
    service = ConversationService(repository=repository, model_catalog=catalog)
    session_id = repository.ensure_session(account_id_for("alice"), member_id=member_id(account_id_for("alice")))
    turn, user_message = _title_job_input(repository, account_id_for("alice"), session_id)
    events_before = repository.session_events(account_id_for("alice"), session_id, repair=False)

    thread = service.titles.start(account_id_for("alice"), turn, user_message)
    assert thread is not None
    assert catalog.started.wait(1)
    service.update_conversation(account_id_for("alice"), session_id, title="手工血压标题")
    thread.join(1)

    assert catalog.cancelled_upstream.is_set()
    assert not thread.is_alive()
    assert (account_id_for("alice"), session_id) not in service.task_state.titles
    row = repository.session_row(account_id_for("alice"), session_id)
    assert row["title"] == "手工血压标题"
    assert row["is_title_manual"] == 1
    assert repository.session_events(account_id_for("alice"), session_id, repair=False) == events_before


def test_rename_wins_after_provider_returns_before_title_write(monkeypatch, tmp_path):
    repository = _repository(monkeypatch, tmp_path)
    catalog = ImmediateTitleCatalog("模型血压标题")
    service = ConversationService(repository=repository, model_catalog=catalog)
    session_id = repository.ensure_session(account_id_for("alice"), member_id=member_id(account_id_for("alice")))
    turn, user_message = _title_job_input(repository, account_id_for("alice"), session_id)
    provider_returned = threading.Event()
    continue_after_return = threading.Event()
    original_generate = service.titles.generate
    replace_calls = []
    original_replace = repository.replace_initial_session_title

    def paused_generate(*args, **kwargs):
        result = original_generate(*args, **kwargs)
        provider_returned.set()
        assert continue_after_return.wait(1)
        return result

    def tracked_replace(*args, **kwargs):
        replace_calls.append(args)
        return original_replace(*args, **kwargs)

    monkeypatch.setattr(service.titles, "generate", paused_generate)
    monkeypatch.setattr(repository, "replace_initial_session_title", tracked_replace)
    thread = service.titles.start(account_id_for("alice"), turn, user_message)
    assert thread is not None
    assert provider_returned.wait(1)

    service.update_conversation(account_id_for("alice"), session_id, title="返回后的手工标题")
    continue_after_return.set()
    thread.join(1)

    assert replace_calls == []
    assert repository.session_row(account_id_for("alice"), session_id)["title"] == "返回后的手工标题"


def test_rename_after_title_job_finished_still_blocks_late_auto_write(monkeypatch, tmp_path):
    repository = _repository(monkeypatch, tmp_path)
    catalog = ImmediateTitleCatalog("模型生成标题")
    service = ConversationService(repository=repository, model_catalog=catalog)
    session_id = repository.ensure_session(account_id_for("alice"), member_id=member_id(account_id_for("alice")))
    turn, user_message = _title_job_input(repository, account_id_for("alice"), session_id)

    thread = service.titles.start(account_id_for("alice"), turn, user_message)
    assert thread is not None
    thread.join(1)
    assert repository.session_row(account_id_for("alice"), session_id)["title"] == "模型生成标题"
    assert (account_id_for("alice"), session_id) not in service.task_state.titles

    service.update_conversation(account_id_for("alice"), session_id, title="最终手工标题")
    assert not repository.replace_initial_session_title(
        account_id_for("alice"), session_id, "模型生成标题", "迟到标题"
    )
    assert repository.session_row(account_id_for("alice"), session_id)["title"] == "最终手工标题"


def test_conversation_metadata_and_batch_http_contracts(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "api"))
    from backend.app.main import create_app

    client = TestClient(create_app())
    sign_up = client.post(
        "/api/auth/sign_up",
        json={
            "account": "alice",
            "account_name": "Alice",
            "password": "secret",
            "confirm_password": "secret",
        },
    )
    assert sign_up.status_code == 200
    repository = ConversationRepository(JsonlSessionPersistence())
    first = repository.ensure_session(account_id_for("alice"), member_id=member_id(account_id_for("alice")))
    second = repository.ensure_session(account_id_for("alice"), member_id=member_id(account_id_for("alice")))
    _insert_indexed_turn(repository, account_id_for("alice"), first, turn_id="first", status="completed")
    _insert_indexed_turn(repository, account_id_for("alice"), second, turn_id="second", status="queued")

    renamed = client.patch(
        f"/api/conversations/{first}", json={"title": "手工标题", "is_pinned": True}
    )
    assert renamed.status_code == 200
    assert renamed.json()["session"]["title"] == "手工标题"
    assert renamed.json()["session"]["is_pinned"] is True
    assert repository.session_row(account_id_for("alice"), first)["is_title_manual"] == 1

    batch_pin = client.post(
        "/api/conversations/batch-pin",
        json={"session_ids": [first, second, first], "is_pinned": False},
    )
    assert batch_pin.status_code == 200
    assert [item["session_id"] for item in batch_pin.json()["sessions"]] == [first, second]
    assert all(not item["is_pinned"] for item in batch_pin.json()["sessions"])

    batch_delete = client.post(
        "/api/conversations/batch-delete",
        json={"session_ids": [first, "missing"]},
    )
    assert batch_delete.status_code == 200
    assert batch_delete.json()["deleted_ids"] == [first]
    assert batch_delete.json()["failed"][0]["session_id"] == "missing"


def test_conversation_list_does_not_wait_for_a_generating_sessions_write_lock(monkeypatch, tmp_path):
    repository = _repository(monkeypatch, tmp_path)
    service = ConversationService(repository=repository)
    account = account_id_for("alice")
    session = repository.ensure_session(account, member_id=member_id(account))
    _insert_indexed_turn(repository, account, session, turn_id="running", status="streaming")
    held = threading.Event()
    release = threading.Event()
    listed = threading.Event()
    results = []
    failures = []

    def write_in_progress():
        with service.task_state.session_lock(account, session):
            held.set()
            release.wait(10)

    def read_list():
        try:
            results.extend(service.list_conversations(account)["sessions"])
        except BaseException as error:
            failures.append(error)
        finally:
            listed.set()

    writer = threading.Thread(target=write_in_progress)
    reader = threading.Thread(target=read_list)
    writer.start()
    try:
        assert held.wait(2)
        reader.start()
        assert listed.wait(2), "the conversation list waited for generation to release its lock"
    finally:
        release.set()
        writer.join(5)
        if reader.ident is not None:
            reader.join(5)
    assert not failures
    assert results[0]["session_id"] == session
    assert results[0]["pending_turn_status"] == "streaming"

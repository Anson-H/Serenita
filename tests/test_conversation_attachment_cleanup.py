from backend.app.api.errors import error_http_status
from member_support import account_id as account_id_for, member_id
import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from backend.app.core.errors import SerenitaError
from backend.app.application.conversation_service import ConversationService
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect


def _resource(
    repository: ConversationRepository,
    account: str,
    *,
    expires_at: str,
    resource_id: str,
    relative_path: str | None = None,
    session_id: str | None = None,
) -> tuple[str, Path]:
    session_id = repository.ensure_session(account, session_id, member_id=member_id(account))
    relative_path = relative_path or (
        f"conversations/attachments/{session_id}/{resource_id}"
    )
    path = app_paths().account_root(account) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"private-attachment")
    repository.insert_ready_resource(
        account_id=account,
        session_id=session_id,
        resource_id=resource_id,
        original_filename="attachment.jpg",
        mime_type="image/jpeg",
        size_bytes=path.stat().st_size,
        relative_path=relative_path,
        sha256=f"sha-{account}-{resource_id}",
        expires_at=expires_at,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    return session_id, path


def _past() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()


def test_queued_attachment_restore_retains_draft_then_resubmit_delete_cleans_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    service = ConversationService(repository=repository)
    session_id, path = _resource(repository, account_id_for("alice"), expires_at=_future(), resource_id="shared-draft")
    resources = [{"resource_type": "file", "resource_id": "shared-draft"}]

    def enqueue(input_id):
        repository.append_session_event(account_id_for("alice"), session_id, "input/queued", {
            "input_id": input_id, "content": "  保持原文\n🙂  ", "model_id": "m",
            "thinking_mode": "high", "context_resources": resources, "created_at": "now",
        })

    enqueue("first")
    enqueue("second")
    restored = service.queue.remove(account_id_for("alice"), session_id, "first", restore_to_draft=True)
    assert restored["queued_input"]["content"] == "  保持原文\n🙂  "
    assert restored["queued_input"]["context_resources"] == resources
    assert restored["queued_input"]["thinking_mode"] == "high"
    service.queue.remove(account_id_for("alice"), session_id, "second")
    assert path.exists()
    enqueue("new-tail")
    service.queue.remove(account_id_for("alice"), session_id, "new-tail")
    assert not path.exists()
    assert repository.resource_row(account_id_for("alice"), session_id, "shared-draft")["lifecycle_status"] == "deleted"


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


def _writing_resource(
    repository: ConversationRepository,
    account: str,
    *,
    resource_id: str,
    expected_content: bytes,
    stored_content: bytes | None,
    updated_at: str,
) -> tuple[str, Path]:
    session_id = repository.ensure_session(
        account,
        member_id=member_id(account),
    )
    relative_path = f"conversations/attachments/{session_id}/{resource_id}"
    path = app_paths().account_root(account) / relative_path
    if stored_content is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(stored_content)
    with connect(app_paths().conversations_db(account)) as connection:
        connection.execute(
            """
            INSERT INTO conversation_resources (
                resource_id, session_id, original_filename, mime_type, size_bytes,
                relative_path, sha256, storage_status, lifecycle_status,
                expires_at, created_at, updated_at
            ) VALUES (?, ?, ?, 'image/jpeg', ?, ?, ?, 'writing', 'pending',
                      NULL, ?, ?)
            """,
            (
                resource_id,
                session_id,
                resource_id,
                len(expected_content),
                relative_path,
                hashlib.sha256(expected_content).hexdigest(),
                updated_at,
                updated_at,
            ),
        )
    return session_id, path


def test_attachment_maintenance_recovers_writes_before_expiration():
    calls = []

    class TrackingRepository:
        def recover_writing_resources(self, account_id, *, limit):
            calls.append(("recover", account_id, limit))

        def expire_due_resources(self, account_id, *, limit):
            calls.append(("expire", account_id, limit))

        def attachment_cleanup_jobs(self, account_id, *, limit):
            calls.append(("cleanup", account_id, limit))
            return []

    ConversationService(repository=TrackingRepository())._maintain_attachments(
        "account-1"
    )

    assert calls == [
        ("recover", "account-1", 100),
        ("expire", "account-1", 100),
        ("cleanup", "account-1", 32),
    ]


def test_complete_writing_resource_is_recovered_as_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    account = account_id_for("writing-complete")
    as_of = datetime.now(timezone.utc)
    session_id, path = _writing_resource(
        repository,
        account,
        resource_id="complete.jpg",
        expected_content=b"complete-upload",
        stored_content=b"complete-upload",
        updated_at=(as_of - timedelta(minutes=1)).isoformat(),
    )

    result = repository.recover_writing_resources(account, as_of=as_of.isoformat())

    assert result == {"recovered": 1, "discarded": 0}
    row = repository.resource_row(account, session_id, "complete.jpg")
    assert row["storage_status"] == "ready"
    assert row["lifecycle_status"] == "pending"
    assert datetime.fromisoformat(row["expires_at"]) == as_of.astimezone() + timedelta(hours=24)
    assert path.read_bytes() == b"complete-upload"


def test_fresh_partial_and_missing_writing_resources_are_not_discarded(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    account = account_id_for("writing-fresh")
    as_of = datetime.now(timezone.utc)
    session_id, path = _writing_resource(
        repository,
        account,
        resource_id="partial.jpg",
        expected_content=b"complete-upload",
        stored_content=b"partial",
        updated_at=as_of.isoformat(),
    )
    missing_session_id, missing_path = _writing_resource(
        repository,
        account,
        resource_id="missing.jpg",
        expected_content=b"missing-upload",
        stored_content=None,
        updated_at=(as_of - timedelta(minutes=5)).isoformat(),
    )

    result = repository.recover_writing_resources(account, as_of=as_of.isoformat())

    assert result == {"recovered": 0, "discarded": 0}
    assert repository.resource_row(account, session_id, "partial.jpg")[
        "storage_status"
    ] == "writing"
    assert repository.resource_row(account, missing_session_id, "missing.jpg")[
        "storage_status"
    ] == "writing"
    assert path.read_bytes() == b"partial"
    assert not missing_path.exists()


def test_stale_partial_and_missing_writes_are_removed(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    service = ConversationService(repository=repository)
    account = account_id_for("writing-stale")
    as_of = datetime.now(timezone.utc)
    stale_at = (as_of - timedelta(minutes=6)).isoformat()
    partial_session, partial_path = _writing_resource(
        repository,
        account,
        resource_id="partial.jpg",
        expected_content=b"complete-upload",
        stored_content=b"partial",
        updated_at=stale_at,
    )
    missing_session, missing_path = _writing_resource(
        repository,
        account,
        resource_id="missing.jpg",
        expected_content=b"missing-upload",
        stored_content=None,
        updated_at=stale_at,
    )

    result = repository.recover_writing_resources(account, as_of=as_of.isoformat())
    service._drain_attachment_cleanup(account)

    assert result == {"recovered": 0, "discarded": 2}
    assert repository.resource_row(account, partial_session, "partial.jpg") is None
    assert repository.resource_row(account, missing_session, "missing.jpg") is None
    assert not partial_path.exists()
    assert not missing_path.exists()
    assert repository.attachment_cleanup_jobs(account) == []


def test_writing_resource_cannot_be_previewed_or_attached(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    service = ConversationService(repository=repository)
    account = account_id_for("writing-unavailable")
    now = datetime.now(timezone.utc).isoformat()
    session_id, _path = _writing_resource(
        repository,
        account,
        resource_id="partial.jpg",
        expected_content=b"complete-upload",
        stored_content=b"partial",
        updated_at=now,
    )

    with pytest.raises(SerenitaError) as preview_error:
        service.context_resource_download(account, session_id, "partial.jpg")
    assert error_http_status(preview_error.value) == 404

    with pytest.raises(SerenitaError) as attach_error:
        repository.file_resource_attachment_payloads(
            account,
            session_id,
            [{"resource_type": "file", "resource_id": "partial.jpg"}],
        )
    assert error_http_status(attach_error.value) == 409
    assert attach_error.value.detail["code"] == "RESOURCE_NOT_READY"
    assert service._trusted_attachment_resource(
        account, session_id, "partial.jpg"
    ) is None
    with pytest.raises(SerenitaError) as send_error:
        service._validate_context_resources(
            account,
            session_id,
            [{"resource_type": "file", "resource_id": "partial.jpg"}],
            {},
        )
    assert error_http_status(send_error.value) == 409
    assert send_error.value.detail["code"] == "RESOURCE_NOT_READY"


def test_expired_attachment_is_physically_deleted_and_tombstoned(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    service = ConversationService(repository=repository)
    session_id, path = _resource(
        repository, account_id_for("alice"), expires_at=_past(), resource_id="expired-file"
    )

    service.list_conversations(account_id_for("alice"))

    assert not path.exists()
    row = repository.resource_row(account_id_for("alice"), session_id, "expired-file")
    assert row["lifecycle_status"] == "deleted"
    assert repository.attachment_cleanup_jobs(account_id_for("alice")) == []


def test_attached_resource_clears_expiry_survives_sweeps_and_rebuilds_name(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    account_id = account_id_for("attached_resource")
    session_id, path = _resource(
        repository,
        account_id,
        expires_at=_future(),
        resource_id="report.pdf",
    )

    repository.attach_file_resources(
        account_id,
        session_id,
        [{"resource_type": "file", "resource_id": "report.pdf"}],
    )

    row = repository.resource_row(account_id, session_id, "report.pdf")
    assert row["storage_status"] == "ready"
    assert row["lifecycle_status"] == "attached"
    assert row["expires_at"] is None
    attached_event = next(
        event
        for event in repository.session_events(account_id, session_id)
        if event.type == "resource/attached"
    )
    assert attached_event.data["original_filename"] == "attachment.jpg"
    assert "source" not in attached_event.data
    assert "thumb_path" not in attached_event.data
    assert "storage_status" not in attached_event.data
    assert "lifecycle_status" not in attached_event.data
    assert repository.expire_due_resources(
        account_id,
        as_of=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
    ) == 0
    assert path.exists()

    with connect(app_paths().conversations_db(account_id)) as connection:
        connection.execute(
            "DELETE FROM conversation_resources WHERE session_id = ?",
            (session_id,),
        )
    repository.reconcile_session_indexes(account_id, session_id)

    rebuilt = repository.resource_row(account_id, session_id, "report.pdf")
    assert rebuilt["original_filename"] == "attachment.jpg"
    assert rebuilt["storage_status"] == "ready"
    assert rebuilt["lifecycle_status"] == "attached"
    assert rebuilt["expires_at"] is None


def test_visible_attachments_include_branch_visible_history(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    service = ConversationService(repository=repository)
    session_id, _old_path = _resource(
        repository,
        account_id_for("alice"),
        expires_at=_future(),
        resource_id="old-file",
    )
    _, _new_path = _resource(
        repository,
        account_id_for("alice"),
        expires_at=_future(),
        resource_id="new-file",
        session_id=session_id,
    )

    messages_by_id = {
        "old-message": {
            "role": "user",
            "message_id": "old-message",
            "context_resources": [
                {"resource_type": "file", "resource_id": "old-file"}
            ],
        },
        "assistant-message": {
            "role": "assistant",
            "message_id": "assistant-message",
            "context_resources": [],
        },
        "current-message": {
            "role": "user",
            "message_id": "current-message",
            "context_resources": [
                {"resource_type": "file", "resource_id": "new-file"}
            ],
        },
    }

    visible = service._visible_attachments_for_messages(
        account_id_for("alice"),
        session_id,
        messages_by_id,
        {"old-message", "assistant-message", "current-message"},
    )

    assert set(visible) == {"old-file", "new-file"}
    assert visible["old-file"]["original_filename"] == "attachment.jpg"


def test_visible_attachments_ignore_inactive_or_missing_resources(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    service = ConversationService(repository=repository)
    session_id, _path = _resource(
        repository,
        account_id_for("alice"),
        expires_at=_future(),
        resource_id="visible-file",
    )
    messages_by_id = {
        "visible": {
            "role": "user",
            "message_id": "visible",
            "context_resources": [
                {"resource_type": "file", "resource_id": "visible-file"}
            ],
        },
        "inactive": {
            "role": "user",
            "message_id": "inactive",
            "context_resources": [
                {"resource_type": "file", "resource_id": "missing-file"}
            ],
        },
    }

    visible = service._visible_attachments_for_messages(
        account_id_for("alice"), session_id, messages_by_id, {"visible"}
    )

    assert set(visible) == {"visible-file"}


def test_attachment_unlink_failure_is_retried_on_next_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    service = ConversationService(repository=repository)
    session_id, path = _resource(
        repository, account_id_for("alice"), expires_at=_past(), resource_id="retry-file"
    )
    original_unlink = Path.unlink
    failed = False

    def fail_once(candidate: Path, missing_ok: bool = False):
        nonlocal failed
        if candidate.resolve() == path.resolve() and not failed:
            failed = True
            raise OSError("simulated interruption")
        return original_unlink(candidate, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_once)

    service.list_conversations(account_id_for("alice"))
    assert path.exists()
    jobs = repository.attachment_cleanup_jobs(account_id_for("alice"))
    assert len(jobs) == 1
    assert jobs[0]["attempt_count"] == 1
    assert repository.resource_row(account_id_for("alice"), session_id, "retry-file")[
        "lifecycle_status"
    ] == "expired"

    service.list_conversations(account_id_for("alice"))
    assert not path.exists()
    assert repository.attachment_cleanup_jobs(account_id_for("alice")) == []
    assert repository.resource_row(account_id_for("alice"), session_id, "retry-file")[
        "lifecycle_status"
    ] == "deleted"


def test_cleanup_is_account_scoped_and_future_attachment_is_preserved(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    service = ConversationService(repository=repository)
    _, alice_path = _resource(
        repository, account_id_for("alice"), expires_at=_future(), resource_id="future-file"
    )
    _, bob_path = _resource(
        repository, account_id_for("bob"), expires_at=_past(), resource_id="bob-file"
    )

    service.list_conversations(account_id_for("alice"))

    assert alice_path.exists()
    assert bob_path.exists()
    assert repository.attachment_cleanup_jobs(account_id_for("alice")) == []
    assert repository.attachment_cleanup_jobs(account_id_for("bob")) == []

    service.list_conversations(account_id_for("bob"))
    assert alice_path.exists()
    assert not bob_path.exists()


def test_traversal_path_is_never_deleted_even_when_conversation_is_deleted(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    repository = ConversationRepository()
    service = ConversationService(repository=repository)
    outside = tmp_path / "must-not-delete.jpg"
    outside.write_bytes(b"outside-private-file")
    account_root = app_paths().account_root(account_id_for("alice"))
    relative_path = os.path.relpath(outside, account_root)
    session_id, created_path = _resource(
        repository,
        account_id_for("alice"),
        expires_at=_past(),
        resource_id="unsafe-file",
        relative_path=relative_path,
    )
    assert created_path.resolve() == outside.resolve()

    service.delete_conversation(account_id_for("alice"), session_id)

    assert outside.exists()
    assert repository.attachment_cleanup_jobs(account_id_for("alice")) == []


def test_attachment_symlink_cannot_escape_account_cleanup_root(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    repository = ConversationRepository()
    service = ConversationService(repository=repository)
    session_id = repository.ensure_session(account_id_for("alice"), member_id=member_id(account_id_for("alice")))
    attachment_dir = (
        app_paths().account_root(account_id_for("alice"))
        / "conversations"
        / "attachments"
        / session_id
    )
    attachment_dir.mkdir(parents=True, exist_ok=True)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside = outside_dir / "must-not-delete.jpg"
    outside.write_bytes(b"outside-private-file")
    (attachment_dir / "escape").symlink_to(outside_dir, target_is_directory=True)
    relative_path = (
        f"conversations/attachments/{session_id}/escape/{outside.name}"
    )
    repository.insert_ready_resource(
        account_id=account_id_for("alice"),
        session_id=session_id,
        resource_id="symlink-file",
        original_filename="must-not-delete.jpg",
        mime_type="image/jpeg",
        size_bytes=outside.stat().st_size,
        relative_path=relative_path,
        sha256="sha-symlink-file",
        expires_at=_past(),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    service.list_conversations(account_id_for("alice"))

    assert outside.exists()
    assert repository.attachment_cleanup_jobs(account_id_for("alice")) == []
    assert repository.resource_row(account_id_for("alice"), session_id, "symlink-file")[
        "lifecycle_status"
    ] == "deleted"

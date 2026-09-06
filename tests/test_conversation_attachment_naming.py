from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import pytest
from member_support import account_id as account_id_for, member_id
from backend.app.application.conversation_service import ConversationService
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect


def _upload(
    repository: ConversationRepository,
    account_id: str,
    session_id: str,
    content: bytes,
    *,
    name: str = "报告.pdf",
):
    return repository.create_uploaded_resource(
        account_id=account_id,
        session_id=session_id,
        original_filename=name,
        fallback_extension=".pdf",
        mime_type="application/pdf",
        content=content,
    )


def _session(repository: ConversationRepository, account: str) -> tuple[str, str]:
    account_id = account_id_for(account)
    session_id = repository.ensure_session(
        account_id,
        member_id=member_id(account_id),
    )
    return account_id, session_id


def test_same_name_uploads_are_flat_sequential_and_never_deduplicated(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    account_id, session_id = _session(repository, "attachment_names")

    first = _upload(repository, account_id, session_id, b"same")
    second = _upload(repository, account_id, session_id, b"same")
    third = _upload(repository, account_id, session_id, b"different")

    assert [first["resource_id"], second["resource_id"], third["resource_id"]] == [
        "报告.pdf",
        "报告-002.pdf",
        "报告-003.pdf",
    ]
    assert {
        first["original_filename"],
        second["original_filename"],
        third["original_filename"],
    } == {"报告.pdf"}
    assert first["sha256"] == second["sha256"]
    assert first["sha256"] != third["sha256"]
    assert first["sha256"] == hashlib.sha256(b"same").hexdigest()

    session_directory = (
        app_paths().account_root(account_id)
        / "conversations"
        / "attachments"
        / session_id
    )
    assert {path.name for path in session_directory.iterdir()} == {
        "报告.pdf",
        "报告-002.pdf",
        "报告-003.pdf",
    }
    for resource in (first, second, third):
        path = app_paths().account_root(account_id) / resource["relative_path"]
        assert path.parent == session_directory
        assert path.name == resource["resource_id"]


def test_deleted_and_orphaned_names_are_not_reused(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    service = ConversationService(repository=repository)
    account_id, session_id = _session(repository, "attachment_history")
    first = _upload(repository, account_id, session_id, b"first")
    first_path = app_paths().account_root(account_id) / first["relative_path"]

    assert repository.expire_resource(account_id, session_id, first["resource_id"])
    service._drain_attachment_cleanup(account_id)
    assert not first_path.exists()
    assert repository.resource_row(account_id, session_id, first["resource_id"])[
        "lifecycle_status"
    ] == "deleted"

    second = _upload(repository, account_id, session_id, b"second")
    assert second["resource_id"] == "报告-002.pdf"
    orphan = first_path.parent / "报告-003.pdf"
    orphan.write_bytes(b"orphan")

    fourth = _upload(repository, account_id, session_id, b"fourth")
    assert fourth["resource_id"] == "报告-004.pdf"
    assert orphan.read_bytes() == b"orphan"


def test_concurrent_same_name_uploads_do_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    account_id, session_id = _session(repository, "attach_concurrent")
    payloads = [f"payload-{index}".encode() for index in range(1, 7)]

    with ThreadPoolExecutor(max_workers=len(payloads)) as executor:
        resources = list(
            executor.map(
                lambda content: _upload(repository, account_id, session_id, content),
                payloads,
            )
        )

    assert {resource["resource_id"] for resource in resources} == {
        "报告.pdf",
        "报告-002.pdf",
        "报告-003.pdf",
        "报告-004.pdf",
        "报告-005.pdf",
        "报告-006.pdf",
    }
    stored_payloads = {
        (app_paths().account_root(account_id) / resource["relative_path"]).read_bytes()
        for resource in resources
    }
    assert stored_payloads == set(payloads)


def test_intent_insert_failure_does_not_create_a_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    account_id, session_id = _session(repository, "attach_compensate")
    with connect(app_paths().conversations_db(account_id)) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_resource_insert
            BEFORE INSERT ON conversation_resources
            BEGIN
                SELECT RAISE(ABORT, 'test insert failure');
            END
            """
        )

    with pytest.raises(Exception, match="test insert failure"):
        _upload(repository, account_id, session_id, b"must-be-removed")

    session_directory = (
        app_paths().account_root(account_id)
        / "conversations"
        / "attachments"
        / session_id
    )
    assert list(session_directory.iterdir()) == []
    assert repository.resource_row(account_id, session_id, "报告.pdf") is None


def test_file_write_failure_removes_intent_and_queues_exact_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    account_id, session_id = _session(repository, "attach_write_failure")

    def fail_fsync(_descriptor):
        raise OSError("test file sync failure")

    monkeypatch.setattr(os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="test file sync failure"):
        _upload(repository, account_id, session_id, b"must-be-removed")

    session_directory = (
        app_paths().account_root(account_id)
        / "conversations"
        / "attachments"
        / session_id
    )
    assert repository.resource_row(account_id, session_id, "报告.pdf") is None
    assert repository.attachment_cleanup_jobs(account_id) == [
        {
            "cleanup_id": hashlib.sha256(
                f"{account_id}\0conversations/attachments/{session_id}/报告.pdf".encode()
            ).hexdigest(),
            "relative_path": f"conversations/attachments/{session_id}/报告.pdf",
            "attempt_count": 0,
        }
    ]

    ConversationService(repository=repository)._drain_attachment_cleanup(account_id)

    assert not session_directory.exists() or list(session_directory.iterdir()) == []
    assert repository.attachment_cleanup_jobs(account_id) == []


def test_ready_update_failure_leaves_recoverable_write_intent(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository()
    account_id, session_id = _session(repository, "attach_ready_failure")

    def fail_ready(*_args, **_kwargs):
        raise RuntimeError("test ready update failure")

    monkeypatch.setattr(repository.attachments, "mark_resource_ready", fail_ready)

    with pytest.raises(RuntimeError, match="test ready update failure"):
        _upload(repository, account_id, session_id, b"recoverable")

    row = repository.resource_row(account_id, session_id, "报告.pdf")
    path = app_paths().account_root(account_id) / row["relative_path"]
    assert row["storage_status"] == "writing"
    assert row["expires_at"] is None
    assert path.read_bytes() == b"recoverable"

    recovered = ConversationRepository().recover_writing_resources(account_id)
    assert recovered == {"recovered": 1, "discarded": 0}
    assert ConversationRepository().resource_row(
        account_id, session_id, "报告.pdf"
    )["storage_status"] == "ready"

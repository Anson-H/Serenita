"""Committed member work preserves atomic storage and historical task scope."""

import sqlite3
from types import SimpleNamespace

import pytest

from backend.app.core.errors import SerenitaError
from backend.app.storage.sqlite import connect, UnsupportedSchemaError


@pytest.mark.parametrize("failure", ["database_create", "after_enqueue", "attachment_limit"])
def test_member_delete_rolls_back_when_task_registration_fails(monkeypatch, failure):
    from member_support import account_id
    from backend.app.application.member_service import MemberService
    from backend.app.application.conversations.service import ConversationService

    owner = account_id("rollback-owner")
    members = MemberService()
    member = members.create_member(owner, {"member_name": "保留成员"})["member_id"]
    conversations = ConversationService(paths=members.paths)
    session = conversations.repository.ensure_session(owner, member_id=member)
    tasks = members.repository.lifecycle_tasks
    enqueue = tasks.enqueue

    def fail(connection, *args, **kwargs):
        if failure == "attachment_limit":
            count = len(connection.execute("PRAGMA database_list").fetchall()) - 1
            connection.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, count)
        enqueue(connection, *args, **kwargs)
        raise RuntimeError("simulated failure after task insertion")

    if failure == "database_create":
        def fail_initialize():
            raise OSError("simulated task database creation failure")
        monkeypatch.setattr(tasks, "initialize", fail_initialize)
    else:
        monkeypatch.setattr(tasks, "enqueue", fail)
    with pytest.raises((OSError, RuntimeError, SerenitaError)):
        members.repository.delete(owner, member)
    assert members.repository.resolve(owner, member).permission == "owner"
    assert conversations.repository.session_row(owner, session)["member_id"] == member
    if tasks.path.exists():
        with connect(tasks.path) as db:
            assert db.execute("SELECT count(*) FROM member_lifecycle_tasks").fetchone()[0] == 0


def test_member_task_atomicity_rejects_wal_before_committing():
    from member_support import account_id
    from backend.app.repositories.member_repository import MemberRepository

    owner = account_id("wal-owner")
    members = MemberRepository()
    tasks = members.lifecycle_tasks
    tasks.initialize()
    with connect(members.paths.auth_db) as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    with pytest.raises(UnsupportedSchemaError, match="DELETE"):
        with connect(members.paths.auth_db) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE accounts SET account_name='must roll back' WHERE account_id=?", (owner,))
            tasks.enqueue(db, owner, "member", [(owner, "session")])
    with connect(members.paths.auth_db) as db:
        assert db.execute("SELECT account_name FROM accounts WHERE account_id=?", (owner,)).fetchone()[0] == "wal-owner"
        db.execute("PRAGMA journal_mode=DELETE")
    assert tasks.pending() == []


def test_delayed_member_task_only_interrupts_older_work(tmp_path):
    from backend.app.application.conversations.lifecycle import ConversationTurnLifecycle
    from backend.app.core.conversation_tasks import ConversationTasks
    from backend.app.storage.paths import AppPaths

    before = "2026-09-09T12:00:00+08:00"
    older, newer = "2026-09-09T11:59:00+08:00", "2026-09-09T12:01:00+08:00"
    removed, cancelled = [], []
    lifecycle = ConversationTurnLifecycle.__new__(ConversationTurnLifecycle)
    lifecycle.paths = AppPaths(tmp_path)
    lifecycle.paths.auth_db.parent.mkdir(parents=True)
    lifecycle.task_state = ConversationTasks()
    lifecycle.queue = SimpleNamespace(
        inputs=lambda *args: [{"input_id": "old-input", "created_at": older}, {"input_id": "new-input", "created_at": newer}],
        remove=lambda actor, session, identity: removed.append(identity),
    )
    lifecycle.repository = SimpleNamespace(list_pending_turn_rows=lambda *args: [
        {"turn_id": "old-turn", "created_at": older}, {"turn_id": "new-turn", "created_at": newer},
    ])
    lifecycle.cancel_turn = lambda actor, session, identity: cancelled.append(identity)
    lifecycle.interrupt_member_session("actor", "session", before=before)
    assert removed == ["old-input"] and cancelled == ["old-turn"]

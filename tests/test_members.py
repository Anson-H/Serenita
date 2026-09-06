from __future__ import annotations
from member_support import accounts as accounts
from backend.app.api.errors import error_http_status
import threading
import pytest
from tests.api_client import TestClient
from member_support import account_id as account_id_for, create_member, grant, report_payload
from backend.app.main import create_app
from backend.app.application.report_service import ReportService
from backend.app.repositories.member_repository import MemberRepository
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect
import sqlite3
import asyncio
from types import SimpleNamespace
from backend.app.api import members


def test_signup_starts_without_members_and_first_member_becomes_default(accounts):
    owner, *_ = accounts
    response = owner.post("/api/auth/sign_up", json={
        "account": "empty",
        "account_name": "empty",
        "password": "secret",
        "confirm_password": "secret",
    })
    assert response.status_code == 200, response.text
    empty_account_id = response.json()["account_id"]
    with TestClient(create_app()) as client:
        signed_in = client.post("/api/auth/sign_in", json={
            "account": "empty",
            "password": "secret",
        })
        assert signed_in.status_code == 200, signed_in.text
        empty = client.get("/api/members").json()
        assert empty["members"] == []
        assert empty["default_member_id"] is None
        assert empty["last_member_id"] is None
        assert empty["initial_member_id"] is None
        assert not app_paths().members_db(empty_account_id).exists()
        assert not app_paths().reports_db(empty_account_id).exists()

        created = client.post("/api/members", json={
            "member_name": "第一位成员",
            "set_as_default": False,
        })
        assert created.status_code == 201, created.text
        member_id = created.json()["member_id"]
        assert created.json()["is_default"] is True
        revision_before_last_selection = client.get("/api/members").json()[
            "access_revision"
        ]
        selected_none = client.patch(
            "/api/account-settings/member-preferences",
            json={"last_member_id": None},
        )
        assert selected_none.status_code == 200, selected_none.text
        assert selected_none.json()["default_member_id"] == member_id
        assert selected_none.json()["last_member_id"] is None
        assert selected_none.json()["initial_member_id"] is None
        assert (
            selected_none.json()["access_revision"]
            > revision_before_last_selection
        )

        deleted = client.delete(f"/api/members/{member_id}")
        assert deleted.status_code == 200, deleted.text
        assert client.get("/api/members").json()["members"] == []


def test_members_grants_and_report_isolation(accounts):
    owner, reader, editor = accounts
    initial = owner.get("/api/members").json()
    assert len(initial["members"]) == 1
    assert initial["startup_mode"] == "last_used"
    member = create_member(owner)
    other = create_member(owner, "另一位家人")
    created = owner.post(f"/api/members/{member}/reports", json=report_payload())
    assert created.status_code == 201, created.text
    report_id = created.json()["report_id"]
    assert created.json()["member_id"] == member
    assert owner.get(f"/api/members/{other}/reports/{report_id}").status_code == 404
    assert reader.get(f"/api/members/{member}/reports").status_code == 403
    grant(owner, member, "reader", "read")
    grant(owner, member, "editor", "edit")
    assert len(reader.get("/api/members").json()["members"]) == 2
    assert reader.get(f"/api/members/{member}/reports/{report_id}").status_code == 200
    assert reader.post(f"/api/members/{member}/reports", json=report_payload()).status_code == 403
    assert reader.delete(f"/api/members/{member}/reports/{report_id}").status_code == 403
    source_endpoint = f"/api/members/{member}/reports/{report_id}/source-files"
    source_upload = [("files", ("shared.jpg", b"\xff\xd8\xffshared", "image/jpeg"))]
    assert reader.post(source_endpoint, files=source_upload).status_code == 403
    supplemented = editor.post(source_endpoint, files=source_upload)
    assert supplemented.status_code == 201, supplemented.text
    source = supplemented.json()["sources"][0]
    assert source["is_primary"] is True
    stored_path, _, _ = ReportService.for_member(account_id_for("owner"), member).source_download(
        member, report_id, source["resource_id"]
    )
    assert stored_path.is_relative_to(app_paths().account_root(account_id_for("owner")))
    assert not stored_path.is_relative_to(app_paths().account_root(account_id_for("editor")))
    assert editor.patch(f"/api/members/{member}/reports/{report_id}/fields", json={"field": "report_name", "value": "已修正"}).status_code == 200
    assert owner.get(f"/api/members/{member}/reports/{report_id}").json()["report_name"] == "已修正"
    assert editor.put("/api/account-settings/member-grants", json={"grantee_account": "reader",
        "grants": [{"member_id": member, "permission": "edit"}]}).status_code == 403
    assert owner.get("/api/reports").status_code == 404
    assert editor.delete(f"/api/members/{member}/reports/{report_id}").status_code == 200


def test_preferences_revoke_and_account_rename(accounts):
    owner, reader, _ = accounts
    member = create_member(owner)
    grants = grant(owner, member, "reader", "read")
    assert reader.patch("/api/account-settings/member-preferences", json={"last_member_id": member}).json()["initial_member_id"] == member
    owner_revision = owner.get("/api/members").json()["access_revision"]
    reader_revision = reader.get("/api/members").json()["access_revision"]
    before = owner.get("/api/auth/session").json()["account_id"]
    renamed = owner.patch("/api/auth/account", json={"account": "renamed", "account_name": "新名称"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["account_id"] == before
    assert owner.get("/api/members").json()["access_revision"] == owner_revision
    reader_state = reader.get("/api/members").json()
    assert reader_state["access_revision"] == reader_revision
    shared_member = reader.get(f"/api/members/{member}").json()
    assert shared_member["owner_account"] == "renamed"
    reader_renamed = reader.patch(
        "/api/auth/account",
        json={"account": "reader-renamed", "account_name": "共享读者"},
    )
    assert reader_renamed.status_code == 200, reader_renamed.text
    assert owner.get("/api/members").json()["access_revision"] == owner_revision
    assert reader.get("/api/members").json()["access_revision"] == reader_revision
    current_grant = owner.get("/api/account-settings/member-grants").json()["grants"][0]
    assert current_grant["grantee_account"] == "reader-renamed"
    assert current_grant["grantee_account_name"] == "共享读者"
    revoked = owner.delete(f"/api/account-settings/member-grants/{member}/{grants[0]['account_id']}")
    assert revoked.status_code == 200, revoked.text
    state = reader.get("/api/members").json()
    assert state["initial_member_id"] == state["default_member_id"]
    assert reader.get(f"/api/members/{member}").status_code == 403
    grant(owner, member, "reader-renamed", "read")
    state = reader.get("/api/members").json()
    assert state["initial_member_id"] == state["default_member_id"]


def test_revoke_waits_for_authorized_operation_and_blocks_next_write(accounts):
    owner, _, _ = accounts
    member = create_member(owner)
    grants = grant(owner, member, "editor", "edit")
    access = MemberRepository().resolve(account_id_for("editor"), member)
    entered = threading.Event()
    finished = threading.Event()
    def revoke():
        entered.set()
        MemberRepository().revoke(account_id_for("owner"), member, grants[0]["account_id"])
        finished.set()
    with access.guard(write=True):
        thread = threading.Thread(target=revoke)
        thread.start()
        assert entered.wait(2)
        assert not finished.wait(.05)
        # A real commit and its nested response read must finish before revoke,
        # even when SQLite already has a revocation writer waiting to commit.
        saved = ReportService(access).create_manual_report(member, report=report_payload())
        assert saved["member_id"] == member
    thread.join(2)
    assert finished.is_set()
    assert owner.get(f"/api/members/{member}/reports/{saved['report_id']}").status_code == 200
    with pytest.raises(Exception) as error:
        ReportService(access).create_manual_report(member, report=report_payload())
    assert error_http_status(error.value) == 403


def test_local_data_contains_member_not_grantee_copy(accounts):
    owner, _, editor = accounts
    member = create_member(owner)
    grant(owner, member, "editor", "edit")
    response = editor.post(f"/api/members/{member}/reports", json=report_payload())
    assert response.status_code == 201, response.text
    with connect(app_paths().reports_db(account_id_for("owner"))) as connection:
        assert connection.execute("SELECT COUNT(*) FROM reports WHERE member_id = ?", (member,)).fetchone()[0] == 1
    assert not app_paths().reports_db(account_id_for("editor")).exists()
    with connect(app_paths().members_db(account_id_for("owner"))) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM members WHERE member_id = ?", (member,)
        ).fetchone()[0] == 1
    with connect(app_paths().members_db(account_id_for("editor"))) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM members WHERE member_id = ?", (member,)
        ).fetchone()[0] == 0


def test_basic_member_validation_and_member_deletion(accounts):
    owner, *_ = accounts
    assert owner.post("/api/members", json={"member_name": "  "}).status_code == 422
    assert owner.post("/api/members", json={"member_name": "家人", "birth_date": "2099-01-01"}).status_code == 422
    assert owner.post("/api/members", json={"member_name": "家人", "blood_type": "invalid"}).status_code == 422
    assert owner.post("/api/members", json={"member_name": "家人", "full_name": "张三"}).status_code == 422
    assert owner.post("/api/members", json={"member_name": "家人", "relationship": "亲属"}).status_code == 422
    created = owner.post("/api/members", json={"member_name": "家人", "blood_type": "ab"})
    assert created.status_code == 201, created.text
    member = created.json()["member_id"]
    assert created.json()["blood_type"] == "ab"
    updated = owner.patch(f"/api/members/{member}", json={"member_name": "家人", "blood_type": "o"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["blood_type"] == "o"
    assert owner.patch(
        f"/api/members/{member}",
        json={"member_name": "家人", "full_name": "张三", "relationship": "亲属"},
    ).status_code == 422
    assert owner.delete(f"/api/members/{member}").status_code == 200


def test_batch_grants_validate_atomically_and_do_not_share_future_members(accounts):
    owner, reader, editor = accounts
    first, second = create_member(owner), create_member(owner)
    foreign = create_member(editor)
    invalid = owner.put("/api/account-settings/member-grants", json={"grantee_account": "reader", "grants": [
        {"member_id": first, "permission": "read"}, {"member_id": foreign, "permission": "edit"}]})
    assert invalid.status_code == 403
    assert reader.get(f"/api/members/{first}").status_code == 403
    valid = owner.put("/api/account-settings/member-grants", json={"grantee_account": "reader", "grants": [
        {"member_id": first, "permission": "read"}, {"member_id": second, "permission": "edit"}]})
    assert valid.status_code == 200
    assert reader.get(f"/api/members/{first}").json()["can_edit"] is False
    assert reader.get(f"/api/members/{second}").json()["can_edit"] is True
    future = create_member(owner)
    assert reader.get(f"/api/members/{future}").status_code == 403
    grant(owner, second, "reader", "read")
    assert reader.patch(f"/api/members/{second}", json={"member_name": "越权"}).status_code == 403


def test_same_report_ids_from_different_owners_have_separate_favorites(accounts):
    owner, reader, editor = accounts
    first, second = create_member(owner), create_member(editor)
    a = owner.post(f"/api/members/{first}/reports", json=report_payload()).json()
    b = editor.post(f"/api/members/{second}/reports", json=report_payload()).json()
    assert a["report_id"] == b["report_id"]
    grant(owner, first, "reader", "read")
    grant(editor, second, "reader", "read")
    for member in (first, second):
        saved = reader.post("/api/favorites", json={"source_type": "report", "member_id": member, "source_id": a["report_id"]})
        assert saved.status_code == 200, saved.text
    assert {item["member_id"] for item in reader.get("/api/favorites").json()["favorites"]} == {first, second}


_ACCOUNT_ID = "00000000-0000-4000-8000-000000000001"


def test_missing_account_config_is_rejected_without_recreation():
    with TestClient(create_app()) as client:
        signup = client.post(
            "/api/auth/sign_up",
            json={
                "account": "missing-config",
                "account_name": "Missing Config",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        account_id = signup.json()["account_id"]
        config_path = app_paths().config_db(account_id)
        config_path.unlink()

        response = client.get("/api/members")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "UNSUPPORTED_SCHEMA"
    assert not config_path.exists()


def test_missing_member_preference_is_rejected_without_repair():
    with TestClient(create_app()) as client:
        signup = client.post(
            "/api/auth/sign_up",
            json={
                "account": "missing-preference",
                "account_name": "Missing Preference",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        account_id = signup.json()["account_id"]
        config_path = app_paths().config_db(account_id)
        with sqlite3.connect(config_path) as connection:
            connection.execute("DELETE FROM member_preferences")

        response = client.get("/api/members")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "UNSUPPORTED_SCHEMA"
    with sqlite3.connect(config_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM member_preferences"
        ).fetchone() == (0,)


def test_registered_member_with_missing_member_database_is_rejected_without_recreation():
    with TestClient(create_app()) as client:
        signup = client.post(
            "/api/auth/sign_up",
            json={
                "account": "missing-member-store",
                "account_name": "Missing Member Store",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        account_id = signup.json()["account_id"]
        created = client.post("/api/members", json={"member_name": "成员一"})
        member_id = created.json()["member_id"]
        member_path = app_paths().members_db(account_id)
        member_path.unlink()

        response = client.get(f"/api/members/{member_id}")
        create_response = client.post(
            "/api/members", json={"member_name": "不应补造的新成员"}
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "UNSUPPORTED_SCHEMA"
    assert create_response.status_code == 409
    assert create_response.json()["detail"]["code"] == "UNSUPPORTED_SCHEMA"
    assert not member_path.exists()


def test_missing_member_profile_blocks_report_creation_without_repair():
    with TestClient(create_app()) as client:
        signup = client.post(
            "/api/auth/sign_up",
            json={
                "account": "missing-profile",
                "account_name": "Missing Member Profile",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        account_id = signup.json()["account_id"]
        created = client.post("/api/members", json={"member_name": "成员一"})
        member_id = created.json()["member_id"]
        with sqlite3.connect(app_paths().members_db(account_id)) as connection:
            connection.execute(
                "DELETE FROM members WHERE member_id = ?", (member_id,)
            )

        response = client.post(
            f"/api/members/{member_id}/reports",
            json={
                "report_type": "其它报告",
                "report_name": "不应创建",
                "report_time": "2026-09-05T12:00:00+08:00",
                "institution_name": None,
                "other_report": {"report_body": "不应保存"},
            },
        )
        create_response = client.post(
            "/api/members", json={"member_name": "不应掩盖缺失资料"}
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "UNSUPPORTED_SCHEMA"
    assert create_response.status_code == 409
    assert create_response.json()["detail"]["code"] == "UNSUPPORTED_SCHEMA"
    assert not app_paths().reports_db(account_id).exists()


def test_access_notification_stream_is_bounded_and_republishes_on_reconnect(monkeypatch):
    elapsed = 0

    async def sleep(seconds):
        nonlocal elapsed
        elapsed += seconds

    async def to_thread(function, account_id):
        assert function == service.access_revision
        assert account_id == "actor-id"
        return 7

    service = SimpleNamespace(access_revision=lambda account_id: 7)

    class ConnectedRequest:
        async def is_disconnected(self):
            return False

    monkeypatch.setattr(members, "asyncio", SimpleNamespace(
        sleep=sleep, to_thread=to_thread,
        get_running_loop=lambda: SimpleNamespace(time=lambda: elapsed),
    ))

    async def read_connection():
        response = await members.access_events(ConnectedRequest(), SimpleNamespace(account_id="actor-id"), service)
        return [chunk async for chunk in response.body_iterator]

    for expected_elapsed in (30, 60):
        chunks = asyncio.run(read_connection())
        assert len(chunks) == 15
        assert 'event: member_access\ndata: {"revision": 7}' in chunks[0]
        assert chunks[1:] == [": keep-alive\n\n"] * 14
        assert elapsed == expected_elapsed

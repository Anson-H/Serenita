"""Explicit account/member setup for tests of the current storage contract."""

from tests.api_client import TestClient
from backend.app.main import create_app
from backend.app.repositories.auth_repository import AuthRepository
from backend.app.repositories.member_repository import MemberRepository
import pytest
import hashlib
from backend.app.application.report_service import ReportService


def account_id(account: str) -> str:
    existing = AuthRepository().account_by_login(account)
    if existing is None:
        with TestClient(create_app()) as client:
            response = client.post("/api/auth/sign_up", json={
                "account": account, "account_name": account,
                "password": "secret", "confirm_password": "secret",
            })
            assert response.status_code == 200, response.text
        existing = AuthRepository().account_by_login(account)
    assert existing is not None
    return str(existing["account_id"])


def member_id(account: str) -> str:
    by_id = AuthRepository().account_by_id(account)
    immutable_id = str(by_id["account_id"]) if by_id is not None else account_id(account)
    existing = MemberRepository.default_member_id(immutable_id)
    if existing is not None:
        return existing
    return MemberRepository().create(
        immutable_id,
        {"member_name": "本人"},
        set_as_default=True,
    )


def member_access(account: str):
    return MemberRepository().resolve(account_id(account), member_id(account))


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    result = []
    for account in ("owner", "reader", "editor"):
        client = TestClient(create_app())
        response = client.post("/api/auth/sign_up", json={"account": account, "account_name": account,
            "password": "secret", "confirm_password": "secret"})
        assert response.status_code == 200, response.text
        created = client.post("/api/members", json={"member_name": "本人"})
        assert created.status_code == 201, created.text
        result.append(client)
    yield result
    for client in result:
        client.close()


def create_member(client, name="家人"):
    response = client.post("/api/members", json={"member_name": name})
    assert response.status_code == 201, response.text
    return response.json()["member_id"]


def report_payload():
    return {"report_type": "其它报告", "report_name": "随访", "report_time": "2026-08-01T12:00:00+08:00",
            "institution_name": "测试机构", "other_report": {"report_body": "测试报告事实"}}


def grant(client, member, account, permission):
    response = client.put("/api/account-settings/member-grants", json={"grantee_account": account,
        "grants": [{"member_id": member, "permission": permission}]})
    assert response.status_code == 200, response.text
    return response.json()["grants"]


def import_report(actor, member, *, payload=None, attachment=None):
    service = ReportService.for_member(account_id(actor), member)
    source = {"source_type": "conversation_text"} if attachment is None else {"source_type": "conversation_attachment", "resource_id": "same-attachment"}
    visible = {} if attachment is None else {"same-attachment": {
        "original_filename": "report.jpg", "path": str(attachment), "mime_type": "image/jpeg",
        "sha256": hashlib.sha256(attachment.read_bytes()).hexdigest(),
    }}
    parsed = service.validate_parsed_reports(member, reports=[{"sources": [source], "report": payload or report_payload()}],
        source_text="同一份报告原文", session_id="same-session", source_message_id="same-message",
        visible_attachments=visible, authorized_report_sources={})
    sources = [{**parsed["sources"][0], **({"source_text": "同一份报告原文"} if attachment is None else {"path": str(attachment)})}]
    return service.create_report_from_parsed(member, parsed_report=parsed["reports"][0]["report"], parsed_sources=sources, session_id="same-session")

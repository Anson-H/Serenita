from member_support import account_id as account_id_for, member_id
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
import pytest
from tests.api_client import TestClient
from pydantic import ValidationError
from backend.app.api.conversations import ContextResourceRef


def _sign_up(client: TestClient, account: str) -> None:
    response = client.post(
        "/api/auth/sign_up",
        json={
            "account": account,
            "account_name": account.title(),
            "password": "secret",
            "confirm_password": "secret",
        },
    )
    assert response.status_code == 200, response.text


def test_context_resource_request_contains_only_reference_fields():
    assert ContextResourceRef(
        resource_type="report",
        resource_id="REPORT-1",
        member_id="MEMBER-1",
    ).model_dump(exclude_none=True) == {
        "resource_type": "report",
        "resource_id": "REPORT-1",
        "member_id": "MEMBER-1",
    }

    with pytest.raises(ValidationError):
        ContextResourceRef(
            resource_type="report",
            resource_id="REPORT-1",
            display_name="旧展示名",
        )


def test_conversation_attachment_preview_is_inline_and_account_scoped(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))

    from backend.app.main import create_app
    from backend.app.repositories.conversation_repository import (
        ConversationRepository,
    )
    from backend.app.storage.paths import app_paths

    app = create_app()
    alice = TestClient(app)
    _sign_up(alice, "alice")

    repository = ConversationRepository()
    account_id = account_id_for("alice")
    session_id = repository.ensure_session(account_id, member_id=member_id("alice"))
    resource_id = "检查 医疗报告-002#1%?.txt"
    original_filename = "原始检查报告.txt"
    relative_path = f"conversations/attachments/{session_id}/{resource_id}"
    attachment_path = app_paths().account_root(account_id) / relative_path
    attachment_path.parent.mkdir(parents=True, exist_ok=True)
    attachment_path.write_text("private attachment", encoding="utf-8")
    repository.insert_ready_resource(
        account_id=account_id,
        session_id=session_id,
        resource_id=resource_id,
        original_filename=original_filename,
        mime_type="text/plain",
        size_bytes=attachment_path.stat().st_size,
        relative_path=relative_path,
        sha256="sha-preview-file",
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    response = alice.get(
        f"/api/conversations/{session_id}/context-resources/{quote(resource_id, safe='')}"
    )

    assert response.status_code == 200
    assert response.content == b"private attachment"
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["content-disposition"].startswith("inline;")
    assert quote(original_filename, safe="") in response.headers["content-disposition"]
    assert quote(resource_id, safe="") not in response.headers["content-disposition"]

    bob = TestClient(app)
    _sign_up(bob, "bob")
    forbidden = bob.get(
        f"/api/conversations/{session_id}/context-resources/{quote(resource_id, safe='')}"
    )

    assert forbidden.status_code == 404
    assert forbidden.json()["detail"]["code"] == "RESOURCE_NOT_FOUND"

"""Conversation attachment reads shared by capability plugins."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.core.attachment_content import AttachmentContent
from backend.app.plugins.body_metric.registry import build_tools as body_tools
from backend.app.plugins.runtime_context import PluginRuntimeContext
from tests.test_runtime_cancellation import session


@pytest.fixture
def attachment(session):
    resource = session.repository.create_uploaded_resource(
        account_id=session.account,
        session_id=session.turn["session_id"],
        original_filename="source.png",
        fallback_extension=".png",
        mime_type="image/png",
        content=b"original attachment content",
    )
    return resource["resource_id"]


def test_content_reader_returns_verified_snapshot_without_storage_paths(session, attachment):
    result = session.service.inputs.read_attachment_content(
        session.account, session.turn["session_id"], attachment
    )
    assert result == AttachmentContent(
        attachment, "source.png", "image/png", b"original attachment content"
    )
    assert not hasattr(result, "path")



@pytest.mark.parametrize("state", ["ready", "missing", "other_session", "changed", "expired"])
def test_plugins_share_verified_reader_and_never_save_unavailable_content(
    session, attachment, state
):
    session_id = session.turn["session_id"]
    if state == "missing":
        attachment = "missing.png"
    elif state == "other_session":
        session_id = session.repository.ensure_session(session.account, member_id=None)
    elif state == "changed":
        source = session.service.inputs.trusted_attachment_resource(
            session.account, session_id, attachment
        )
        Path(source["path"]).write_bytes(b"changed after upload")
    elif state == "expired":
        session.repository.set_resource_lifecycle_status(
            session.account, session_id, attachment, "expired"
        )

    saves = []

    def save(*args, **kwargs):
        saves.append(args)
        return {"saved": True}

    context = PluginRuntimeContext(
        account_id=session.account,
        member_id="member",
        event_recorder=lambda event: None,
        services={"body_metric": SimpleNamespace(attach=save)},
        conversation_attachment_reader=lambda resource_id: session.service.inputs.read_attachment_content(
            session.account, session_id, resource_id
        ),
    )
    tool = next(tool for tool in body_tools(runtime_context=context) if tool.name == "attach_body_record_file")
    arguments = {"resource_id": attachment, "record_id": "record"}

    if state == "ready":
        assert tool.run(arguments).output["saved"] is True
        assert len(saves) == 1
        assert saves[0][3:6] == ("source.png", "image/png", b"original attachment content")
    else:
        with pytest.raises(ValueError if state == "changed" else PermissionError):
            tool.run(arguments)
        assert saves == []


def test_content_reader_rejects_another_account(session, attachment):
    from member_support import account_id

    other_account = account_id("other-attachment")
    other_session = session.repository.ensure_session(other_account, member_id=None)
    with pytest.raises(PermissionError):
        session.service.inputs.read_attachment_content(other_account, other_session, attachment)

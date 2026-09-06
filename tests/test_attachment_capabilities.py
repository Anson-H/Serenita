from types import SimpleNamespace
import pytest
from backend.app.core.errors import SerenitaError
from tests.api_client import TestClient
from backend.app.application.conversation_service import ConversationService
from backend.app.api.dependencies import get_conversation_service, require_current_user
from backend.app.main import create_app
from backend.app.application.report_file_validation import REPORT_SIGNATURE_ERROR, validate_report_signature


class Catalog:
    def __init__(self, chat_types, vision_types, native_types):
        self.chat = {"model_id": "test:chat", "file_mime_types": chat_types}
        self.vision = {"model_id": "test:vision", "file_mime_types": vision_types} if vision_types is not None else None
        self.native_types = set(native_types)

    def default_model_for_account(self, account_id, purpose="chat"):
        return self.chat if purpose == "chat" else self.vision

    def model_for_account(self, account_id, model_id):
        return self.chat if model_id == self.chat["model_id"] else None

    def provider_supports_native_attachment(self, model, mime_type):
        return mime_type in self.native_types


def service(chat, vision, native):
    instance = ConversationService(model_catalog=Catalog(chat, vision, native))
    return instance


@pytest.mark.parametrize("chat,vision,native,expected", [
    ([], ["image/jpeg", "image/png"], ["image/jpeg", "image/png"], {"image/jpeg", "image/png", "application/pdf"}),
    ([], ["image/png"], ["image/png"], {"image/png"}),
    (["audio/wav", "video/mp4"], ["image/jpeg"], ["audio/wav", "video/mp4", "image/jpeg"], {"audio/wav", "video/mp4", "image/jpeg", "application/pdf"}),
    (["image/heic"], None, ["image/heic"], {"image/heic"}),
    (["application/pdf"], None, [], set()),
    ([], None, [], set()),
])
def test_attachment_advertisement_matches_upload_and_send_acceptance(chat, vision, native, expected):
    instance = service(chat, vision, native)
    capabilities = instance.attachment_capabilities("test-account")
    assert set(capabilities["file_mime_types"]) == expected
    for mime in {"image/jpeg", "image/png", "image/heic", "application/pdf", "audio/wav", "video/mp4"}:
        if mime in expected:
            instance._validate_attachment_supported_for_conversation("test-account", instance.model_catalog.chat, mime)
        else:
            with pytest.raises(SerenitaError):
                instance._validate_attachment_supported_for_conversation("test-account", instance.model_catalog.chat, mime)


def test_attachment_endpoint_authentication_unknown_model_and_empty_default():
    app = create_app()
    instance = service([], ["image/jpeg"], ["image/jpeg"])
    app.dependency_overrides[get_conversation_service] = lambda: instance
    client = TestClient(app)
    assert client.get("/api/conversations/attachment-capabilities").status_code == 401
    app.dependency_overrides[require_current_user] = lambda: SimpleNamespace(account_id="test-account")
    response = client.get("/api/conversations/attachment-capabilities", params={"model_id": "test:chat"})
    assert response.status_code == 200
    assert response.json() == {"model_id": "test:chat", "file_mime_types": ["application/pdf", "image/jpeg"]}
    assert client.get("/api/conversations/attachment-capabilities?model_id=another-account:model").status_code == 404
    instance.model_catalog.chat = None
    assert client.get("/api/conversations/attachment-capabilities").json() == {"model_id": None, "file_mime_types": []}


@pytest.mark.parametrize(
    ("mime_type", "content"),
    [
        ("image/jpeg", b"\xff\xd8\xff\xe0payload"),
        ("image/png", b"\x89PNG\r\n\x1a\npayload"),
        ("application/pdf", b"%PDF-1.7\npayload"),
        ("image/heic", b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1"),
    ],
)
def test_allowlisted_report_signatures(mime_type, content):
    validate_report_signature(content, mime_type)


@pytest.mark.parametrize(
    "mime_type",
    ["image/jpeg", "image/png", "application/pdf", "image/heic"],
)
def test_extension_spoofing_is_rejected(mime_type):
    with pytest.raises(ValueError, match=REPORT_SIGNATURE_ERROR):
        validate_report_signature(b"not a report file", mime_type)

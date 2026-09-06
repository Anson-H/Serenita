from member_support import accounts as accounts
from backend.app.api.errors import error_http_status
from types import SimpleNamespace
from backend.app.api.conversations import upload_context_resource
import asyncio
import json
import pytest
from backend.app.core.errors import SerenitaError
from member_support import account_id as account_id_for
from member_support import create_member, grant, report_payload, import_report
from tests.report_support import report_payload as lab_payload
from tests.model_support import ConversationModelCatalog, BlockingConversationModelCatalog
from backend.app.agent_runtime.model_types import ModelStreamChunk, ToolCallDelta
from backend.app.application.conversation_service import ConversationService
from backend.app.application.model_provider_service import ModelProviderService, PreparedProviderRequest
from backend.app.application.report_service import ReportService
from backend.app.plugins.report.tools.mutation_tools import UpdateReportFieldsTool, DeleteReportTool
from backend.app.plugins.report.tools.query_tools import ReadReportCatalogTool
from backend.app.plugins.report.tools.write_report_analysis import WriteReportAnalysisTool
from backend.app.plugins import PluginRuntimeContext, build_available_tools, build_builtin_skills
from backend.app.repositories.member_repository import MemberRepository
from backend.app.core.report_errors import ReportImportWriteConflictError
from backend.app.providers.base import ModelProvider
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.storage.sqlite import UnsupportedSchemaError


def test_memberless_chat_supports_attachments_actions_and_favorites(accounts):
    _, reader, _ = accounts

    class AttachmentProvider(ModelProvider):
        def supports_native_attachment(self, mime_type):
            return mime_type == "image/jpeg"

    class InspectingCatalog(ConversationModelCatalog):
        def __init__(self):
            self.agent_requests = []

        def prepare_stream_chat_for_account(self, **kwargs):
            request = kwargs["model_request"]
            if request.model_config.get("purpose") == "agent_action":
                self.agent_requests.append(request)
            model = kwargs["model"]
            thinking_mode = kwargs["thinking_mode"]
            provider = AttachmentProvider()
            transport_request = ModelProviderService.prepare_transport_request(
                model, request, thinking_mode
            )
            payload = provider.build_chat_payload(
                remote_model_id=model["remote_model_id"],
                model_request=transport_request,
                thinking_mode=thinking_mode,
                stream=True,
            )
            return PreparedProviderRequest(
                provider=provider,
                provider_id=model["provider_id"],
                remote_model_id=model["remote_model_id"],
                transport_request=transport_request,
                provider_payload=payload,
                transport_mode=transport_request.transport_mode,
                thinking_mode=thinking_mode,
                api_url="https://provider.example/v1",
                api_key="test-key",
            )

    catalog = InspectingCatalog()
    catalog.model = {**catalog.model, "file_mime_types": ["image/jpeg"]}
    catalog.provider_supports_native_attachment = lambda *_: True
    service = ConversationService(model_catalog=catalog)

    class TextUpload:
        content_type = "image/jpeg"
        filename = "temporary.jpg"

        async def read(self, _limit):
            return b"\xff\xd8\xfftemporary"

    uploaded = asyncio.run(
        upload_context_resource(user=SimpleNamespace(account_id=account_id_for("reader")), session_id=None, model_id="model_1", file=TextUpload(), service=service, member_id=None)
    )
    assert uploaded["member_id"] is None
    resource = uploaded["resource"]
    assert (
        resource["resource_id"]
        == resource["original_filename"]
        == "temporary.jpg"
    )
    assert resource["relative_path"].endswith(
        f"/{uploaded['session_id']}/temporary.jpg"
    )
    assert resource["storage_status"] == "ready"
    assert resource["lifecycle_status"] == "pending"
    assert resource["expires_at"] is not None
    assert "status" not in resource
    assert "usage_status" not in resource
    assert "source" not in resource
    assert "thumb_path" not in resource
    started = service.send_message(
        account_id_for("reader"),
        uploaded["session_id"],
        "请阅读附件",
        "model_1",
        "default",
        [{"resource_type": "file", "resource_id": resource["resource_id"]}],
        member_id=None,
    )
    attached_row = service.repository.resource_row(
        account_id_for("reader"),
        uploaded["session_id"],
        resource["resource_id"],
    )
    assert attached_row["storage_status"] == "ready"
    assert attached_row["lifecycle_status"] == "attached"
    assert attached_row["expires_at"] is None
    service.start_turn_job(account_id_for("reader"), started["session_id"], started["stream_id"])
    service.wait_for_all_jobs(timeout=5)
    detail = service.get_conversation(account_id_for("reader"), started["session_id"])
    assert detail["member_id"] is None
    assert detail["member_name"] is None
    assert detail["access_state"] == "available"
    assert detail["fork_available"] is True
    assert catalog.agent_requests
    assert "report-query" in catalog.agent_requests[0].system
    assert "没有可操作的报告档案库目标" in catalog.agent_requests[0].system

    runtime_context = PluginRuntimeContext(
        account_id=account_id_for("reader"), member_id=None, event_recorder=lambda _event: None
    )
    runtime_tool_names = {tool.name for tool in build_available_tools(runtime_context=runtime_context)}
    assert "web_search" in runtime_tool_names
    assert "read_report_catalog" not in runtime_tool_names
    assert "report-query" in {skill.name for skill in build_builtin_skills()}

    user = next(record for record in detail["records"] if record["kind"] == "user")
    answers = [record for record in detail["records"] if record["kind"] == "assistant"]
    assert answers, repr(detail["records"])
    answer = answers[0]
    favorite = reader.post("/api/favorites", json={
        "source_type": "message",
        "source_session_id": started["session_id"],
        "source_id": answer["message_id"],
    })
    assert favorite.status_code == 200, favorite.text
    assert favorite.json()["member_id"] is None
    assert favorite.json()["member_name"] is None
    assert reader.post("/api/favorites", json={
        "source_type": "message",
        "source_session_id": started["session_id"],
        "source_id": answer["message_id"],
    }).status_code == 409

    regenerated = service.regenerate_message(
        account_id_for("reader"), started["session_id"], answer["message_id"], "model_1", "default"
    )
    service.start_turn_job(account_id_for("reader"), started["session_id"], regenerated["stream_id"])
    service.wait_for_all_jobs(timeout=5)
    edited = service.edit_message(
        account_id_for("reader"),
        started["session_id"],
        user["message_id"],
        "修改后的问题",
        "model_1",
        "default",
        [],
    )
    service.start_turn_job(account_id_for("reader"), started["session_id"], edited["stream_id"])
    service.wait_for_all_jobs(timeout=5)
    forked = service.fork_conversation(account_id_for("reader"), started["session_id"])
    assert forked["session"]["member_id"] is None

    bound = MemberRepository.default_member_id(account_id_for("reader"))
    with pytest.raises(SerenitaError) as error:
        service.send_message(
            account_id_for("reader"),
            started["session_id"],
            "不能改绑",
            "model_1",
            "default",
            [],
            member_id=bound,
        )
    assert error.value.detail["code"] == "MEMBER_MISMATCH"


def test_memberless_chat_queue_promotes_without_a_member(accounts):
    _, reader, _ = accounts
    catalog = BlockingConversationModelCatalog()
    service = ConversationService(model_catalog=catalog)
    first = service.send_message(
        account_id_for("reader"), None, "第一条", "model_1", "default", [], member_id=None
    )
    service.start_turn_job(account_id_for("reader"), first["session_id"], first["stream_id"])
    try:
        assert catalog.first_chunk_persisted.wait(2)
        queued = service.send_message(
            account_id_for("reader"),
            first["session_id"],
            "排队继续",
            "model_1",
            "default",
            [],
            member_id=None,
        )
        assert queued["disposition"] == "queued"
        assert queued["member_id"] is None
    finally:
        catalog.release.set()
        service.wait_for_all_jobs(timeout=5)
    detail = service.get_conversation(account_id_for("reader"), first["session_id"])
    assert detail["member_id"] is None
    assert detail["access_state"] == "available"
    assert detail["queued_inputs"] == []
    assert [record["content"] for record in detail["records"] if record["kind"] == "user"] == [
        "第一条",
        "排队继续",
    ]


def test_shared_tools_enforce_member_and_permission(accounts):
    owner, reader, editor = accounts
    target = create_member(owner)
    report = import_report("owner", target)
    grant(owner, target, "reader", "read")
    grant(owner, target, "editor", "edit")
    service = ReportService.for_member(account_id_for("reader"), target)
    query = ReadReportCatalogTool(account_id=account_id_for("reader"), member_id=target, service=service).run({})
    assert query.output["total"] == 1
    assert query.effects["resource_refs"][0]["member_id"] == target
    for cls, arguments in (
        (UpdateReportFieldsTool, {"report_id": report["report_id"], "updates": [{"field": "report_name", "value": "越权"}]}),
        (DeleteReportTool, {"report_id": report["report_id"]}),
        (WriteReportAnalysisTool, {"report_id": report["report_id"], "analysis_content": "越权解读"}),
    ):
        with pytest.raises(SerenitaError) as error:
            cls(account_id=account_id_for("reader"), member_id=target, service=service).run(arguments)
        assert error.value.detail["code"] == "MEMBER_READ_ONLY"
    updated = UpdateReportFieldsTool(account_id=account_id_for("editor"), member_id=target, service=ReportService.for_member(account_id_for("editor"), target)).run(
        {"report_id": report["report_id"], "updates": [{"field": "report_name", "value": "编辑者修正"}]})
    assert updated.effects["resource_refs"][0]["member_id"] == target
    own = reader.get("/api/members").json()["default_member_id"]
    with pytest.raises(SerenitaError) as error:
        service.list_reports(own)
    assert error.value.detail["code"] == "MEMBER_MISMATCH"


def test_identical_originals_are_owned_and_isolated_per_member(accounts):
    owner, _, editor = accounts
    first, second = create_member(owner, "同名人员"), create_member(owner, "同名人员")
    grant(owner, first, "editor", "edit")
    attachment = app_paths().account_root(account_id_for("editor")) / "conversations" / "attachments" / "original.jpg"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_bytes(b"\xff\xd8\xfforiginal")
    a = import_report("editor", first, attachment=attachment)
    b = import_report("owner", second, attachment=attachment)
    service = ReportService.for_member(account_id_for("editor"), first)
    source_a = service.get_report(first, a["report_id"])["sources"][0]
    source_b = owner.get(f"/api/members/{second}/reports/{b['report_id']}").json()["sources"][0]
    assert source_a["resource_id"] != source_b["resource_id"]
    stored, _, _ = service.source_download(first, a["report_id"], source_a["resource_id"])
    assert stored.is_relative_to(app_paths().account_root(account_id_for("owner")))
    assert stored.read_bytes() == attachment.read_bytes()
    assert owner.get(f"/api/members/{second}/reports/{a['report_id']}/source-files/{source_a['resource_id']}").status_code == 404
    assert editor.get(f"/api/members/{second}/reports").status_code == 403
    assert owner.delete(f"/api/members/{first}/reports/{a['report_id']}").status_code == 200
    assert attachment.exists()
    assert owner.get(source_b["download_url"]).status_code == 200
    assert not app_paths().reports_db(account_id_for("editor")).exists()


def test_invited_import_can_add_alias_but_not_change_owner_classification(accounts):
    owner, _, editor = accounts
    target, other = create_member(owner), create_member(owner)
    original = import_report("owner", other, payload=lab_payload())
    grant(owner, target, "editor", "edit")
    imported = lab_payload()
    imported["lab_test_results"][0]["aliases"].append("新别名")
    import_report("editor", target, payload=imported)
    dictionary = owner.get("/api/account-settings/lab-dictionary").json()
    assert "新别名" in dictionary["items"][0]["aliases"]
    changed = lab_payload()
    changed["report_name"] = "肾功能"
    changed["lab_test_results"][0]["category_name"] = "肾功能"
    with pytest.raises(ReportImportWriteConflictError):
        import_report("editor", target, payload=changed)
    assert owner.get(f"/api/members/{other}/reports/{original['report_id']}").json()["report_name"] == "肝功能"
    assert editor.patch(f"/api/members/{target}/lab-dictionary/items/item-alt", json={}).status_code == 404


def test_revoked_chat_is_private_readable_history_but_not_executable(accounts):
    owner, reader, _ = accounts
    target = create_member(owner)
    grants = grant(owner, target, "reader", "read")
    catalog = ConversationModelCatalog()
    service = ConversationService(model_catalog=catalog)
    started = service.send_message(account_id_for("reader"), None, "阅读共享档案", "model_1", "default", [], member_id=target)
    service.start_turn_job(account_id_for("reader"), started["session_id"], started["stream_id"])
    service.wait_for_all_jobs(timeout=5)
    detail = service.get_conversation(account_id_for("reader"), started["session_id"])
    assert detail["member_id"] == target
    answer = next(record for record in detail["records"] if record["kind"] == "assistant")
    favorite = reader.post("/api/favorites", json={"source_type": "message", "source_session_id": started["session_id"], "source_id": answer["message_id"]})
    assert favorite.status_code == 200, favorite.text
    assert owner.get(f"/api/conversations/{started['session_id']}").status_code == 404
    owner.delete(f"/api/account-settings/member-grants/{target}/{grants[0]['account_id']}")
    historical = service.get_conversation(account_id_for("reader"), started["session_id"])
    assert historical["access_state"] == "history_only"
    assert historical["member_id"] == target
    assert not historical["fork_available"]
    assert reader.get(f"/api/favorites/{favorite.json()['favorite_id']}").json()["content_snapshot"]
    for call in (
        lambda: service.send_message(account_id_for("reader"), started["session_id"], "继续", "model_1", "default", [], member_id=target),
        lambda: service.regenerate_message(account_id_for("reader"), started["session_id"], answer["message_id"], "default"),
        lambda: service.fork_conversation(account_id_for("reader"), started["session_id"]),
    ):
        with pytest.raises(SerenitaError) as error: call()
        assert error_http_status(error.value) == 403


def test_revoke_during_model_generation_stops_followups_and_queue(accounts):
    owner, _, _ = accounts
    target = create_member(owner)
    grants = grant(owner, target, "editor", "edit")
    catalog = BlockingConversationModelCatalog()
    service = ConversationService(model_catalog=catalog)
    first = service.send_message(account_id_for("editor"), None, "先读取报告", "model_1", "default", [], member_id=target)
    service.start_turn_job(account_id_for("editor"), first["session_id"], first["stream_id"])
    try:
        assert catalog.first_chunk_persisted.wait(2)
        queued = service.send_message(account_id_for("editor"), first["session_id"], "再更新报告", "model_1", "default", [], member_id=target)
        owner.delete(f"/api/account-settings/member-grants/{target}/{grants[0]['account_id']}")
    finally:
        catalog.release.set()
        service.wait_for_all_jobs(timeout=5)
    detail = service.get_conversation(account_id_for("editor"), first["session_id"])
    assert detail["access_state"] == "history_only"
    assert detail["pending_turns"] == []
    assert detail["queued_inputs"] == []
    with pytest.raises(SerenitaError):
        service.queue.run_now(account_id_for("editor"), first["session_id"], queued["queued_input"]["input_id"])
    assert not app_paths().reports_db(account_id_for("editor")).exists()


def test_revoke_while_upload_body_is_pending_and_mismatched_chat_member(accounts):
    owner, _, _ = accounts
    target = create_member(owner)
    grants = grant(owner, target, "editor", "edit")
    service = ConversationService(model_catalog=ConversationModelCatalog())
    service.model_catalog.model = {**service.model_catalog.model, "file_mime_types": ["image/jpeg"]}
    service.model_catalog.provider_supports_native_attachment = lambda *_: True
    class PendingUpload:
        content_type = "image/jpeg"
        filename = "report.jpg"
        async def read(self, _limit):
            MemberRepository().revoke(account_id_for("owner"), target, grants[0]["account_id"])
            return b"\xff\xd8\xfforiginal"
    with pytest.raises(SerenitaError) as error:
        asyncio.run(upload_context_resource(user=SimpleNamespace(account_id=account_id_for("editor")), session_id=None, model_id="model_1", file=PendingUpload(), service=service, member_id=target))
    assert error_http_status(error.value) == 403
    assert service.list_conversations(account_id_for("editor"))["sessions"] == []
    own = MemberRepository.default_member_id(account_id_for("editor"))
    session = service.repository.ensure_session(account_id_for("editor"), member_id=own)
    with pytest.raises(SerenitaError) as error:
        service.send_message(account_id_for("editor"), session, "不能换成员", "model_1", "default", [], member_id=target)
    assert error.value.detail["code"] == "MEMBER_MISMATCH"


def test_source_urls_and_existing_service_follow_rename_then_revoke(accounts):
    owner, reader, _ = accounts
    member = create_member(owner)
    report = import_report("owner", member)
    grants = grant(owner, member, "reader", "read")
    service = ReportService.for_member(account_id_for("reader"), member)
    source = reader.get(f"/api/members/{member}/reports/{report['report_id']}").json()["sources"][0]
    assert owner.patch("/api/auth/account", json={"account": "renamed", "account_name": "owner"}).status_code == 200
    path, _, _ = service.source_download(member, report["report_id"], source["resource_id"])
    assert path.is_relative_to(app_paths().account_root(account_id_for("renamed")))
    assert reader.get(source["download_url"]).status_code == 200
    owner.delete(f"/api/account-settings/member-grants/{member}/{grants[0]['account_id']}")
    assert reader.get(source["download_url"]).status_code == 403
    assert reader.get(source["download_url"] + "/thumbnail").status_code == 403
    with pytest.raises(SerenitaError): service.source_download(member, report["report_id"], source["resource_id"])

def test_each_model_request_refreshes_member_permission_and_uses_actor_configuration(accounts):
    owner, _, _ = accounts
    target = create_member(owner, "所有者的家人")
    grant(owner, target, "editor", "edit")

    class PermissionCatalog(ConversationModelCatalog):
        def __init__(self):
            self.requests = []
            self.accounts = []
            self.calls = 0

        def prepare_stream_chat_for_account(self, **kwargs):
            prepared = super().prepare_stream_chat_for_account(**kwargs)
            self.accounts.append(kwargs["account_id"])
            if prepared.transport_request.model_config.get("purpose") == "agent_action":
                self.requests.append(prepared.provider_payload)
            return prepared

        def stream_prepared_chat_for_account(self, **kwargs):
            purpose = kwargs["prepared_request"].transport_request.model_config.get("purpose")
            if purpose == "agent_action" and self.calls == 0:
                self.calls += 1
                MemberRepository().set_grants(account_id_for("owner"), "editor", [{"member_id": target, "permission": "read"}])
                yield ModelStreamChunk(tool_call_deltas=(ToolCallDelta(index=0, id="skill", name_delta="load_skill", arguments_delta='{"name":"report-query"}'),))
                yield ModelStreamChunk(stop_reason="tool_calls")
                return
            yield from super().stream_prepared_chat_for_account(**kwargs)

    catalog = PermissionCatalog()
    service = ConversationService(model_catalog=catalog)
    started = service.send_message(account_id_for("editor"), None, "查看档案", "model_1", "default", [], member_id=target)
    service.start_turn_job(account_id_for("editor"), started["session_id"], started["stream_id"])
    service.wait_for_all_jobs(timeout=5)
    assert catalog.accounts and set(catalog.accounts) == {account_id_for("editor")}
    assert len(catalog.requests) == 2
    contexts = []
    for payload in catalog.requests:
        system = next(message["content"] for message in payload["messages"] if message["role"] == "system")
        # RUNTIME_CONTEXT is the final JSON section of the actual provider system input.
        contexts.append(json.loads(system.split("RUNTIME_CONTEXT\n", 1)[1])["member"])
    assert [item["permission"] for item in contexts] == ["edit", "read"]
    assert all(item["member_id"] == target and item["owner_account"] == "owner" for item in contexts)


def test_names_are_live_and_deleted_member_detaches_previously_revoked_history(accounts):
    owner, reader, _ = accounts
    member = create_member(owner, "原名称")
    grants = grant(owner, member, "reader", "read")
    actor = account_id_for("reader")
    service = ConversationService(model_catalog=ConversationModelCatalog())
    report = owner.post(f"/api/members/{member}/reports", json=report_payload()).json()
    reference = ReportService.for_member(actor, member).validate_report_context(member, report["report_id"])
    started = service.send_message(actor, None, "记录", "model_1", "default", [reference], member_id=member)
    session = started["session_id"]
    service.start_turn_job(actor, session, started["stream_id"])
    service.wait_for_all_jobs(timeout=5)
    detail = service.get_conversation(actor, session)
    answer = next(r for r in detail["records"] if r["kind"] == "assistant")
    favorite = reader.post("/api/favorites", json={"source_type": "message", "source_session_id": session, "source_id": answer["message_id"]}).json()
    assert favorite["source_type"] == "message"
    report_favorite = reader.post("/api/favorites", json={"source_type": "report", "member_id": member, "source_id": report["report_id"]}).json()
    owner.delete(f"/api/account-settings/member-grants/{member}/{grants[0]['account_id']}")
    assert owner.patch(f"/api/members/{member}", json={"member_name": "新名称"}).status_code == 200
    historical = service.get_conversation(actor, session)
    assert historical["member_name"] == "新名称"
    assert historical["access_state"] == "history_only"
    assert reader.get(f"/api/members/{member}").status_code == 403
    assert MemberRepository().historical_member_name(account_id_for("owner"), "conversation", session) is None
    records = [{"kind": "user", "context_resources": [reference]}]
    assert service._conversation_resource_states(actor, member, records)[0]["availability"] == "forbidden"
    grant(owner, member, "reader", "read")
    assert service.get_conversation(actor, session)["access_state"] == "available"
    owner.delete(f"/api/account-settings/member-grants/{member}/{grants[0]['account_id']}")
    before = service.repository.session_events(actor, session)
    deleted = owner.delete(f"/api/members/{member}")
    assert deleted.status_code == 200, deleted.text
    detail = service.get_conversation(actor, session)
    assert detail["member_id"] is None and detail["member_name"] is None
    assert detail["access_state"] == "available"
    assert detail["records"] == historical["records"] or any(r.get("content") == answer["content"] for r in detail["records"])
    assert service.repository.session_events(actor, session) == before
    assert service._conversation_resource_states(actor, None, records)[0]["availability"] == "deleted"
    for saved in (favorite, report_favorite):
        retained = reader.get(f"/api/favorites/{saved['favorite_id']}").json()
        assert retained["member_id"] is None and retained["member_name"] is None
        assert retained["content_snapshot"] == saved["content_snapshot"]
    for path, table in ((app_paths().conversations_db(actor), "conversations"), (app_paths().favorites_db(actor), "favorites")):
        with connect(path) as connection:
            assert "member_name" not in {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
            assert connection.execute(f"SELECT COUNT(*) FROM {table} WHERE member_id IS NOT NULL").fetchone()[0] == 0
    next_turn = service.send_message(actor, session, "普通问题", "model_1", "default", [], member_id=None)
    assert next_turn["member_id"] is None
    service.cancel_turn(actor, session, next_turn["turn_id"])


def test_delete_interrupts_active_work_without_promoting_old_queue(accounts):
    owner, _, _ = accounts
    member = create_member(owner)
    actor = account_id_for("owner")
    catalog = BlockingConversationModelCatalog()
    service = ConversationService(model_catalog=catalog)
    first = service.send_message(actor, None, "正在执行", "model_1", "default", [], member_id=member)
    service.start_turn_job(actor, first["session_id"], first["stream_id"])
    try:
        assert catalog.first_chunk_persisted.wait(2)
        service.send_message(actor, first["session_id"], "旧队列", "model_1", "default", [], member_id=member)
        response = owner.delete(f"/api/members/{member}")
        assert response.status_code == 200, response.text
    finally:
        catalog.release.set()
        service.wait_for_all_jobs(timeout=5)
    detail = service.get_conversation(actor, first["session_id"])
    assert detail["member_id"] is None
    assert detail["pending_turns"] == [] and detail["queued_inputs"] == []
    assert not any(r.get("content") == "旧队列" for r in detail["records"])


def test_private_schema_failure_rolls_back_member_delete(accounts):
    owner, _, _ = accounts
    actor = account_id_for("owner")
    member = create_member(owner)
    repository = ConversationRepository()
    session = repository.ensure_session(actor, member_id=member)
    from backend.app.storage.favorite_database import initialize_favorites_database
    initialize_favorites_database(actor)
    with connect(app_paths().favorites_db(actor)) as connection:
        connection.execute("ALTER TABLE favorites ADD COLUMN unsupported TEXT")
    with pytest.raises(UnsupportedSchemaError):
        MemberRepository().delete(actor, member)
    assert repository.session_row(actor, session)["member_id"] == member
    assert owner.get(f"/api/members/{member}").status_code == 200

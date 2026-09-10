from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import sqlite3
import pytest
from member_support import accounts as accounts, account_id, create_member, grant, report_payload
from backend.app.application.medical_log_service import MedicalLogService
from backend.app.application.report_service import ReportService
from backend.app.core.errors import SerenitaError
from backend.app.plugins.runtime_context import PluginRuntimeContext
from backend.app.plugins.medical_log.registry import build_tools, build_skills
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect


def log_url(member, log_id=None):
    return f"/api/members/{member}/medical-logs" + (f"/{log_id}" if log_id else "")


def create_log(owner, member, **extra):
    response = owner.post(log_url(member), json={"recorded_on": "2026-09-07", "title": "症状变化", "content": "家属描述：可能昨日发热", **extra})
    assert response.status_code == 201, response.text
    return response.json()["medical_log"]


def test_logs_dates_partial_update_search_and_validation(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    latest = create_log(owner, member)
    dated = create_log(owner, member, recorded_on="2026-09-01")
    older = create_log(owner, member, recorded_on="2026-08-01", title="复诊", content="体温正常")
    url = log_url(member)
    assert [v["medical_log_id"] for v in owner.get(url).json()["medical_logs"]] == [latest["medical_log_id"], dated["medical_log_id"], older["medical_log_id"]]
    found = owner.get(url + "?after_date=2026-09-01&before_date=2026-09-01&query=家属").json()["medical_logs"]
    assert [v["medical_log_id"] for v in found] == [dated["medical_log_id"]]
    assert len(owner.get(url + "?query=可能").json()["medical_logs"]) == 2
    detail_url = log_url(member, latest["medical_log_id"])
    assert owner.patch(detail_url, json={"title": latest["title"]}).json()["medical_log"]["updated_at"] == latest["updated_at"]
    changed = owner.patch(detail_url, json={"title": "更正", "recorded_on": "2026-09-02"}).json()["medical_log"]
    assert changed["content"] == latest["content"]
    assert changed["created_at"] == latest["created_at"]
    for invalid in ({}, {"recorded_on": None}, {"recorded_on": ""}, {"title": " "}, {"content": None}, {"recorded_on": "2026-02-30"}, {"report_ids": []}, {"reports": []}, {"member_id": member}):
        assert owner.patch(detail_url, json=invalid).status_code == 422
        assert owner.get(detail_url).json()["medical_log"] == changed
    assert owner.get(url + "?after_date=2026-10-01&before_date=2026-01-01").status_code == 400
    assert owner.delete(detail_url).status_code == 200
    assert owner.patch(detail_url, json={"title": "不能复活"}).status_code == 404


def test_log_storage_is_independent_and_member_deletion_removes_logs(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    actor = account_id("owner")
    report_path = app_paths().reports_db(actor)
    assert not report_path.exists()
    record = create_log(owner, member)
    assert set(record) == {"medical_log_id", "member_id", "recorded_on", "title", "content", "created_at", "updated_at"}
    assert owner.get(log_url(member, record["medical_log_id"])).json()["medical_log"] == record
    assert not report_path.exists()
    with connect(app_paths().medical_logs_db(actor)) as db:
        assert [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")] == ["medical_logs"]
    report = owner.post(f"/api/members/{member}/reports", json=report_payload()).json()
    assert owner.delete(f"/api/members/{member}/reports/{report['report_id']}").status_code == 200
    assert owner.get(log_url(member, record["medical_log_id"])).json()["medical_log"] == record
    assert owner.delete(f"/api/members/{member}").status_code == 200
    with connect(app_paths().medical_logs_db(actor)) as db:
        assert db.execute("SELECT count(*) FROM medical_logs").fetchone()[0] == 0


def test_permissions_tools_and_cross_conversation(accounts):
    owner, reader, editor = accounts
    member = create_member(owner)
    other = create_member(owner)
    grant(owner, member, "editor", "edit")
    grant(owner, member, "reader", "read")
    record = create_log(owner, member)
    url = log_url(member, record["medical_log_id"])
    assert reader.get(url).status_code == 200
    assert reader.patch(url, json={"title": "禁止"}).status_code == 403
    assert reader.delete(url).status_code == 403
    assert editor.get(log_url(other, record["medical_log_id"])).status_code == 403
    assert owner.get(log_url(other, record["medical_log_id"])).status_code == 404
    def tools():
        return {tool.name: tool for tool in build_tools(runtime_context=PluginRuntimeContext(account_id=account_id("editor"), member_id=member, event_recorder=lambda _: None))}
    first = tools()
    saved = first["create_log"].run({"recorded_on": "2026-09-07", "title": "复诊", "content": "自述症状好转"}).output["medical_log"]
    assert owner.get(log_url(member, saved["medical_log_id"])).json()["medical_log"]["content"] == "自述症状好转"
    assert tools()["read_log"].run({"medical_log_ids": [saved["medical_log_id"]]}).logical_pages[0]["medical_logs"][0] == saved
    assert build_skills()[0].name == "log"
    assert build_tools(runtime_context=PluginRuntimeContext(account_id=account_id("owner"), event_recorder=lambda _: None)) == []
    with pytest.raises(PermissionError):
        first["create_log"].bind_runtime_arguments({}, context=SimpleNamespace(account_id=account_id("editor"), member_id=other), observations=[])
    MedicalLogService().members.revoke(account_id("owner"), member, account_id("editor"))
    with pytest.raises(SerenitaError): first["create_log"].run({"recorded_on": "2026-09-07", "title": "禁止", "content": "撤权后"})


def test_concurrent_updates_and_report_deletion(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    log = create_log(owner, member)
    service, actor = MedicalLogService(), account_id("owner")
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(service.update, actor, member, log["medical_log_id"], change) for change in ({"title": "更新标题"}, {"content": "更新正文"})]
        for future in futures: future.result(timeout=10)
    result = service.read(actor, member, medical_log_ids=[log["medical_log_id"]])["medical_logs"][0]
    assert result["title"] == "更新标题" and result["content"] == "更新正文"
    report = owner.post(f"/api/members/{member}/reports", json=report_payload()).json()
    with ThreadPoolExecutor(2) as pool:
        update = pool.submit(service.update, actor, member, log["medical_log_id"], {"content": "删除报告期间补充正文"})
        delete = pool.submit(ReportService.for_member(actor, member).delete_report, member, report["report_id"])
        update.result(timeout=10)
        delete.result(timeout=10)
    assert service.read(actor, member, medical_log_ids=[log["medical_log_id"]])["medical_logs"][0]["content"] == "删除报告期间补充正文"


def test_log_storage_failure_preserves_content_and_allows_report_deletion(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    report = owner.post(f"/api/members/{member}/reports", json=report_payload()).json()
    log = create_log(owner, member)
    actor = account_id("owner")
    with connect(app_paths().medical_logs_db(actor)) as db:
        db.execute("CREATE TRIGGER fail_log BEFORE UPDATE ON medical_logs BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        MedicalLogService().update(actor, member, log["medical_log_id"], {"title": "失败"})
    ReportService.for_member(actor, member).delete_report(member, report["report_id"])
    assert owner.get(log_url(member, log["medical_log_id"])).json()["medical_log"] == log
    assert owner.get(f"/api/members/{member}/reports/{report['report_id']}").status_code == 404


def test_other_report_deletion_path_and_member_rollback(accounts):
    from backend.app.repositories.report_repository import ReportRepository
    owner, *_ = accounts
    member = create_member(owner)
    report = owner.post(f"/api/members/{member}/reports", json=report_payload()).json()
    log = create_log(owner, member)
    actor = account_id("owner")
    repository = ReportRepository(actor)
    with repository.transaction(write=True) as transaction:
        repository.facts.delete_report(transaction, member, report["report_id"])
    assert owner.get(log_url(member, log["medical_log_id"])).json()["medical_log"] == log
    with connect(app_paths().medical_logs_db(actor)) as db:
        db.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON medical_logs BEGIN SELECT RAISE(ABORT, 'injected delete failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        MedicalLogService().members.delete(actor, member)
    assert owner.get(log_url(member, log["medical_log_id"])).status_code == 200
    assert any(item["member_id"] == member for item in owner.get("/api/members").json()["members"])


def test_revocation_waits_for_inflight_log_write(accounts, monkeypatch):
    from threading import Event
    from backend.app.repositories.medical_log_repository import MedicalLogRepository
    owner, *_ = accounts
    member = create_member(owner)
    log = create_log(owner, member)
    grant(owner, member, "editor", "edit")
    service = MedicalLogService()
    entered, release = Event(), Event()
    original = MedicalLogRepository.update
    def held(self, *args):
        entered.set()
        assert release.wait(5)
        return original(self, *args)
    monkeypatch.setattr(MedicalLogRepository, "update", held)
    actor = account_id("editor")
    owner_id = account_id("owner")
    with ThreadPoolExecutor(2) as pool:
        update = pool.submit(service.update, actor, member, log["medical_log_id"], {"title": "撤权前有效更新"})
        assert entered.wait(5)
        revoke = pool.submit(service.members.revoke, owner_id, member, actor)
        assert not revoke.done()
        release.set()
        assert update.result(timeout=10)["medical_log"]["title"] == "撤权前有效更新"
        revoke.result(timeout=10)
    with pytest.raises(SerenitaError): service.read(actor, member, medical_log_ids=[log["medical_log_id"]])


def test_required_record_date_validation_and_runtime_schema(accounts):
    from backend.app.agent_runtime.runtime import AgentHarnessRuntime
    from backend.app.plugins.medical_log.tools import CreateMedicalLogTool, UpdateMedicalLogTool
    owner, *_ = accounts
    member = create_member(owner)
    payload = {"title": "经过", "content": "用户自述"}
    for date_fields in ({}, {"recorded_on": None}, {"recorded_on": ""}, {"recorded_on": "2026-02-30"}, {"recorded_on": "2026-9-7"}):
        assert owner.post(log_url(member), json={**payload, **date_fields}).status_code == 422
    assert owner.get(log_url(member)).json()["medical_logs"] == []
    record = create_log(owner, member)
    with connect(app_paths().medical_logs_db(account_id("owner"))) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE medical_logs SET recorded_on = NULL WHERE medical_log_id = ?", (record["medical_log_id"],))
    for tool, fields in ((CreateMedicalLogTool, payload), (UpdateMedicalLogTool, {"medical_log_id": "known"})):
        AgentHarnessRuntime._validate_schema({**fields, "recorded_on": "2026-09-07"}, tool.input_schema, label="参数")
        for value in (None, ""):
            with pytest.raises(ValueError):
                AgentHarnessRuntime._validate_schema({**fields, "recorded_on": value}, tool.input_schema, label="参数")
    with pytest.raises(ValueError):
        AgentHarnessRuntime._validate_schema(payload, CreateMedicalLogTool.input_schema, label="参数")


def test_reading_logs_does_not_lock_reports(accounts):
    from backend.app.repositories.medical_log_repository import MedicalLogRepository
    owner, *_ = accounts
    member = create_member(owner)
    report = owner.post(f"/api/members/{member}/reports", json=report_payload()).json()
    record = create_log(owner, member)
    actor = account_id("owner")
    repository = MedicalLogRepository(actor, app_paths())
    with repository.transaction() as reader:
        reader.execute("SELECT * FROM medical_logs").fetchall()
        with connect(app_paths().reports_db(actor)) as writer:
            writer.execute("UPDATE reports SET report_name = '并发更新' WHERE report_id = ?", (report["report_id"],))
        assert repository._detail(reader, member, record["medical_log_id"]) == record


@pytest.mark.parametrize("field", ["report_ids", "reports"])
def test_report_association_fields_are_rejected_by_api_service_and_tools(accounts, field):
    from backend.app.agent_runtime.runtime import AgentHarnessRuntime
    from backend.app.plugins.medical_log.tools import CreateMedicalLogTool, UpdateMedicalLogTool
    owner, *_ = accounts
    member = create_member(owner)
    payload = {"recorded_on": "2026-09-07", "title": "经过", "content": "用户自述", field: []}
    assert owner.post(log_url(member), json=payload).status_code == 422
    with pytest.raises(SerenitaError):
        MedicalLogService().create(account_id("owner"), member, payload)
    record = create_log(owner, member)
    changes = {"title": "不应写入", field: []}
    assert owner.patch(log_url(member, record["medical_log_id"]), json=changes).status_code == 422
    with pytest.raises(SerenitaError):
        MedicalLogService().update(account_id("owner"), member, record["medical_log_id"], changes)
    assert owner.get(log_url(member, record["medical_log_id"])).json()["medical_log"] == record
    for tool, values in ((CreateMedicalLogTool, payload), (UpdateMedicalLogTool, {"medical_log_id": record["medical_log_id"], **changes})):
        with pytest.raises(ValueError):
            AgentHarnessRuntime._validate_schema(values, tool.input_schema, label="参数")


def read_tool(actor, member):
    return next(tool for tool in build_tools(runtime_context=PluginRuntimeContext(
        account_id=actor, member_id=member, event_recorder=lambda _: None,
    )) if tool.name == "read_log")


def tool_page(tool, arguments):
    result = tool.run(arguments)
    return {**result.output, "medical_logs": [log for page in result.logical_pages for log in page["medical_logs"]]}


def test_read_log_queries_complete_content_by_ids_dates_and_keywords(accounts):
    owner, *_ = accounts
    member = create_member(owner)
    actor = account_id("owner")
    content = "就诊经过。" * 300 + "夜间咳嗽，今天好转。"
    target = create_log(owner, member, recorded_on="2026-09-02", content=content)
    later = create_log(owner, member, recorded_on="2026-09-03", title="咳嗽复诊", content="症状缓解")
    create_log(owner, member, recorded_on="2026-08-01", content="夜间咳嗽")
    other_member = create_member(owner)
    create_log(owner, other_member, recorded_on="2026-09-02", content=content)
    tool = read_tool(actor, member)
    page = tool_page(tool, {"after_date": "2026-09-02", "before_date": "2026-09-03", "query": "咳嗽"})
    assert page == {"member_id": member, "medical_logs": [later, target], "total": 2, "pagination": {"page": 1, "complete": True}}
    by_ids = tool_page(tool, {"medical_log_ids": [target["medical_log_id"], later["medical_log_id"]]})
    assert by_ids == page
    assert tool_page(tool, {"medical_log_ids": [target["medical_log_id"], later["medical_log_id"]],
                            "before_date": "2026-09-02", "query": "夜间"})["medical_logs"] == [target]
    assert tool_page(tool, {"query": "未记载关键词"}) == {
        "member_id": member, "medical_logs": [], "total": 0, "pagination": {"page": 1, "complete": True},
    }
    assert tool_page(tool, {})["total"] == 3
    assert tool_page(tool, {"query": "  "})["total"] == 3


def test_read_log_pages_cover_full_content_and_keep_query_scope(accounts):
    from backend.app.agent_runtime.runtime import AgentHarnessRuntime
    owner, *_ = accounts
    actor = account_id("owner")
    member = create_member(owner)
    service = MedicalLogService()
    records = [service.create(actor, member, {
        "recorded_on": "2026-09-01", "title": f"日记 {index}", "content": "完整内容" * 1000,
    })["medical_log"] for index in range(31)]
    tool = read_tool(actor, member)
    filters = {"medical_log_ids": [log["medical_log_id"] for log in records], "query": "完整"}
    result = tool.run(filters)
    filters["query"] = "changed after invocation"
    first = AgentHarnessRuntime._assemble_tool_output(result)
    second_result = result.next_page()
    second = AgentHarnessRuntime._assemble_tool_output(second_result)
    assert first["total"] == second["total"] == 31
    assert len(first["medical_logs"]) == 24 and len(second["medical_logs"]) == 7
    assert first["pagination"] == {"page": 1, "complete": False}
    assert second["pagination"] == {"page": 2, "complete": True}
    assert second_result.next_page is None
    expected = sorted(records, key=lambda log: (log["recorded_on"], log["created_at"], log["medical_log_id"]), reverse=True)
    assert first["medical_logs"] + second["medical_logs"] == expected
    # Permission is rechecked for each actual read, including internal pages.
    grant(owner, member, "reader", "read")
    reader_result = read_tool(account_id("reader"), member).run({})
    service.members.revoke(actor, member, account_id("reader"))
    with pytest.raises(SerenitaError):
        reader_result.next_page()


def test_read_log_rejects_missing_or_foreign_ids_before_pagination(accounts):
    owner, reader, *_ = accounts
    actor = account_id("owner")
    member = create_member(owner)
    grant(owner, member, "reader", "read")
    record = create_log(owner, member)
    foreign = create_log(owner, create_member(owner))
    tool = read_tool(actor, member)
    for invalid_id in (foreign["medical_log_id"], "missing"):
        with pytest.raises(SerenitaError) as error:
            tool.run({"medical_log_ids": [record["medical_log_id"], invalid_id], "query": "无匹配"})
        assert error.value.kind == "missing"
    assert tool_page(read_tool(account_id("reader"), member), {})["medical_logs"] == [record]
    MedicalLogService().members.revoke(actor, member, account_id("reader"))
    with pytest.raises(SerenitaError):
        read_tool(account_id("reader"), member).run({})


@pytest.mark.parametrize("arguments", [
    {"medical_log_ids": None}, {"medical_log_ids": []}, {"medical_log_ids": ["x", "x"]},
    {"medical_log_ids": [" "]}, {"medical_log_ids": [str(i) for i in range(101)]},
    {"medical_log_ids": "x"}, {"medical_log_ids": [1]}, {"after_date": None},
    {"after_date": "2026-02-30"}, {"before_date": "2026-9-1"}, {"before_date": None},
    {"after_date": "2026-09-02", "before_date": "2026-09-01"},
    {"query": None}, {"unknown": "x"},
])
def test_read_log_validates_query_arguments(accounts, arguments):
    owner, *_ = accounts
    member = create_member(owner)
    with pytest.raises(SerenitaError) as error:
        read_tool(account_id("owner"), member).run(arguments)
    assert error.value.kind == "invalid_input"


@pytest.mark.parametrize("arguments", [{"cursor": "next"}, {"limit": 24}, {"offset": 0}])
def test_read_log_model_cannot_control_storage_pages(arguments):
    from backend.app.agent_runtime.tools.parameters import validate_parameters
    from backend.app.plugins.medical_log.tools.query_tools import ReadMedicalLogTool
    with pytest.raises(ValueError):
        validate_parameters(arguments, ReadMedicalLogTool.input_schema, label="read_log")

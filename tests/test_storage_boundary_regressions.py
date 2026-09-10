"""Storage and plugin boundary regressions with isolated synthetic data."""

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.app.application.account_settings_service import AccountSettingsService
from backend.app.application.body_metric_import import parse_file
from backend.app.application.body_metric_service import BodyMetricService
from backend.app.application.report_file_cleanup import drain_report_file_cleanup
from backend.app.application.report_service import ReportService
from backend.app.application.report_source_store import ReportSourceStore
from backend.app.application.report_validation import validate_final_parsed_report
from backend.app.core.errors import SerenitaError
from backend.app.core.report_errors import LabDictionaryNameConflictError
from backend.app.repositories.body_metric_repository import BodyMetricRepository
from backend.app.repositories.medication_source_repository import MedicationSourceRepository
from backend.app.repositories.report_repository import ReportRepository
from backend.app.storage.paths import AppPaths
from backend.app.storage.sqlite import connect, UnsupportedSchemaError


@pytest.fixture
def report_repo(tmp_path):
    return ReportRepository(str(uuid4()), AppPaths(tmp_path))


def lab_report(category, items):
    return validate_final_parsed_report({
        "report_type": "检验报告", "report_name": category,
        "report_time": "2026-09-01T09:00:00+08:00", "source_kind": "unknown",
        "lab_test_results": [dict(item_id=identity, item_name_zh=name,
            category_name=category, result_text="10 U/L", reference_text="0-20 U/L",
            flag_text="正常") for identity, name in items],
    })


def other_report(name="测试医疗报告"):
    return {"report_type": "其它医疗报告", "report_name": name,
        "report_time": "2026-09-01T09:00:00+08:00",
        "other_report": {"report_body": "合成正文"}}


def revision(repo):
    return repo.lab_dictionary()["dictionary_revision"]


def settings(repo):
    return AccountSettingsService(repository=repo, paths=repo.paths)


def category(repo, name):
    return settings(repo).create_lab_category(repo.account_id, category_name=name,
        description=None, expected_dictionary_revision=revision(repo))


def item(repo, name, primary):
    result = settings(repo).create_lab_item(repo.account_id, item_name_zh=name,
        aliases=[], description=None, primary_category_name=primary,
        related_category_names=[], expected_dictionary_revision=revision(repo))
    return result["effects"]["created_item_id"]


def test_report_cleanup_cannot_delete_a_recreated_source(report_repo, monkeypatch):
    repo = report_repo
    store = ReportSourceStore(repo)
    text = "合成原件"
    parsed_source = dict(source_type="conversation_text", session_id="session",
        message_id="message", source_text=text, sha256=hashlib.sha256(text.encode()).hexdigest())
    source, _ = store.ensure_parsed_source("member", parsed_source, session_id="session")
    path = store.source_path("member", source)
    repo.delete_source_if_unlinked("member", source["resource_id"])
    stale_job = repo.file_cleanup_jobs()[0]
    original_unlink = Path.unlink

    def fail_once(value, *args, **kwargs):
        if value == path:
            raise OSError("simulated interruption")
        return original_unlink(value, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_once)
        drain_report_file_cleanup(repo)
    assert repo.file_cleanup_jobs()[0]["attempt_count"] == 1
    recreated, created = store.ensure_parsed_source("member", parsed_source, session_id="session")
    assert created and recreated["resource_id"] == source["resource_id"]
    repo.create_report_from_parsed("member", other_report(), resource_ids=[source["resource_id"]])
    repo.clean_source_file(stale_job)  # A cleaner may already have read this job.
    drain_report_file_cleanup(repo)
    assert path.read_text() == text
    assert repo.file_cleanup_jobs() == []


def test_duplicate_check_survives_another_committed_upload(report_repo, monkeypatch):
    repo = report_repo
    report_id = repo.create_manual_report("member", other_report())["report_id"]
    service = ReportService.__new__(ReportService)
    service.repository, service.sources = repo, ReportSourceStore(repo)
    service.get_report = lambda member, report: repo.get_report_detail(member, report)
    upload = [{"original_filename": "same.pdf", "mime_type": "application/pdf", "content": b"%PDF-synthetic"}]
    attach = ReportService.add_report_sources.__wrapped__
    read_digests = repo.source_digests_for_report
    interleaved = False

    def read_then_commit(member, report):
        nonlocal interleaved
        digests = read_digests(member, report)
        if not interleaved:
            interleaved = True
            attach(service, member, report, uploads=upload)
        return digests

    monkeypatch.setattr(repo, "source_digests_for_report", read_then_commit)
    with pytest.raises(SerenitaError) as error:
        attach(service, "member", report_id, uploads=upload)
    assert error.value.code == "REPORT_SOURCE_DUPLICATE"
    assert len(repo.get_report_detail("member", report_id)["sources"]) == 1
    assert len(list(repo.paths.report_attachments_dir(repo.account_id).iterdir())) == 1


def test_catalog_merge_preserves_all_originals(report_repo):
    repo = report_repo
    category(repo, "血常规"); category(repo, "肝功能")
    source = item(repo, "来源指标", "血常规")
    target = item(repo, "目标指标", "肝功能")
    for resource in ("shared", "source-only"):
        repo.persist_source_file("member", resource_id=resource, extension="txt",
            mime_type="text/plain", content=resource.encode(), source_kind="unknown")
    source_report = repo.create_report_from_parsed("member", lab_report("血常规", [(source, "来源指标")]),
        resource_ids=["shared", "source-only"])["report_id"]
    target_report = repo.create_report_from_parsed("member", lab_report("肝功能", [(target, "目标指标")]),
        resource_ids=["shared"])["report_id"]
    result = settings(repo).merge_lab_items(repo.account_id, source, target_item_id=target,
        expected_dictionary_revision=revision(repo))
    assert result["effects"]["deduplicated_result_count"] == 1
    assert not repo.report_exists("member", source_report)
    detail = repo.get_report_detail("member", target_report)
    assert {value["resource_id"] for value in detail["sources"]} == {"shared", "source-only"}
    assert sum(source["is_primary"] for source in detail["sources"]) == 1
    assert repo.paths.report_attachment_path(repo.account_id, "source-only", "txt").exists()


def test_catalog_merge_validates_final_aliases_and_rolls_back(report_repo):
    repo = report_repo
    category(repo, "血常规"); category(repo, "肝功能")
    source = item(repo, "同名指标", "血常规")
    target = item(repo, "目标指标", "肝功能")
    item(repo, "同名指标", "肝功能")
    before = revision(repo)
    with pytest.raises(LabDictionaryNameConflictError):
        settings(repo).merge_lab_items(repo.account_id, source, target_item_id=target,
            expected_dictionary_revision=before)
    assert revision(repo) == before


def test_manual_report_can_split_without_sources(report_repo):
    repo = report_repo
    category(repo, "血常规"); category(repo, "肝功能")
    source = item(repo, "指标甲", "血常规")
    other = item(repo, "指标乙", "血常规")
    report_id = repo.create_manual_report("member", lab_report("血常规", [(source, "指标甲"), (other, "指标乙")]))["report_id"]
    repo.save_report_analysis("member", report_id, "已有解读")
    settings(repo).update_lab_item(repo.account_id, source, item_name_zh="指标甲",
        aliases=[], description=None, primary_category_name="肝功能", related_category_names=[],
        expected_dictionary_revision=revision(repo))
    reports = repo.report_evidence("member")
    assert len(reports) == 2
    assert {r["report_name"] for r in reports} == {"血常规", "肝功能"}
    assert all(r["sources"] == [] for r in reports)
    assert repo.get_report_detail("member", report_id)["analysis_outdated"]


def measurement():
    return dict(kind="measurement", metric="weight", starts_at="2026-09-01T08:00:00+08:00",
        data={"value": 70, "unit": "kg"})


def test_body_import_non_objects_are_row_errors():
    payload = {"format": "serenita-body-metrics", "records": [measurement(), [], "bad", None, 42]}
    result = parse_file("synthetic.json", json.dumps(payload).encode())
    assert result["valid_count"] == 1
    assert result["unsupported"]["invalid"] == 4
    assert [value["row"] for value in result["issues"]] == [2, 3, 4, 5]


def test_body_tool_partial_data_matches_domain_contract(tmp_path):
    from backend.app.agent_runtime.tools.parameters import validate_parameters
    from backend.app.domain.body_records import updated_record
    from backend.app.plugins.body_metric.registry import build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    from backend.app.schemas.body_metric import BodyRecord

    context = PluginRuntimeContext(account_id="owner", member_id="member", event_recorder=lambda event: None,
        services={"body_metric": object()})
    tools = {value.name: value for value in build_tools(runtime_context=context)}
    schema = tools["update_body_record"].input_schema
    change = {"record_id": "record", "changes": {"data": {"value": 71}}}
    validate_parameters(change, schema, label="arguments")
    updated, _ = updated_record(BodyRecord.model_validate(measurement()).model_dump(), change["changes"])
    assert updated["data"]["value"] == 71 and updated["data"]["unit"] == "kg"
    with pytest.raises(ValueError):
        validate_parameters({"record_id": "record", "changes": {"data": {"unknown": 1}}}, schema, label="arguments")
    with pytest.raises(ValueError):
        validate_parameters({"record_id": "record", "changes": {"data": {"foods": [{"name": "缺少完整明细"}]}}}, schema, label="arguments")


def test_body_preview_parses_outside_guard_and_reauthorizes(tmp_path, monkeypatch):
    class Members:
        paths = AppPaths(tmp_path)
        active = 0
        allowed = True
        @contextmanager
        def access_guard(self, actor, member, *, write=False):
            if not self.allowed:
                raise PermissionError("revoked")
            self.active += 1
            try:
                yield SimpleNamespace(account_id=str(uuid4()))
            finally:
                self.active -= 1
    members = Members()
    def parsing(filename, content):
        assert members.active == 0
        members.allowed = False
        return {"records": []}
    monkeypatch.setattr("backend.app.application.body_metric_service.parse_file", parsing)
    with pytest.raises(PermissionError, match="revoked"):
        BodyMetricService(members).preview("actor", "member", "file.json", b"content")
    assert not list(tmp_path.rglob("body_metrics.db"))


def test_body_import_list_uses_one_summary_query_per_page(tmp_path, monkeypatch):
    repo = BodyMetricRepository(str(uuid4()), AppPaths(tmp_path))
    parsed = parse_file("data.json", json.dumps({"format": "serenita-body-metrics", "records": [measurement()] * 1000}).encode())
    for index in range(3):
        repo.preview("member", f"{index}.json", str(index), parsed, "actor", str(index), "Asia/Shanghai")
    statements = []
    original_transaction = repo.transaction
    @contextmanager
    def traced(write=False):
        with original_transaction(write) as db:
            db.set_trace_callback(statements.append)
            yield db
    monkeypatch.setattr(repo, "transaction", traced)
    original_loads = json.loads
    def summary_only(value, *args, **kwargs):
        decoded = original_loads(value, *args, **kwargs)
        assert not isinstance(decoded, dict) or "records" not in decoded
        return decoded
    monkeypatch.setattr("backend.app.repositories.body_metric_repository.json.loads", summary_only)
    first = repo.imports("member", limit=2)
    second = repo.imports("member", cursor=first["next_cursor"], limit=2)
    assert len(first["items"]) == 2 and first["has_more"]
    assert len(second["items"]) == 1 and not second["has_more"]
    assert len({value["import_id"] for value in first["items"] + second["items"]}) == 3
    assert sum(query.lstrip().upper().startswith("SELECT") for query in statements) == 2


def test_medication_cleanup_advances_past_a_failed_batch(tmp_path, monkeypatch):
    from backend.app.storage.medication_database import MEDICATION_DATABASE_SCHEMA
    from backend.app.storage.database_lifecycle import ensure_database
    paths, owner = AppPaths(tmp_path), str(uuid4())
    path = paths.medications_db(owner)
    ensure_database(MEDICATION_DATABASE_SCHEMA, path)
    with connect(path) as db:
        db.executemany("INSERT INTO medication_source_cleanup_outbox VALUES (?,?,?)",
            [(f"{index:03}", f"{index:03}.txt", "2026-09-01") for index in range(101)])
    attempts = []
    original = Path.unlink
    def remove(value, *args, **kwargs):
        if value.parent == paths.medication_files_dir(owner):
            attempts.append(value.name)
            if value.name != "100.txt":
                raise OSError("unavailable")
        return original(value, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", remove)
    repo = MedicationSourceRepository(owner, paths)
    repo.drain_files(); repo.drain_files()
    assert "100.txt" in attempts
    with connect(path) as db:
        assert db.execute("SELECT count(*) FROM medication_source_cleanup_outbox").fetchone()[0] == 100


@pytest.mark.parametrize("replacement", [False, True])
def test_schema_cache_ignores_data_writes_but_detects_schema_changes(report_repo, monkeypatch, replacement):
    from backend.app.storage.schema import Database
    repo = report_repo
    calls = []
    original = Database.validate_existing
    def validate(schema, path):
        calls.append(str(path))
        return original(schema, path)
    monkeypatch.setattr(Database, "validate_existing", validate)
    repo.init_db()
    validated = len(calls)
    report_id = repo.create_manual_report("member", other_report())["report_id"]
    repo.get_report_detail("member", report_id)
    assert len(calls) == validated
    path = repo.paths.reports_db(repo.account_id)
    if replacement:
        other = path.with_name("replacement.db")
        with connect(other) as db:
            db.execute("CREATE TABLE unexpected (value TEXT)")
        other.replace(path)
    else:
        with connect(path) as db:
            db.execute("ALTER TABLE reports ADD COLUMN unexpected TEXT")
    with pytest.raises(UnsupportedSchemaError):
        repo.init_db()


def test_schema_cache_detects_uncheckpointed_wal_ddl(report_repo):
    repo = report_repo
    repo.init_db()
    path = repo.paths.reports_db(repo.account_id)
    with connect(path) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        writer.execute("PRAGMA wal_autocheckpoint=0")
        repo.init_db()
        header = path.read_bytes()[:44]
        writer.execute("ALTER TABLE reports ADD COLUMN unexpected TEXT")
        writer.commit()
        assert path.read_bytes()[:44] == header
        with pytest.raises(UnsupportedSchemaError):
            repo.init_db()


def test_registered_report_catalog_uses_real_service_pagination(monkeypatch):
    from backend.app.agent_runtime.runtime import AgentHarnessRuntime
    from member_support import account_id, member_access
    from backend.app.plugins.medical_report.registry import build_tools
    from backend.app.plugins.runtime_context import PluginRuntimeContext
    account, access = account_id("catalog-reader"), member_access("catalog-reader")
    service = ReportService(access)
    for index in range(3):
        service.create_manual_report(access.member_id, report=other_report(f"医疗报告{index}"))
    context = PluginRuntimeContext(account_id=account, member_id=access.member_id,
        event_recorder=lambda event: None, services={"medical_report": service})
    tool = next(value for value in build_tools(runtime_context=context) if value.name == "read_report_catalog")
    monkeypatch.setattr("backend.app.plugins.medical_report.tools.query_tools.REPORT_CATALOG_LOGICAL_PAGE_SIZE", 2)
    result = tool.run({})
    first = AgentHarnessRuntime._assemble_tool_output(result)
    assert result.next_page is not None
    following = result.next_page()
    second = AgentHarnessRuntime._assemble_tool_output(following)
    assert len(first["reports"]) == 2 and len(second["reports"]) == 1
    assert first["total"] == second["total"] == 3
    assert set(first["report_ids"]).isdisjoint(second["report_ids"])
    assert first["pagination"]["complete"] is False
    assert second["pagination"]["complete"] is True and following.next_page is None


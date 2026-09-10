from tests.member_support import create_stored_report
import pytest
from member_support import account_id as account_id_for, member_access, member_id
from pathlib import Path
from backend.app.application.report_service import ReportService
from backend.app.plugins.medical_report.tools.mutation_tools import DeleteReportTool
from backend.app.repositories.report_repository import ReportRepository
from backend.app.storage.paths import AppPaths


@pytest.fixture(autouse=True)
def isolated_members(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))


def _service(tmp_path) -> tuple[ReportService, ReportRepository, AppPaths]:
    paths = AppPaths(tmp_path)
    repository = ReportRepository(account_id_for("alice"), paths)
    return ReportService(member_access("alice"), repository=repository, paths=paths), repository, paths


def _source(
    repository: ReportRepository,
    paths: AppPaths,
    account: str,
    resource_id: str,
) -> Path:
    immutable_id = account_id_for(account)
    path = paths.report_attachment_path(immutable_id, resource_id, "jpg")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xd8\xffprivate-report")
    repository.register_source_file(
        member_id(account),
        resource_id=resource_id,
        relative_path=str(path.relative_to(paths.account_root(immutable_id))),
        mime_type="image/jpeg",
        size_bytes=path.stat().st_size,
        sha256=f"sha-{account}-{resource_id}",
        source_kind="photo",
    )
    return path


def _report(
    repository: ReportRepository,
    account: str,
    resource_id: str,
    *,
    minute: int = 0,
) -> str:
    candidate = {
        "report_type": "其它医疗报告",
        "report_name": "清理测试医疗报告",
        "report_time": f"2026-08-08T08:{minute:02d}:00+08:00",
        "other_report": {"report_body": "仅用于源文件清理测试"},
    }
    return create_stored_report(repository, 
        member_id(account),
        candidate,
        resource_id=resource_id,
    )


def _fail_first_unlink(monkeypatch, target: Path) -> None:
    original_unlink = Path.unlink
    failed = False

    def flaky_unlink(path: Path, missing_ok: bool = False):
        nonlocal failed
        if path.resolve() == target.resolve() and not failed:
            failed = True
            raise OSError("simulated cleanup interruption")
        return original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)


def _delete_report(
    service: ReportService, account: str, report_id: str
) -> dict:
    return service.delete_report(member_id(account), report_id)


def test_report_page_delete_does_not_require_a_conversation(tmp_path):
    service, repository, paths = _service(tmp_path)
    source_path = _source(repository, paths, "alice", "FILE-direct-delete")
    report_id = _report(repository, "alice", "FILE-direct-delete")
    response = service.delete_report(member_id("alice"), report_id)

    assert response == {"report_id": report_id, "deleted": True}
    assert repository.get_report(member_id("alice"), report_id) is None
    assert not source_path.exists()


def test_delete_report_retries_sensitive_file_cleanup_on_next_entry(
    tmp_path, monkeypatch
):
    service, repository, paths = _service(tmp_path)
    source_path = _source(repository, paths, "alice", "FILE-delete")
    report_id = _report(repository, "alice", "FILE-delete")
    _fail_first_unlink(monkeypatch, source_path)

    response = _delete_report(service, "alice", report_id)

    assert response["deleted"] is True
    assert repository.get_report(member_id("alice"), report_id) is None
    assert repository.source_file(member_id("alice"), "FILE-delete") is None
    assert source_path.exists()
    jobs = repository.file_cleanup_jobs(member_id("alice"))
    assert len(jobs) == 1
    assert jobs[0]["attempt_count"] == 1

    service.list_reports(member_id("alice"))

    assert not source_path.exists()
    assert repository.file_cleanup_jobs(member_id("alice")) == []


def test_agent_delete_tool_uses_the_same_durable_cleanup_path(
    tmp_path, monkeypatch
):
    service, repository, paths = _service(tmp_path)
    source_path = _source(repository, paths, "alice", "FILE-pending-delete")
    report_id = _report(repository, "alice", "FILE-pending-delete")
    _fail_first_unlink(monkeypatch, source_path)

    response = DeleteReportTool(account_id=account_id_for("alice"), member_id=member_id("alice"), service=service).run(
        {"report_id": report_id}
    ).output

    assert response["deleted"] is True
    assert response["report_id"] == report_id
    assert repository.get_report(member_id("alice"), report_id) is None
    assert source_path.exists()
    assert len(repository.file_cleanup_jobs(member_id("alice"))) == 1

    service.list_reports(member_id("alice"))
    assert not source_path.exists()
    assert repository.file_cleanup_jobs(member_id("alice")) == []


def test_delete_source_if_unlinked_queues_cleanup_but_preserves_linked_source(
    tmp_path,
):
    service, repository, paths = _service(tmp_path)
    source_path = _source(repository, paths, "alice", "FILE-shared")
    first_report = _report(repository, "alice", "FILE-shared", minute=1)
    second_report = _report(repository, "alice", "FILE-shared", minute=2)

    _delete_report(service, "alice", first_report)

    assert repository.get_report(member_id("alice"), second_report) is not None
    assert repository.source_file(member_id("alice"), "FILE-shared") is not None
    assert repository.file_cleanup_jobs(member_id("alice")) == []
    assert source_path.exists()
    assert repository.delete_source_if_unlinked(member_id("alice"), "FILE-shared") is None

    _delete_report(service, "alice", second_report)
    assert repository.source_file(member_id("alice"), "FILE-shared") is None
    assert not source_path.exists()


def test_cleanup_drain_cannot_process_another_accounts_outbox(
    tmp_path, monkeypatch
):
    service, repository, paths = _service(tmp_path)
    source_path = _source(repository, paths, "alice", "FILE-private")
    report_id = _report(repository, "alice", "FILE-private")
    _fail_first_unlink(monkeypatch, source_path)
    _delete_report(service, "alice", report_id)
    assert len(repository.file_cleanup_jobs(member_id("alice"))) == 1

    ReportService(member_access("bob")).list_reports(member_id("bob"))

    assert source_path.exists()
    assert len(repository.file_cleanup_jobs(member_id("alice"))) == 1
    assert ReportRepository(account_id_for("bob"), paths).file_cleanup_jobs(member_id("bob")) == []

    service.list_reports(member_id("alice"))
    assert not source_path.exists()


def test_cleanup_outbox_rejects_paths_outside_account_uploads(tmp_path):
    service, repository, paths = _service(tmp_path)
    outside = tmp_path / "must-not-delete.jpg"
    outside.write_bytes(b"private")
    repository.register_source_file(
        member_id("alice"),
        resource_id="FILE-unsafe",
        relative_path="../../must-not-delete.jpg",
        mime_type="image/jpeg",
        size_bytes=outside.stat().st_size,
        sha256="sha-unsafe",
        source_kind="unknown",
    )

    assert repository.delete_source_if_unlinked(member_id("alice"), "FILE-unsafe") is not None
    service.list_reports(member_id("alice"))

    assert outside.exists()
    assert repository.file_cleanup_jobs(member_id("alice")) == []

from __future__ import annotations

from backend.app.repositories.report_repository import ReportRepository


def drain_report_file_cleanup(repository: ReportRepository, *, member_id: str | None = None, limit: int = 8) -> None:
    """Retry committed file removals within the owner's report attachments directory.

    Jobs survive member deletion. Authorization to schedule them is checked by
    the original mutation; draining cannot depend on that member still existing.
    """
    try:
        jobs = repository.file_cleanup_jobs(member_id, limit=limit)
    except Exception:
        return
    for job in jobs:
        try:
            account_root = repository.paths.account_root(repository.account_id).resolve()
            attachments_root = repository.paths.report_attachments_dir(
                repository.account_id
            ).resolve()
            path = (account_root / job["relative_path"]).resolve()
            if not path.is_relative_to(attachments_root):
                raise ValueError("不安全的报告源文件路径")
            path.unlink(missing_ok=True)
        except (OSError, ValueError):
            try:
                repository.record_file_cleanup_attempt(job["member_id"], job["cleanup_id"])
            except Exception:
                pass
            continue
        try:
            repository.complete_file_cleanup(job["member_id"], job["cleanup_id"])
        except Exception:
            # The durable job permits an idempotent retry after interruption.
            continue

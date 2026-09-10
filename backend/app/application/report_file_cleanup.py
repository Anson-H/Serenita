from __future__ import annotations

from backend.app.repositories.report_repository import ReportRepository
from backend.app.storage.cleanup_queue import drain_cleanup_batch


def drain_report_file_cleanup(repository: ReportRepository, *, member_id: str | None = None, limit: int = 8) -> None:
    """Retry committed file removals within the owner's report attachments directory.

    Jobs survive member deletion. Authorization to schedule them is checked by
    the original mutation; draining cannot depend on that member still existing.
    """
    try:
        jobs = repository.file_cleanup_jobs(member_id, limit=limit)
    except Exception:
        return
    drain_cleanup_batch(jobs, repository.clean_source_file,
        lambda job: repository.record_file_cleanup_attempt(job["member_id"], job["cleanup_id"]))

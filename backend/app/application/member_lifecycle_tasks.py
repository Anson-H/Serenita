"""Run every committed member task independently, preserving failed tasks."""
import logging

from backend.app.core.member_lifecycle import member_lifecycle_guard
from backend.app.application.report_file_cleanup import drain_report_file_cleanup
from backend.app.repositories.member_lifecycle_repository import MemberLifecycleRepository
from backend.app.repositories.report_repository import ReportRepository


class MemberLifecycleTasks:
    def __init__(self, paths, conversations):
        self.paths = paths
        self.repository = MemberLifecycleRepository(paths)
        self.conversations = conversations

    def drain(self):
        if not self.repository.path.exists():
            return
        # The same lock orders deletion, revocation and session scheduling across processes.
        with member_lifecycle_guard(exclusive=True, paths=self.paths):
            for task in self.repository.pending():
                try:
                    self.execute(task)
                    self.repository.finish(task)
                except Exception as exc:
                    logging.getLogger(__name__).exception("Member post-commit task failed")
                    try:
                        self.repository.retry(task, exc)
                    except Exception:
                        logging.getLogger(__name__).exception("Failed to schedule member task retry")

    def execute(self, task):
        if task["operation"] == "interrupt_session":
            service = self.conversations()
            if service.repository.session_row(task["actor_account_id"], task["session_id"]) is not None:
                service.interrupt_member_session(task["actor_account_id"], task["session_id"], before=task["created_at"])
        else:
            repository = ReportRepository(task["owner_account_id"], self.paths)
            if repository.validate_existing_database():
                drain_report_file_cleanup(repository, member_id=task["member_id"], limit=50)
                if repository.file_cleanup_count(task["member_id"]):
                    raise OSError("成员文件清理尚未完成。")

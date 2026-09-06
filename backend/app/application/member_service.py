from __future__ import annotations

from typing import Any, Callable
from backend.app.core.member_lifecycle import member_lifecycle_change
from backend.app.application.conversation_service import ConversationService
from backend.app.application.report_file_cleanup import drain_report_file_cleanup

from backend.app.application.auth_service import normalize_account
from backend.app.repositories.member_repository import MemberRepository
from backend.app.repositories.report_repository import ReportRepository


class MemberService:
    def __init__(self, repository: MemberRepository | None = None, *, after_delete: tuple[Callable[[str, str], None], ...] = (), conversations=None):
        self.after_delete = after_delete
        self.repository = repository or MemberRepository()
        self.paths = self.repository.paths
        self.conversations = conversations

    def access_revision(self, account_id: str) -> int:
        return self.repository.revision(account_id, self.repository.paths)

    def member_exists(self, member_id: str) -> bool:
        return self.repository.member_exists(member_id)

    def list_members(self, actor_account_id: str) -> dict[str, Any]:
        return self.repository.list_accessible(actor_account_id)

    def get_member(self, actor_account_id: str, member_id: str) -> dict[str, Any]:
        with self.repository.access_guard(actor_account_id, member_id) as access:
            default_member_id = self.repository.default_member_id(
                actor_account_id,
                self.repository.paths,
            )
            return self.repository.detail(
                access,
                self.repository.paths,
                is_default=default_member_id == member_id,
            )

    def create_member(self, actor_account_id: str, values: dict[str, Any], *, set_as_default: bool = False) -> dict[str, Any]:
        member_id = self.repository.create(actor_account_id, values, set_as_default=set_as_default)
        return self.get_member(actor_account_id, member_id)

    def update_member(self, actor_account_id: str, member_id: str, values: dict[str, Any], *, set_as_default: bool = False) -> dict[str, Any]:
        access = self.repository.resolve(actor_account_id, member_id, write=True)
        if values or set_as_default:
            self.repository.update(access, values, set_as_default=set_as_default)
        return self.get_member(actor_account_id, member_id)

    @member_lifecycle_change
    def delete_member(self, actor_account_id: str, member_id: str) -> dict[str, Any]:
        account_id, sessions = self.repository.delete(actor_account_id, member_id)
        self._interrupt_sessions(sessions)
        for callback in self.after_delete:
            callback(account_id, member_id)
        repository = ReportRepository(account_id, self.repository.paths)
        drain_report_file_cleanup(repository, member_id=member_id, limit=50)
        pending_file_cleanup = (
            repository.file_cleanup_count(member_id)
            if repository.validate_existing_database()
            else 0
        )
        return {"member_id": member_id, "deleted": True,
                "pending_file_cleanup": pending_file_cleanup,
                "collection": self.repository.list_accessible(actor_account_id)}

    def preferences(self, actor_account_id: str, **values: Any) -> dict[str, Any]:
        self.repository.save_preferences(actor_account_id, **values)
        return self.list_members(actor_account_id)

    def grants(self, actor_account_id: str) -> dict[str, Any]:
        return {"grants": self.repository.grants(actor_account_id)}

    def set_grants(self, actor_account_id: str, grantee_account: str, grants: list[dict[str, str]]) -> dict[str, Any]:
        self.repository.set_grants(
            actor_account_id,
            normalize_account(grantee_account),
            grants,
        )
        return self.grants(actor_account_id)

    @member_lifecycle_change
    def revoke(self, actor_account_id: str, member_id: str, account_id: str) -> dict[str, Any]:
        sessions = self.repository.revoke(actor_account_id, member_id, account_id)
        self._interrupt_sessions(sessions)
        return self.grants(actor_account_id)

    def _interrupt_sessions(self, sessions: list[tuple[str, str]]) -> None:
        service = self.conversations or ConversationService(paths=self.paths, members=self.repository)
        for account_id, session_id in sessions:
            service.interrupt_member_session(account_id, session_id)

from __future__ import annotations

from typing import Any
from backend.app.core.member_lifecycle import member_lifecycle_change
from backend.app.application.conversations.service import ConversationService
from backend.app.application.member_lifecycle_tasks import MemberLifecycleTasks

from backend.app.application.auth_service import normalize_account
from backend.app.repositories.member_repository import MemberRepository
from backend.app.repositories.report_repository import ReportRepository


class MemberService:
    def __init__(self, repository: MemberRepository | None = None, *, conversations=None, notifications=None):
        self.repository = repository or MemberRepository()
        self.paths = self.repository.paths
        self.conversations = conversations
        from backend.app.application.notification_service import NotificationService
        self.notifications = notifications or NotificationService(self.repository)
        self.lifecycle_tasks = MemberLifecycleTasks(self.paths, self._conversations)

    def _conversations(self):
        return self.conversations or ConversationService(paths=self.paths, members=self.repository)

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
            self.notifications.resources_changed(member_id=member_id)
        return self.get_member(actor_account_id, member_id)

    @member_lifecycle_change
    def delete_member(self, actor_account_id: str, member_id: str) -> dict[str, Any]:
        affected_accounts = self.notifications.repository.member_accounts(member_id)
        account_id, sessions = self.repository.delete(actor_account_id, member_id)
        self.notifications.resources_changed(member_id=member_id, account_ids=affected_accounts)
        self.lifecycle_tasks.drain()
        repository = ReportRepository(account_id, self.repository.paths)
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
        for member_id in {grant["member_id"] for grant in grants}:
            self.notifications.resources_changed(member_id=member_id)
        return self.grants(actor_account_id)

    @member_lifecycle_change
    def revoke(self, actor_account_id: str, member_id: str, account_id: str) -> dict[str, Any]:
        sessions = self.repository.revoke(actor_account_id, member_id, account_id)
        self.notifications.resources_changed(member_id=member_id, account_ids=(actor_account_id, account_id))
        self.lifecycle_tasks.drain()
        return self.grants(actor_account_id)

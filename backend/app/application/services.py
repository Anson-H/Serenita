"""Application composition rooted in one explicitly selected data directory."""

from functools import cached_property
from backend.app.storage.paths import AppPaths, app_paths


class ApplicationServices:
    def __init__(self, paths: AppPaths | None = None, *, members=None):
        self.paths = paths or app_paths()
        if members is not None:
            self.members = members

    @cached_property
    def members(self):
        from backend.app.repositories.member_repository import MemberRepository

        return MemberRepository(paths=self.paths)

    @cached_property
    def auth(self):
        from backend.app.application.auth_service import AuthService

        return AuthService(paths=self.paths)

    @cached_property
    def models(self):
        from backend.app.application.model_provider_service import ModelProviderService

        return ModelProviderService(paths=self.paths)

    @cached_property
    def model_settings(self):
        from backend.app.application.model_settings_service import ModelSettingsService

        return ModelSettingsService(paths=self.paths)

    @cached_property
    def account_settings(self):
        from backend.app.application.account_settings_service import (
            AccountSettingsService,
        )

        return AccountSettingsService(paths=self.paths)

    @cached_property
    def conversations(self):
        from backend.app.application.conversation_service import ConversationService

        return ConversationService(
            paths=self.paths,
            members=self.members,
            model_catalog=self.models,
            services=self,
        )

    @cached_property
    def member_service(self):
        from backend.app.application.member_service import MemberService

        return MemberService(self.members, conversations=self.conversations)

    @cached_property
    def favorites(self):
        from backend.app.application.favorite_service import FavoriteService

        return FavoriteService(
            paths=self.paths,
            member_repository=self.members,
            conversation_service=self.conversations,
        )

    @cached_property
    def web(self):
        from backend.app.plugins.web.service import WebAccessService
        from backend.app.repositories.web_access_repository import WebAccessRepository

        return WebAccessService(repository=WebAccessRepository(paths=self.paths))

    def report(self, account_id: str, member_id: str):
        from backend.app.application.report_service import ReportService

        return ReportService.for_member(account_id, member_id, members=self.members)

    def plugin_service(self, account_id: str, member_id: str | None, plugin_id: str):
        if plugin_id == "web":
            return self.web
        if plugin_id == "members":
            return self.member_service
        if plugin_id == "report" and member_id:
            return self.report(account_id, member_id)
        if plugin_id.startswith("report:"):
            return self.report(account_id, plugin_id.partition(":")[2])
        raise KeyError(plugin_id)

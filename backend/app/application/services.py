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
        from backend.app.repositories.members.repository import MemberRepository

        return MemberRepository(paths=self.paths)

    @cached_property
    def auth(self):
        from backend.app.application.accounts.auth_service import AuthService

        return AuthService(paths=self.paths)

    @cached_property
    def deployment(self):
        from backend.app.core.model_service_config import ModelServiceConfig

        return ModelServiceConfig.from_environment()

    @cached_property
    def local_workspace(self):
        from backend.app.application.accounts.local_workspace_service import (
            LocalWorkspaceService,
        )

        return LocalWorkspaceService(self.auth)

    @cached_property
    def models(self):
        from backend.app.application.models.provider_service import ModelProviderService

        return ModelProviderService(
            paths=self.paths,
            official_service=self.model_service if self.deployment.official else None,
        )

    @cached_property
    def model_service(self):
        from server.backend.models.service import ModelService

        return ModelService(paths=self.paths)

    @cached_property
    def model_settings(self):
        from backend.app.application.models.settings_service import ModelSettingsService

        return ModelSettingsService(
            paths=self.paths,
            official_service=self.model_service if self.deployment.official else None,
        )

    @cached_property
    def model_connections(self):
        from backend.app.application.models.connection_service import (
            ModelConnectionService,
        )

        return ModelConnectionService(
            paths=self.paths,
            official_service=self.model_service if self.deployment.official else None,
        )

    @cached_property
    def account_settings(self):
        from backend.app.application.accounts.settings_service import (
            AccountSettingsService,
        )

        return AccountSettingsService(paths=self.paths)

    @cached_property
    def lab_catalog(self):
        from backend.app.application.lab_catalog_service import LabCatalogService

        return LabCatalogService(paths=self.paths)

    @cached_property
    def conversations(self):
        from backend.app.application.conversations.service import ConversationService

        return ConversationService(
            paths=self.paths,
            members=self.members,
            model_catalog=self.models,
            plugin_service=self.plugin_service,
            notifications=self.notifications,
        )

    @cached_property
    def member_service(self):
        from backend.app.application.accounts.member_service import MemberService

        return MemberService(
            self.members,
            conversations=self.conversations,
            notifications=self.notifications,
        )

    @cached_property
    def medical_history(self):
        from backend.app.application.medical_history_service import (
            MedicalHistoryService,
        )

        return MedicalHistoryService(self.members)

    @cached_property
    def medical_logs(self):
        from backend.app.application.medical_log_service import MedicalLogService

        return MedicalLogService(self.members)

    @cached_property
    def knowledge(self):
        from backend.app.application.knowledge_service import KnowledgeService

        return KnowledgeService(paths=self.paths)

    @cached_property
    def memory(self):
        from backend.app.application.memory.service import MemoryService

        return MemoryService(self.members, models=self.models)

    @cached_property
    def memory_scheduler(self):
        from backend.app.application.memory.processing.scheduler import MemoryScheduler

        return MemoryScheduler(self.memory)

    @cached_property
    def memory_reads(self):
        from backend.app.application.memory.capabilities import MemoryReadServices

        return MemoryReadServices(self.memory)

    @cached_property
    def memory_commands(self):
        from backend.app.application.memory.commands import (
            MemoryProcessingCommands,
        )

        return MemoryProcessingCommands(self.memory, self.memory_scheduler.tasks)

    @cached_property
    def body_metrics(self):
        from backend.app.application.body_metrics.service import BodyMetricService

        return BodyMetricService(self.members)

    @cached_property
    def medications(self):
        from backend.app.application.medications.service import MedicationService

        return MedicationService(self.members, notifications=self.notifications)

    @cached_property
    def notifications(self):
        from backend.app.application.notifications.service import NotificationService

        return NotificationService(self.members)

    @cached_property
    def notification_scheduler(self):
        from backend.app.application.notifications.scheduler import NotificationScheduler
        from backend.app.application.medications.notifications import (
            MedicationNotificationProducer,
        )

        def cleanup_medication_files():
            for actor in self.notifications.repository.accounts():
                if self.paths.medications_db(actor).exists():
                    self.medications.drain_files(actor)

        def maintain_conversations():
            self.conversations.maintenance.reconcile(self.auth.repository.account_ids())

        return NotificationScheduler(
            self.notifications,
            producers=(MedicationNotificationProducer(self.notifications),),
            maintenance=(
                self.member_service.lifecycle_tasks.drain,
                cleanup_medication_files,
                maintain_conversations,
            ),
        )

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
        from backend.app.application.reports.service import ReportService

        return ReportService.for_member(account_id, member_id, members=self.members)

    def plugin_service(self, account_id: str, member_id: str | None, plugin_id: str):
        if plugin_id == "memory":
            return self.memory
        if plugin_id == "knowledge":
            return self.knowledge
        if plugin_id == "body_metric":
            return self.body_metrics
        if plugin_id == "web":
            return self.web
        if plugin_id == "medication":
            return self.medications
        if plugin_id == "medical_log":
            return self.medical_logs
        if plugin_id == "medical_history":
            return self.medical_history
        if plugin_id == "members":
            return self.member_service
        if plugin_id == "medical_report" and member_id:
            return self.report(account_id, member_id)
        if plugin_id.startswith("medical_report:"):
            return self.report(account_id, plugin_id.partition(":")[2])
        raise KeyError(plugin_id)

from __future__ import annotations

from typing import Any, Optional

from backend.app.application.lab_catalog_service import LabCatalogService
from backend.app.repositories.report_repository import ReportRepository
from backend.app.repositories.config_repository import ConfigRepository
from backend.app.storage.paths import AppPaths


class AccountSettingsService(LabCatalogService):
    def __init__(
        self,
        repository: Optional[ReportRepository] = None,
        *,
        paths: Optional[AppPaths] = None,
        config_repository: Optional[ConfigRepository] = None,
    ):
        super().__init__(repository, paths=paths)
        self.config_repository = config_repository or ConfigRepository(paths=self.paths)

    def conversation_preferences(self, account_id: str) -> dict[str, Any]:
        return self.config_repository.conversation_preferences(account_id)

    def replace_conversation_preferences(
        self, account_id: str, **values: Any
    ) -> dict[str, Any]:
        return self.config_repository.replace_conversation_preferences(
            account_id, **values
        )

from __future__ import annotations

from typing import Any, Iterable
from backend.app.application.report_validation import semantic_lab_category
from backend.app.application.report_file_cleanup import drain_report_file_cleanup
from backend.app.repositories.report_repository import ReportRepository
from backend.app.storage.paths import app_paths


class LabCatalogService:
    """Owner-scoped catalogue management and committed source maintenance."""

    def __init__(self, repository=None, *, paths=None):
        self.paths = paths or app_paths()
        self.repository = repository

    def _repository(self, account_id: str) -> ReportRepository:
        if self.repository is not None:
            if self.repository.account_id != account_id:
                raise PermissionError("Catalogue belongs to another account.")
            return self.repository
        return ReportRepository(account_id, self.paths)

    @staticmethod
    def _category_name(value: str) -> str:
        return semantic_lab_category(str(value or "").strip(), ())

    def lab_dictionary(self, account_id: str) -> dict[str, Any]:
        return self._repository(account_id).lab_dictionary()

    def create_lab_item(
        self,
        account_id: str,
        *,
        item_name_zh: str,
        aliases: Iterable[str],
        description: str | None,
        primary_category_name: str,
        related_category_names: Iterable[str],
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        return self._repository(account_id).create_lab_item(
            item_name_zh=item_name_zh,
            aliases=aliases,
            description=description,
            primary_category_name=self._category_name(primary_category_name),
            related_category_names=[
                self._category_name(value) for value in related_category_names
            ],
            expected_dictionary_revision=expected_dictionary_revision,
        )

    def update_lab_item(
        self, account_id: str, item_id: str, **values: Any
    ) -> dict[str, Any]:
        values["primary_category_name"] = self._category_name(
            values["primary_category_name"]
        )
        values["related_category_names"] = [
            self._category_name(value)
            for value in values.get("related_category_names") or []
        ]
        result = self._repository(account_id).update_lab_item(item_id, **values)
        self._drain_file_cleanup(account_id)
        return result

    def delete_lab_item(
        self, account_id: str, item_id: str, **values: Any
    ) -> dict[str, Any]:
        result = self._repository(account_id).delete_lab_item(item_id, **values)
        self._drain_file_cleanup(account_id)
        return result

    def merge_lab_items(
        self, account_id: str, source_item_id: str, **values: Any
    ) -> dict[str, Any]:
        result = self._repository(account_id).merge_lab_items(source_item_id, **values)
        self._drain_file_cleanup(account_id)
        return result

    def create_lab_category(self, account_id: str, **values: Any) -> dict[str, Any]:
        values["category_name"] = self._category_name(values["category_name"])
        return self._repository(account_id).create_lab_category(**values)

    def update_lab_category(
        self, account_id: str, current_category_name: str, **values: Any
    ) -> dict[str, Any]:
        values["category_name"] = self._category_name(values["category_name"])
        return self._repository(account_id).update_lab_category(
            current_category_name, **values
        )

    def delete_lab_category(
        self, account_id: str, category_name: str, **values: Any
    ) -> dict[str, Any]:
        result = self._repository(account_id).delete_lab_category(category_name, **values)
        self._drain_file_cleanup(account_id)
        return result

    def _drain_file_cleanup(self, account_id: str) -> None:
        drain_report_file_cleanup(self._repository(account_id))

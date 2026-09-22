from __future__ import annotations

from typing import Any, Iterable
from functools import wraps
import inspect

from backend.app.repositories.reports.changes import command_value
from backend.app.application.reports.validation import normalize_lab_category
from backend.app.repositories.reports.repository import ReportRepository
from backend.app.storage.paths import app_paths


def catalog_write(method):
    signature = inspect.signature(method)
    @wraps(method)
    def execute(self, account_id, *args, **kwargs):
        bound = signature.bind(self, account_id, *args, **kwargs)
        bound.apply_defaults()
        values = {key: value for key, value in bound.arguments.items() if key != "self"}
        # Consume iterable fields once so command hashing and execution agree.
        for key, value in list(values.items()):
            if value is not None and not isinstance(value, (str, dict, list, tuple)) and hasattr(value, "__iter__"):
                values[key] = list(value)
                bound.arguments[key] = values[key]
        return self._repository(account_id).run_business_command(
            {"domain": "lab_dictionary", "action": method.__name__, "values": command_value(values)},
            lambda: method(*bound.args, **bound.kwargs), actor_account_id=account_id, drain_files=True,
        )
    return execute


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
        return normalize_lab_category(value)

    def lab_dictionary(self, account_id: str) -> dict[str, Any]:
        return self._repository(account_id).lab_dictionary()

    @catalog_write
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

    @catalog_write
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

    @catalog_write
    def delete_lab_item(
        self, account_id: str, item_id: str, **values: Any
    ) -> dict[str, Any]:
        result = self._repository(account_id).delete_lab_item(item_id, **values)
        self._drain_file_cleanup(account_id)
        return result

    @catalog_write
    def merge_lab_items(
        self, account_id: str, source_item_id: str, **values: Any
    ) -> dict[str, Any]:
        result = self._repository(account_id).merge_lab_items(source_item_id, **values)
        self._drain_file_cleanup(account_id)
        return result

    @catalog_write
    def create_lab_category(self, account_id: str, **values: Any) -> dict[str, Any]:
        values["category_name"] = self._category_name(values["category_name"])
        return self._repository(account_id).create_lab_category(**values)

    @catalog_write
    def update_lab_category(
        self, account_id: str, current_category_name: str, **values: Any
    ) -> dict[str, Any]:
        values["category_name"] = self._category_name(values["category_name"])
        return self._repository(account_id).update_lab_category(
            current_category_name, **values
        )

    @catalog_write
    def delete_lab_category(
        self, account_id: str, category_name: str, **values: Any
    ) -> dict[str, Any]:
        result = self._repository(account_id).delete_lab_category(category_name, **values)
        self._drain_file_cleanup(account_id)
        return result

    def _drain_file_cleanup(self, account_id: str) -> None:
        self._repository(account_id).drain_file_cleanup()

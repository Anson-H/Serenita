from backend.app.repositories.report_sources import ReportSources
from backend.app.repositories.report_queries import ReportQueries
from contextlib import contextmanager
from backend.app.repositories.lab_catalog import LabCatalog
from backend.app.repositories.report_facts import ReportFacts
from backend.app.repositories.report_transaction import ReportTransaction
from backend.app.repositories.report_values import _lab_value_key, _now_iso
from backend.app.storage.report_database import REPORT_DATABASE_SCHEMA
from backend.app.core.report_errors import ReportImportWriteConflictError
from backend.app.schemas.report import (
    REPORT_TYPED_STORAGE_FIELDS,
    REPORT_STRUCTURES,
    REPORT_TYPED_FIELDS,
    REPORT_REQUIRED_EDITABLE_FIELDS,
)

import json
import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Optional

from backend.app.storage.paths import AppPaths, app_paths
from backend.app.storage.sqlite import connect


_HARDENED_REPORT_STORAGE: set[Path] = set()
_HARDENED_REPORT_STORAGE_LOCK = threading.Lock()


class ReportRepository(ReportSources, ReportQueries):
    """SQLite persistence for an owner's member-scoped reports and source files."""

    def __init__(self, account_id: str, paths: Optional[AppPaths] = None):
        self._account_id = account_id
        self.paths = paths or app_paths()
        self.facts = ReportFacts(self.account_id, self.paths)
        self.catalog = LabCatalog(self.transaction, self.facts)

    def lab_dictionary(self, member_id: str | None = None) -> dict[str, Any]:
        return self.catalog.lab_dictionary(member_id)

    def create_lab_item(
        self,
        *,
        item_name_zh: str,
        aliases: Iterable[str],
        description: str | None,
        primary_category_name: str,
        related_category_names: Iterable[str],
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        return self.catalog.create_lab_item(
            item_name_zh=item_name_zh,
            aliases=aliases,
            description=description,
            primary_category_name=primary_category_name,
            related_category_names=related_category_names,
            expected_dictionary_revision=expected_dictionary_revision,
        )

    def update_lab_item(
        self,
        item_id: str,
        *,
        item_name_zh: str,
        aliases: Iterable[str],
        description: str | None,
        primary_category_name: str,
        related_category_names: Iterable[str],
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        return self.catalog.update_lab_item(
            item_id,
            item_name_zh=item_name_zh,
            aliases=aliases,
            description=description,
            primary_category_name=primary_category_name,
            related_category_names=related_category_names,
            expected_dictionary_revision=expected_dictionary_revision,
        )

    def merge_lab_items(
        self,
        source_item_id: str,
        *,
        target_item_id: str,
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        return self.catalog.merge_lab_items(
            source_item_id,
            target_item_id=target_item_id,
            expected_dictionary_revision=expected_dictionary_revision,
        )

    def delete_lab_item(
        self,
        item_id: str,
        *,
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        return self.catalog.delete_lab_item(
            item_id, expected_dictionary_revision=expected_dictionary_revision
        )

    def create_lab_category(
        self,
        *,
        category_name: str,
        description: str | None,
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        return self.catalog.create_lab_category(
            category_name=category_name,
            description=description,
            expected_dictionary_revision=expected_dictionary_revision,
        )

    def update_lab_category(
        self,
        current_category_name: str,
        *,
        category_name: str,
        description: str | None,
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        return self.catalog.update_lab_category(
            current_category_name,
            category_name=category_name,
            description=description,
            expected_dictionary_revision=expected_dictionary_revision,
        )

    def delete_lab_category(
        self,
        category_name: str,
        *,
        expected_dictionary_revision: str,
    ) -> dict[str, Any]:
        return self.catalog.delete_lab_category(
            category_name, expected_dictionary_revision=expected_dictionary_revision
        )

    @contextmanager
    def transaction(self, *, write: bool = False):
        self.init_db()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield ReportTransaction(connection)

    @property
    def account_id(self) -> str:
        return self._account_id

    def validate_existing_database(self) -> bool:
        """Strictly validate the report database without creating it."""

        return REPORT_DATABASE_SCHEMA.validate_existing(
            self.paths.reports_db(self.account_id)
        )

    def init_db(self) -> None:
        database_path = self.paths.reports_db(self.account_id)
        from backend.app.storage.database_lifecycle import ensure_database

        ensure_database(REPORT_DATABASE_SCHEMA, database_path)
        try:
            database_path.chmod(0o600)
        except OSError:
            pass
        self._harden_existing_report_storage(database_path)

    def _harden_existing_report_storage(self, database_path: Path) -> None:
        """Apply private modes once per owner database and attachment directory."""
        storage_key = database_path.resolve()
        with _HARDENED_REPORT_STORAGE_LOCK:
            if storage_key in _HARDENED_REPORT_STORAGE:
                return
            attachments_dir = self.paths.report_attachments_dir(self.account_id)
            attachments_dir.mkdir(parents=True, exist_ok=True)
            try:
                attachments_dir.chmod(0o700)
            except OSError:
                pass
            try:
                entries = list(attachments_dir.iterdir())
            except OSError:
                entries = []
            for entry in entries:
                # Report originals are intentionally flat. Never follow a link.
                if entry.is_symlink() or not entry.is_file():
                    continue
                try:
                    entry.chmod(0o600)
                except OSError:
                    continue
            _HARDENED_REPORT_STORAGE.add(storage_key)

    def delete_member_on_connection(
        self,
        connection,
        member_id: str,
        *,
        schema_alias: str = "report_data",
    ) -> None:
        """Remove member-scoped report data in a caller-owned transaction."""

        if not re.fullmatch(r"[a-z][a-z0-9_]*", schema_alias):
            raise ValueError("report database schema alias is invalid")
        schema = f'"{schema_alias}"'
        for source in connection.execute(
            f"SELECT relative_path FROM {schema}.report_sources WHERE member_id = ?",
            (member_id,),
        ).fetchall():
            self.facts.enqueue_file_cleanup(
                ReportTransaction(connection),
                member_id,
                source["relative_path"],
                schema_alias=schema_alias,
            )
        connection.execute(
            f"DELETE FROM {schema}.reports WHERE member_id = ?", (member_id,)
        )
        connection.execute(
            f"DELETE FROM {schema}.report_sources WHERE member_id = ?",
            (member_id,),
        )

    def update_report_fields(
        self,
        member_id: str,
        report_id: str,
        *,
        updates: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        """Update report fields and refresh evidence metadata in one transaction."""

        if not updates:
            raise ValueError("字段更新列表不能为空。")
        seen_targets: set[tuple[str, str]] = set()
        for update in updates:
            field = str(update.get("field") or "")
            item_id = (
                str(update.get("item_id") or "")
                if field in {"lab_result", "lab_reference", "lab_flag"}
                else ""
            )
            target = (field, item_id)
            if target in seen_targets:
                raise ValueError("同一次操作不能重复更新同一字段。")
            seen_targets.add(target)

        self.init_db()
        metadata_columns = {
            "report_name": "report_name",
            "institution_name": "institution_name",
        }
        lab_columns = {
            "lab_result": "result_text",
            "lab_reference": "reference_text",
            "lab_flag": "flag_text",
        }
        typed_fields = REPORT_TYPED_STORAGE_FIELDS
        required_fields = REPORT_REQUIRED_EDITABLE_FIELDS
        timestamp = _now_iso()

        with connect(self.paths.reports_db(self.account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            report = connection.execute(
                "SELECT report_type, report_name, report_time, institution_name, analysis_content FROM reports WHERE member_id = ? AND report_id = ?",
                (member_id, report_id),
            ).fetchone()
            if report is None:
                return None
            changed_any = False
            evidence_changed_any = False
            for update in updates:
                field = str(update.get("field") or "")
                value = update.get("value")
                item_id = str(update.get("item_id") or "")
                normalized = value.strip() if isinstance(value, str) else None
                if field in required_fields and not normalized:
                    raise ValueError("该字段不能为空。")
                if field == "lab_flag" and normalized not in {
                    "未标记",
                    "正常",
                    "异常",
                    "偏高",
                    "偏低",
                }:
                    raise ValueError("结果标记只能为未标记、正常、异常、偏高或偏低。")
                stored_value: Optional[str] = normalized or None
                if field == "report_name" and report["report_type"] == "检验报告":
                    raise ValueError(
                        "检验报告名称必须在账号检验指标分类目录中统一更新。"
                    )

                changed = False
                if field == "analysis_content":
                    content = normalized or ""
                    changed = content != str(report["analysis_content"] or "")
                    if changed:
                        connection.execute(
                            """
                            UPDATE reports
                            SET analysis_content = ?, analysis_outdated = 0,
                                analysis_updated_at = ?,
                                updated_at = ?
                            WHERE member_id = ? AND report_id = ?
                            """,
                            (content, timestamp, timestamp, member_id, report_id),
                        )
                elif field == "report_time":
                    changed = stored_value != report["report_time"]
                    if changed:
                        connection.execute(
                            "UPDATE reports SET report_time = ? WHERE member_id = ? AND report_id = ?",
                            (stored_value, member_id, report_id),
                        )
                elif field in metadata_columns:
                    column = metadata_columns[field]
                    changed = stored_value != report[column]
                    if changed:
                        connection.execute(
                            f"UPDATE reports SET {column} = ? WHERE member_id = ? AND report_id = ?",
                            (stored_value, member_id, report_id),
                        )
                elif field in lab_columns:
                    if report["report_type"] != "检验报告" or not item_id:
                        raise ValueError("检验指标字段缺少有效指标。")
                    column = lab_columns[field]
                    row = connection.execute(
                        "SELECT * FROM lab_test_report WHERE member_id = ? AND report_id = ? AND item_id = ?",
                        (member_id, report_id, item_id),
                    ).fetchone()
                    if row is None:
                        raise LookupError("医疗报告指标不存在。")
                    changed = stored_value != row[column]
                    if changed:
                        connection.execute(
                            f"UPDATE lab_test_report SET {column} = ? WHERE member_id = ? AND report_id = ? AND item_id = ?",
                            (stored_value, member_id, report_id, item_id),
                        )
                else:
                    mapping = typed_fields.get(report["report_type"], {}).get(field)
                    if mapping is None:
                        raise ValueError("该字段不属于当前医疗报告类型。")
                    table, column = mapping
                    row = connection.execute(
                        f"SELECT {column} FROM {table} WHERE member_id = ? AND report_id = ?",
                        (member_id, report_id),
                    ).fetchone()
                    if row is None:
                        raise LookupError("医疗报告结构化内容不存在。")
                    changed = stored_value != row[column]
                    if changed:
                        connection.execute(
                            f"UPDATE {table} SET {column} = ? WHERE member_id = ? AND report_id = ?",
                            (stored_value, member_id, report_id),
                        )

                changed_any = changed_any or changed
                evidence_changed_any = evidence_changed_any or (
                    changed and field != "analysis_content"
                )

            if changed_any and evidence_changed_any:
                connection.execute(
                    """
                    UPDATE reports
                    SET analysis_outdated = CASE WHEN trim(analysis_content) <> '' THEN 1 ELSE 0 END,
                        updated_at = ?
                    WHERE member_id = ? AND report_id = ?
                    """,
                    (timestamp, member_id, report_id),
                )
        return self.get_report_detail(member_id, report_id)

    def add_lab_report_item(
        self,
        member_id: str,
        report_id: str,
        *,
        item_id: str,
        result_text: str,
        reference_text: Optional[str],
        flag_text: str,
    ) -> Optional[dict[str, Any]]:
        """Append one dictionary-backed result to a lab report in one transaction."""

        return self.add_lab_report_items(
            member_id,
            report_id,
            items=[
                {
                    "item_id": item_id,
                    "result_text": result_text,
                    "reference_text": reference_text,
                    "flag_text": flag_text,
                }
            ],
        )

    def add_lab_report_items(
        self,
        member_id: str,
        report_id: str,
        *,
        items: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        """Append dictionary-backed results to one lab report in one transaction."""

        normalized_items: list[dict[str, str | None]] = []
        for item in items:
            normalized_item_id = str(item.get("item_id") or "").strip()
            normalized_result = str(item.get("result_text") or "").strip()
            reference_text = item.get("reference_text")
            normalized_reference = (
                str(reference_text).strip() if reference_text is not None else ""
            )
            normalized_flag = str(item.get("flag_text") or "").strip() or "未标记"
            if not normalized_item_id or not normalized_result:
                raise ValueError("检验指标和结果不能为空。")
            if normalized_flag not in {"未标记", "正常", "异常", "偏高", "偏低"}:
                raise ValueError("结果标记只能为未标记、正常、异常、偏高或偏低。")
            normalized_items.append(
                {
                    "item_id": normalized_item_id,
                    "result_text": normalized_result,
                    "reference_text": normalized_reference or None,
                    "flag_text": normalized_flag,
                }
            )

        if not normalized_items:
            raise ValueError("要添加的检验指标不能为空。")
        normalized_item_ids = [str(item["item_id"]) for item in normalized_items]
        if len(normalized_item_ids) != len(set(normalized_item_ids)):
            raise ValueError("同一次操作不能重复添加同一检验指标。")

        self.init_db()
        timestamp = _now_iso()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            report = connection.execute(
                "SELECT report_type, report_name FROM reports WHERE member_id = ? AND report_id = ?",
                (member_id, report_id),
            ).fetchone()
            if report is None:
                return None
            if report["report_type"] != "检验报告":
                raise ValueError("只有检验报告可以添加指标。")
            category_rows = connection.execute(
                """
                SELECT DISTINCT category_name FROM lab_test_report
                WHERE member_id = ? AND report_id = ?
                """,
                (member_id, report_id),
            ).fetchall()
            if len(category_rows) != 1:
                raise RuntimeError("检验报告缺少唯一分类。")
            report_category_name = str(category_rows[0]["category_name"])
            for item in normalized_items:
                normalized_item_id = str(item["item_id"])
                dictionary_item = connection.execute(
                    """
                    SELECT i.item_id, i.item_name_zh, c.category_name
                    FROM lab_items i
                    JOIN lab_item_category_links c
                      ON c.item_id = i.item_id AND c.is_primary = 1
                    WHERE i.item_id = ?
                    """,
                    (normalized_item_id,),
                ).fetchone()
                if dictionary_item is None:
                    raise LookupError(
                        f"检验指标 {normalized_item_id} 不存在于当前账号的检验指标分类目录中。"
                    )
                existing = connection.execute(
                    "SELECT 1 FROM lab_test_report WHERE member_id = ? AND report_id = ? AND item_id = ?",
                    (member_id, report_id, normalized_item_id),
                ).fetchone()
                if existing is not None:
                    raise ValueError(f"目标检验报告中已存在指标 {normalized_item_id}。")
                dictionary_category_name = str(dictionary_item["category_name"])
                if dictionary_category_name != report_category_name:
                    raise ValueError(
                        f"该医疗报告属于“{report_category_name}”，不能添加主分类为“{dictionary_category_name}”的指标。"
                    )
                connection.execute(
                    """
                    INSERT INTO lab_test_report(
                        report_id, item_id, member_id, category_name, item_name_zh,
                        result_text, reference_text, flag_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        normalized_item_id,
                        member_id,
                        report_category_name,
                        str(dictionary_item["item_name_zh"]),
                        str(item["result_text"]),
                        item["reference_text"],
                        str(item["flag_text"]),
                    ),
                )
            connection.execute(
                """
                UPDATE reports
                SET analysis_outdated = CASE WHEN trim(analysis_content) <> '' THEN 1 ELSE 0 END,
                    updated_at = ?
                WHERE member_id = ? AND report_id = ?
                """,
                (timestamp, member_id, report_id),
            )
        return self.get_report_detail(member_id, report_id)

    def delete_lab_report_items(
        self,
        member_id: str,
        report_id: str,
        *,
        item_ids: list[str],
    ) -> Optional[dict[str, Any]]:
        """Delete report-scoped lab results without changing the dictionary in one transaction."""

        normalized_item_ids = [str(item_id).strip() for item_id in item_ids]
        if not normalized_item_ids or any(
            not item_id for item_id in normalized_item_ids
        ):
            raise ValueError("要删除的检验指标不能为空。")
        if len(normalized_item_ids) != len(set(normalized_item_ids)):
            raise ValueError("同一次操作不能重复删除同一检验指标。")

        self.init_db()
        timestamp = _now_iso()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            report = connection.execute(
                "SELECT report_type FROM reports WHERE member_id = ? AND report_id = ?",
                (member_id, report_id),
            ).fetchone()
            if report is None:
                return None
            if report["report_type"] != "检验报告":
                raise ValueError("只有检验报告可以删除指标。")
            rows = connection.execute(
                "SELECT item_id FROM lab_test_report WHERE member_id = ? AND report_id = ?",
                (member_id, report_id),
            ).fetchall()
            stored_item_ids = {str(row["item_id"]) for row in rows}
            missing_item_ids = [
                item_id
                for item_id in normalized_item_ids
                if item_id not in stored_item_ids
            ]
            if missing_item_ids:
                raise LookupError(
                    "目标检验报告中不存在以下指标：" + "、".join(missing_item_ids)
                )
            if len(rows) <= len(normalized_item_ids):
                raise ValueError(
                    "不能删除检验报告中的最后一个指标；如需移除该内容，请明确删除整份医疗报告。"
                )
            placeholders = ", ".join("?" for _item_id in normalized_item_ids)
            connection.execute(
                f"DELETE FROM lab_test_report WHERE member_id = ? AND report_id = ? AND item_id IN ({placeholders})",
                (member_id, report_id, *normalized_item_ids),
            )
            connection.execute(
                """
                UPDATE reports
                SET analysis_outdated = CASE WHEN trim(analysis_content) <> '' THEN 1 ELSE 0 END,
                    updated_at = ?
                WHERE member_id = ? AND report_id = ?
                """,
                (timestamp, member_id, report_id),
            )
        return self.get_report_detail(member_id, report_id)

    def reclassify_report(
        self,
        member_id: str,
        report_id: str,
        parsed_report: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Replace one report's typed projection in one transaction without changing its ID.

        ``report_id`` is referenced by conversations, favorites, pending actions, and
        source links. Keeping it stable is therefore safer than replacing the report
        merely to make its historical type prefix match the new classification.
        """
        self.init_db()
        timestamp = _now_iso()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """
                SELECT report_type, report_time
                FROM reports WHERE member_id = ? AND report_id = ?
                """,
                (member_id, report_id),
            ).fetchone()
            if current is None:
                return None
            effective_report = deepcopy(parsed_report)
            effective_report["report_time"] = str(current["report_time"])
            self._replace_structured_data_on_connection(
                connection,
                member_id,
                report_id,
                effective_report,
                timestamp=timestamp,
            )
        return self.get_report_detail(member_id, report_id)

    def save_report_analysis(
        self,
        member_id: str,
        report_id: str,
        analysis_content: str,
    ) -> Optional[dict[str, Any]]:
        """Replace one existing report's derived analysis in one transaction."""

        self.init_db()
        timestamp = _now_iso()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE reports
                SET analysis_content = ?, analysis_outdated = 0,
                    analysis_updated_at = ?, updated_at = ?
                WHERE member_id = ? AND report_id = ?
                """,
                (
                    analysis_content,
                    timestamp,
                    timestamp,
                    member_id,
                    report_id,
                ),
            )
            if cursor.rowcount != 1:
                return None
        return self.get_report_detail(member_id, report_id)

    def _create_report_record_on_connection(
        self,
        connection,
        member_id: str,
        report_data: dict[str, Any],
        *,
        timestamp: str,
    ) -> str:
        report_id = self.facts.next_report_id(
            ReportTransaction(connection),
            report_data["report_type"],
            report_data["report_time"],
        )
        connection.execute(
            """
            INSERT INTO reports (
                report_id, member_id, report_type, report_name, report_time,
                institution_name,
                analysis_content, analysis_outdated,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, '', 0, ?, ?)
            """,
            (
                report_id,
                member_id,
                report_data["report_type"],
                report_data["report_name"],
                report_data["report_time"],
                report_data.get("institution_name"),
                timestamp,
                timestamp,
            ),
        )
        self._insert_typed_payload(connection, member_id, report_id, report_data)
        return report_id

    def _create_report_on_connection(
        self,
        connection,
        member_id: str,
        report_data: dict[str, Any],
        *,
        resource_ids: list[str],
        timestamp: str,
    ) -> str:
        if not resource_ids:
            raise ValueError("创建医疗报告必须至少关联一个来源。")
        report_id = self._create_report_record_on_connection(
            connection,
            member_id,
            report_data,
            timestamp=timestamp,
        )
        for source_index, resource_id in enumerate(dict.fromkeys(resource_ids)):
            connection.execute(
                """
                INSERT INTO report_source_links(report_id, resource_id, member_id, is_primary, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (report_id, resource_id, member_id, int(source_index == 0), timestamp),
            )
        return report_id

    def _replace_structured_data_on_connection(
        self,
        connection,
        member_id: str,
        report_id: str,
        report_data: dict[str, Any],
        *,
        timestamp: str,
    ) -> None:
        for table in ("lab_test_report", *REPORT_TYPED_FIELDS):
            connection.execute(
                f"DELETE FROM {table} WHERE member_id = ? AND report_id = ?",
                (member_id, report_id),
            )
        self._insert_typed_payload(connection, member_id, report_id, report_data)
        connection.execute(
            """
            UPDATE reports
            SET report_type = ?, report_name = ?, report_time = ?,
                institution_name = ?,
                analysis_outdated = CASE
                    WHEN trim(analysis_content) <> '' THEN 1 ELSE analysis_outdated END,
                updated_at = ?
            WHERE member_id = ? AND report_id = ?
            """,
            (
                report_data["report_type"],
                report_data["report_name"],
                report_data["report_time"],
                report_data.get("institution_name"),
                timestamp,
                member_id,
                report_id,
            ),
        )

    def create_report_from_parsed(
        self,
        member_id: str,
        parsed_report: dict[str, Any],
        *,
        resource_ids: list[str],
    ) -> dict[str, Any]:
        self.init_db()
        timestamp = _now_iso()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            report = deepcopy(parsed_report)
            if report.get("report_type") == "检验报告":
                normalized, _aliases, issues = self.catalog.normalize_lab_items(
                    ReportTransaction(connection),
                    list(report.get("lab_test_results") or []),
                )
                if issues:
                    raise ReportImportWriteConflictError(
                        "解析医疗报告包含无法唯一匹配的检验指标。", details=issues
                    )
                report["lab_test_results"] = normalized
            report_id = self._create_report_on_connection(
                connection,
                member_id,
                report,
                resource_ids=resource_ids,
                timestamp=timestamp,
            )
        return {"report_id": report_id}

    def create_manual_report(
        self,
        member_id: str,
        report_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a user-entered report without manufacturing an original file."""

        self.init_db()
        timestamp = _now_iso()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            report = deepcopy(report_data)
            if report.get("report_type") == "检验报告":
                normalized, _aliases, issues = self.catalog.normalize_lab_items(
                    ReportTransaction(connection),
                    list(report.get("lab_test_results") or []),
                )
                if issues:
                    raise ValueError(
                        "录入的检验指标无法与当前检验指标分类目录唯一匹配。"
                    )
                report["lab_test_results"] = normalized
            report_id = self._create_report_record_on_connection(
                connection,
                member_id,
                report,
                timestamp=timestamp,
            )
        return {"report_id": report_id}

    def merge_parsed_report(
        self,
        member_id: str,
        parsed_report: dict[str, Any],
        *,
        report_id: str,
        resource_ids: list[str],
    ) -> dict[str, Any]:
        self.init_db()
        timestamp = _now_iso()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            target = connection.execute(
                "SELECT report_type, report_name, institution_name, report_time FROM reports WHERE member_id = ? AND report_id = ?",
                (member_id, report_id),
            ).fetchone()
            if target is None:
                raise LookupError("模型指定的目标医疗报告不存在。")
            report = deepcopy(parsed_report)
            differences: list[dict[str, Any]] = []
            for field in ("report_type", "report_name", "report_time"):
                if str(target[field] or "") != str(report.get(field) or ""):
                    differences.append(
                        {
                            "field": field,
                            "existing_value": target[field],
                            "parsed_value": report.get(field),
                        }
                    )
            existing_institution = str(target["institution_name"] or "").strip()
            parsed_institution = str(report.get("institution_name") or "").strip()
            if (
                existing_institution
                and parsed_institution
                and existing_institution != parsed_institution
            ):
                differences.append(
                    {
                        "field": "institution_name",
                        "existing_value": target["institution_name"],
                        "parsed_value": report.get("institution_name"),
                    }
                )

            inserted_items: list[dict[str, Any]] = []
            typed_updates: dict[str, Any] = {}
            typed_table = ""
            if not differences and report.get("report_type") == "检验报告":
                normalized, _aliases, normalization_issues = (
                    self.catalog.normalize_lab_items(
                        ReportTransaction(connection),
                        list(report.get("lab_test_results") or []),
                    )
                )
                differences.extend(normalization_issues)
                existing_items = {
                    str(row["item_id"]): row
                    for row in connection.execute(
                        """
                        SELECT * FROM lab_test_report
                        WHERE member_id = ? AND report_id = ?
                        """,
                        (member_id, report_id),
                    ).fetchall()
                }
                for item in normalized:
                    stored = existing_items.get(str(item["item_id"]))
                    if stored is None:
                        inserted_items.append(item)
                        continue
                    fields = ("result_text", "reference_text", "flag_text")
                    values_match = (
                        all(
                            _lab_value_key(stored[field])
                            == _lab_value_key(item.get(field))
                            for field in fields[:2]
                        )
                        and str(stored["flag_text"]).strip()
                        == str(item.get("flag_text") or "未标记").strip()
                    )
                    if not values_match:
                        differences.append(
                            {
                                "kind": "lab_items_value_difference",
                                "report_id": report_id,
                                "item_id": item["item_id"],
                                "item_name_zh": item["item_name_zh"],
                                "existing": {field: stored[field] for field in fields},
                                "parsed": {field: item.get(field) for field in fields},
                            }
                        )
            elif not differences:
                typed_table = payload_field = REPORT_STRUCTURES[str(report["report_type"])][0]
                parsed_payload = report.get(payload_field)
                stored_payload = connection.execute(
                    f"SELECT * FROM {typed_table} WHERE member_id = ? AND report_id = ?",
                    (member_id, report_id),
                ).fetchone()
                if stored_payload is None or not isinstance(parsed_payload, dict):
                    differences.append(
                        {
                            "field": payload_field,
                            "existing_value": None,
                            "parsed_value": parsed_payload,
                        }
                    )
                else:
                    for field, parsed_value in parsed_payload.items():
                        if field in {"report_id", "member_id"}:
                            continue
                        existing_value = stored_payload[field]
                        if parsed_value in {None, ""}:
                            continue
                        if existing_value in {None, ""}:
                            typed_updates[field] = parsed_value
                        elif str(existing_value) != str(parsed_value):
                            differences.append(
                                {
                                    "field": field,
                                    "existing_value": existing_value,
                                    "parsed_value": parsed_value,
                                }
                            )

            if differences:
                raise ReportImportWriteConflictError(
                    "解析内容与目标医疗报告存在不同旧值，未执行合并。",
                    details=differences,
                )

            changed = False
            for item in inserted_items:
                connection.execute(
                    """
                    INSERT INTO lab_test_report(
                        report_id, item_id, member_id, category_name, item_name_zh,
                        result_text, reference_text, flag_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        item["item_id"],
                        member_id,
                        item["category_name"],
                        item["item_name_zh"],
                        item["result_text"],
                        item.get("reference_text"),
                        item.get("flag_text") or "未标记",
                    ),
                )
                changed = True
            if typed_updates:
                assignments = ", ".join(f"{field} = ?" for field in typed_updates)
                connection.execute(
                    f"UPDATE {typed_table} SET {assignments} WHERE member_id = ? AND report_id = ?",
                    (*typed_updates.values(), member_id, report_id),
                )
                changed = True
            if not existing_institution and parsed_institution:
                connection.execute(
                    "UPDATE reports SET institution_name = ? WHERE member_id = ? AND report_id = ?",
                    (parsed_institution, member_id, report_id),
                )
                changed = True
            if not resource_ids:
                raise ValueError("合并医疗报告必须至少包含一个来源。")
            for resource_id in dict.fromkeys(resource_ids):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO report_source_links(
                        report_id, resource_id, member_id, is_primary, created_at
                    ) VALUES (?, ?, ?, 0, ?)
                    """,
                    (report_id, resource_id, member_id, timestamp),
                )
            if changed:
                connection.execute(
                    """
                    UPDATE reports
                    SET analysis_outdated = CASE
                            WHEN trim(analysis_content) <> '' THEN 1 ELSE analysis_outdated END,
                        updated_at = ?
                    WHERE member_id = ? AND report_id = ?
                    """,
                    (timestamp, member_id, report_id),
                )
        return {
            "report_id": report_id,
            "changed": changed,
            "added_item_ids": [str(item["item_id"]) for item in inserted_items],
            "updated_fields": sorted(typed_updates),
        }

    def delete_report(
        self,
        member_id: str,
        report_id: str,
    ) -> Optional[list[dict[str, Any]]]:
        self.init_db()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            report = connection.execute(
                "SELECT 1 FROM reports WHERE member_id = ? AND report_id = ?",
                (member_id, report_id),
            ).fetchone()
            if report is None:
                return None
            orphaned = self.facts.delete_report(
                ReportTransaction(connection), member_id, report_id
            )
        return orphaned

    def _insert_typed_payload(
        self, connection, member_id: str, report_id: str, report_data: dict[str, Any]
    ) -> None:
        report_type = report_data["report_type"]
        if report_type == "检验报告":
            for item in report_data.get("lab_test_results", []):
                item_id = str(item.get("item_id") or "").strip()
                item_name_zh = str(item.get("item_name_zh") or "").strip()
                if not item_id or not item_name_zh:
                    raise ValueError("检验指标缺少 item_id 或规范名称。")
                aliases = self.catalog.normalized_dictionary_aliases(
                    item_name_zh, item.get("aliases") or []
                )
                category_name = str(item["category_name"]).strip()
                connection.execute(
                    """
                    INSERT OR IGNORE INTO lab_items(item_id, item_name_zh, aliases, description)
                    VALUES (?, ?, ?, NULL)
                    """,
                    (item_id, item_name_zh, json.dumps(aliases, ensure_ascii=False)),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO lab_categories(category_name, description)
                    VALUES (?, NULL)
                    """,
                    (category_name,),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO lab_item_category_links(
                        item_id, category_name, is_primary
                    ) VALUES (
                        ?, ?,
                        CASE WHEN EXISTS (
                            SELECT 1 FROM lab_item_category_links
                            WHERE item_id = ? AND is_primary = 1
                        ) THEN 0 ELSE 1 END
                    )
                    """,
                    (item_id, category_name, item_id),
                )
                primary_row = connection.execute(
                    """
                    SELECT category_name FROM lab_item_category_links
                    WHERE item_id = ? AND is_primary = 1
                    """,
                    (item_id,),
                ).fetchone()
                if primary_row is None:
                    raise RuntimeError("检验指标缺少主分类。")
                canonical_category_name = str(primary_row["category_name"])
                connection.execute(
                    """
                    INSERT INTO lab_test_report (
                        report_id, item_id, member_id, category_name, item_name_zh,
                        result_text, reference_text, flag_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        item_id,
                        member_id,
                        canonical_category_name,
                        item_name_zh,
                        item["result_text"],
                        item.get("reference_text"),
                        item.get("flag_text") or "未标记",
                    ),
                )
        else:
            table, model = REPORT_STRUCTURES[report_type]
            item = report_data[table]
            fields = tuple(model.model_fields)
            connection.execute(
                f"INSERT INTO {table}(report_id, member_id, {', '.join(fields)}) "
                f"VALUES (?, ?, {', '.join('?' for _ in fields)})",
                (report_id, member_id, *(item.get(field) for field in fields)),
            )

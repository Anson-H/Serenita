from backend.app.repositories.report_values import _lab_value_key
from backend.app.core.report_errors import LabDictionaryMergeResultConflictError
from backend.app.repositories.report_transaction import ReportTransaction

import hashlib
import re
from typing import Any, Iterable

from backend.app.core.time import local_now


from backend.app.repositories.report_values import REPORT_PREFIXES, _now_iso


class ReportFacts:
    """Report fact changes participating in their caller's transaction."""

    def __init__(self, account_id, paths):
        self.account_id = account_id
        self.paths = paths

    def delete_report(
        self, transaction: ReportTransaction, member_id: str, report_id: str
    ) -> list[dict[str, Any]]:
        connection = transaction.connection
        linked = connection.execute(
            """
            SELECT f.* FROM report_sources f
            JOIN report_source_links l ON l.resource_id = f.resource_id AND l.member_id = f.member_id
            WHERE l.member_id = ? AND l.report_id = ?
            """,
            (member_id, report_id),
        ).fetchall()
        connection.execute(
            "DELETE FROM reports WHERE member_id = ? AND report_id = ?",
            (member_id, report_id),
        )
        orphaned: list[dict[str, Any]] = []
        for source in linked:
            remaining = connection.execute(
                """
                SELECT 1 FROM report_source_links
                WHERE member_id = ? AND resource_id = ? LIMIT 1
                """,
                (member_id, source["resource_id"]),
            ).fetchone()
            if not remaining:
                orphaned.append(dict(source))
                self.enqueue_file_cleanup(
                    transaction, member_id, source["relative_path"]
                )
                connection.execute(
                    "DELETE FROM report_sources WHERE member_id = ? AND resource_id = ?",
                    (member_id, source["resource_id"]),
                )
        return orphaned

    def enqueue_file_cleanup(
        self,
        transaction: ReportTransaction,
        member_id: str,
        relative_path: str,
        *,
        schema_alias: str | None = None,
    ) -> bool:
        """Queue only a path beneath this owner's report attachments root."""
        connection = transaction.connection
        if schema_alias is not None and not re.fullmatch(
            r"[a-z][a-z0-9_]*", schema_alias
        ):
            raise ValueError("report database schema alias is invalid")
        table = (
            f'"{schema_alias}".report_source_file_cleanup_outbox'
            if schema_alias is not None
            else "report_source_file_cleanup_outbox"
        )
        try:
            account_root = self.paths.account_root(self.account_id).resolve()
            attachments_root = self.paths.report_attachments_dir(
                self.account_id
            ).resolve()
            resolved_path = (account_root / str(relative_path)).resolve()
            if not resolved_path.is_relative_to(attachments_root):
                return False
            relative_path = resolved_path.relative_to(account_root).as_posix()
        except (OSError, ValueError, TypeError):
            return False
        cleanup_id = hashlib.sha256(
            f"{member_id}\0{relative_path}".encode("utf-8")
        ).hexdigest()
        connection.execute(
            f"""
            INSERT OR IGNORE INTO {table}(
                cleanup_id, member_id, relative_path, attempt_count, created_at
            ) VALUES (?, ?, ?, 0, ?)
            """,
            (cleanup_id, member_id, relative_path, _now_iso()),
        )
        return True

    def dictionary_impact(
        self,
        transaction: ReportTransaction,
        *,
        operation: str,
        item_id: str | None = None,
        category_name: str | None = None,
    ) -> dict[str, Any]:
        connection = transaction.connection
        clauses: list[str] = []
        parameters: list[Any] = []
        primary_item_count = 0
        related_item_count = 0
        if operation == "delete_item":
            clauses.append("item_id = ?")
            parameters.append(str(item_id or ""))
        elif operation == "delete_category":
            clauses.append("category_name = ?")
            parameters.append(str(category_name or ""))
            category_usage = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN is_primary = 1 THEN 1 ELSE 0 END) AS primary_count,
                    SUM(CASE WHEN is_primary = 0 THEN 1 ELSE 0 END) AS related_count
                FROM lab_item_category_links WHERE category_name = ?
                """,
                (str(category_name or ""),),
            ).fetchone()
            primary_item_count = int(category_usage["primary_count"] or 0)
            related_item_count = int(category_usage["related_count"] or 0)
        else:
            raise ValueError("不支持的字典影响操作。")

        rows = connection.execute(
            f"""
            SELECT report_id, item_id, item_name_zh, category_name FROM lab_test_report
            WHERE {" AND ".join(clauses)}
            """,
            parameters,
        ).fetchall()
        affected_report_ids = sorted({str(row["report_id"]) for row in rows})
        deleted_report_ids: list[str] = []
        for report_id_value in affected_report_ids:
            total = int(
                connection.execute(
                    """
                    SELECT COUNT(*) AS total FROM lab_test_report
                    WHERE report_id = ?
                    """,
                    (report_id_value,),
                ).fetchone()["total"]
            )
            removed_count = sum(
                str(row["report_id"]) == report_id_value for row in rows
            )
            if total == removed_count:
                deleted_report_ids.append(report_id_value)

        orphaned_source_ids: set[str] = set()
        if deleted_report_ids:
            placeholders = ",".join("?" for _ in deleted_report_ids)
            candidates = connection.execute(
                f"""
                SELECT DISTINCT resource_id FROM report_source_links
                WHERE report_id IN ({placeholders})
                """,
                (*deleted_report_ids,),
            ).fetchall()
            for candidate in candidates:
                linked_elsewhere = connection.execute(
                    f"""
                    SELECT 1 FROM report_source_links
                    WHERE resource_id = ?
                      AND report_id NOT IN ({placeholders}) LIMIT 1
                    """,
                    (candidate["resource_id"], *deleted_report_ids),
                ).fetchone()
                if linked_elsewhere is None:
                    orphaned_source_ids.add(str(candidate["resource_id"]))
        return {
            "result_count": len(rows),
            "affected_report_count": len(affected_report_ids),
            "deleted_report_count": len(deleted_report_ids),
            "orphaned_source_count": len(orphaned_source_ids),
            "primary_item_count": primary_item_count,
            "related_item_count": related_item_count,
            "_affected_report_ids": affected_report_ids,
            "_deleted_report_ids": deleted_report_ids,
        }

    def reconcile_dictionary_report_changes(
        self,
        transaction: ReportTransaction,
        report_ids: Iterable[str],
    ) -> dict[str, int]:
        connection = transaction.connection
        timestamp = _now_iso()
        deleted_reports = 0
        orphaned_sources = 0
        updated_reports = 0
        for report_id in sorted(set(report_ids)):
            report = connection.execute(
                """
                SELECT member_id FROM reports
                WHERE report_id = ?
                """,
                (report_id,),
            ).fetchone()
            if report is None:
                continue
            member_id = str(report["member_id"])
            remaining = int(
                connection.execute(
                    """
                    SELECT COUNT(*) AS total FROM lab_test_report
                    WHERE member_id = ? AND report_id = ?
                    """,
                    (member_id, report_id),
                ).fetchone()["total"]
            )
            if remaining == 0:
                orphaned_sources += len(
                    self.delete_report(transaction, member_id, report_id)
                )
                deleted_reports += 1
            else:
                connection.execute(
                    """
                    UPDATE reports
                    SET analysis_outdated = CASE
                            WHEN trim(analysis_content) <> '' THEN 1 ELSE 0 END,
                        updated_at = ?
                    WHERE member_id = ? AND report_id = ?
                    """,
                    (timestamp, member_id, report_id),
                )
                updated_reports += 1
        return {
            "updated_report_count": updated_reports,
            "deleted_report_count": deleted_reports,
            "orphaned_source_count": orphaned_sources,
        }

    def reclassify_lab_item_results(
        self,
        transaction: ReportTransaction,
        *,
        item_id: str,
        primary_category_name: str,
    ) -> dict[str, Any]:
        """Keep category-scoped lab reports consistent after a primary-category change."""
        connection = transaction.connection

        rows = connection.execute(
            """
            SELECT l.member_id, l.report_id, l.category_name, r.report_name, r.report_time,
                   r.institution_name
            FROM lab_test_report l
            JOIN reports r ON r.report_id = l.report_id AND r.member_id = l.member_id
            WHERE l.item_id = ?
            ORDER BY l.report_id
            """,
            (item_id,),
        ).fetchall()
        affected_report_ids: set[str] = set()
        reclassified_result_count = 0
        moved_to_existing_report_count = 0
        created_report_count = 0
        timestamp = _now_iso()

        for row in rows:
            member_id = str(row["member_id"])
            source_report_id = str(row["report_id"])
            category_changed = str(row["category_name"]) != primary_category_name
            report_name_changed = str(row["report_name"]) != primary_category_name
            if not category_changed and not report_name_changed:
                continue

            source_item_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*) AS total FROM lab_test_report
                    WHERE member_id = ? AND report_id = ?
                    """,
                    (member_id, source_report_id),
                ).fetchone()["total"]
            )
            target = connection.execute(
                """
                SELECT DISTINCT target.report_id
                FROM reports target
                JOIN report_source_links target_link
                  ON target_link.report_id = target.report_id
                 AND target_link.member_id = target.member_id
                JOIN report_source_links source_link
                  ON source_link.resource_id = target_link.resource_id
                 AND source_link.member_id = target_link.member_id
                WHERE target.member_id = ?
                  AND target.report_type = '检验报告'
                  AND target.report_name = ?
                  AND target.report_time = ?
                  AND source_link.report_id = ?
                  AND target.report_id <> ?
                  AND NOT EXISTS (
                      SELECT 1 FROM lab_test_report existing
                      WHERE existing.member_id = target.member_id
                        AND existing.report_id = target.report_id
                        AND existing.item_id = ?
                  )
                ORDER BY target.created_at, target.report_id
                LIMIT 1
                """,
                (
                    member_id,
                    primary_category_name,
                    row["report_time"],
                    source_report_id,
                    source_report_id,
                    item_id,
                ),
            ).fetchone()

            if target is not None:
                target_report_id = str(target["report_id"])
                self.copy_report_sources(
                    transaction, member_id, source_report_id, target_report_id
                )
                connection.execute(
                    """
                    UPDATE lab_test_report
                    SET report_id = ?, category_name = ?
                    WHERE member_id = ? AND report_id = ? AND item_id = ?
                    """,
                    (
                        target_report_id,
                        primary_category_name,
                        member_id,
                        source_report_id,
                        item_id,
                    ),
                )
                affected_report_ids.update((source_report_id, target_report_id))
                moved_to_existing_report_count += 1
            elif source_item_count == 1:
                connection.execute(
                    """
                    UPDATE lab_test_report SET category_name = ?
                    WHERE member_id = ? AND report_id = ? AND item_id = ?
                    """,
                    (primary_category_name, member_id, source_report_id, item_id),
                )
                connection.execute(
                    """
                    UPDATE reports SET report_name = ?
                    WHERE member_id = ? AND report_id = ?
                    """,
                    (primary_category_name, member_id, source_report_id),
                )
                affected_report_ids.add(source_report_id)
            else:
                target_report_id = self.next_report_id(
                    transaction, "检验报告", str(row["report_time"])
                )
                connection.execute(
                    """
                    INSERT INTO reports(
                        report_id, member_id, report_type, report_name, report_time,
                        institution_name, analysis_content, analysis_outdated,
                        analysis_updated_at,
                        created_at, updated_at
                    ) VALUES (?, ?, '检验报告', ?, ?, ?, '', 0, NULL, ?, ?)
                    """,
                    (
                        target_report_id,
                        member_id,
                        primary_category_name,
                        row["report_time"],
                        row["institution_name"],
                        timestamp,
                        timestamp,
                    ),
                )
                self.copy_report_sources(
                    transaction, member_id, source_report_id, target_report_id
                )
                connection.execute(
                    """
                    UPDATE lab_test_report
                    SET report_id = ?, category_name = ?
                    WHERE member_id = ? AND report_id = ? AND item_id = ?
                    """,
                    (
                        target_report_id,
                        primary_category_name,
                        member_id,
                        source_report_id,
                        item_id,
                    ),
                )
                affected_report_ids.add(source_report_id)
                created_report_count += 1

            if category_changed:
                reclassified_result_count += 1

        return {
            "affected_report_ids": affected_report_ids,
            "reclassified_result_count": reclassified_result_count,
            "moved_to_existing_report_count": moved_to_existing_report_count,
            "created_report_count": created_report_count,
        }

    def next_report_id(
        self, transaction: ReportTransaction, report_type: str, report_time: str
    ) -> str:
        connection = transaction.connection
        prefix = REPORT_PREFIXES[report_type]
        day = re.sub(r"[^0-9]", "", report_time[:10])[:8]
        if len(day) != 8:
            day = local_now().strftime("%Y%m%d")
        base = f"{prefix}-{day}-"
        rows = connection.execute(
            "SELECT report_id FROM reports WHERE report_id LIKE ?", (f"{base}%",)
        ).fetchall()
        maximum = 0
        for row in rows:
            try:
                maximum = max(maximum, int(row["report_id"].rsplit("-", 1)[1]))
            except (IndexError, ValueError):
                continue
        return f"{base}{maximum + 1:04d}"

    def copy_report_sources(
        self, transaction: ReportTransaction, member_id: str,
        source_report_id: str, target_report_id: str,
    ) -> None:
        """Preserve evidence when facts move; empty manual sources stay empty."""
        if source_report_id == target_report_id:
            return
        db = transaction.connection
        rows = db.execute(
            """SELECT resource_id FROM report_source_links
            WHERE member_id = ? AND report_id = ?
            ORDER BY is_primary DESC, created_at, resource_id""",
            (member_id, source_report_id),
        ).fetchall()
        timestamp = _now_iso()
        copied = 0
        for row in rows:
            copied += db.execute(
                """INSERT OR IGNORE INTO report_source_links
                (report_id, resource_id, member_id, is_primary, created_at)
                VALUES (?, ?, ?, 0, ?)""",
                (target_report_id, row["resource_id"], member_id, timestamp),
            ).rowcount
        if rows and not db.execute(
            """SELECT 1 FROM report_source_links
            WHERE member_id = ? AND report_id = ? AND is_primary = 1""",
            (member_id, target_report_id),
        ).fetchone():
            db.execute(
                """UPDATE report_source_links SET is_primary = 1
                WHERE member_id = ? AND report_id = ? AND resource_id = ?""",
                (member_id, target_report_id, rows[0]["resource_id"]),
            )
        if copied:
            db.execute(
                "UPDATE reports SET updated_at = ? WHERE member_id = ? AND report_id = ?",
                (timestamp, member_id, target_report_id),
            )

    def category_usage(self, transaction: ReportTransaction, member_id, category_name):
        connection = transaction.connection
        usage = connection.execute(
            """
            SELECT COUNT(*) AS result_count,
                   COUNT(DISTINCT report_id) AS report_count
            FROM lab_test_report
            WHERE member_id = COALESCE(?, member_id) AND category_name = ?
            """,
            (member_id, category_name),
        ).fetchone()
        return usage

    def item_usage(self, transaction: ReportTransaction, member_id, item_id):
        connection = transaction.connection
        usages = connection.execute(
            """
            SELECT ic.category_name, ic.is_primary,
                   COUNT(l.report_id) AS result_count,
                   COUNT(DISTINCT l.report_id) AS report_count
            FROM lab_item_category_links ic
            LEFT JOIN lab_test_report l
              ON l.item_id = ic.item_id AND l.category_name = ic.category_name
             AND l.member_id = COALESCE(?, l.member_id)
            WHERE ic.item_id = ?
            GROUP BY ic.category_name, ic.is_primary
            ORDER BY ic.is_primary DESC, ic.category_name
            """,
            (member_id, item_id),
        ).fetchall()
        return usages

    def report_ids_for_item(
        self, transaction: ReportTransaction, item_id: str, member_id=None
    ) -> set[str]:
        return {
            str(row["report_id"])
            for row in transaction.connection.execute(
                "SELECT DISTINCT report_id FROM lab_test_report WHERE member_id = COALESCE(?, member_id) AND item_id = ?",
                (member_id, item_id),
            ).fetchall()
        }

    def report_ids_for_category(
        self, transaction: ReportTransaction, category_name: str
    ) -> set[str]:
        return {
            str(row["report_id"])
            for row in transaction.connection.execute(
                "SELECT DISTINCT report_id FROM lab_test_report WHERE category_name = ?",
                (category_name,),
            ).fetchall()
        }

    def set_lab_item_name(
        self, transaction: ReportTransaction, item_id: str, item_name_zh: str
    ) -> None:
        transaction.connection.execute(
            "UPDATE lab_test_report SET item_name_zh = ? WHERE item_id = ?",
            (item_name_zh, item_id),
        )

    def rename_report_titles(
        self, transaction: ReportTransaction, report_ids: set[str], report_name: str
    ) -> None:
        if report_ids:
            placeholders = ",".join("?" for _ in report_ids)
            transaction.connection.execute(
                f"UPDATE reports SET report_name = ? WHERE report_id IN ({placeholders})",
                (report_name, *sorted(report_ids)),
            )

    def merge_lab_item_results(
        self,
        transaction: ReportTransaction,
        source_item_id: str,
        target_item_id: str,
        target_name: str,
        target_primary: str,
    ):
        connection = transaction.connection
        source_report_ids = {
            str(row["report_id"])
            for row in connection.execute(
                """
                SELECT report_id FROM lab_test_report
                WHERE item_id = ?
                """,
                (source_item_id,),
            ).fetchall()
        }

        collisions = connection.execute(
            """
            SELECT DISTINCT
                source_result.member_id AS member_id,
                source_result.report_id AS source_report_id,
                source_result.result_text AS source_result_text,
                source_result.reference_text AS source_reference_text,
                source_result.flag_text AS source_flag_text,
                target_result.report_id AS target_report_id,
                target_result.result_text AS target_result_text,
                target_result.reference_text AS target_reference_text,
                target_result.flag_text AS target_flag_text
            FROM lab_test_report source_result
            JOIN reports source_report
              ON source_report.report_id = source_result.report_id
             AND source_report.member_id = source_result.member_id
            JOIN lab_test_report target_result
              ON target_result.member_id = source_result.member_id
             AND target_result.item_id = ?
            JOIN reports target_report
              ON target_report.report_id = target_result.report_id
             AND target_report.member_id = target_result.member_id
            WHERE source_result.item_id = ?
              AND (
                target_result.report_id = source_result.report_id
                OR (
                  target_report.report_time = source_report.report_time
                  AND EXISTS (
                    SELECT 1
                    FROM report_source_links source_link
                    JOIN report_source_links target_link
                      ON target_link.member_id = source_link.member_id
                     AND target_link.resource_id = source_link.resource_id
                    WHERE source_link.member_id = source_result.member_id
                      AND source_link.report_id = source_result.report_id
                      AND target_link.report_id = target_result.report_id
                  )
                )
              )
            ORDER BY source_result.report_id, target_result.report_id
            """,
            (target_item_id, source_item_id),
        ).fetchall()
        exact_duplicate_reports: set[str] = set()
        source_transfers: set[tuple[str, str, str]] = set()
        result_conflicts: list[dict[str, Any]] = []
        for row in collisions:
            values_match = (
                _lab_value_key(row["source_result_text"])
                == _lab_value_key(row["target_result_text"])
                and _lab_value_key(row["source_reference_text"])
                == _lab_value_key(row["target_reference_text"])
                and str(row["source_flag_text"] or "").strip()
                == str(row["target_flag_text"] or "").strip()
            )
            if values_match:
                exact_duplicate_reports.add(str(row["source_report_id"]))
                source_transfers.add((
                    str(row["member_id"]), str(row["source_report_id"]),
                    str(row["target_report_id"]),
                ))
                continue
            result_conflicts.append(
                {
                    "source_report_id": str(row["source_report_id"]),
                    "target_report_id": str(row["target_report_id"]),
                    "source": {
                        "result_text": row["source_result_text"],
                        "reference_text": row["source_reference_text"],
                        "flag_text": row["source_flag_text"],
                    },
                    "target": {
                        "result_text": row["target_result_text"],
                        "reference_text": row["target_reference_text"],
                        "flag_text": row["target_flag_text"],
                    },
                }
            )
        if result_conflicts:
            raise LabDictionaryMergeResultConflictError(
                "同一原件和就诊时间中存在不同结果，未执行指标合并。",
                details=result_conflicts,
            )

        for member_id, source_report_id, target_report_id in sorted(source_transfers):
            self.copy_report_sources(
                transaction, member_id, source_report_id, target_report_id
            )
        for report_id in exact_duplicate_reports:
            connection.execute(
                """
                DELETE FROM lab_test_report
                WHERE report_id = ? AND item_id = ?
                """,
                (report_id, source_item_id),
            )
        moved_result_count = connection.execute(
            """
            UPDATE lab_test_report
            SET item_id = ?, item_name_zh = ?, category_name = ?
            WHERE item_id = ?
            """,
            (
                target_item_id,
                target_name,
                target_primary,
                source_item_id,
            ),
        ).rowcount

        return (source_report_ids, moved_result_count, len(exact_duplicate_reports))

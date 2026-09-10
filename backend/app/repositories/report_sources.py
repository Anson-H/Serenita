from __future__ import annotations

from typing import Any, Optional
from backend.app.storage.sqlite import connect
from backend.app.repositories.report_transaction import ReportTransaction
from backend.app.repositories.report_values import _now_iso, _row_dict
from backend.app.core.errors import raise_error
from backend.app.storage.cleanup_queue import cleanup_batch
import hashlib


class ReportSources:
    """Source metadata, references and durable file lifecycle in report transactions."""

    def register_source_file(
        self,
        member_id: str,
        *,
        resource_id: str,
        relative_path: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        source_kind: str,
    ) -> tuple[dict[str, Any], bool]:
        self.init_db()
        timestamp = _now_iso()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO report_sources (
                    resource_id, member_id, mime_type, size_bytes,
                    relative_path, sha256, source_kind, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resource_id,
                    member_id,
                    mime_type,
                    size_bytes,
                    relative_path,
                    sha256,
                    source_kind,
                    timestamp,
                ),
            )
            connection.execute(
                "DELETE FROM report_source_file_cleanup_outbox WHERE relative_path = ?",
                (relative_path,),
            )
        return self.source_file(member_id, resource_id), True

    def persist_source_file(
        self, member_id: str, *, resource_id: str, extension: str,
        mime_type: str, content: bytes, source_kind: str,
    ) -> tuple[dict[str, Any], bool]:
        """Write or reuse one source under the same lock as physical cleanup."""
        destination = self.paths.report_attachment_path(self.account_id, resource_id, extension)
        relative_path = str(destination.relative_to(self.paths.account_root(self.account_id)))
        signature = hashlib.sha256(content).hexdigest()
        try:
            with self.transaction(write=True) as transaction:
                db = transaction.connection
                existing = db.execute(
                    "SELECT * FROM report_sources WHERE member_id = ? AND resource_id = ?",
                    (member_id, resource_id),
                ).fetchone()
                if existing is not None:
                    if existing["sha256"] != signature:
                        raise_error("conflict", "REPORT_SOURCE_CHANGED", "已登记来源与原件内容不一致。")
                    return dict(existing), False
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.parent.chmod(0o700)
                destination.write_bytes(content)
                destination.chmod(0o600)
                source = dict(resource_id=resource_id, member_id=member_id,
                    mime_type=mime_type, size_bytes=len(content), relative_path=relative_path,
                    sha256=signature, source_kind=source_kind, created_at=_now_iso())
                db.execute(
                    """INSERT INTO report_sources
                    (resource_id, member_id, mime_type, size_bytes, relative_path, sha256, source_kind, created_at)
                    VALUES (:resource_id, :member_id, :mime_type, :size_bytes, :relative_path, :sha256, :source_kind, :created_at)""",
                    source,
                )
                db.execute("DELETE FROM report_source_file_cleanup_outbox WHERE relative_path = ?", (relative_path,))
            return source, True
        except Exception:
            # A commit may have succeeded despite a later failure. Never unlink
            # here: recheck current ownership and enqueue only unregistered paths.
            with self.transaction(write=True) as transaction:
                if not transaction.connection.execute(
                    "SELECT 1 FROM report_sources WHERE relative_path = ?", (relative_path,)
                ).fetchone():
                    self.facts.enqueue_file_cleanup(transaction, member_id, relative_path)
            raise

    def clean_source_file(self, job: dict[str, Any]) -> None:
        """Recheck a claimed cleanup job and its live references before removal."""
        with self.transaction(write=True) as transaction:
            db = transaction.connection
            current = db.execute(
                "SELECT * FROM report_source_file_cleanup_outbox WHERE cleanup_id = ? AND member_id = ?",
                (job["cleanup_id"], job["member_id"]),
            ).fetchone()
            if current is None:
                return
            referenced = db.execute(
                "SELECT 1 FROM report_sources WHERE relative_path = ?", (current["relative_path"],)
            ).fetchone()
            if not referenced:
                account_root = self.paths.account_root(self.account_id).resolve()
                root = self.paths.report_attachments_dir(self.account_id).resolve()
                path = (account_root / current["relative_path"]).resolve()
                if not path.is_relative_to(root):
                    raise ValueError("不安全的医疗报告源文件路径")
                path.unlink(missing_ok=True)
            db.execute("DELETE FROM report_source_file_cleanup_outbox WHERE cleanup_id = ?", (job["cleanup_id"],))

    def source_file(self, member_id: str, resource_id: str) -> Optional[dict[str, Any]]:
        self.init_db()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            row = connection.execute(
                "SELECT * FROM report_sources WHERE member_id = ? AND resource_id = ?",
                (member_id, resource_id),
            ).fetchone()
        return _row_dict(row)

    def delete_source_if_unlinked(
        self, member_id: str, resource_id: str
    ) -> Optional[dict[str, Any]]:
        """Delete an unlinked upload record and transactionally queue its file."""
        self.init_db()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM report_sources WHERE member_id = ? AND resource_id = ?",
                (member_id, resource_id),
            ).fetchone()
            if row is None:
                return None
            linked = connection.execute(
                """
                SELECT 1 FROM report_source_links
                WHERE member_id = ? AND resource_id = ? LIMIT 1
                """,
                (member_id, resource_id),
            ).fetchone()
            if linked is not None:
                return None
            self.facts.enqueue_file_cleanup(
                ReportTransaction(connection), member_id, row["relative_path"]
            )
            connection.execute(
                "DELETE FROM report_sources WHERE member_id = ? AND resource_id = ?",
                (member_id, resource_id),
            )
            return dict(row)

    def file_cleanup_jobs(
        self, member_id: str | None = None, *, limit: int = 8
    ) -> list[dict[str, Any]]:
        """Return a small member_id-scoped batch of durable source cleanup jobs."""
        self.init_db()
        safe_limit = max(1, min(int(limit), 50))
        with connect(self.paths.reports_db(self.account_id)) as connection:
            return cleanup_batch(connection, "report_source_file_cleanup_outbox",
                scope=self.paths.reports_db(self.account_id),
                where="(? IS NULL OR member_id = ?)", parameters=(member_id, member_id),
                limit=safe_limit)

    def file_cleanup_count(self, member_id: str) -> int:
        with connect(self.paths.reports_db(self.account_id)) as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM report_source_file_cleanup_outbox WHERE member_id = ?",
                    (member_id,),
                ).fetchone()[0]
            )

    def complete_file_cleanup(self, member_id: str, cleanup_id: str) -> bool:
        self.init_db()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            cursor = connection.execute(
                """
                DELETE FROM report_source_file_cleanup_outbox
                WHERE member_id = ? AND cleanup_id = ?
                """,
                (member_id, cleanup_id),
            )
        return cursor.rowcount > 0

    def record_file_cleanup_attempt(self, member_id: str, cleanup_id: str) -> bool:
        """Record a retry without persisting filesystem paths or error details."""
        self.init_db()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            cursor = connection.execute(
                """
                UPDATE report_source_file_cleanup_outbox
                SET attempt_count = attempt_count + 1, last_attempt_at = ?
                WHERE member_id = ? AND cleanup_id = ?
                """,
                (_now_iso(), member_id, cleanup_id),
            )
        return cursor.rowcount > 0

    def update_source_kind(
        self, member_id: str, resource_id: str, source_kind: str
    ) -> bool:
        if source_kind not in {"screenshot", "scan", "pdf", "photo", "unknown"}:
            return False
        self.init_db()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            cursor = connection.execute(
                """
                UPDATE report_sources SET source_kind = ?
                WHERE member_id = ? AND resource_id = ?
                """,
                (source_kind, member_id, resource_id),
            )
        return cursor.rowcount > 0

    def report_ids_for_source(self, member_id: str, resource_id: str) -> list[str]:
        self.init_db()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            rows = connection.execute(
                """
                SELECT report_id FROM report_source_links
                WHERE member_id = ? AND resource_id = ? ORDER BY report_id
                """,
                (member_id, resource_id),
            ).fetchall()
        return [row["report_id"] for row in rows]

    def link_source(self, member_id: str, report_id: str, resource_id: str) -> bool:
        result = self.link_report_sources(
            member_id,
            report_id=report_id,
            resource_ids=[resource_id],
        )
        return bool(result["linked_resource_ids"])

    def source_digests_for_report(self, member_id: str, report_id: str) -> set[str]:
        self.init_db()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            rows = connection.execute(
                """
                SELECT f.sha256
                FROM report_source_links l
                JOIN report_sources f
                  ON f.resource_id = l.resource_id AND f.member_id = l.member_id
                WHERE l.member_id = ? AND l.report_id = ?
                """,
                (member_id, report_id),
            ).fetchall()
        return {str(row["sha256"]) for row in rows}

    def link_parsed_report_sources(
        self,
        member_id: str,
        *,
        report_id: str,
        resource_ids: list[str],
    ) -> dict[str, Any]:
        return self.link_report_sources(
            member_id,
            report_id=report_id,
            resource_ids=resource_ids,
        )

    def link_report_sources(
        self,
        member_id: str,
        *,
        report_id: str,
        resource_ids: list[str],
        reject_duplicate_content: bool = False,
    ) -> dict[str, Any]:
        """Link existing source rows and make the first source primary when needed."""

        unique_resource_ids = list(
            dict.fromkeys(str(resource_id) for resource_id in resource_ids)
        )
        if not unique_resource_ids or any(
            not resource_id for resource_id in unique_resource_ids
        ):
            raise ValueError("关联医疗报告必须至少包含一个来源。")
        self.init_db()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if (
                connection.execute(
                    "SELECT 1 FROM reports WHERE member_id = ? AND report_id = ?",
                    (member_id, report_id),
                ).fetchone()
                is None
            ):
                raise LookupError("目标医疗报告不存在。")

            placeholders = ",".join("?" for _ in unique_resource_ids)
            source_rows = connection.execute(
                f"""
                SELECT resource_id, sha256 FROM report_sources
                WHERE member_id = ? AND resource_id IN ({placeholders})
                """,
                (member_id, *unique_resource_ids),
            ).fetchall()
            available_resource_ids = {str(row["resource_id"]) for row in source_rows}
            missing_resource_ids = [
                resource_id
                for resource_id in unique_resource_ids
                if resource_id not in available_resource_ids
            ]
            if missing_resource_ids:
                raise LookupError("要关联的医疗报告原件不存在。")

            if reject_duplicate_content:
                digests = [str(row["sha256"]) for row in source_rows]
                existing_digests = {str(row[0]) for row in connection.execute(
                    """SELECT f.sha256 FROM report_source_links l
                    JOIN report_sources f ON f.resource_id = l.resource_id AND f.member_id = l.member_id
                    WHERE l.member_id = ? AND l.report_id = ?""", (member_id, report_id)
                )}
                if len(digests) != len(set(digests)) or existing_digests.intersection(digests):
                    raise_error("conflict", "REPORT_SOURCE_DUPLICATE", "所选原件已关联到该医疗报告。")

            existing_source_count = int(
                connection.execute(
                    """
                SELECT COUNT(*) FROM report_source_links
                WHERE member_id = ? AND report_id = ?
                """,
                    (member_id, report_id),
                ).fetchone()[0]
            )
            timestamp = _now_iso()
            linked_resource_ids: list[str] = []
            for source_index, resource_id in enumerate(unique_resource_ids):
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO report_source_links(
                        report_id, resource_id, member_id, is_primary, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        resource_id,
                        member_id,
                        int(existing_source_count == 0 and source_index == 0),
                        timestamp,
                    ),
                )
                if cursor.rowcount:
                    linked_resource_ids.append(resource_id)
            if linked_resource_ids:
                connection.execute(
                    "UPDATE reports SET updated_at = ? WHERE member_id = ? AND report_id = ?",
                    (timestamp, member_id, report_id),
                )
        return {"report_id": report_id, "linked_resource_ids": linked_resource_ids}

    def source_for_report(
        self, member_id: str, report_id: str, resource_id: str
    ) -> Optional[dict[str, Any]]:
        self.init_db()
        with connect(self.paths.reports_db(self.account_id)) as connection:
            row = connection.execute(
                """
                SELECT f.* FROM report_sources f
                JOIN report_source_links l ON l.resource_id = f.resource_id AND l.member_id = f.member_id
                JOIN reports r ON r.report_id = l.report_id AND r.member_id = l.member_id
                WHERE r.member_id = ? AND r.report_id = ? AND f.resource_id = ?
                """,
                (member_id, report_id, resource_id),
            ).fetchone()
        return _row_dict(row)

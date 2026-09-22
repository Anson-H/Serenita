import hashlib
import os
import unicodedata
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

from backend.app.core.errors import raise_error
from backend.app.core.time import (
    local_iso,
    local_now,
    local_now_iso,
    parse_local_datetime,
)
from backend.app.domain.conversations.events import (
    SessionEventCorruptionError,
)
from backend.app.storage.paths import ensure_private_directory
from backend.app.storage.sqlite import (
    connect,
)


now_iso = local_now_iso

MAX_ATTACHMENT_FILENAME_BYTES = 180


ATTACHMENT_PENDING_TTL = timedelta(hours=24)


ATTACHMENT_WRITE_STALE_AFTER = timedelta(minutes=5)


def _truncate_utf8(value: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _filename_parts(filename: str) -> tuple[str, str]:
    suffix = Path(filename).suffix
    if not suffix:
        return filename, ""
    return filename[: -len(suffix)], suffix


def normalize_attachment_name(filename: Any, fallback_extension: str) -> str:
    """Return the safe, user-visible filename retained for an upload."""
    leaf = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    leaf = unicodedata.normalize("NFC", leaf)
    leaf = "".join(
        character
        for character in leaf
        if character not in {"/", "\\"}
        and not unicodedata.category(character).startswith("C")
    )
    leaf = leaf.strip().rstrip(" .")
    if not leaf:
        normalized_extension = str(fallback_extension or "").strip().lower()
        if normalized_extension and not normalized_extension.startswith("."):
            normalized_extension = f".{normalized_extension}"
        leaf = f"upload{normalized_extension}"

    stem, suffix = _filename_parts(leaf)
    suffix = _truncate_utf8(suffix, MAX_ATTACHMENT_FILENAME_BYTES)
    stem = _truncate_utf8(
        stem,
        MAX_ATTACHMENT_FILENAME_BYTES - len(suffix.encode("utf-8")),
    )
    normalized = f"{stem}{suffix}".strip().rstrip(" .")
    return normalized or "upload"


def attachment_resource_id(original_filename: str, ordinal: int) -> str:
    """Insert a stable upload ordinal before the final filename extension."""
    if ordinal < 1:
        raise ValueError("attachment ordinal must be positive")
    if ordinal == 1:
        return original_filename
    stem, suffix = _filename_parts(original_filename)
    marker = f"-{ordinal:03d}"
    marker_bytes = len(marker.encode("utf-8"))
    suffix = _truncate_utf8(
        suffix,
        MAX_ATTACHMENT_FILENAME_BYTES - marker_bytes,
    )
    reserved_bytes = marker_bytes + len(suffix.encode("utf-8"))
    stem = _truncate_utf8(stem, MAX_ATTACHMENT_FILENAME_BYTES - reserved_bytes)
    return f"{stem}{marker}{suffix}"


def _filename_collision_key(filename: str) -> str:
    return unicodedata.normalize("NFC", filename).casefold()


class ConversationAttachments:
    def __init__(self, paths, *, initialize, session_row):
        self.paths = paths
        self.init_db = initialize
        self.session_row = session_row

    def resource_row(self, account_id: str, session_id: str, resource_id: str):
        if self.session_row(account_id, session_id) is None:
            return None
        with connect(self.paths.conversations_db(account_id)) as connection:
            return connection.execute(
                """
                SELECT * FROM conversation_resources
                WHERE session_id = ? AND resource_id = ?
                """,
                (session_id, resource_id),
            ).fetchone()

    def set_resource_lifecycle_status(
        self,
        account_id: str,
        session_id: str,
        resource_id: str,
        lifecycle_status: str,
        timestamp: Optional[str] = None,
    ) -> None:
        with connect(self.paths.conversations_db(account_id)) as connection:
            connection.execute(
                """
                UPDATE conversation_resources
                SET lifecycle_status = ?,
                    expires_at = CASE WHEN ? = 'attached' THEN NULL ELSE expires_at END,
                    updated_at = ?
                WHERE session_id = ? AND resource_id = ?
                """,
                (
                    lifecycle_status,
                    lifecycle_status,
                    timestamp or now_iso(),
                    session_id,
                    resource_id,
                ),
            )

    def expire_resource(
        self, account_id: str, session_id: str, resource_id: str
    ) -> bool:
        """Expire a pending resource and durably queue its private file."""
        self.init_db(account_id)
        timestamp = now_iso()
        with connect(self.paths.conversations_db(account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT relative_path FROM conversation_resources
                WHERE session_id = ? AND resource_id = ?
                  AND storage_status = 'ready'
                  AND lifecycle_status = 'pending'
                """,
                (session_id, resource_id),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                """
                UPDATE conversation_resources
                SET lifecycle_status = ?, updated_at = ?
                WHERE session_id = ? AND resource_id = ?
                  AND storage_status = 'ready'
                  AND lifecycle_status = 'pending'
                """,
                ("expired", timestamp, session_id, resource_id),
            )
            queued = self.enqueue_if_attachment_unreferenced(
                connection, account_id, row["relative_path"]
            )
            if not queued:
                connection.execute(
                    """
                    UPDATE conversation_resources
                    SET lifecycle_status = 'deleted', updated_at = ?
                    WHERE session_id = ? AND resource_id = ?
                    """,
                    (timestamp, session_id, resource_id),
                )
        return True

    def expire_due_resources(
        self, account_id: str, *, as_of: Optional[str] = None, limit: int = 50
    ) -> int:
        """Expire due pending resources and persist cleanup jobs together."""
        self.init_db(account_id)
        safe_limit = max(1, min(int(limit), 200))
        timestamp = local_iso(as_of) if as_of else now_iso()
        with connect(self.paths.conversations_db(account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT resources.session_id, resources.resource_id, resources.relative_path
                FROM conversation_resources AS resources
                LEFT JOIN conversation_resource_cleanup_outbox AS cleanup
                  ON cleanup.relative_path = resources.relative_path
                WHERE resources.expires_at IS NOT NULL
                  AND resources.expires_at <= ?
                  AND resources.storage_status = 'ready'
                  AND resources.lifecycle_status = 'pending'
                  AND cleanup.cleanup_id IS NULL
                ORDER BY resources.expires_at, resources.resource_id
                LIMIT ?
                """,
                (timestamp, safe_limit),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE conversation_resources
                    SET lifecycle_status = ?, updated_at = ?
                    WHERE session_id = ? AND resource_id = ?
                      AND storage_status = 'ready'
                      AND lifecycle_status = 'pending'
                    """,
                    (
                        "expired",
                        timestamp,
                        row["session_id"],
                        row["resource_id"],
                    ),
                )
                queued = self.enqueue_if_attachment_unreferenced(
                    connection,
                    account_id,
                    row["relative_path"],
                )
                if not queued:
                    connection.execute(
                        """
                        UPDATE conversation_resources
                        SET lifecycle_status = 'deleted', updated_at = ?
                        WHERE session_id = ? AND resource_id = ?
                        """,
                        (
                            timestamp,
                            row["session_id"],
                            row["resource_id"],
                        ),
                    )
        return len(rows)

    def attachment_cleanup_jobs(
        self, account_id: str, *, limit: int = 16
    ) -> list[dict[str, Any]]:
        self.init_db(account_id)
        safe_limit = max(1, min(int(limit), 100))
        with connect(self.paths.conversations_db(account_id)) as connection:
            rows = connection.execute(
                """
                SELECT cleanup_id, relative_path, attempt_count
                FROM conversation_resource_cleanup_outbox
                ORDER BY attempt_count, created_at, cleanup_id
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def complete_attachment_cleanup(self, account_id: str, cleanup_id: str) -> bool:
        self.init_db(account_id)
        with connect(self.paths.conversations_db(account_id)) as connection:
            row = connection.execute(
                """
                SELECT relative_path FROM conversation_resource_cleanup_outbox
                WHERE cleanup_id = ?
                """,
                (cleanup_id,),
            ).fetchone()
            if row is None:
                return False
            cursor = connection.execute(
                """
                DELETE FROM conversation_resource_cleanup_outbox
                WHERE cleanup_id = ?
                """,
                (cleanup_id,),
            )
            connection.execute(
                """
                UPDATE conversation_resources
                SET lifecycle_status = 'deleted', updated_at = ?
                WHERE relative_path = ?
                  AND lifecycle_status IN ('expired', 'deleted')
                """,
                (now_iso(), row["relative_path"]),
            )
        return cursor.rowcount > 0

    def record_attachment_cleanup_attempt(
        self, account_id: str, cleanup_id: str
    ) -> bool:
        self.init_db(account_id)
        with connect(self.paths.conversations_db(account_id)) as connection:
            cursor = connection.execute(
                """
                UPDATE conversation_resource_cleanup_outbox
                SET attempt_count = attempt_count + 1, last_attempt_at = ?
                WHERE cleanup_id = ?
                """,
                (now_iso(), cleanup_id),
            )
        return cursor.rowcount > 0

    def attachment_cleanup_path(
        self, account_id: str, relative_path: str
    ) -> Optional[Path]:
        """Resolve only an account_id's conversation attachment tree."""
        try:
            account_root = self.paths.account_root(account_id).resolve()
            conversations_root = account_root / "conversations"
            attachments_path = conversations_root / "attachments"
            if conversations_root.is_symlink() or attachments_path.is_symlink():
                return None
            attachments_root = attachments_path.resolve()
            if not attachments_root.is_relative_to(account_root):
                return None
            candidate = account_root / str(relative_path)
            resolved_candidate = candidate.resolve()
            if (
                resolved_candidate == attachments_root
                or not resolved_candidate.is_relative_to(attachments_root)
            ):
                return None
        except (OSError, TypeError, ValueError):
            return None
        return candidate

    def remove_empty_attachment_dirs(self, account_id: str, path: Path) -> None:
        """Remove empty parents without ever crossing the account_id attachment root."""
        try:
            account_root = self.paths.account_root(account_id).resolve()
            conversations_root = account_root / "conversations"
            attachments_path = conversations_root / "attachments"
            if conversations_root.is_symlink() or attachments_path.is_symlink():
                return
            attachments_root = attachments_path.resolve()
            if not attachments_root.is_relative_to(account_root):
                return
            current = path.resolve()
            if current == attachments_root or not current.is_relative_to(
                attachments_root
            ):
                return
        except (OSError, ValueError):
            return
        while current != attachments_root:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    def insert_ready_resource(
        self,
        account_id: str,
        session_id: str,
        resource_id: str,
        original_filename: str,
        mime_type: str,
        size_bytes: int,
        relative_path: str,
        sha256: str,
        expires_at: str,
        timestamp: str,
    ) -> None:
        local_expires_at = local_iso(expires_at)
        local_timestamp = local_iso(timestamp)
        with connect(self.paths.conversations_db(account_id)) as connection:
            connection.execute(
                """
                INSERT INTO conversation_resources (
                    session_id, resource_id, original_filename, mime_type, size_bytes,
                    relative_path, sha256, storage_status, lifecycle_status,
                    expires_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'ready', 'pending', ?, ?, ?)
                """,
                (
                    session_id,
                    resource_id,
                    original_filename,
                    mime_type,
                    size_bytes,
                    relative_path,
                    sha256,
                    local_expires_at,
                    local_timestamp,
                    local_timestamp,
                ),
            )

    def discard_writing_resource(
        self,
        account_id: str,
        session_id: str,
        resource_id: str,
        *,
        queue_cleanup: bool,
    ) -> bool:
        """Remove an incomplete write intent and optionally queue its exact path."""
        with connect(self.paths.conversations_db(account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT relative_path FROM conversation_resources
                WHERE session_id = ? AND resource_id = ?
                  AND storage_status = 'writing'
                  AND lifecycle_status = 'pending'
                """,
                (session_id, resource_id),
            ).fetchone()
            if row is None:
                return False
            cursor = connection.execute(
                """
                DELETE FROM conversation_resources
                WHERE session_id = ? AND resource_id = ?
                  AND storage_status = 'writing'
                  AND lifecycle_status = 'pending'
                """,
                (session_id, resource_id),
            )
            if cursor.rowcount and queue_cleanup:
                self.enqueue_attachment_cleanup_on_connection(
                    connection,
                    account_id,
                    str(row["relative_path"]),
                )
        return cursor.rowcount > 0

    def mark_resource_ready(
        self,
        account_id: str,
        session_id: str,
        resource_id: str,
        *,
        expires_at: str,
        timestamp: str,
    ) -> None:
        local_expires_at = local_iso(expires_at)
        local_timestamp = local_iso(timestamp)
        with connect(self.paths.conversations_db(account_id)) as connection:
            cursor = connection.execute(
                """
                UPDATE conversation_resources
                SET storage_status = 'ready', expires_at = ?, updated_at = ?
                WHERE session_id = ? AND resource_id = ?
                  AND storage_status = 'writing'
                  AND lifecycle_status = 'pending'
                """,
                (
                    local_expires_at,
                    local_timestamp,
                    session_id,
                    resource_id,
                ),
            )
            if cursor.rowcount != 1:
                row = connection.execute(
                    """
                    SELECT storage_status FROM conversation_resources
                    WHERE session_id = ? AND resource_id = ?
                    """,
                    (session_id, resource_id),
                ).fetchone()
                if row is None or row["storage_status"] != "ready":
                    raise RuntimeError("attachment write intent is unavailable")

    @staticmethod
    def _resource_file_matches(path: Path, *, size_bytes: int, sha256: str) -> bool:
        if path.is_symlink() or not path.is_file() or size_bytes < 0:
            return False
        digest = hashlib.sha256()
        total = 0
        try:
            with path.open("rb") as handle:
                while total <= size_bytes:
                    chunk = handle.read(min(1024 * 1024, size_bytes + 1 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    digest.update(chunk)
        except OSError:
            return False
        return total == size_bytes and digest.hexdigest() == sha256

    def recover_writing_resources(
        self,
        account_id: str,
        *,
        as_of: str | None = None,
        limit: int = 100,
    ) -> dict[str, int]:
        """Finalize complete writes and discard stale incomplete write intents."""
        self.init_db(account_id)
        current = parse_local_datetime(as_of) if as_of else local_now()
        timestamp = current.isoformat()
        stale_before = current - ATTACHMENT_WRITE_STALE_AFTER
        expires_at = (current + ATTACHMENT_PENDING_TTL).isoformat()
        safe_limit = max(1, min(int(limit), 200))
        with connect(self.paths.conversations_db(account_id)) as connection:
            rows = connection.execute(
                """
                SELECT session_id, resource_id, relative_path, size_bytes,
                       sha256, updated_at
                FROM conversation_resources
                WHERE storage_status = 'writing'
                  AND lifecycle_status = 'pending'
                ORDER BY updated_at, session_id, resource_id
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        recovered = 0
        discarded = 0
        for row in rows:
            path = self.attachment_cleanup_path(account_id, str(row["relative_path"]))
            if path is not None and self._resource_file_matches(
                path,
                size_bytes=int(row["size_bytes"]),
                sha256=str(row["sha256"]),
            ):
                with connect(self.paths.conversations_db(account_id)) as connection:
                    cursor = connection.execute(
                        """
                        UPDATE conversation_resources
                        SET storage_status = 'ready', expires_at = ?, updated_at = ?
                        WHERE session_id = ? AND resource_id = ?
                          AND storage_status = 'writing'
                          AND lifecycle_status = 'pending'
                        """,
                        (
                            expires_at,
                            timestamp,
                            row["session_id"],
                            row["resource_id"],
                        ),
                    )
                recovered += int(cursor.rowcount > 0)
                continue

            if parse_local_datetime(str(row["updated_at"])) >= stale_before:
                continue
            discarded += int(
                self.discard_writing_resource(
                    account_id,
                    str(row["session_id"]),
                    str(row["resource_id"]),
                    queue_cleanup=path is not None,
                )
            )
        return {"recovered": recovered, "discarded": discarded}

    def create_uploaded_resource(
        self,
        *,
        account_id: str,
        session_id: str,
        original_filename: Any,
        fallback_extension: str,
        mime_type: str,
        content: bytes,
    ) -> dict[str, Any]:
        """Reserve a never-reused filename, persist bytes, then mark it ready."""
        self.init_db(account_id)
        original_filename = normalize_attachment_name(
            original_filename, fallback_extension
        )
        created_at = now_iso()
        sha256 = hashlib.sha256(content).hexdigest()
        account_root = self.paths.account_root(account_id)
        session_directory = account_root / "conversations" / "attachments" / session_id
        ensure_private_directory(session_directory)
        while True:
            with connect(self.paths.conversations_db(account_id)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                if (
                    connection.execute(
                        "SELECT 1 FROM conversations WHERE session_id = ?",
                        (session_id,),
                    ).fetchone()
                    is None
                ):
                    raise_error("missing", "NOT_FOUND", "聊天不存在。")

                used_names = {
                    _filename_collision_key(str(row["resource_id"]))
                    for row in connection.execute(
                        """
                        SELECT resource_id FROM conversation_resources
                        WHERE session_id = ?
                        """,
                        (session_id,),
                    ).fetchall()
                }
                try:
                    used_names.update(
                        _filename_collision_key(entry.name)
                        for entry in session_directory.iterdir()
                    )
                except FileNotFoundError:
                    ensure_private_directory(session_directory)

                ordinal = 1
                while True:
                    resource_id = attachment_resource_id(original_filename, ordinal)
                    collision_key = _filename_collision_key(resource_id)
                    if collision_key in used_names:
                        ordinal += 1
                        continue
                    relative_path = (
                        f"conversations/attachments/{session_id}/{resource_id}"
                    )
                    candidate = self.attachment_cleanup_path(account_id, relative_path)
                    if candidate is None or candidate.parent != session_directory:
                        raise SessionEventCorruptionError(
                            "attachment filename escaped its session directory"
                        )
                    connection.execute(
                        """
                        INSERT INTO conversation_resources (
                            session_id, resource_id, original_filename, mime_type, size_bytes,
                            relative_path, sha256, storage_status, lifecycle_status,
                            expires_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'writing', 'pending', NULL, ?, ?)
                        """,
                        (
                            session_id,
                            resource_id,
                            original_filename,
                            mime_type,
                            len(content),
                            relative_path,
                            sha256,
                            created_at,
                            created_at,
                        ),
                    )
                    break

            try:
                descriptor = os.open(
                    candidate,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError:
                self.discard_writing_resource(
                    account_id,
                    session_id,
                    resource_id,
                    queue_cleanup=False,
                )
                continue
            except Exception:
                self.discard_writing_resource(
                    account_id,
                    session_id,
                    resource_id,
                    queue_cleanup=True,
                )
                raise

            try:
                with os.fdopen(descriptor, "wb") as attachment_file:
                    written = attachment_file.write(content)
                    if written != len(content):
                        raise OSError("attachment write was incomplete")
                    attachment_file.flush()
                    os.fsync(attachment_file.fileno())
            except Exception:
                self.discard_writing_resource(
                    account_id,
                    session_id,
                    resource_id,
                    queue_cleanup=True,
                )
                raise

            ready_at = local_now()
            ready_timestamp = ready_at.isoformat()
            expires_at = (ready_at + ATTACHMENT_PENDING_TTL).isoformat()
            self.mark_resource_ready(
                account_id,
                session_id,
                resource_id,
                expires_at=expires_at,
                timestamp=ready_timestamp,
            )
            return {
                "resource_id": resource_id,
                "original_filename": original_filename,
                "mime_type": mime_type,
                "size_bytes": len(content),
                "relative_path": relative_path,
                "sha256": sha256,
                "storage_status": "ready",
                "lifecycle_status": "pending",
                "expires_at": expires_at,
            }

    def file_resource_attachment_payloads(
        self,
        account_id: str,
        session_id: str,
        references: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        self.session_row(account_id, session_id)
        attached: list[dict[str, Any]] = []
        with connect(self.paths.conversations_db(account_id)) as connection:
            for reference in references:
                if reference["resource_type"] != "file":
                    continue
                resource = connection.execute(
                    """
                    SELECT * FROM conversation_resources
                    WHERE session_id = ? AND resource_id = ?
                    """,
                    (session_id, reference["resource_id"]),
                ).fetchone()
                if resource is None:
                    raise_error("missing", "NOT_FOUND", "上下文资源不存在。")
                if resource["storage_status"] != "ready":
                    raise_error(
                        "conflict", "RESOURCE_NOT_READY", "上下文资源尚未完成写入。"
                    )
                if resource["lifecycle_status"] in {"expired", "deleted"}:
                    raise_error(
                        "invalid_input", "INVALID_REQUEST", "上下文资源已过期。"
                    )
                attached.append(
                    {
                        "resource_id": resource["resource_id"],
                        "original_filename": resource["original_filename"],
                        "mime_type": resource["mime_type"],
                        "size_bytes": resource["size_bytes"],
                        "relative_path": resource["relative_path"],
                        "sha256": resource["sha256"],
                    }
                )
        return attached

    def mark_file_resources_attached(
        self,
        account_id: str,
        session_id: str,
        resource_ids: list[str],
    ) -> None:
        if not resource_ids:
            return
        with connect(self.paths.conversations_db(account_id)) as connection:
            for resource_id in resource_ids:
                connection.execute(
                    """
                    UPDATE conversation_resources
                    SET lifecycle_status = 'attached', expires_at = NULL, updated_at = ?
                    WHERE session_id = ? AND resource_id = ?
                      AND storage_status = 'ready'
                      AND lifecycle_status IN ('pending', 'attached')
                    """,
                    (now_iso(), session_id, resource_id),
                )

    def enqueue_attachment_cleanup_on_connection(
        self,
        connection,
        account_id: str,
        relative_path: str,
    ) -> bool:
        """Queue only a normalized path beneath this account_id's attachment root."""
        candidate = self.attachment_cleanup_path(account_id, relative_path)
        if candidate is None:
            return False
        account_root = self.paths.account_root(account_id).resolve()
        try:
            normalized_path = candidate.resolve().relative_to(account_root).as_posix()
        except (OSError, ValueError):
            return False
        cleanup_id = hashlib.sha256(
            f"{account_id}\0{normalized_path}".encode("utf-8")
        ).hexdigest()
        connection.execute(
            """
            INSERT OR IGNORE INTO conversation_resource_cleanup_outbox(
                cleanup_id, relative_path, attempt_count, created_at
            ) VALUES (?, ?, 0, ?)
            """,
            (cleanup_id, normalized_path, now_iso()),
        )
        return True

    def enqueue_if_attachment_unreferenced(
        self,
        connection,
        account_id: str,
        relative_path: str,
    ) -> bool:
        """Keep shared immutable attachments until the last live reference is gone."""
        live_reference = connection.execute(
            """
            SELECT 1 FROM conversation_resources
            WHERE relative_path = ?
              AND lifecycle_status NOT IN ('expired', 'deleted')
            LIMIT 1
            """,
            (relative_path,),
        ).fetchone()
        if live_reference is not None:
            return True
        return self.enqueue_attachment_cleanup_on_connection(
            connection,
            account_id,
            relative_path,
        )

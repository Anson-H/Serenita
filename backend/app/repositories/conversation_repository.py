from backend.app.domain.conversations.titles import UNTITLED_CONVERSATION
from backend.app.repositories.conversation_index import ConversationIndex
from backend.app.repositories.turn_index import TurnIndex
from backend.app.repositories.conversation_attachments import ConversationAttachments
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Optional

from backend.app.core.errors import raise_error
from backend.app.core.member_lifecycle import member_lifecycle_operation
from backend.app.repositories.member_repository import MemberRepository
from backend.app.core.member_errors import member_error
from backend.app.domain.conversations.timeline import active_records, records_from_events
from backend.app.domain.conversations.queries import messages_from_events
from backend.app.core.time import (
    local_datetime_from_epoch_ms,
    local_now_iso,
)
from backend.app.domain.conversations.events import (
    SessionEvent,
    SessionEventCorruptionError,
    SessionHeader,
    iso_to_epoch_ms,
    make_event,
)
from backend.app.core.conversation_tasks import tasks_for_paths
from backend.app.storage.paths import app_paths
from backend.app.storage.session_persistence import (
    JsonlSessionPersistence,
    StoredSession,
    UnsupportedSessionLogError,
    SessionPersistence,
)
from backend.app.storage.sqlite import (
    UnsupportedSchemaError,
    connect,
)


now_iso = local_now_iso

_SESSION_MEMBER_UNSET = object()

USER_MESSAGE_CONTEXT_UPDATE_FIELDS = frozenset(
    {
        "content",
        "model_id",
        "thinking_mode",
        "context_resources",
    }
)


class ConversationRepository:
    def __init__(
        self, persistence: SessionPersistence | None = None, *, paths=None, members=None
    ):
        self.paths = paths or app_paths()
        self.notifications = tasks_for_paths(self.paths).notifications
        self.members = members or MemberRepository(paths=self.paths)
        self.persistence = persistence or JsonlSessionPersistence(paths=self.paths)
        self.index = ConversationIndex(self.paths)
        self.turns = TurnIndex(
            self.paths,
            initialize=self.init_db,
            session_row=lambda *args: self.session_row(*args),
        )
        self.attachments = ConversationAttachments(
            self.paths,
            initialize=self.init_db,
            session_row=lambda *args: self.session_row(*args),
        )

    def validate_existing_database(self, account_id: str) -> bool:
        return self.index.validate_existing_database(account_id)

    def init_db(self, account_id: str) -> None:
        return self.index.init_db(account_id)

    def session_row(self, account_id: str, session_id: str):
        return self.index.session_row(account_id, session_id)

    def has_closed_turn(self, account_id: str, session_id: str) -> bool:
        return self.index.has_closed_turn(account_id, session_id)

    def touch_session(
        self,
        account_id: str,
        session_id: str,
    ) -> None:
        return self.index.touch_session(account_id, session_id)

    def initial_session_title(self, user_input: str) -> str:
        return self.index.initial_session_title(user_input)

    def set_initial_session_title(
        self,
        account_id: str,
        session_id: str,
        title: str,
    ) -> bool:
        return self.index.set_initial_session_title(account_id, session_id, title)

    def replace_initial_session_title(
        self,
        account_id: str,
        session_id: str,
        initial_title: str,
        generated_title: str,
    ) -> bool:
        return self.index.replace_initial_session_title(
            account_id, session_id, initial_title, generated_title
        )

    def update_session_metadata(
        self,
        account_id: str,
        session_id: str,
        *,
        title: str | None = None,
        is_pinned: bool | None = None,
    ):
        return self.index.update_session_metadata(
            account_id, session_id, title=title, is_pinned=is_pinned
        )

    def batch_set_pinned(
        self,
        account_id: str,
        session_ids: list[str],
        is_pinned: bool,
    ) -> list[Any]:
        return self.index.batch_set_pinned(account_id, session_ids, is_pinned)

    def clean_generated_session_title(self, raw_title: str) -> str:
        return self.index.clean_generated_session_title(raw_title)

    def generate_session_title(self, title_seed: str) -> str:
        return self.index.generate_session_title(title_seed)

    def list_sessions(self, account_id: str, *, cursor=None, limit=24):
        return self.index.list_sessions(account_id, cursor=cursor, limit=limit)

    def conversation_exists(self, account_id: str, session_id: str) -> bool:
        return self.index.conversation_exists(account_id, session_id)

    def validate_no_pending_turn(self, account_id: str, session_id: str) -> None:
        return self.turns.validate_no_pending_turn(account_id, session_id)

    def insert_turn(
        self,
        account_id: str,
        session_id: str,
        turn_id: str,
        user_message_id: Optional[str],
        final_assistant_message_id: Optional[str],
        stream_id: str,
        status: str,
        error_code: Optional[str],
        error_message: Optional[str],
        created_at: str,
        updated_at: str,
    ) -> None:
        return self.turns.insert_turn(
            account_id,
            session_id,
            turn_id,
            user_message_id,
            final_assistant_message_id,
            stream_id,
            status,
            error_code,
            error_message,
            created_at,
            updated_at,
        )

    def claim_turn_job(self, account_id: str, session_id: str, turn_id: str) -> bool:
        return self.turns.claim_turn_job(account_id, session_id, turn_id)

    def touch_turn_job(self, account_id: str, session_id: str, turn_id: str) -> None:
        return self.turns.touch_turn_job(account_id, session_id, turn_id)

    def expired_turn_job_sessions(self, account_id: str, cutoff: str) -> list[str]:
        return self.turns.expired_turn_job_sessions(account_id, cutoff)

    def expire_turn_jobs(self, account_id: str, session_id: str, cutoff: str) -> list[dict[str, Any]]:
        return self.turns.expire_turn_jobs(account_id, session_id, cutoff)

    def update_turn_completed(
        self,
        account_id: str,
        session_id: str,
        turn_id: str,
        final_assistant_message_id: Optional[str],
        timestamp: Optional[str] = None,
        *,
        notification_event=None,
    ) -> None:
        return self.turns.update_turn_completed(
            account_id, session_id, turn_id, final_assistant_message_id, timestamp,
            notification_event=notification_event,
        )

    def update_turn_failed(
        self,
        account_id: str,
        session_id: str,
        turn_id: str,
        error_code: str,
        error_message: str,
        timestamp: Optional[str] = None,
    ) -> None:
        return self.turns.update_turn_failed(
            account_id, session_id, turn_id, error_code, error_message, timestamp
        )

    def update_turn_cancelled(
        self,
        account_id: str,
        session_id: str,
        turn_id: str,
        final_assistant_message_id: Optional[str],
        error_code: str = "CANCELLED",
        error_message: str = "生成已取消。",
        timestamp: Optional[str] = None,
    ) -> None:
        return self.turns.update_turn_cancelled(
            account_id,
            session_id,
            turn_id,
            final_assistant_message_id,
            error_code,
            error_message,
            timestamp,
        )

    def turn_row(self, account_id: str, session_id: str, turn_id: str):
        return self.turns.turn_row(account_id, session_id, turn_id)

    def turn_by_stream_id(self, account_id: str, session_id: str, stream_id: str):
        return self.turns.turn_by_stream_id(account_id, session_id, stream_id)

    def list_pending_turn_rows(self, account_id: str, session_id: str):
        return self.turns.list_pending_turn_rows(account_id, session_id)

    def pending_turn_status(self, account_id: str, session_id: str) -> str | None:
        return self.turns.pending_turn_status(account_id, session_id)

    def list_turn_rows(self, account_id: str, session_id: str):
        return self.turns.list_turn_rows(account_id, session_id)

    def resource_row(self, account_id: str, session_id: str, resource_id: str):
        return self.attachments.resource_row(account_id, session_id, resource_id)

    def set_resource_lifecycle_status(
        self,
        account_id: str,
        session_id: str,
        resource_id: str,
        lifecycle_status: str,
        timestamp: Optional[str] = None,
    ) -> None:
        return self.attachments.set_resource_lifecycle_status(
            account_id, session_id, resource_id, lifecycle_status, timestamp
        )

    def expire_resource(
        self, account_id: str, session_id: str, resource_id: str
    ) -> bool:
        return self.attachments.expire_resource(account_id, session_id, resource_id)

    def expire_due_resources(
        self, account_id: str, *, as_of: Optional[str] = None, limit: int = 50
    ) -> int:
        return self.attachments.expire_due_resources(
            account_id, as_of=as_of, limit=limit
        )

    def attachment_cleanup_jobs(
        self, account_id: str, *, limit: int = 16
    ) -> list[dict[str, Any]]:
        return self.attachments.attachment_cleanup_jobs(account_id, limit=limit)

    def complete_attachment_cleanup(self, account_id: str, cleanup_id: str) -> bool:
        return self.attachments.complete_attachment_cleanup(account_id, cleanup_id)

    def record_attachment_cleanup_attempt(
        self, account_id: str, cleanup_id: str
    ) -> bool:
        return self.attachments.record_attachment_cleanup_attempt(
            account_id, cleanup_id
        )

    def attachment_cleanup_path(
        self, account_id: str, relative_path: str
    ) -> Optional[Path]:
        return self.attachments.attachment_cleanup_path(account_id, relative_path)

    def remove_empty_attachment_dirs(self, account_id: str, path: Path) -> None:
        return self.attachments.remove_empty_attachment_dirs(account_id, path)

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
        return self.attachments.insert_ready_resource(
            account_id,
            session_id,
            resource_id,
            original_filename,
            mime_type,
            size_bytes,
            relative_path,
            sha256,
            expires_at,
            timestamp,
        )

    def discard_writing_resource(
        self,
        account_id: str,
        session_id: str,
        resource_id: str,
        *,
        queue_cleanup: bool,
    ) -> bool:
        return self.attachments.discard_writing_resource(
            account_id, session_id, resource_id, queue_cleanup=queue_cleanup
        )

    def mark_resource_ready(
        self,
        account_id: str,
        session_id: str,
        resource_id: str,
        *,
        expires_at: str,
        timestamp: str,
    ) -> None:
        return self.attachments.mark_resource_ready(
            account_id,
            session_id,
            resource_id,
            expires_at=expires_at,
            timestamp=timestamp,
        )

    def recover_writing_resources(
        self,
        account_id: str,
        *,
        as_of: str | None = None,
        limit: int = 100,
    ) -> dict[str, int]:
        return self.attachments.recover_writing_resources(
            account_id, as_of=as_of, limit=limit
        )

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
        return self.attachments.create_uploaded_resource(
            account_id=account_id,
            session_id=session_id,
            original_filename=original_filename,
            fallback_extension=fallback_extension,
            mime_type=mime_type,
            content=content,
        )

    def file_resource_attachment_payloads(
        self,
        account_id: str,
        session_id: str,
        references: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return self.attachments.file_resource_attachment_payloads(
            account_id, session_id, references
        )

    def mark_file_resources_attached(
        self,
        account_id: str,
        session_id: str,
        resource_ids: list[str],
    ) -> None:
        return self.attachments.mark_file_resources_attached(
            account_id, session_id, resource_ids
        )

    @member_lifecycle_operation
    def ensure_session(
        self,
        account_id: str,
        session_id: Optional[str] = None,
        *,
        member_id: str | None | object = _SESSION_MEMBER_UNSET,
    ) -> str:
        self.init_db(account_id)
        if session_id:
            if row := self.session_row(account_id, session_id):
                if (
                    member_id is not _SESSION_MEMBER_UNSET
                    and member_id != row["member_id"]
                ):
                    member_error(
                        "MEMBER_MISMATCH", "聊天关联的成员不能更改。", "conflict"
                    )
                self._stored_session(account_id, session_id, repair=False)
                return session_id
            raise_error("missing", "NOT_FOUND", "聊天不存在。")

        selected_member_id = None if member_id is _SESSION_MEMBER_UNSET else member_id
        access = None
        if selected_member_id is not None:
            access = self.members.resolve(account_id, selected_member_id)
            if access.actor_account_id != account_id:
                raise SessionEventCorruptionError("member access identity mismatch")
        new_session_id = self.new_id()
        timestamp = now_iso()
        relative_path = self.timeline_relative_path(new_session_id)
        with (
            access.guard() if access else nullcontext(),
            connect(self.paths.conversations_db(account_id)) as connection,
        ):
            connection.execute(
                """
                INSERT INTO conversations (
                    session_id, member_id, parent_session_id,
                    title, relative_path, seed_event_count,
                    created_at, last_active_at
                )
                VALUES (?, ?, NULL, ?, ?, 0, ?, ?)
                """,
                (
                    new_session_id,
                    selected_member_id,
                    UNTITLED_CONVERSATION,
                    relative_path,
                    timestamp,
                    timestamp,
                ),
            )
        try:
            self.persistence.create(
                SessionHeader(
                    id=new_session_id,
                    account_id=account_id,
                    created_at=iso_to_epoch_ms(timestamp),
                )
            )
        except Exception:
            with connect(self.paths.conversations_db(account_id)) as connection:
                connection.execute(
                    "DELETE FROM conversations WHERE session_id = ?",
                    (new_session_id,),
                )
            raise
        return new_session_id

    @member_lifecycle_operation
    def create_fork(
        self,
        account_id: str,
        source_session_id: str,
        seed: list[SessionEvent],
        *,
        title: str,
    ):
        """Create a durable child whose immutable seed is a source prefix."""

        source = self.session_row(account_id, source_session_id)
        if source is None:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        if not seed:
            raise_error(
                "conflict", "FORK_UNAVAILABLE", "聊天没有可用于分支的已结束轮次。"
            )
        child_id = self.new_id()
        timestamp = now_iso()
        header = SessionHeader(
            id=child_id,
            account_id=account_id,
            created_at=iso_to_epoch_ms(timestamp),
            parent_session_id=source_session_id,
            seed_event_count=len(seed),
        )
        relative_path = self.timeline_relative_path(child_id)
        guard = (
            self.members.access_guard(account_id, source["member_id"])
            if source["member_id"]
            else nullcontext()
        )
        with guard, connect(self.paths.conversations_db(account_id)) as connection:
            connection.execute(
                """
                INSERT INTO conversations (
                    session_id, member_id, parent_session_id,
                    title, relative_path, seed_event_count,
                    created_at, last_active_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    child_id,
                    source["member_id"],
                    source_session_id,
                    title,
                    relative_path,
                    len(seed),
                    timestamp,
                    timestamp,
                ),
            )
        try:
            self.persistence.create(header, seed)
            self.reconcile_session_indexes(account_id, child_id, events=seed)
        except Exception:
            self.persistence.delete(account_id, child_id)
            with connect(self.paths.conversations_db(account_id)) as connection:
                connection.execute(
                    "DELETE FROM conversation_resources WHERE session_id = ?",
                    (child_id,),
                )
                connection.execute(
                    "DELETE FROM conversation_turns WHERE session_id = ?",
                    (child_id,),
                )
                connection.execute(
                    "DELETE FROM conversations WHERE session_id = ?",
                    (child_id,),
                )
            raise
        return self.session_row(account_id, child_id)

    def session_records(self, account_id: str, session_id: str) -> list[dict[str, Any]]:
        row = self.session_row(account_id, session_id)
        if not row:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        stored = self._stored_session(account_id, session_id, repair=False)
        return [] if stored is None else [event.to_record() for event in stored.events]

    def session_events(
        self, account_id: str, session_id: str, *, repair: bool = False
    ) -> list[SessionEvent]:
        row = self.session_row(account_id, session_id)
        if not row:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        stored = self._stored_session(account_id, session_id, repair=repair, row=row)
        return [] if stored is None else list(stored.events)

    def session_event_snapshot(
        self, account_id: str, session_id: str
    ) -> StoredSession | None:
        row = self.session_row(account_id, session_id)
        if not row:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        return self._stored_session(account_id, session_id, repair=False, row=row)

    def session_event_revision(self, account_id: str, session_id: str) -> str | None:
        row = self.session_row(account_id, session_id)
        if not row:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        return self.persistence.revision(account_id, session_id)

    def session_event_tail(
        self, account_id: str, session_id: str, from_seq: int
    ) -> StoredSession | None:
        row = self.session_row(account_id, session_id)
        if not row:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        try:
            return self.persistence.read_from(account_id, session_id, from_seq)
        except UnsupportedSessionLogError as exc:
            raise UnsupportedSchemaError(
                "UNSUPPORTED_SCHEMA: session event log is not current."
            ) from exc

    def message_payloads(
        self, account_id: str, session_id: str
    ) -> list[dict[str, Any]]:
        return messages_from_events(
            self.session_events(account_id, session_id, repair=False)
        )

    def timeline_records(
        self, account_id: str, session_id: str
    ) -> list[dict[str, Any]]:
        return records_from_events(
            self.session_events(account_id, session_id, repair=False)
        )

    def repair_session(self, account_id: str, session_id: str) -> list[SessionEvent]:
        """Close an abandoned event tail, then rebuild its disposable indexes."""
        row = self.session_row(account_id, session_id)
        if not row:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        stored = self._stored_session(account_id, session_id, repair=True)
        events = [] if stored is None else list(stored.events)
        self.reconcile_session_indexes(account_id, session_id, events=events)
        return events

    def reconcile_session_indexes(
        self,
        account_id: str,
        session_id: str,
        *,
        events: list[SessionEvent] | None = None,
    ) -> None:
        """Rebuild Turn and attached-resource indexes from the event log.

        The index database is deliberately not a conversation-content source.  An
        open event turn never overwrites a terminal turn row, which keeps this
        safe when a GET races with the live stream that is closing the turn.
        """
        row = self.session_row(account_id, session_id)
        if not row:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        materialized = (
            list(events)
            if events is not None
            else self.session_events(account_id, session_id, repair=False)
        )
        if not materialized:
            return

        turns: dict[str, dict[str, Any]] = {}
        resources: dict[str, dict[str, Any]] = {}
        for event in materialized:
            data = event.data
            event_iso = self._event_time_iso(event.time)
            if event.type == "turn/start":
                turn_id = str(data.get("turn_id") or "")
                if not turn_id:
                    continue
                turns[turn_id] = {
                    "turn_id": turn_id,
                    "user_message_id": data["user_message_id"],
                    "final_assistant_message_id": data.get(
                        "final_assistant_message_id"
                    ),
                    "stream_id": data["stream_id"],
                    # A turn reconstructed from its durable start event has not
                    # been claimed by a worker in this process yet.
                    "status": "queued",
                    "error_code": None,
                    "error_message": None,
                    "created_at": event_iso,
                    "updated_at": event_iso,
                }
                continue
            if event.type == "user/message":
                turn = turns.get(str(data.get("turn_id") or ""))
                if turn is not None:
                    turn["user_message_id"] = data.get("message_id")
                    turn["updated_at"] = event_iso
                continue
            if event.type == "assistant/message":
                turn = turns.get(str(data.get("turn_id") or ""))
                if turn is not None and data.get("branch_addressable") is not False:
                    turn["final_assistant_message_id"] = data.get("message_id")
                    turn["updated_at"] = event_iso
                continue
            if event.type == "turn/end":
                turn = turns.get(str(data.get("turn_id") or ""))
                if turn is None:
                    continue
                reason = data.get("reason")
                reason = reason if isinstance(reason, dict) else {"kind": reason}
                kind = str(reason.get("kind") or "error")
                if kind == "completed":
                    status = "completed"
                elif kind in {"cancelled", "aborted", "steered"}:
                    status = "cancelled"
                else:
                    status = "failed"
                turn.update(
                    {
                        "status": status,
                        "error_code": (
                            None
                            if status == "completed"
                            else str(reason.get("code") or kind.upper())
                        ),
                        "error_message": (
                            None
                            if status == "completed"
                            else str(
                                reason.get("message")
                                or (
                                    "聊天生成被进程中断。"
                                    if kind == "interrupted"
                                    else "生成已取消。"
                                    if status == "cancelled"
                                    else "生成失败。"
                                )
                            )
                        ),
                        "updated_at": event_iso,
                    }
                )
                continue
            if event.type == "resource/attached":
                resource_id = str(data.get("resource_id") or "")
                if resource_id:
                    resources[resource_id] = {**data, "created_at": event_iso}

        with connect(self.paths.conversations_db(account_id)) as connection:
            for turn in turns.values():
                connection.execute(
                    """
                    INSERT INTO conversation_turns (
                        session_id, turn_id, user_message_id,
                        final_assistant_message_id, stream_id,
                        status, error_code, error_message, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, turn_id) DO UPDATE SET
                        user_message_id = excluded.user_message_id,
                        final_assistant_message_id = excluded.final_assistant_message_id,
                        stream_id = excluded.stream_id,
                        status = CASE
                            WHEN excluded.status = 'queued'
                             AND conversation_turns.status IN ('queued', 'streaming')
                            THEN conversation_turns.status
                            WHEN excluded.status = 'queued'
                             AND conversation_turns.status NOT IN ('queued', 'streaming')
                            THEN conversation_turns.status
                            ELSE excluded.status
                        END,
                        error_code = CASE
                            WHEN excluded.status = 'queued'
                            THEN conversation_turns.error_code
                            ELSE excluded.error_code
                        END,
                        error_message = CASE
                            WHEN excluded.status = 'queued'
                            THEN conversation_turns.error_message
                            ELSE excluded.error_message
                        END,
                        updated_at = CASE
                            WHEN excluded.updated_at > conversation_turns.updated_at
                            THEN excluded.updated_at
                            ELSE conversation_turns.updated_at
                        END
                    """,
                    (
                        session_id,
                        turn["turn_id"],
                        turn["user_message_id"],
                        turn["final_assistant_message_id"],
                        turn["stream_id"],
                        turn["status"],
                        turn["error_code"],
                        turn["error_message"],
                        turn["created_at"],
                        turn["updated_at"],
                    ),
                )
            for resource in resources.values():
                required = {
                    "resource_id",
                    "original_filename",
                    "mime_type",
                    "size_bytes",
                    "relative_path",
                    "sha256",
                }
                if not required.issubset(resource):
                    continue
                connection.execute(
                    """
                    INSERT INTO conversation_resources (
                        session_id, resource_id, original_filename, mime_type,
                        size_bytes, relative_path, sha256,
                        storage_status, lifecycle_status,
                        expires_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'ready', 'attached', NULL, ?, ?)
                    ON CONFLICT(session_id, resource_id) DO UPDATE SET
                        original_filename = excluded.original_filename,
                        mime_type = excluded.mime_type,
                        size_bytes = excluded.size_bytes,
                        relative_path = excluded.relative_path,
                        sha256 = excluded.sha256,
                        storage_status = 'ready',
                        lifecycle_status = 'attached',
                        expires_at = NULL,
                        updated_at = excluded.updated_at
                    """,
                    (
                        session_id,
                        resource["resource_id"],
                        resource["original_filename"],
                        resource["mime_type"],
                        resource["size_bytes"],
                        resource["relative_path"],
                        resource["sha256"],
                        resource["created_at"],
                        resource["created_at"],
                    ),
                )

    @staticmethod
    def _event_time_iso(timestamp: int) -> str:
        return local_datetime_from_epoch_ms(timestamp).isoformat()

    def append_session_event(
        self,
        account_id: str,
        session_id: str,
        event_type: str,
        data: dict[str, Any],
        *,
        timestamp: int | None = None,
        source_event_seqs: list[int] | None = None,
        surface_op: str | dict[str, Any] | None = None,
    ) -> SessionEvent:
        return self.append_session_events(
            account_id,
            session_id,
            [
                {
                    "type": event_type,
                    "data": data,
                    "timestamp": timestamp,
                    "source_event_seqs": source_event_seqs,
                    "surface_op": surface_op,
                }
            ],
        )[0]

    def append_session_events(
        self,
        account_id: str,
        session_id: str,
        specifications: list[dict[str, Any]],
        *,
        expected_seq: int | None = None,
    ) -> list[SessionEvent]:
        row = self.session_row(account_id, session_id)
        if not row:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        if expected_seq is not None:
            if (
                not isinstance(expected_seq, int)
                or isinstance(expected_seq, bool)
                or expected_seq < 0
            ):
                raise ValueError("expected_seq must be a non-negative integer")
            events = [
                make_event(
                    str(specification["type"]),
                    expected_seq + offset,
                    dict(specification["data"]),
                    timestamp=specification.get("timestamp"),
                    source_event_seqs=specification.get("source_event_seqs"),
                    surface_op=specification.get("surface_op"),
                )
                for offset, specification in enumerate(specifications)
            ]
            self.persistence.append(
                account_id,
                session_id,
                events,
                created_at=iso_to_epoch_ms(row["created_at"]),
                expected_seq=expected_seq,
            )
            if events:
                self.notifications.publish(
                    account_id,
                    session_id,
                    events[-1].seq,
                )
            return events
        last_error: SessionEventCorruptionError | None = None
        for attempt in range(128):
            stored = self._stored_session(account_id, session_id, repair=False)
            seq = 0 if stored is None else len(stored.events)
            events = [
                make_event(
                    str(specification["type"]),
                    seq + offset,
                    dict(specification["data"]),
                    timestamp=specification.get("timestamp"),
                    source_event_seqs=specification.get("source_event_seqs"),
                    surface_op=specification.get("surface_op"),
                )
                for offset, specification in enumerate(specifications)
            ]
            try:
                self.persistence.append(
                    account_id,
                    session_id,
                    events,
                    created_at=iso_to_epoch_ms(row["created_at"]),
                    expected_seq=None,
                )
            except SessionEventCorruptionError as exc:
                if "seq" not in str(exc) and "already exists" not in str(exc):
                    raise
                last_error = exc
                time.sleep(min(0.0005 * (attempt + 1), 0.01))
                continue
            self.notifications.publish(
                account_id,
                session_id,
                events[-1].seq,
            )
            return events
        raise SessionEventCorruptionError(
            f"concurrent append retry limit exceeded for session {session_id}"
        ) from last_error

    def messages_by_id(
        self, account_id: str, session_id: str
    ) -> dict[str, dict[str, Any]]:
        return {
            message["message_id"]: message
            for message in self.message_payloads(account_id, session_id)
        }

    def attach_file_resources(
        self, account_id: str, session_id: str, references: list[dict[str, Any]]
    ) -> None:
        attached = self.file_resource_attachment_payloads(
            account_id,
            session_id,
            references,
        )
        self.mark_file_resources_attached(
            account_id,
            session_id,
            [str(resource["resource_id"]) for resource in attached],
        )
        if attached:
            self.append_session_events(
                account_id,
                session_id,
                [
                    {"type": "resource/attached", "data": payload}
                    for payload in attached
                ],
            )

    def delete_conversation(self, account_id: str, session_id: str) -> None:
        row = self.session_row(account_id, session_id)
        if not row:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        self._stored_session(account_id, session_id, repair=False)

        with connect(self.paths.conversations_db(account_id)) as connection:
            resources = connection.execute(
                """
                SELECT relative_path FROM conversation_resources
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchall()
            connection.execute(
                "DELETE FROM conversation_turns WHERE session_id = ?",
                (session_id,),
            )
            connection.execute(
                "DELETE FROM conversation_resources WHERE session_id = ?",
                (session_id,),
            )
            for resource in resources:
                self.attachments.enqueue_if_attachment_unreferenced(
                    connection,
                    account_id,
                    resource["relative_path"],
                )
            connection.execute(
                "DELETE FROM conversations WHERE session_id = ?",
                (session_id,),
            )
        self.persistence.delete(account_id, session_id)

    def source_message_for_favorite(
        self, account_id: str, session_id: str, message_id: str
    ):
        row = self.session_row(account_id, session_id)
        if not row:
            return None
        events = self.session_events(account_id, session_id, repair=False)
        current = active_records(records_from_events(events), events)
        message = next(
            (
                record
                for record in current
                if record.get("kind") == "assistant"
                and str(record.get("message_id") or record.get("record_id") or "")
                == message_id
            ),
            None,
        )
        if message is None:
            return None
        parent = next(
            (
                record
                for record in current
                if record.get("kind") == "user"
                and str(record.get("turn_id") or "")
                == str(message.get("turn_id") or "")
            ),
            None,
        )
        context_resources = list(parent.get("context_resources", [])) if parent else []
        return {
            "title": row["title"],
            "content": message["content"],
            "message_id": message_id,
            "context_resources": context_resources,
            "_turn_id": str(message.get("turn_id") or ""),
        }

    def timeline_relative_path(self, session_id: str) -> str:
        return f"conversations/sessions/{session_id}.jsonl"

    def timeline_abs_path(self, account_id: str, relative_path: str) -> Path:
        return self.paths.account_root(account_id) / relative_path

    def _stored_session(self, account_id: str, session_id: str, *, repair: bool, row=None):
        if row is None:
            row = self.session_row(account_id, session_id)
        if row is None:
            raise SessionEventCorruptionError("session index row is missing")
        if str(row["relative_path"]) != self.timeline_relative_path(session_id):
            raise SessionEventCorruptionError(
                "session index timeline path is inconsistent"
            )
        try:
            stored = self.persistence.load(account_id, session_id, repair=repair)
        except UnsupportedSessionLogError as exc:
            raise UnsupportedSchemaError(
                "UNSUPPORTED_SCHEMA: session event log is not current."
            ) from exc
        if stored is None:
            raise SessionEventCorruptionError("session event artifact is missing")
        if stored.header.account_id != account_id or stored.header.id != session_id:
            raise SessionEventCorruptionError(
                "session header does not match its index and account directory"
            )
        return stored

    def new_id(self) -> str:
        import uuid

        return str(uuid.uuid4())

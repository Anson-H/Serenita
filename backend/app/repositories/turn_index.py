from typing import Any, Optional

from backend.app.core.errors import raise_error
from backend.app.core.time import (
    local_now_iso,
)
from backend.app.session_events import (
    SessionEventCorruptionError,
)
from backend.app.storage.sqlite import (
    connect,
)


now_iso = local_now_iso


class TurnIndex:
    def __init__(self, paths, *, initialize, session_row):
        self.paths = paths
        self.init_db = initialize
        self.session_row = session_row

    def validate_no_pending_turn(self, account_id: str, session_id: str) -> None:
        if self.session_row(account_id, session_id) is None:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        with connect(self.paths.conversations_db(account_id)) as connection:
            row = connection.execute(
                """
                SELECT turn_id FROM conversation_turns
                WHERE session_id = ? AND status IN ('queued', 'streaming')
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        if row:
            raise_error(
                "invalid_input", "INVALID_REQUEST", "当前聊天有正在进行的生成任务。"
            )

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
        with connect(self.paths.conversations_db(account_id)) as connection:
            cursor = connection.execute(
                """
                INSERT INTO conversation_turns (
                    session_id, turn_id, user_message_id,
                    final_assistant_message_id, stream_id, status, error_code, error_message,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, turn_id) DO NOTHING
                """,
                (
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
                ),
            )
            if cursor.rowcount == 1:
                return
            existing = connection.execute(
                """
                SELECT user_message_id, final_assistant_message_id, stream_id, created_at
                FROM conversation_turns
                WHERE session_id = ? AND turn_id = ?
                """,
                (session_id, turn_id),
            ).fetchone()
            expected = (
                user_message_id,
                final_assistant_message_id,
                stream_id,
                created_at,
            )
            actual = None if existing is None else tuple(existing)
            if actual != expected:
                raise SessionEventCorruptionError(
                    f"turn index conflict for session {session_id}, turn {turn_id}"
                )

    def claim_turn_job(self, account_id: str, session_id: str, turn_id: str) -> bool:
        """Claim one queued Agent Turn for an independent worker in one transaction."""
        with connect(self.paths.conversations_db(account_id)) as connection:
            cursor = connection.execute(
                """
                UPDATE conversation_turns
                SET status = 'streaming', updated_at = ?
                WHERE session_id = ? AND turn_id = ? AND status = 'queued'
                """,
                (now_iso(), session_id, turn_id),
            )
            return cursor.rowcount == 1

    def touch_turn_job(self, account_id: str, session_id: str, turn_id: str) -> None:
        with connect(self.paths.conversations_db(account_id)) as connection:
            connection.execute(
                """
                UPDATE conversation_turns
                SET updated_at = ?
                WHERE session_id = ? AND turn_id = ? AND status = 'streaming'
                """,
                (now_iso(), session_id, turn_id),
            )

    def expire_turn_jobs(self, account_id: str, cutoff: str) -> list[dict[str, Any]]:
        """Truthfully terminate workers whose persisted lease heartbeat expired."""
        timestamp = now_iso()
        with connect(self.paths.conversations_db(account_id)) as connection:
            rows = connection.execute(
                """
                SELECT * FROM conversation_turns
                WHERE status = 'streaming' AND updated_at < ?
                """,
                (cutoff,),
            ).fetchall()
            if rows:
                connection.executemany(
                    """
                    UPDATE conversation_turns
                    SET status = 'failed', error_code = 'TURN_INTERRUPTED',
                        error_message = 'Agent Turn 运行租约已过期，任务已中断。',
                        updated_at = ?
                    WHERE session_id = ? AND turn_id = ? AND status = 'streaming'
                    """,
                    [(timestamp, row["session_id"], row["turn_id"]) for row in rows],
                )
        return [dict(row) for row in rows]

    def update_turn_completed(
        self,
        account_id: str,
        session_id: str,
        turn_id: str,
        final_assistant_message_id: Optional[str],
        timestamp: Optional[str] = None,
    ) -> None:
        with connect(self.paths.conversations_db(account_id)) as connection:
            connection.execute(
                """
                UPDATE conversation_turns
                SET final_assistant_message_id = ?, status = 'completed',
                    error_code = NULL, error_message = NULL, updated_at = ?
                WHERE session_id = ? AND turn_id = ?
                """,
                (
                    final_assistant_message_id,
                    timestamp or now_iso(),
                    session_id,
                    turn_id,
                ),
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
        with connect(self.paths.conversations_db(account_id)) as connection:
            connection.execute(
                """
                UPDATE conversation_turns
                SET status = 'failed', error_code = ?, error_message = ?, updated_at = ?
                WHERE session_id = ? AND turn_id = ?
                """,
                (
                    error_code,
                    error_message,
                    timestamp or now_iso(),
                    session_id,
                    turn_id,
                ),
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
        with connect(self.paths.conversations_db(account_id)) as connection:
            connection.execute(
                """
                UPDATE conversation_turns
                SET final_assistant_message_id = ?, status = 'cancelled',
                    error_code = ?, error_message = ?, updated_at = ?
                WHERE session_id = ? AND turn_id = ?
                """,
                (
                    final_assistant_message_id,
                    error_code,
                    error_message,
                    timestamp or now_iso(),
                    session_id,
                    turn_id,
                ),
            )

    def turn_row(self, account_id: str, session_id: str, turn_id: str):
        with connect(self.paths.conversations_db(account_id)) as connection:
            return connection.execute(
                """
                SELECT * FROM conversation_turns
                WHERE session_id = ? AND turn_id = ?
                """,
                (session_id, turn_id),
            ).fetchone()

    def turn_by_stream_id(self, account_id: str, session_id: str, stream_id: str):
        self.init_db(account_id)
        with connect(self.paths.conversations_db(account_id)) as connection:
            return connection.execute(
                """
                SELECT * FROM conversation_turns
                WHERE session_id = ? AND stream_id = ?
                """,
                (session_id, stream_id),
            ).fetchone()

    def list_pending_turn_rows(self, account_id: str, session_id: str):
        with connect(self.paths.conversations_db(account_id)) as connection:
            return connection.execute(
                """
                SELECT * FROM conversation_turns
                WHERE session_id = ? AND status IN ('queued', 'streaming')
                ORDER BY created_at
                """,
                (session_id,),
            ).fetchall()

    def pending_turn_status(self, account_id: str, session_id: str) -> str | None:
        with connect(self.paths.conversations_db(account_id)) as connection:
            row = connection.execute(
                """
                SELECT status FROM conversation_turns
                WHERE session_id = ? AND status IN ('queued', 'streaming')
                ORDER BY created_at DESC, turn_id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return None if row is None else str(row["status"])

    def list_turn_rows(self, account_id: str, session_id: str):
        with connect(self.paths.conversations_db(account_id)) as connection:
            return connection.execute(
                """
                SELECT * FROM conversation_turns
                WHERE session_id = ?
                ORDER BY created_at, turn_id
                """,
                (session_id,),
            ).fetchall()

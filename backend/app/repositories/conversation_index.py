from backend.app.storage.conversation_database import CONVERSATION_DATABASE_SCHEMA
import re
from typing import Any

from backend.app.core.errors import raise_error
from backend.app.core.time import (
    local_now_iso,
)
from backend.app.session_title import (
    SESSION_TITLE_INITIAL_CHARS,
    SESSION_TITLE_MAX_CHARS,
    TITLE_LEADING_LABELS,
    TITLE_PREFIXES,
    TITLE_TAIL_REPLACEMENTS,
)
from backend.app.storage.sqlite import (
    connect,
)


from backend.app.session_title import UNTITLED_CONVERSATION

now_iso = local_now_iso


class ConversationIndex:
    def __init__(self, paths):
        self.paths = paths

    def validate_existing_database(self, account_id: str) -> bool:
        database_path = self.paths.conversations_db(account_id)
        return CONVERSATION_DATABASE_SCHEMA.validate_existing(database_path)

    def init_db(self, account_id: str) -> None:
        if self.validate_existing_database(account_id):
            return
        database_path = self.paths.conversations_db(account_id)
        with connect(database_path) as connection:
            CONVERSATION_DATABASE_SCHEMA.create(connection)
        self.validate_existing_database(account_id)

    def session_row(self, account_id: str, session_id: str):
        self.init_db(account_id)
        with connect(self.paths.conversations_db(account_id)) as connection:
            return connection.execute(
                "SELECT * FROM conversations WHERE session_id = ?",
                (session_id,),
            ).fetchone()

    def has_closed_turn(self, account_id: str, session_id: str) -> bool:
        with connect(self.paths.conversations_db(account_id)) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM conversation_turns
                WHERE session_id = ?
                  AND status NOT IN ('queued', 'streaming')
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return row is not None

    def touch_session(
        self,
        account_id: str,
        session_id: str,
    ) -> None:
        self.init_db(account_id)
        with connect(self.paths.conversations_db(account_id)) as connection:
            connection.execute(
                """
                UPDATE conversations
                SET last_active_at = ?
                WHERE session_id = ?
                """,
                (
                    now_iso(),
                    session_id,
                ),
            )

    def initial_session_title(self, user_input: str) -> str:
        """Return the immediate sidebar title shown before model post-processing."""
        normalized = re.sub(r"\s+", " ", user_input or "").strip()
        return normalized[:SESSION_TITLE_INITIAL_CHARS] or UNTITLED_CONVERSATION

    def set_initial_session_title(
        self,
        account_id: str,
        session_id: str,
        title: str,
    ) -> bool:
        """Set the first-input title once without overwriting an existing title."""
        initial_title = self.initial_session_title(title)
        if initial_title == UNTITLED_CONVERSATION:
            return False
        with connect(self.paths.conversations_db(account_id)) as connection:
            cursor = connection.execute(
                """
                UPDATE conversations
                SET title = ?
                WHERE session_id = ? AND title = ?
                  AND is_title_manual = 0
                """,
                (initial_title, session_id, UNTITLED_CONVERSATION),
            )
        return cursor.rowcount > 0

    def replace_initial_session_title(
        self,
        account_id: str,
        session_id: str,
        initial_title: str,
        generated_title: str,
    ) -> bool:
        """CAS the model title over the provisional first-input title."""
        cleaned_title = self.clean_generated_session_title(generated_title)
        expected_title = self.initial_session_title(initial_title)
        if cleaned_title == UNTITLED_CONVERSATION:
            return False
        with connect(self.paths.conversations_db(account_id)) as connection:
            cursor = connection.execute(
                """
                UPDATE conversations
                SET title = ?
                WHERE session_id = ? AND title = ?
                  AND is_title_manual = 0
                """,
                (cleaned_title, session_id, expected_title),
            )
        return cursor.rowcount > 0

    def update_session_metadata(
        self,
        account_id: str,
        session_id: str,
        *,
        title: str | None = None,
        is_pinned: bool | None = None,
    ):
        self.init_db(account_id)
        assignments: list[str] = []
        values: list[Any] = []
        if title is not None:
            assignments.extend(["title = ?", "is_title_manual = 1"])
            values.append(title)
        if is_pinned is not None:
            assignments.append("is_pinned = ?")
            values.append(1 if is_pinned else 0)
        if not assignments:
            raise_error("invalid_input", "INVALID_REQUEST", "没有可更新的聊天字段。")

        with connect(self.paths.conversations_db(account_id)) as connection:
            cursor = connection.execute(
                f"""
                UPDATE conversations
                SET {", ".join(assignments)}
                WHERE session_id = ?
                """,
                (*values, session_id),
            )
            if cursor.rowcount == 0:
                raise_error("missing", "NOT_FOUND", "聊天不存在。")
            return connection.execute(
                "SELECT * FROM conversations WHERE session_id = ?",
                (session_id,),
            ).fetchone()

    def batch_set_pinned(
        self,
        account_id: str,
        session_ids: list[str],
        is_pinned: bool,
    ) -> list[Any]:
        self.init_db(account_id)
        unique_ids = list(dict.fromkeys(session_ids))
        if not unique_ids:
            raise_error("invalid_input", "INVALID_REQUEST", "请选择至少一个聊天。")
        placeholders = ", ".join("?" for _ in unique_ids)
        with connect(self.paths.conversations_db(account_id)) as connection:
            existing_rows = connection.execute(
                f"""
                SELECT * FROM conversations
                WHERE session_id IN ({placeholders})
                """,
                unique_ids,
            ).fetchall()
            existing_by_id = {str(row["session_id"]): row for row in existing_rows}
            missing_ids = [
                session_id
                for session_id in unique_ids
                if session_id not in existing_by_id
            ]
            if missing_ids:
                raise_error("missing", "NOT_FOUND", f"聊天不存在：{missing_ids[0]}")
            connection.execute(
                f"""
                UPDATE conversations
                SET is_pinned = ?
                WHERE session_id IN ({placeholders})
                """,
                (1 if is_pinned else 0, *unique_ids),
            )
            updated_rows = connection.execute(
                f"""
                SELECT * FROM conversations
                WHERE session_id IN ({placeholders})
                """,
                unique_ids,
            ).fetchall()
        updated_by_id = {str(row["session_id"]): row for row in updated_rows}
        return [updated_by_id[session_id] for session_id in unique_ids]

    def clean_generated_session_title(self, raw_title: str) -> str:
        title = re.sub(r"\s+", " ", raw_title or "").strip()
        if not title:
            return UNTITLED_CONVERSATION
        title = re.sub(r"^[#>*`\\-\\s]+", "", title)
        title = title.strip(" \t，,。.！？?!；;：:“”\"'「」『』()（）[]【】")
        changed = True
        while changed:
            changed = False
            for label in (*TITLE_LEADING_LABELS, "标题", "聊天标题"):
                label_pattern = rf"^{re.escape(label)}\s*[：:]\s*"
                next_title = re.sub(label_pattern, "", title).strip()
                if next_title != title and next_title:
                    title = next_title
                    changed = True
        title = re.sub(
            r"[，,。！？?!；;：:“”\"'「」『』()（）\\[\\]【】]+", "", title
        ).strip()
        return title[:SESSION_TITLE_MAX_CHARS] or UNTITLED_CONVERSATION

    def generate_session_title(self, title_seed: str) -> str:
        text = re.sub(r"\s+", " ", title_seed or "").strip()
        if not text:
            return UNTITLED_CONVERSATION

        text = re.sub(r"^[#>*`\\-\\s]+", "", text)
        text = re.sub(r"^模型真实回复\s*\d*\s*[：:]\s*", "", text)
        first_sentence = next(
            (
                part.strip()
                for part in re.split(r"[。！？?!\n\r；;]", text)
                if part.strip()
            ),
            text,
        )
        title = first_sentence.strip(" \t，,。.！？?!；;：:“”\"'「」『』()（）[]【】")

        changed = True
        while changed:
            changed = False
            for label in TITLE_LEADING_LABELS:
                label_pattern = rf"^{re.escape(label)}\s*[：:]\s*"
                next_title = re.sub(label_pattern, "", title).strip()
                if next_title != title and next_title:
                    title = next_title
                    changed = True
            for prefix in TITLE_PREFIXES:
                if title.startswith(prefix) and len(title) > len(prefix):
                    title = title[len(prefix) :].lstrip(" ，,：:").strip()
                    changed = True

        for target, replacement in TITLE_TAIL_REPLACEMENTS:
            title = title.replace(target, replacement)

        return self.clean_generated_session_title(title or text)

    def list_sessions(self, account_id: str):
        self.init_db(account_id)
        with connect(self.paths.conversations_db(account_id)) as connection:
            return connection.execute(
                """
                SELECT conversations.*,
                       (
                           SELECT status FROM conversation_turns
                           WHERE conversation_turns.session_id = conversations.session_id
                             AND conversation_turns.status IN ('queued', 'streaming')
                           ORDER BY conversation_turns.created_at DESC,
                                    conversation_turns.turn_id DESC
                           LIMIT 1
                       ) AS pending_turn_status
                FROM conversations
                WHERE EXISTS (
                      SELECT 1 FROM conversation_turns
                      WHERE conversation_turns.session_id = conversations.session_id
                  )
                ORDER BY is_pinned DESC, last_active_at DESC
                """
            ).fetchall()

    def conversation_exists(self, account_id: str, session_id: str) -> bool:
        return self.session_row(account_id, session_id) is not None

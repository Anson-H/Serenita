import json
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from backend.app.api.auth import now_iso, raise_error
from backend.app.storage.jsonl import append_record, read_records
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect

UNTITLED_CONVERSATION = "新对话"
SESSION_TITLE_MAX_CHARS = 14
TITLE_PREFIXES = (
    "你好",
    "您好",
    "请问",
    "麻烦你",
    "麻烦",
    "帮我看看",
    "可以帮我看看",
    "可以帮我",
    "我想问问",
    "我想问一下",
    "想问问",
    "想问一下",
    "我想了解",
    "我想",
    "我最近",
    "最近",
    "我",
)
TITLE_TAIL_REPLACEMENTS = (
    ("需要注意些什么", "注意事项"),
    ("需要注意什么", "注意事项"),
    ("要注意些什么", "注意事项"),
    ("要注意什么", "注意事项"),
    ("应该注意些什么", "注意事项"),
    ("应该注意什么", "注意事项"),
    ("该注意些什么", "注意事项"),
    ("该注意什么", "注意事项"),
    ("怎么办", "处理建议"),
    ("怎么处理", "处理建议"),
    ("怎么回事", "原因分析"),
    ("是什么原因", "原因分析"),
)
TITLE_LEADING_LABELS = (
    "模型真实回复",
    "核心结论",
    "下一步建议",
    "结论",
    "建议",
)


class ConversationRepository:
    def init_db(self, account: str) -> None:
        with connect(app_paths().conversations_db(account)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    session_id TEXT PRIMARY KEY,
                    account TEXT NOT NULL,
                    title TEXT NOT NULL,
                    timeline_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_active_at TEXT NOT NULL,
                    last_message_preview TEXT DEFAULT '',
                    active_path_message_ids TEXT DEFAULT '[]'
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    turn_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    account TEXT NOT NULL,
                    user_message_id TEXT,
                    assistant_message_id TEXT,
                    thinking_message_id TEXT,
                    stream_id TEXT,
                    status TEXT NOT NULL,
                    error_code TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES conversation_sessions(session_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_resources (
                    resource_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    account TEXT NOT NULL,
                    name TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    relative_path TEXT NOT NULL,
                    thumb_path TEXT,
                    sha256 TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    usage_status TEXT NOT NULL DEFAULT 'pending',
                    expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES conversation_sessions(session_id)
                )
                """
            )
        self.migrate_dated_timeline_paths(account)

    def ensure_session(self, account: str, session_id: Optional[str] = None) -> str:
        self.init_db(account)
        if session_id:
            if self.session_row(account, session_id):
                return session_id
            raise_error(404, "NOT_FOUND", "会话不存在。")

        new_session_id = self.new_id()
        timestamp = now_iso()
        relative_path = self.timeline_relative_path(new_session_id)
        with connect(app_paths().conversations_db(account)) as connection:
            connection.execute(
                """
                INSERT INTO conversation_sessions (
                    session_id, account, title, timeline_path, created_at,
                    last_active_at, last_message_preview, active_path_message_ids
                )
                VALUES (?, ?, ?, ?, ?, ?, '', '[]')
                """,
                (new_session_id, account, UNTITLED_CONVERSATION, relative_path, timestamp, timestamp),
            )
        self.timeline_abs_path(account, relative_path).parent.mkdir(parents=True, exist_ok=True)
        return new_session_id

    def session_row(self, account: str, session_id: str):
        self.init_db(account)
        with connect(app_paths().conversations_db(account)) as connection:
            return connection.execute(
                "SELECT * FROM conversation_sessions WHERE account = ? AND session_id = ?",
                (account, session_id),
            ).fetchone()

    def session_records(self, account: str, session_id: str) -> list[dict[str, Any]]:
        row = self.session_row(account, session_id)
        if not row:
            raise_error(404, "NOT_FOUND", "会话不存在。")
        return read_records(self.timeline_abs_path(account, row["timeline_path"]))

    def message_payloads(self, account: str, session_id: str) -> list[dict[str, Any]]:
        records = self.session_records(account, session_id)
        messages = []
        for record in records:
            if record["type"] in {"user_message", "thinking_process", "assistant_message"}:
                payload = record["payload"]
                role = {"user_message": "user", "thinking_process": "thinking"}.get(
                    record["type"],
                    "assistant",
                )
                messages.append({**payload, "role": role})
        return messages

    def messages_by_id(self, account: str, session_id: str) -> dict[str, dict[str, Any]]:
        return {message["message_id"]: message for message in self.message_payloads(account, session_id)}

    def path_to_message(
        self,
        messages_by_id: dict[str, dict[str, Any]],
        message_id: Optional[str],
    ) -> list[str]:
        if not message_id:
            return []
        path = []
        current_id = message_id
        seen = set()
        while current_id:
            if current_id in seen or current_id not in messages_by_id:
                raise_error(400, "INVALID_REQUEST", "消息链路不连续。")
            seen.add(current_id)
            path.append(current_id)
            current_id = messages_by_id[current_id].get("parent_message_id")
        return list(reversed(path))

    def message_response(self, message: dict[str, Any]) -> dict[str, Any]:
        response = {
            "message_id": message["message_id"],
            "turn_id": message["turn_id"],
            "parent_message_id": message.get("parent_message_id"),
            "role": message["role"],
            "model_id": message.get("model_id"),
            "content": message.get("content", ""),
            "created_at": message.get("created_at"),
        }
        if message["role"] == "user":
            response["thinking_mode"] = message.get("thinking_mode", "default")
            response["context_resources"] = message.get("context_resources", [])
        if message["role"] == "assistant":
            response["status"] = message.get("status", "completed")
            response["stop_reason"] = message.get("stop_reason", "end_turn")
            response["usage"] = message.get("usage", {})
        if message["role"] == "thinking":
            response["duration_ms"] = message.get("duration_ms", 0)
        return response

    def update_session_after_message(
        self,
        account: str,
        session_id: str,
        active_path: list[str],
        generated_title: Optional[str],
        preview: str,
        legacy_title_seed: Optional[str] = None,
    ) -> None:
        row = self.session_row(account, session_id)
        title = row["title"]
        if generated_title is not None and self.is_generated_session_title(
            title,
            generated_title,
            legacy_title_seed,
        ):
            title = self.clean_generated_session_title(generated_title)
        with connect(app_paths().conversations_db(account)) as connection:
            connection.execute(
                """
                UPDATE conversation_sessions
                SET title = ?, last_active_at = ?, last_message_preview = ?,
                    active_path_message_ids = ?
                WHERE account = ? AND session_id = ?
                """,
                (
                    title,
                    now_iso(),
                    preview[:120],
                    json.dumps(active_path, ensure_ascii=False),
                    account,
                    session_id,
                ),
            )

    def clean_generated_session_title(self, raw_title: str) -> str:
        title = re.sub(r"\s+", " ", raw_title or "").strip()
        if not title:
            return UNTITLED_CONVERSATION
        title = re.sub(r"^[#>*`\\-\\s]+", "", title)
        title = title.strip(" \t，,。.！？?!；;：:“”\"'「」『』()（）[]【】")
        changed = True
        while changed:
            changed = False
            for label in (*TITLE_LEADING_LABELS, "标题", "会话标题"):
                label_pattern = rf"^{re.escape(label)}\s*[：:]\s*"
                next_title = re.sub(label_pattern, "", title).strip()
                if next_title != title and next_title:
                    title = next_title
                    changed = True
        title = re.sub(r"[，,。！？?!；;：:“”\"'「」『』()（）\\[\\]【】]+", "", title).strip()
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

    def legacy_session_title(self, title_seed: str) -> str:
        return (title_seed or "").strip()[:20] or UNTITLED_CONVERSATION

    def is_generated_session_title(
        self,
        title: str,
        title_seed: str,
        legacy_title_seed: Optional[str] = None,
    ) -> bool:
        stripped_seed = (title_seed or "").strip()
        generated_titles = {
            UNTITLED_CONVERSATION,
            stripped_seed,
            self.legacy_session_title(stripped_seed),
        }
        if legacy_title_seed:
            stripped_legacy_seed = legacy_title_seed.strip()
            generated_titles.update(
                {
                    stripped_legacy_seed,
                    self.legacy_session_title(stripped_legacy_seed),
                    self.generate_session_title(stripped_legacy_seed),
                }
            )
        return title in generated_titles

    def backfill_generated_session_titles(self, account: str) -> None:
        self.init_db(account)
        with connect(app_paths().conversations_db(account)) as connection:
            rows = connection.execute(
                """
                SELECT session_id, title, timeline_path
                FROM conversation_sessions
                WHERE account = ?
                """,
                (account,),
            ).fetchall()

        updates = []
        for row in rows:
            records = read_records(self.timeline_abs_path(account, row["timeline_path"]))
            first_user_content = next(
                (
                    record.get("payload", {}).get("content", "")
                    for record in records
                    if record.get("type") == "user_message"
                ),
                "",
            )
            first_assistant_content = next(
                (
                    record.get("payload", {}).get("content", "")
                    for record in records
                    if record.get("type") == "assistant_message"
                ),
                "",
            )
            if not first_user_content or not first_assistant_content:
                continue
            title_seed = self.title_seed_from_turn(first_user_content, first_assistant_content)
            next_title = self.generate_session_title(title_seed)
            if next_title != row["title"] and self.is_generated_session_title(
                row["title"],
                title_seed,
                first_user_content,
            ):
                updates.append((next_title, row["session_id"]))

        if not updates:
            return
        with connect(app_paths().conversations_db(account)) as connection:
            connection.executemany(
                """
                UPDATE conversation_sessions
                SET title = ?
                WHERE session_id = ?
                """,
                updates,
            )

    def title_seed_from_turn(self, question: str, answer: str) -> str:
        question = (question or "").strip()
        answer = (answer or "").strip()
        if answer:
            return f"{answer}\n{question}" if question else answer
        return question

    def validate_no_pending_turn(self, account: str, session_id: str) -> None:
        with connect(app_paths().conversations_db(account)) as connection:
            row = connection.execute(
                """
                SELECT turn_id FROM conversation_turns
                WHERE session_id = ? AND account = ? AND status IN ('queued', 'streaming')
                LIMIT 1
                """,
                (session_id, account),
            ).fetchone()
        if row:
            raise_error(400, "INVALID_REQUEST", "当前会话有正在进行的生成任务。")

    def resource_row(self, account: str, session_id: str, resource_id: str):
        with connect(app_paths().conversations_db(account)) as connection:
            return connection.execute(
                """
                SELECT * FROM conversation_resources
                WHERE account = ? AND session_id = ? AND resource_id = ?
                """,
                (account, session_id, resource_id),
            ).fetchone()

    def set_resource_usage_status(
        self,
        account: str,
        resource_id: str,
        usage_status: str,
        timestamp: Optional[str] = None,
    ) -> None:
        with connect(app_paths().conversations_db(account)) as connection:
            connection.execute(
                """
                UPDATE conversation_resources
                SET usage_status = ?, updated_at = ?
                WHERE resource_id = ?
                """,
                (usage_status, timestamp or now_iso(), resource_id),
            )

    def insert_uploaded_resource(
        self,
        account: str,
        session_id: str,
        resource_id: str,
        name: str,
        mime_type: str,
        size_bytes: int,
        relative_path: str,
        sha256: str,
        expires_at: str,
        timestamp: str,
    ) -> None:
        with connect(app_paths().conversations_db(account)) as connection:
            connection.execute(
                """
                INSERT INTO conversation_resources (
                    resource_id, session_id, account, name, mime_type, size_bytes,
                    relative_path, thumb_path, sha256, source, status, usage_status,
                    expires_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 'user_upload', 'uploaded', 'pending', ?, ?, ?)
                """,
                (
                    resource_id,
                    session_id,
                    account,
                    name,
                    mime_type,
                    size_bytes,
                    relative_path,
                    sha256,
                    expires_at,
                    timestamp,
                    timestamp,
                ),
            )

    def attach_file_resources(self, account: str, session_id: str, references: list[dict[str, Any]]) -> None:
        row = self.session_row(account, session_id)
        timeline_path = self.timeline_abs_path(account, row["timeline_path"])
        with connect(app_paths().conversations_db(account)) as connection:
            for reference in references:
                if reference["resource_type"] != "file":
                    continue
                resource = connection.execute(
                    "SELECT * FROM conversation_resources WHERE resource_id = ?",
                    (reference["resource_id"],),
                ).fetchone()
                append_record(
                    timeline_path,
                    {
                        "timestamp": now_iso(),
                        "type": "file_upload",
                        "payload": {
                            "session_id": session_id,
                            "resource_id": resource["resource_id"],
                            "name": resource["name"],
                            "mime_type": resource["mime_type"],
                            "size_bytes": resource["size_bytes"],
                            "relative_path": resource["relative_path"],
                            "thumb_path": resource["thumb_path"],
                            "sha256": resource["sha256"],
                            "source": resource["source"],
                            "status": resource["status"],
                        },
                    },
                )
                connection.execute(
                    """
                    UPDATE conversation_resources
                    SET usage_status = 'attached', updated_at = ?
                    WHERE resource_id = ?
                    """,
                    (now_iso(), reference["resource_id"]),
                )

    def insert_turn(
        self,
        account: str,
        session_id: str,
        turn_id: str,
        user_message_id: Optional[str],
        assistant_message_id: Optional[str],
        thinking_message_id: Optional[str],
        stream_id: str,
        status: str,
        error_code: Optional[str],
        error_message: Optional[str],
        created_at: str,
        updated_at: str,
    ) -> None:
        with connect(app_paths().conversations_db(account)) as connection:
            connection.execute(
                """
                INSERT INTO conversation_turns (
                    turn_id, session_id, account, user_message_id, assistant_message_id,
                    thinking_message_id, stream_id, status, error_code, error_message,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn_id,
                    session_id,
                    account,
                    user_message_id,
                    assistant_message_id,
                    thinking_message_id,
                    stream_id,
                    status,
                    error_code,
                    error_message,
                    created_at,
                    updated_at,
                ),
            )

    def update_turn_completed(
        self,
        account: str,
        turn_id: str,
        assistant_message_id: Optional[str],
        thinking_message_id: Optional[str],
        timestamp: Optional[str] = None,
    ) -> None:
        with connect(app_paths().conversations_db(account)) as connection:
            connection.execute(
                """
                UPDATE conversation_turns
                SET assistant_message_id = ?, thinking_message_id = ?, status = 'completed',
                    error_code = NULL, error_message = NULL, updated_at = ?
                WHERE account = ? AND turn_id = ?
                """,
                (
                    assistant_message_id,
                    thinking_message_id,
                    timestamp or now_iso(),
                    account,
                    turn_id,
                ),
            )

    def update_turn_failed(
        self,
        account: str,
        turn_id: str,
        error_code: str,
        error_message: str,
        timestamp: Optional[str] = None,
    ) -> None:
        with connect(app_paths().conversations_db(account)) as connection:
            connection.execute(
                """
                UPDATE conversation_turns
                SET status = 'failed', error_code = ?, error_message = ?, updated_at = ?
                WHERE account = ? AND turn_id = ?
                """,
                (
                    error_code,
                    error_message,
                    timestamp or now_iso(),
                    account,
                    turn_id,
                ),
            )

    def update_turn_cancelled(
        self,
        account: str,
        turn_id: str,
        assistant_message_id: Optional[str],
        thinking_message_id: Optional[str],
        error_code: str = "CANCELLED",
        error_message: str = "生成已取消。",
        timestamp: Optional[str] = None,
    ) -> None:
        with connect(app_paths().conversations_db(account)) as connection:
            connection.execute(
                """
                UPDATE conversation_turns
                SET assistant_message_id = ?, thinking_message_id = ?, status = 'cancelled',
                    error_code = ?, error_message = ?, updated_at = ?
                WHERE account = ? AND turn_id = ?
                """,
                (
                    assistant_message_id,
                    thinking_message_id,
                    error_code,
                    error_message,
                    timestamp or now_iso(),
                    account,
                    turn_id,
                ),
            )

    def turn_row(self, account: str, session_id: str, turn_id: str):
        with connect(app_paths().conversations_db(account)) as connection:
            return connection.execute(
                """
                SELECT * FROM conversation_turns
                WHERE account = ? AND session_id = ? AND turn_id = ?
                """,
                (account, session_id, turn_id),
            ).fetchone()

    def turn_by_stream_id(self, account: str, stream_id: str):
        self.init_db(account)
        with connect(app_paths().conversations_db(account)) as connection:
            return connection.execute(
                """
                SELECT * FROM conversation_turns
                WHERE account = ? AND stream_id = ?
                """,
                (account, stream_id),
            ).fetchone()

    def list_pending_turn_rows(self, account: str, session_id: str):
        with connect(app_paths().conversations_db(account)) as connection:
            return connection.execute(
                """
                SELECT * FROM conversation_turns
                WHERE account = ? AND session_id = ? AND status IN ('queued', 'streaming')
                ORDER BY created_at
                """,
                (account, session_id),
            ).fetchall()

    def list_sessions(self, account: str):
        self.backfill_generated_session_titles(account)
        self.init_db(account)
        with connect(app_paths().conversations_db(account)) as connection:
            return connection.execute(
                """
                SELECT * FROM conversation_sessions
                WHERE account = ?
                  AND COALESCE(NULLIF(TRIM(active_path_message_ids), ''), '[]') != '[]'
                ORDER BY last_active_at DESC
                LIMIT 50
                """,
                (account,),
            ).fetchall()

    def update_active_path(
        self,
        account: str,
        session_id: str,
        active_path_message_ids: list[str],
        timestamp: Optional[str] = None,
    ) -> None:
        with connect(app_paths().conversations_db(account)) as connection:
            connection.execute(
                """
                UPDATE conversation_sessions
                SET active_path_message_ids = ?, last_active_at = ?
                WHERE account = ? AND session_id = ?
                """,
                (
                    json.dumps(active_path_message_ids, ensure_ascii=False),
                    timestamp or now_iso(),
                    account,
                    session_id,
                ),
            )

    def delete_conversation(self, account: str, session_id: str) -> None:
        row = self.session_row(account, session_id)
        if not row:
            raise_error(404, "NOT_FOUND", "会话不存在。")

        timeline_path = self.timeline_abs_path(account, row["timeline_path"])
        attachments_dir = app_paths().account_root(account) / "conversations" / "attachments" / session_id
        with connect(app_paths().conversations_db(account)) as connection:
            connection.execute("DELETE FROM conversation_turns WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM conversation_resources WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM conversation_sessions WHERE session_id = ?", (session_id,))
        if timeline_path.exists():
            timeline_path.unlink()
        shutil.rmtree(attachments_dir, ignore_errors=True)

    def source_message_for_favorite(self, account: str, session_id: str, message_id: str):
        row = self.session_row(account, session_id)
        if not row:
            return None
        messages_by_id = self.messages_by_id(account, session_id)
        message = messages_by_id.get(message_id)
        if not message or message["role"] != "assistant":
            return None
        return {
            "title": row["title"],
            "content": message["content"],
            "message_id": message_id,
        }

    def conversation_exists(self, account: str, session_id: str) -> bool:
        return self.session_row(account, session_id) is not None

    def timeline_relative_path(self, session_id: str) -> str:
        return f"conversations/sessions/{session_id}.jsonl"

    def timeline_abs_path(self, account: str, relative_path: str) -> Path:
        return app_paths().account_root(account) / relative_path

    def migrate_dated_timeline_paths(self, account: str) -> None:
        sessions_dir = app_paths().account_root(account) / "conversations" / "sessions"
        with connect(app_paths().conversations_db(account)) as connection:
            rows = connection.execute(
                """
                SELECT session_id, timeline_path FROM conversation_sessions
                WHERE timeline_path LIKE 'conversations/sessions/%/%.jsonl'
                """
            ).fetchall()
            for row in rows:
                flattened_relative_path = self.timeline_relative_path(row["session_id"])
                if row["timeline_path"] == flattened_relative_path:
                    continue

                dated_path = self.timeline_abs_path(account, row["timeline_path"])
                flattened_path = self.timeline_abs_path(account, flattened_relative_path)
                flattened_path.parent.mkdir(parents=True, exist_ok=True)
                if dated_path.exists() and not flattened_path.exists():
                    dated_path.replace(flattened_path)
                    self.remove_empty_dated_timeline_dirs(dated_path.parent, sessions_dir)

                connection.execute(
                    """
                    UPDATE conversation_sessions
                    SET timeline_path = ?
                    WHERE account = ? AND session_id = ?
                    """,
                    (flattened_relative_path, account, row["session_id"]),
                )

    def remove_empty_dated_timeline_dirs(self, path: Path, stop_at: Path) -> None:
        try:
            path.relative_to(stop_at)
        except ValueError:
            return

        current = path
        while current != stop_at:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    def new_id(self) -> str:
        import uuid

        return str(uuid.uuid4())

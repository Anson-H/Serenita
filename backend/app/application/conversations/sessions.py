"""更新会话元数据，处理置顶、删除和会话分支创建。"""

import re
from backend.app.core.member_lifecycle import member_lifecycle_operation, member_lifecycle_guard
from typing import Any, Optional
from backend.app.core.errors import SerenitaError
from backend.app.core.errors import raise_error
from backend.app.domain.conversations.titles import SESSION_TITLE_MAX_CHARS
from backend.app.domain.conversations.titles import UNTITLED_CONVERSATION

class ConversationSessionCommands:
    def __init__(self, *, repository, paths, events, inputs, jobs, task_state, titles, queries):
        self.repository = repository
        self.paths = paths
        self.events = events
        self.inputs = inputs
        self.jobs = jobs
        self.task_state = task_state
        self.titles = titles
        self.queries = queries

    def update_conversation(
        self,
        account_id: str,
        session_id: str,
        *,
        title: str | None = None,
        is_pinned: bool | None = None,
    ) -> dict[str, Any]:
        normalized_title: str | None = None
        if title is not None:
            normalized_title = re.sub(r"\s+", " ", title).strip()
            if not normalized_title:
                raise_error("invalid_input", "INVALID_REQUEST", "聊天标题不能为空。")
            if len(normalized_title) > SESSION_TITLE_MAX_CHARS:
                raise_error(
                    "invalid_input",
                    "INVALID_REQUEST",
                    f"聊天标题不能超过 {SESSION_TITLE_MAX_CHARS} 个字符。",
                )
            self.titles.cancel(account_id, session_id)

        row = self.repository.update_session_metadata(
            account_id,
            session_id,
            title=normalized_title,
            is_pinned=is_pinned,
        )
        return {"session": self.queries.summary(account_id, row)}


    def batch_pin_conversations(
        self,
        account_id: str,
        session_ids: list[str],
        is_pinned: bool,
    ) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(str(value).strip() for value in session_ids))
        if any(not session_id for session_id in unique_ids):
            raise_error("invalid_input", "INVALID_REQUEST", "聊天标识不能为空。")
        rows = self.repository.batch_set_pinned(account_id, unique_ids, is_pinned)
        return {
            "sessions": [self.queries.summary(account_id, row) for row in rows]
        }


    def batch_delete_conversations(
        self,
        account_id: str,
        session_ids: list[str],
    ) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(str(value).strip() for value in session_ids))
        if not unique_ids or any(not session_id for session_id in unique_ids):
            raise_error("invalid_input", "INVALID_REQUEST", "请选择至少一个有效聊天。")
        deleted_ids: list[str] = []
        failed: list[dict[str, str]] = []
        for session_id in unique_ids:
            try:
                self.delete_conversation(account_id, session_id)
                deleted_ids.append(session_id)
            except SerenitaError as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {}
                failed.append(
                    {
                        "session_id": session_id,
                        "code": str(detail.get("code") or "DELETE_FAILED"),
                        "message": str(detail.get("message") or exc.detail),
                    }
                )
            except Exception as exc:
                failed.append(
                    {
                        "session_id": session_id,
                        "code": "DELETE_FAILED",
                        "message": str(exc) or "删除聊天失败。",
                    }
                )
        return {
            "success": not failed,
            "deleted_ids": deleted_ids,
            "failed": failed,
        }


    @member_lifecycle_operation
    def fork_conversation(
        self,
        account_id: str,
        session_id: str,
        at_seq: Optional[int] = None,
    ) -> dict[str, Any]:
        self.queries.member_access(account_id, session_id)
        row = self.repository.session_row(account_id, session_id)
        if row is None:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        events = list(self.events.view(account_id, session_id).events)
        if at_seq is None:
            boundary = next(
                (event for event in reversed(events) if event.type == "turn/end"),
                None,
            )
        else:
            anchor = next((event for event in events if event.seq == at_seq), None)
            turn_id = str(anchor.data.get("turn_id") or "") if anchor else ""
            boundary = next(
                (
                    event
                    for event in events
                    if event.type == "turn/end"
                    and str(event.data.get("turn_id") or "") == turn_id
                ),
                None,
            )
        if boundary is None:
            raise_error(
                "conflict", "FORK_UNAVAILABLE", "所选位置没有已结束的稳定轮次边界。"
            )

        next_turn = next(
            (
                event
                for event in events
                if event.type == "turn/start" and event.seq > boundary.seq
            ),
            None,
        )
        cutoff = next_turn.seq if next_turn is not None else len(events)
        seed = list(events[:cutoff])
        if not seed or seed[-1].seq != cutoff - 1:
            raise_error("conflict", "FORK_UNAVAILABLE", "无法形成连续的稳定聊天前缀。")

        child = self.repository.create_fork(
            account_id,
            session_id,
            seed,
            title=self._increment_fork_title(
                str(row["title"] or UNTITLED_CONVERSATION)
            ),
        )
        return {"session": self.queries.summary(account_id, child)}


    def delete_conversation(self, account_id: str, session_id: str) -> dict[str, Any]:
        self.inputs.maintain_attachments(account_id)
        self.titles.cancel(account_id, session_id)
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            pending = self.repository.list_pending_turn_rows(account_id, session_id)
            for turn in pending:
                self.jobs.cancel(account_id, session_id, str(turn["stream_id"]))
            for turn in pending:
                self.jobs.wait(
                    account_id, session_id, str(turn["stream_id"]), timeout=5.0
                )
            self.repository.delete_conversation(account_id, session_id)
        self.inputs.drain_attachment_cleanup(account_id)
        return {"success": True, "session_id": session_id, "message": "聊天已删除"}


    @staticmethod
    def _increment_fork_title(title: str) -> str:
        match = re.search(r"(\s*)([（(])(\d+)([）)])$", title)
        if match and ((match.group(2), match.group(4)) in {("(", ")"), ("（", "）")}):
            base = title[: match.start()]
            return (
                f"{base}{match.group(1)}{match.group(2)}"
                f"{int(match.group(3)) + 1}{match.group(4)}"
            )
        return f"{title} (1)"


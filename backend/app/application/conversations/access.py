"""检查会话成员权限、当前轮次状态和取消信号，保护执行与写入边界。"""

from backend.app.core.errors import raise_error


def session_member_access(repository, members, account_id, session_id):
    row = repository.session_row(account_id, session_id)
    if row is None:
        raise_error("missing", "NOT_FOUND", "聊天不存在。")
    if row["member_id"] is None:
        return None
    with members.access_guard(account_id, str(row["member_id"])) as access:
        return access


class ConversationExecutionGuard:
    """Live member authorization and cancellation shared by execution collaborators."""

    def __init__(self, repository, members):
        self.repository = repository
        self.members = members

    def member_access(self, account_id, session_id):
        return session_member_access(
            self.repository, self.members, account_id, session_id
        )

    def turn_cancelled(self, account_id, turn):
        current = self.repository.turn_row(
            account_id, turn["session_id"], turn["turn_id"]
        )
        return bool(current and current["status"] == "cancelled")

    def cancelled(self, account_id, turn, cancellation_token):
        return bool(
            cancellation_token and cancellation_token.is_cancelled
        ) or self.turn_cancelled(account_id, turn)

    def ensure_active(self, account_id, turn, cancellation_token):
        from backend.app.core.cancellation import OperationCancelledError

        self.member_access(account_id, str(turn["session_id"]))
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()
        current = self.repository.turn_row(account_id, turn["session_id"], turn["turn_id"])
        if current is None or current["status"] not in {"queued", "streaming"}:
            raise OperationCancelledError("当前任务已经结束。")

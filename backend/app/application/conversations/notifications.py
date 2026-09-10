"""构造回答完成通知及其类型定义，供应用通知模块装配。"""

from datetime import datetime
from backend.app.application.notification_types import NotificationType
from backend.app.core.values import digest
from backend.app.repositories.notification_repository import timestamp
from backend.app.repositories.notification_repository import NotificationRepository


def completion_event(account_id, session_id, turn_id, completed_at):
    at = timestamp(datetime.fromisoformat(completed_at))
    return {
        "event_id": digest(["answer_completed", account_id, session_id, turn_id]),
        "recipients": [account_id],
        "content": {
            "member_id": None,
            "resource_type": "conversation",
            "resource_id": session_id,
            "notification_type": "answer_completed",
            "occurred_at": at,
            "available_at": at,
            "title": "回答已生成",
            "message": "",
            "validity_key": turn_id,
            "event_revision": 1,
        },
    }


def build_types(paths):
    def load(scope, ids):
        rows = NotificationRepository(paths).completed_conversations(scope.actor_account_id, ids)
        result = {}
        for row in rows:
            entry = result.setdefault(row["session_id"], {"title": row["title"], "turns": set()})
            entry["turns"].add(row["turn_id"])
        return result

    def present(row, conversation):
        if row["validity_key"] not in conversation["turns"]:
            return None
        return {
            "message": conversation["title"],
            "details": [{"label": "聊天", "text": conversation["title"]}],
        }

    return [NotificationType("answer_completed", "conversation", load, present, requires_member=False)]

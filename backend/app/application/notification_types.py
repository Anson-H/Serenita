"""Application-owned notification types and resource projections."""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class AccountNotificationScope:
    account_id: str
    actor_account_id: str
    member_id: None = None


@dataclass(frozen=True)
class NotificationType:
    name: str
    resource_type: str | None
    load: Callable
    present: Callable
    requires_member: bool = True
    delivery_allowed: Callable | None = None


def build_notification_types(paths):
    from backend.app.application.conversations.notifications import build_types as conversation_types
    from backend.app.application.medication_notifications import build_types as medication_types

    result = {}
    for builder in (conversation_types, medication_types):
        for item in builder(paths):
            if item.name in result:
                raise ValueError("重复的通知类型")
            result[item.name] = item
    return result

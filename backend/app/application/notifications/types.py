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
    delivery_admission: Callable | None = None

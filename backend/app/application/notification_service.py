"""Shared notification authorization, projections and delivery."""

import base64
import json
import logging
from collections import defaultdict
from contextlib import nullcontext
from backend.app.core.errors import SerenitaError, raise_error
from backend.app.core.notification_runtime import notification_runtime
from backend.app.domain.notification_preferences import PREFERENCE_NAMES
from backend.app.application.notification_types import (
    build_notification_types,
    AccountNotificationScope,
)
from backend.app.repositories.notification_repository import NotificationRepository

log = logging.getLogger(__name__)
_UNSET = object()


class NotificationService:
    def __init__(self, members, *, types=None):
        self.members, self.paths = members, members.paths
        self.repository = NotificationRepository(self.paths)
        self.runtime = notification_runtime(self.paths)
        self.types = (
            types if types is not None else build_notification_types(self.paths)
        )

    def preferences(self, actor):
        return self.repository.preferences(actor)

    def set_preferences(self, actor, notifications_enabled=_UNSET, **changes):
        if notifications_enabled is not _UNSET:
            changes["notifications_enabled"] = notifications_enabled
        allowed = {f"{name}_enabled" for name in PREFERENCE_NAMES}
        if not changes or any(key not in allowed or type(value) is not bool for key, value in changes.items()):
            raise_error(
                "invalid_input",
                "NOTIFICATION_PREFERENCES_INVALID",
                "至少提供一个有效的通知开关，值必须为布尔值。",
            )
        if "notifications_enabled" in changes and len(changes) > 1:
            raise_error(
                "invalid_input", "NOTIFICATION_PREFERENCES_INVALID",
                "总通知与子通知不能在同一次请求中设置。",
            )
        value = self.repository.set_preferences(actor, changes)
        self.runtime.changed([actor], reschedule=True)
        return value

    def guard(self, actor, member):
        return (
            self.members.access_guard(actor, member)
            if member
            else nullcontext(AccountNotificationScope(actor, actor))
        )

    def project(self, actor, rows):
        groups = defaultdict(list)
        for row in rows:
            groups[(row["notification_type"], row["member_id"])].append(row)
        visible, invalid, errors = [], [], []
        for (name, member), batch in groups.items():
            adapter = self.types.get(name)
            if adapter is None:
                errors.append(
                    {
                        "code": "NOTIFICATION_TYPE_UNAVAILABLE",
                        "message": "部分通知暂时无法读取，请重试。",
                    }
                )
                continue
            if adapter.requires_member and not member:
                invalid.extend(row["notification_id"] for row in batch)
                continue
            try:
                with self.guard(actor, member) as access:
                    resources = adapter.load(
                        access, {row["resource_id"] for row in batch}
                    )
                    for row in batch:
                        resource = resources.get(row["resource_id"])
                        view = (
                            adapter.present(row, resource)
                            if resource is not None
                            and row["resource_type"] == adapter.resource_type
                            else None
                        )
                        if view is None:
                            invalid.append(row["notification_id"])
                            continue
                        visible.append(
                            {
                                **row,
                                **view,
                                "target": view.get("target", {
                                    "member_id": member,
                                    "resource_type": row["resource_type"],
                                    "resource_id": row["resource_id"],
                                }),
                                "actions": ["read"]
                                if row["status"] == "pending"
                                else [],
                            }
                        )
            except (SerenitaError, LookupError) as exc:
                if isinstance(exc, LookupError) or exc.kind in ("missing", "forbidden"):
                    invalid.extend(row["notification_id"] for row in batch)
                else:
                    raise
            except Exception:
                log.exception("Notification projection failed")
                errors.append(
                    {
                        "code": "NOTIFICATION_READ_FAILED",
                        "message": "部分通知暂时无法读取，请重试。",
                    }
                )
        self.repository.cancel(actor, invalid)
        if invalid:
            self.runtime.changed([actor])
        return visible, errors

    def revalidate(self, actor, *, member_id=None):
        after = ""
        while True:
            rows = self.repository.active_resources(actor, member_id=member_id, after=after)
            if not rows:
                return
            self.project(actor, rows)
            after = rows[-1]["notification_id"]

    def resources_changed(self, *, member_id, account_ids=None):
        try:
            accounts = tuple(account_ids) if account_ids is not None else self.repository.member_accounts(member_id)
        except Exception:
            log.exception("Failed to resolve notification recipients after resource commit")
            self.runtime.changed((), reschedule=True)
            return
        for actor in accounts:
            try:
                self.revalidate(actor, member_id=member_id)
            except Exception:
                log.exception("Notification revalidation failed after resource commit")
        self.runtime.changed(accounts, reschedule=True)

    def list(self, actor, *, status="pending", limit=50, cursor=None):
        if (
            status not in ("pending", "read")
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise_error(
                "invalid_input", "NOTIFICATION_QUERY_INVALID", "通知查询参数无效。"
            )
        before = None
        if cursor:
            try:
                value = json.loads(base64.urlsafe_b64decode(cursor))
                if (
                    value[:2] != [actor, status]
                    or len(value) != 4
                    or not all(isinstance(v, str) for v in value)
                ):
                    raise ValueError()
                before = value[2:]
            except Exception:
                raise_error(
                    "invalid_input", "NOTIFICATION_CURSOR_INVALID", "通知分页标识无效。"
                )
        rows = self.repository.rows(actor, status=status, before=before, limit=500)
        window = rows[:500]
        visible, errors = self.project(actor, window)
        by_id = {row["notification_id"]: row for row in visible}
        items, consumed = [], None
        for row in window:
            consumed = row
            if row["notification_id"] in by_id:
                items.append(by_id[row["notification_id"]])
            if len(items) == limit:
                break
        next_cursor = None
        if consumed and (consumed != rows[-1] or len(rows) == 500):
            next_cursor = base64.urlsafe_b64encode(
                json.dumps(
                    [
                        actor,
                        status,
                        consumed["occurred_at"],
                        consumed["notification_id"],
                    ]
                ).encode()
            ).decode()
        return {"items": items, "next_cursor": next_cursor, "errors": errors}

    def summary(self, actor):
        before, count, errors = None, 0, []
        for _ in range(4):
            rows = self.repository.rows(actor, before=before, limit=500)
            visible, failed = self.project(actor, rows)
            count += len(visible)
            errors.extend(failed)
            if count >= 100:
                return {"pending_count": 100, "errors": errors}
            if len(rows) < 500:
                return {"pending_count": None if errors else count, "errors": errors}
            before = (rows[-1]["occurred_at"], rows[-1]["notification_id"])
        return {
            "pending_count": None,
            "errors": errors
            or [
                {
                    "code": "NOTIFICATION_COUNT_INCOMPLETE",
                    "message": "通知数量暂时无法确认。",
                }
            ],
        }

    def act(self, actor, notification_id, action):
        if action != "read":
            raise_error(
                "invalid_input", "NOTIFICATION_ACTION_INVALID", "通知操作无效。"
            )
        row = self.repository.get(actor, notification_id)
        if not row:
            raise_error("missing", "NOTIFICATION_NOT_FOUND", "通知不存在。")
        with self.guard(actor, row["member_id"]):
            if row["status"] == "cancelled":
                raise_error("conflict", "NOTIFICATION_INVALID", "通知已失效。")
            visible, errors = self.project(actor, [row])
            if errors:
                raise_error(
                    "conflict", "NOTIFICATION_UNAVAILABLE", "通知暂时无法处理，请重试。"
                )
            if not visible:
                raise_error("conflict", "NOTIFICATION_INVALID", "通知已失效。")
            result = self.repository.mark_read(actor, notification_id)
        self.runtime.changed([actor])
        return result

    def deliver(self, actor, event_id, content):
        adapter = self.types.get(content["notification_type"])
        if adapter is None:
            raise ValueError("通知类型不可用")
        if adapter.requires_member and not content["member_id"]:
            return "skipped"
        with self.guard(actor, content["member_id"]) as access:
            resource = adapter.load(access, {content["resource_id"]}).get(
                content["resource_id"]
            )
            if (
                content["resource_type"] != adapter.resource_type
                or resource is None
                or adapter.present(content, resource) is None
                or (adapter.delivery_allowed is not None
                    and not adapter.delivery_allowed(content, resource))
            ):
                return "skipped"
            self.repository.preferences(actor)
            outcome = self.repository.deliver(actor, event_id, content)
        if outcome == "delivered":
            self.runtime.changed([actor])
        return outcome

    def dispatch(self, owner, at=None):
        accounts = set(self.repository.accounts())
        for row in self.repository.pending(owner, at):
            try:
                result = (
                    self.deliver(row["recipient_account_id"], row["event_id"], row)
                    if row["recipient_account_id"] in accounts
                    else "skipped"
                )
                self.repository.finish_delivery(owner, row, result)
            except (SerenitaError, LookupError) as exc:
                if isinstance(exc, LookupError) or exc.kind in ("forbidden", "missing"):
                    self.repository.finish_delivery(owner, row, "skipped")
                else:
                    self.repository.finish_delivery(
                        owner, row, "pending", "NOTIFICATION_DELIVERY_FAILED"
                    )
            except Exception:
                log.exception("Notification delivery failed")
                self.repository.finish_delivery(
                    owner, row, "pending", "NOTIFICATION_DELIVERY_FAILED"
                )

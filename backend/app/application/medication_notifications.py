"""Medication notification projection and saved-schedule producer."""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from backend.app.application.notification_types import NotificationType
from backend.app.core.values import digest
from backend.app.domain.medications import medication_name, plan_status
from backend.app.domain.notification_preferences import reception_since
from backend.app.domain.medication_schedule import (
    first_occurrence,
    occurrences,
    schedulable,
)
from backend.app.repositories.medication_repository import MedicationRepository
from backend.app.repositories.notification_repository import timestamp


REMINDER_WINDOW = timedelta(minutes=10)


def reminder_delivery_allowed(row, plan):
    elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(row["occurred_at"])
    return timedelta(0) <= elapsed < REMINDER_WINDOW


def batch_expiration(batch):
    if (not batch.get("expires_on") or batch["expires_on"] == "9999-12-31"
        or Decimal(batch["quantity"]) == 0):
        return None
    # A date-only expiry remains valid through the end of that local day.
    return (datetime.fromisoformat(batch["expires_on"]) + timedelta(days=1)).astimezone(timezone.utc)


def expired_content(member, batch, due):
    return {
        "member_id": member,
        "resource_type": "medication_batch",
        "resource_id": batch["medication_batch_id"],
        "notification_type": "medication_expired",
        "occurred_at": timestamp(due),
        "available_at": timestamp(due),
        "title": "药品已过期",
        "message": "请查看药品批次。",
        "validity_key": batch["expires_on"],
        "event_revision": 1,
    }


def medication_validity_key(plan):
    return digest(
        {
            key: plan.get(key)
            for key in (
                "medication_id",
                "starts_at",
                "ends_at",
                "start_precision",
                "end_precision",
                "timezone",
                "dose_text",
                "route",
                "schedule",
                "usage_status",
            )
        }
    )


def build_types(paths):
    def load(access, ids):
        if not paths.medications_db(access.account_id).exists():
            return {}
        repo = MedicationRepository(access.account_id, paths)
        with repo.transaction() as db:
            plans = repo.plan_snapshots(db, access.member_id, ids)
        name = access.access_repository.detail(access, paths)["member_name"]
        return {key: {**value, "member_name": name} for key, value in plans.items()}

    def present(row, plan):
        if (
            not schedulable(plan)
            or plan_status(plan)[0] == "ended"
            or row["validity_key"] != medication_validity_key(plan)
        ):
            return None
        drug = medication_name(plan["medication_identity"])
        dose = plan.get("dose_text")
        summary = f"{drug} {dose}" if dose else drug
        return {
            "message": f"{plan['member_name']} · {summary}",
            "details": [
                {"label": "成员", "text": plan["member_name"]},
                {"label": "药品", "text": medication_name(plan["medication_identity"])},
                {"label": "每次剂量", "text": plan.get("dose_text") or "未记录"},
            ]
        }

    def load_batches(access, ids):
        if not paths.medications_db(access.account_id).exists():
            return {}
        repo = MedicationRepository(access.account_id, paths)
        with repo.transaction() as db:
            batches = repo.batch_snapshots(db, access.member_id, ids)
        name = access.access_repository.detail(access, paths)["member_name"]
        return {key: {**value, "member_name": name} for key, value in batches.items()}

    def present_expired(row, batch):
        expiration = batch_expiration(batch)
        if (expiration is None or expiration > datetime.now(timezone.utc)
            or row["validity_key"] != batch["expires_on"]):
            return None
        drug = medication_name(batch["medication_identity"])
        return {
            "message": f"{batch['member_name']} · {drug} · 有效期至 {batch['expires_on']}",
            "details": [
                {"label": "成员", "text": batch["member_name"]},
                {"label": "药品", "text": drug},
                {"label": "有效期", "text": batch["expires_on"]},
            ],
            "target": {
                "member_id": batch["member_id"],
                "resource_type": "medication_batch",
                "resource_id": batch["medication_batch_id"],
                "medication_id": batch["medication_id"],
            },
        }

    return [
        NotificationType("medication_due", "medication_plan", load, present,
                         delivery_allowed=reminder_delivery_allowed),
        NotificationType("medication_expired", "medication_batch", load_batches, present_expired),
    ]


class MedicationNotificationProducer:
    task_name = "medication_reminders"

    def __init__(self, notifications):
        self.notifications = notifications
        self.members, self.paths, self.repository = (
            notifications.members,
            notifications.paths,
            notifications.repository,
        )

    def resources(self, actor, notification_type, kind):
        pref = self.repository.preferences(actor)
        since = reception_since(pref, notification_type)
        if since is None:
            return []
        results = []
        for member in self.members.list_accessible(actor)["members"]:
            member_id = member["member_id"]
            with self.members.access_guard(actor, member_id) as access:
                if not self.paths.medications_db(access.account_id).exists():
                    continue
                granted = since
                if access.grant_updated_at is not None:
                    granted = max(since, access.grant_updated_at)
                repo = MedicationRepository(access.account_id, self.paths)
                with repo.transaction() as db:
                    snapshots = repo.plan_snapshots if kind == "plan" else repo.batch_snapshots
                    for plan in snapshots(db, member_id).values():
                        lower = max(
                            granted,
                            datetime.fromisoformat(plan["created_at"]),
                            datetime.fromisoformat(plan["updated_at"]),
                        )
                        results.append((member_id, plan, lower))
        return results

    def plans(self, actor, notification_type):
        return self.resources(actor, notification_type, "plan")

    def unnotified_batches(self, actor):
        received = self.repository.received_resources(actor, "medication_expired")
        return [
            (member, batch, lower)
            for member, batch, lower in self.resources(actor, "medication_expired", "batch")
            if (member, batch["medication_batch_id"]) not in received
        ]

    @staticmethod
    def content(member, plan, due):
        return {
            "member_id": member,
            "resource_type": "medication_plan",
            "resource_id": plan["medication_plan_id"],
            "notification_type": "medication_due",
            "occurred_at": timestamp(due),
            "available_at": timestamp(due),
            "title": "用药时间到了",
            "message": "请查看当前用药计划。",
            "validity_key": medication_validity_key(plan),
            "event_revision": 1,
        }

    def publish(self, actor, member, plan, due):
        content = self.content(member, plan, due)
        event_id = digest(
            [
                content["notification_type"],
                member,
                content["resource_id"],
                content["validity_key"],
                timestamp(due),
            ]
        )
        return self.notifications.deliver(actor, event_id, content)

    def publish_expired(self, actor, member, batch, due):
        event_id = digest(["medication_expired", member, batch["medication_batch_id"]])
        return self.notifications.deliver(actor, event_id, expired_content(member, batch, due))

    def next_job(self, actor, member, plan, after):
        from backend.app.application.notification_scheduler import ScheduledCall

        due = first_occurrence(plan, after, datetime(9998, 1, 1, tzinfo=timezone.utc))
        if due is None:
            return None

        def execute():
            self.publish(actor, member, plan, due)
            return self.next_job(actor, member, plan, due)

        return ScheduledCall(due.timestamp(), execute)

    def jobs(self, at):
        jobs = []
        for actor in self.repository.accounts():
            try:
                for member, plan, lower in self.plans(actor, "medication_due"):
                    job = self.next_job(actor, member, plan, max(at, lower))
                    if job:
                        jobs.append(job)
                from backend.app.application.notification_scheduler import ScheduledCall

                for member, batch, lower in self.unnotified_batches(actor):
                    expiration = batch_expiration(batch)
                    if expiration is None:
                        continue
                    due = max(expiration, lower)
                    def execute(actor=actor, member=member, batch=batch, due=due):
                        self.publish_expired(actor, member, batch, due)
                    jobs.append(ScheduledCall(max(at, due).timestamp(), execute))
            except Exception:
                logging.getLogger(__name__).exception(
                    "Account medication schedule unavailable"
                )
        return jobs

    def recover_actor(self, actor, at):
        pref = self.repository.preferences(actor)
        if not pref["notifications_enabled"]:
            return
        row = self.repository.checkpoint(
            actor, self.task_name, pref["notifications_enabled_since"], timestamp(at)
        )
        lower, upper = (
            datetime.fromisoformat(row["scan_from"]),
            datetime.fromisoformat(row["scan_until"]),
        )
        recent = max(at, datetime.now(timezone.utc)) - REMINDER_WINDOW
        for member, plan, eligible in self.plans(actor, "medication_due"):
            start = max(lower, eligible)
            for due, _ in occurrences(plan, max(start, recent), upper):
                self.publish(actor, member, plan, due)
        self.repository.complete_checkpoint(actor, row)
        for member, batch, eligible in self.unnotified_batches(actor):
            expiration = batch_expiration(batch)
            if expiration is not None and max(expiration, eligible) <= at:
                self.publish_expired(actor, member, batch, max(expiration, eligible))

    def recover(self, at):
        for actor in self.repository.accounts():
            try:
                self.recover_actor(actor, at)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Account medication recovery failed"
                )

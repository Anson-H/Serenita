"""Canonical account notification and background-task schemas."""

from backend.app.domain.notification_preferences import NOTIFICATION_TYPES

from backend.app.storage.schema import (
    Column,
    ColumnGroup as G,
    Database,
    Table,
    CheckConstraint as Check,
    Index,
)


def col(name, group=G.DATA, nullable=False, storage="TEXT", default=None, **rules):
    return Column(name, storage, group, nullable=nullable, default=default, **rules)


ACCOUNT_PREFERENCES_TABLE = Table(
    "account_preferences",
    (
        col("singleton_id", G.PRIMARY_KEY, storage="INTEGER"),
        col("notifications_enabled", G.STATE, storage="INTEGER", default="0"),
        col("notifications_enabled_since", G.STATE, nullable=True),
        *(column for name in NOTIFICATION_TYPES for column in (
            col(f"{name}_enabled", G.STATE, storage="INTEGER", default="0"),
            col(f"{name}_enabled_since", G.STATE, nullable=True),
        )),
        col("notifications_updated_at", G.AUDIT),
    ),
    ("singleton_id",),
    checks=(
        Check("singleton_id = 1"),
        Check("notifications_enabled IN (0, 1)"),
        Check("notifications_enabled = 0 OR notifications_enabled_since IS NOT NULL"),
        *(Check(f"{name}_enabled IN (0, 1)") for name in NOTIFICATION_TYPES),
        *(Check(f"{name}_enabled = 0 OR {name}_enabled_since IS NOT NULL") for name in NOTIFICATION_TYPES),
        Check("notifications_enabled = (" + " OR ".join(f"{name}_enabled" for name in NOTIFICATION_TYPES) + ")"),
    ),
)


def content_columns():
    return (
        col("member_id", G.SCOPE, nullable=True),
        col("resource_type", G.REFERENCE, nullable=True),
        col("resource_id", G.REFERENCE, nullable=True),
        col("notification_type"),
        col("occurred_at"),
        col("available_at"),
        col("title"),
        col("message", non_blank=False),
        col("validity_key", G.STATE, nullable=True),
        col("event_revision", G.STATE, storage="INTEGER"),
    )


CONTENT_CHECKS = (
    Check("(resource_type IS NULL) = (resource_id IS NULL)"),
    Check("event_revision > 0"),
    Check("notification_type IN ('medication_due','medication_expired','answer_completed')"),
    Check("resource_type IS NOT NULL AND resource_id IS NOT NULL AND validity_key IS NOT NULL"),
    Check("notification_type = 'answer_completed' OR member_id IS NOT NULL"),
    Check("available_at >= occurred_at"),
)
NOTIFICATION_DATABASE_SCHEMA = Database(
    "notifications.db",
    (
        Table(
            "notifications",
            (
                col("notification_id", G.PRIMARY_KEY),
                *content_columns(),
                col("status", G.STATE),
                col("created_at", G.AUDIT),
                col("updated_at", G.AUDIT),
            ),
            ("notification_id",),
            checks=CONTENT_CHECKS
            + (Check("status IN ('pending', 'read', 'cancelled')"),),
            indexes=(
                Index(
                    "notification_list", ("status", "occurred_at", "notification_id")
                ),
                Index("notification_available", ("status", "available_at")),
                Index(
                    "notification_resource",
                    ("member_id", "resource_type", "resource_id"),
                ),
            ),
        ),
        Table(
            "notification_outbox",
            (
                col("event_id", G.PRIMARY_KEY),
                col("recipient_account_id", G.PRIMARY_KEY),
                *content_columns(),
                col("status", G.STATE),
                col("attempt_count", G.STATE, storage="INTEGER", default="0"),
                col("next_attempt_at", G.STATE),
                col("last_error_code", G.STATE, nullable=True),
                col("created_at", G.AUDIT),
                col("updated_at", G.AUDIT),
            ),
            ("event_id", "recipient_account_id"),
            checks=CONTENT_CHECKS
            + (
                Check("status IN ('pending', 'delivered', 'skipped')"),
                Check("attempt_count >= 0"),
            ),
            indexes=(
                Index("notification_outbox_ready", ("status", "next_attempt_at")),
            ),
        ),
    ),
)

BACKGROUND_TASK_DATABASE_SCHEMA = Database(
    "background_tasks.db",
    (
        Table(
            "background_task_checkpoints",
            (
                col("task_name", G.PRIMARY_KEY),
                col("last_completed_at", G.STATE),
                col("scan_from", G.STATE, nullable=True),
                col("scan_until", G.STATE, nullable=True),
                col("created_at", G.AUDIT),
                col("updated_at", G.AUDIT),
            ),
            ("task_name",),
            checks=(
                Check("(scan_from IS NULL) = (scan_until IS NULL)"),
                Check("scan_from IS NULL OR scan_from <= scan_until"),
            ),
        ),
    ),
)

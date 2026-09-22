"""Canonical account notification and background-task schemas."""

from backend.app.domain.notification_preferences import NOTIFICATION_TYPES
from backend.app.storage.business_change_database import BUSINESS_CHANGE_TABLES

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

        col("notifications_enabled_since", G.STATE, nullable=True, storage="DATETIME"),
        *(column for name in NOTIFICATION_TYPES for column in (
            col(f"{name}_enabled", G.STATE, storage="INTEGER", default="0"),
            col(f"{name}_enabled_since", G.STATE, nullable=True, storage="DATETIME"),
        )),
        col("notifications_updated_at", G.AUDIT, storage="DATETIME"),
    ),
    ("singleton_id",),
    checks=(
        Check("singleton_id = 1"),


        *(Check(f"{name}_enabled IN (0, 1)") for name in NOTIFICATION_TYPES),
        *(Check(f"{name}_enabled = 0 OR {name}_enabled_since IS NOT NULL") for name in NOTIFICATION_TYPES),

    ),
)


def content_columns():
    return (
        col("member_id", G.SCOPE, nullable=True),
        col("resource_type", G.REFERENCE, nullable=True),
        col("resource_id", G.REFERENCE, nullable=True),
        col("notification_type"),
        col("occurred_at", storage="DATETIME"),
        col("available_at", storage="DATETIME"),
        col("title"),
        col("message", non_blank=False),
        col("validity_key", G.STATE, nullable=True),

    )


CONTENT_CHECKS = (
    Check("(resource_type IS NULL) = (resource_id IS NULL)"),

    Check("notification_type IN (" + ",".join("'" + name + "'" for name in NOTIFICATION_TYPES) + ")"),
    Check("resource_type IS NOT NULL AND resource_id IS NOT NULL AND validity_key IS NOT NULL"),
    Check("notification_type = 'answer_completed' OR member_id IS NOT NULL"),
    Check("available_at >= occurred_at"),
)
BACKGROUND_TASK_CHECKPOINTS_TABLE = Table(
    "background_task_checkpoints",
    (
        col("task_name", G.PRIMARY_KEY),
        col("last_completed_at", G.STATE, storage="DATETIME"),
        col("scan_from", G.STATE, nullable=True, storage="DATETIME"),
        col("scan_until", G.STATE, nullable=True, storage="DATETIME"),
        col("created_at", G.AUDIT, storage="DATETIME"),
        col("updated_at", G.AUDIT, storage="DATETIME"),
    ),
    ("task_name",),
    checks=(
        Check("(scan_from IS NULL) = (scan_until IS NULL)"),
        Check("scan_from IS NULL OR scan_from <= scan_until"),
    ),
)


NOTIFICATION_DATABASE_SCHEMA = Database(
    "notifications.db",
    (
        *BUSINESS_CHANGE_TABLES,
        ACCOUNT_PREFERENCES_TABLE,
        BACKGROUND_TASK_CHECKPOINTS_TABLE,
        Table(
            "notifications",
            (
                col("notification_id", G.PRIMARY_KEY),
                *content_columns(),
                col("status", G.STATE),
                col("created_at", G.AUDIT, storage="DATETIME"),
                col("updated_at", G.AUDIT, storage="DATETIME"),
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
    ),
)

"""Pending answer notifications commit with their conversation turn."""

from backend.app.storage.notification_database import CONTENT_CHECKS, col, content_columns
from backend.app.storage.schema import CheckConstraint, ColumnGroup as G, Index, Table


NOTIFICATION_OUTBOX_TABLE = Table(
    "notification_outbox",
    (
        col("event_id", G.PRIMARY_KEY),
        col("recipient_account_id", G.PRIMARY_KEY),
        *content_columns(),
        col("status", G.STATE),
        col("attempt_count", G.STATE, storage="INTEGER", default="0"),
        col("next_attempt_at", G.STATE, storage="DATETIME"),
        col("last_error_code", G.STATE, nullable=True),
        col("created_at", G.AUDIT, storage="DATETIME"),
        col("updated_at", G.AUDIT, storage="DATETIME"),
    ),
    ("event_id", "recipient_account_id"),
    checks=CONTENT_CHECKS + (
        CheckConstraint("status IN ('pending', 'delivered', 'skipped')"),
        CheckConstraint("attempt_count >= 0"),
    ),
    indexes=(Index("notification_outbox_ready", ("status", "next_attempt_at")),),
)

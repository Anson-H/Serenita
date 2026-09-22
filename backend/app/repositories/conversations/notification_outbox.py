"""Answer notification delivery state belongs to the sending conversation store."""
from datetime import timedelta

from backend.app.core.time import local_now
from backend.app.storage.conversations.notification_database import NOTIFICATION_OUTBOX_TABLE
from backend.app.storage.sqlite import connect


def timestamp(value=None):
    return (value or local_now()).astimezone().isoformat(timespec="microseconds")


class ConversationNotificationOutboxRepository:
    def __init__(self, paths):
        self.paths = paths

    @staticmethod
    def insert(db, table, value):
        NOTIFICATION_OUTBOX_TABLE.validate_values(value)
        db.execute(
            f"INSERT INTO {table} ({','.join(value)}) VALUES ({','.join('?' for _ in value)})",
            tuple(value.values()),
        )

    def enqueue(self, db, event_id, recipients, content):
        if not db.in_transaction:
            raise ValueError("待发送通知必须与会话完成使用同一事务。")
        table = "notification_outbox"
        at = timestamp()
        for recipient in sorted(set(recipients)):
            if db.execute(
                f"SELECT 1 FROM {table} WHERE event_id=? AND recipient_account_id=?",
                (event_id, recipient),
            ).fetchone():
                continue
            self.insert(
                db, table,
                {
                    "event_id": event_id,
                    "recipient_account_id": recipient,
                    **content,
                    "status": "pending",
                    "attempt_count": 0,
                    "next_attempt_at": at,
                    "last_error_code": None,
                    "created_at": at,
                    "updated_at": at,
                },
            )

    def pending(self, owner, at=None):
        path = self.paths.conversations_db(owner)
        if not path.exists():
            return []
        with connect(path) as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM notification_outbox WHERE status='pending' AND next_attempt_at<=? ORDER BY next_attempt_at,event_id LIMIT 100",
                    (timestamp(at),),
                )
            ]

    def finish_delivery(self, owner, row, status, error=None):
        retry = (1, 2, 5, 10, 30, 60, 120, 300)[min(row["attempt_count"], 7)]
        at = timestamp()
        next_at = (
            timestamp(local_now() + timedelta(seconds=retry))
            if error
            else at
        )
        with connect(self.paths.conversations_db(owner)) as db:
            db.execute(
                "UPDATE notification_outbox SET status=?,attempt_count=attempt_count+?,next_attempt_at=?,last_error_code=?,updated_at=? WHERE event_id=? AND recipient_account_id=? AND status='pending'",
                (
                    status,
                    int(bool(error)),
                    next_at,
                    error,
                    at,
                    row["event_id"],
                    row["recipient_account_id"],
                ),
            )

    def next_delivery(self, owner):
        path = self.paths.conversations_db(owner)
        if not path.exists():
            return None
        with connect(path) as db:
            return db.execute(
                "SELECT min(next_attempt_at) FROM notification_outbox WHERE status='pending'"
            ).fetchone()[0]

"""Account-isolated notification persistence, delivery and recovery checkpoints."""

from datetime import datetime, timezone, timedelta
from threading import RLock
from backend.app.core.values import digest
from backend.app.domain.notification_preferences import NOTIFICATION_TYPES, PREFERENCE_NAMES, reception_since
from backend.app.storage.sqlite import connect
from backend.app.storage.config_database import initialize_config_database
from backend.app.storage.notification_database import (
    NOTIFICATION_DATABASE_SCHEMA,
    BACKGROUND_TASK_DATABASE_SCHEMA,
    ACCOUNT_PREFERENCES_TABLE,
)


def timestamp(value=None):
    return (
        (value or datetime.now(timezone.utc))
        .astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
    )


CONTENT = (
    "member_id",
    "resource_type",
    "resource_id",
    "notification_type",
    "occurred_at",
    "available_at",
    "title",
    "message",
    "validity_key",
    "event_revision",
)


class NotificationRepository:
    def __init__(self, paths):
        self.paths = paths
        self._ready = set()
        self._ready_preferences = set()
        self._lock = RLock()

    def accounts(self):
        if not self.paths.auth_db.exists():
            return []
        with connect(self.paths.auth_db) as db:
            return [row[0] for row in db.execute("SELECT account_id FROM accounts")]

    def completed_conversations(self, actor, session_ids):
        path = self.paths.conversations_db(actor)
        if not path.exists() or not session_ids:
            return []
        with connect(path) as db:
            return db.execute(
                "SELECT c.session_id, c.title, t.turn_id FROM conversations c "
                "JOIN conversation_turns t ON t.session_id=c.session_id "
                f"WHERE c.session_id IN ({','.join('?' for _ in session_ids)}) "
                "AND t.status='completed' AND t.final_assistant_message_id IS NOT NULL",
                tuple(session_ids),
            ).fetchall()

    def member_accounts(self, member_id):
        with connect(self.paths.auth_db) as db:
            return [row[0] for row in db.execute(
                "SELECT account_id FROM member_ownerships WHERE member_id=? "
                "UNION SELECT account_id FROM member_grants WHERE member_id=?",
                (member_id, member_id),
            )]

    def active_resources(self, actor, *, member_id=None, after="", limit=500):
        path = self.paths.notifications_db(actor)
        if not path.exists():
            return []
        where = "status!='cancelled' AND notification_id>?"
        args = [after]
        if member_id is not None:
            where += " AND member_id=?"
            args.append(member_id)
        with connect(path) as db:
            return [dict(row) for row in db.execute(
                f"SELECT * FROM notifications WHERE {where} ORDER BY notification_id LIMIT ?",
                (*args, limit),
            )]

    def initialize(self, account):
        with self._lock:
            if account in self._ready:
                return
            path = self.paths.notifications_db(account)
            if not NOTIFICATION_DATABASE_SCHEMA.validate_existing(path):
                with connect(path) as db:
                    db.execute("BEGIN IMMEDIATE")
                    NOTIFICATION_DATABASE_SCHEMA.create(db)
            self._ready.add(account)

    def preferences(self, account):
        with self._lock:
            if account not in self._ready_preferences:
                initialize_config_database(account, self.paths)
                self._ready_preferences.add(account)
        with connect(self.paths.config_db(account)) as db:
            row = dict(
                db.execute(
                    "SELECT * FROM account_preferences WHERE singleton_id=1"
                ).fetchone()
            )
        row.pop("singleton_id")
        for name in PREFERENCE_NAMES:
            row[f"{name}_enabled"] = bool(row[f"{name}_enabled"])
        return row

    def set_preferences(self, account, changes):
        self.preferences(account)
        with connect(self.paths.config_db(account)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM account_preferences WHERE singleton_id=1"
            ).fetchone()
            type_keys = [f"{name}_enabled" for name in NOTIFICATION_TYPES]
            if "notifications_enabled" in changes:
                changes = {key: changes["notifications_enabled"] for key in type_keys}
            states = {key: changes.get(key, bool(row[key])) for key in type_keys}
            changes = {**states, "notifications_enabled": any(states.values())}
            updates = {}
            at = timestamp()
            for key, enabled in changes.items():
                if bool(row[key]) != enabled:
                    updates[key] = int(enabled)
                    if enabled:
                        updates[f"{key}_since"] = at
            if updates:
                updates["notifications_updated_at"] = at
                ACCOUNT_PREFERENCES_TABLE.validate_values({**dict(row), **updates})
                db.execute(
                    f"UPDATE account_preferences SET {','.join(key + '=?' for key in updates)} WHERE singleton_id=1",
                    tuple(updates.values()),
                )
        return self.preferences(account)

    def rows(self, account, *, status="pending", before=None, limit=500, at=None):
        path = self.paths.notifications_db(account)
        if not path.exists():
            return []
        where, args = ["status=?"], [status]
        if status == "pending":
            where.append("available_at<=?")
            args.append(timestamp(at))
        if before:
            where.append("(occurred_at,notification_id)<(?,?)")
            args.extend(before)
        with connect(path) as db:
            return [
                dict(row)
                for row in db.execute(
                    f"SELECT * FROM notifications WHERE {' AND '.join(where)} ORDER BY occurred_at DESC,notification_id DESC LIMIT ?",
                    (*args, limit),
                )
            ]

    def get(self, account, notification_id):
        path = self.paths.notifications_db(account)
        if not path.exists():
            return None
        with connect(path) as db:
            row = db.execute(
                "SELECT * FROM notifications WHERE notification_id=?",
                (notification_id,),
            ).fetchone()
            return dict(row) if row else None

    def received_resources(self, account, notification_type):
        path = self.paths.notifications_db(account)
        if not path.exists():
            return set()
        with connect(path) as db:
            return {
                (row["member_id"], row["resource_id"])
                for row in db.execute(
                    "SELECT member_id,resource_id FROM notifications WHERE notification_type=?",
                    (notification_type,),
                )
            }

    def deliver(self, account, event_id, content):
        self.initialize(account)
        notification_id = digest([event_id, account])
        with connect(self.paths.notifications_db(account)) as db:
            db.execute(
                "ATTACH DATABASE ? AS config", (str(self.paths.config_db(account)),)
            )
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT * FROM notifications WHERE notification_id=?",
                (notification_id,),
            ).fetchone()
            pref = db.execute(
                "SELECT * FROM config.account_preferences WHERE singleton_id=1"
            ).fetchone()
            if old:
                if old["status"] == "cancelled":
                    return "skipped"
                if old["event_revision"] >= content["event_revision"]:
                    return "delivered"
                NOTIFICATION_DATABASE_SCHEMA.table_by_name['notifications'].validate_values({**dict(old), **content})
                fields = [
                    key for key in CONTENT if key not in ("occurred_at", "available_at")
                ]
                db.execute(
                    f"UPDATE notifications SET {','.join(key + '=?' for key in fields)},updated_at=? WHERE notification_id=?",
                    (*(content[key] for key in fields), timestamp(), notification_id),
                )
            else:
                since = reception_since(pref, content["notification_type"]) if pref else None
                if (
                    since is None
                    or datetime.fromisoformat(content["occurred_at"]) < since
                ):
                    return "skipped"
                value = {
                    "notification_id": notification_id,
                    **{key: content[key] for key in CONTENT},
                    "status": "pending",
                    "created_at": timestamp(),
                    "updated_at": timestamp(),
                }
                self.insert(db, "notifications", value)
        return "delivered"

    @staticmethod
    def insert(db, table, value):
        contract = {**NOTIFICATION_DATABASE_SCHEMA.table_by_name, **BACKGROUND_TASK_DATABASE_SCHEMA.table_by_name}[table.rsplit('.', 1)[-1]]
        contract.validate_values(value)
        db.execute(
            f"INSERT INTO {table} ({','.join(value)}) VALUES ({','.join('?' for _ in value)})",
            tuple(value.values()),
        )

    def mark_read(self, account, notification_id):
        with connect(self.paths.notifications_db(account)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = dict(
                db.execute(
                    "SELECT * FROM notifications WHERE notification_id=?",
                    (notification_id,),
                ).fetchone()
            )
            if row["status"] == "pending":
                row["status"] = "read"
                db.execute(
                    "UPDATE notifications SET status='read',updated_at=? WHERE notification_id=?",
                    (timestamp(), notification_id),
                )
            return {
                key: row[key] for key in ("notification_id", "status", "available_at")
            }

    def cancel(self, account, ids):
        if not ids:
            return
        with connect(self.paths.notifications_db(account)) as db:
            db.executemany(
                "UPDATE notifications SET status='cancelled',updated_at=? WHERE notification_id=? AND status!='cancelled'",
                [(timestamp(), key) for key in ids],
            )

    def enqueue(self, db, event_id, recipients, content, *, alias="notification_data"):
        table = f"{alias}.notification_outbox"
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
        path = self.paths.notifications_db(owner)
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
            timestamp(datetime.now(timezone.utc) + timedelta(seconds=retry))
            if error
            else at
        )
        with connect(self.paths.notifications_db(owner)) as db:
            db.execute(
                "UPDATE notification_outbox SET status=?,attempt_count=attempt_count+?,next_attempt_at=?,last_error_code=?,updated_at=? WHERE event_id=? AND recipient_account_id=? AND event_revision=?",
                (
                    status,
                    int(bool(error)),
                    next_at,
                    error,
                    at,
                    row["event_id"],
                    row["recipient_account_id"],
                    row["event_revision"],
                ),
            )

    def next_delivery(self, owner):
        path = self.paths.notifications_db(owner)
        if not path.exists():
            return None
        with connect(path) as db:
            return db.execute(
                "SELECT min(next_attempt_at) FROM notification_outbox WHERE status='pending'"
            ).fetchone()[0]

    def checkpoint(self, account, task_name, lower, upper):
        path = self.paths.background_tasks_db(account)
        if not BACKGROUND_TASK_DATABASE_SCHEMA.validate_existing(path):
            with connect(path) as db:
                BACKGROUND_TASK_DATABASE_SCHEMA.create(db)
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO background_task_checkpoints VALUES (?,?,NULL,NULL,?,?)",
                (task_name, lower, timestamp(), timestamp()),
            )
            row = dict(
                db.execute(
                    "SELECT * FROM background_task_checkpoints WHERE task_name=?",
                    (task_name,),
                ).fetchone()
            )
            start = max(lower, row["last_completed_at"])
            if not row["scan_from"] or row["scan_from"] < lower:
                db.execute(
                    "UPDATE background_task_checkpoints SET scan_from=?,scan_until=?,updated_at=? WHERE task_name=?",
                    (start, max(start, upper), timestamp(), task_name),
                )
                row.update(scan_from=start, scan_until=max(start, upper))
            return row

    def complete_checkpoint(self, account, row):
        with connect(self.paths.background_tasks_db(account)) as db:
            db.execute(
                "UPDATE background_task_checkpoints SET last_completed_at=?,scan_from=NULL,scan_until=NULL,updated_at=? WHERE task_name=? AND scan_from=? AND scan_until=?",
                (
                    row["scan_until"],
                    timestamp(),
                    row["task_name"],
                    row["scan_from"],
                    row["scan_until"],
                ),
            )

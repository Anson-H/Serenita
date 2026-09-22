"""Account-isolated notification persistence, delivery and recovery checkpoints."""
from backend.app.core.time import local_now

from datetime import datetime
from threading import RLock
from backend.app.core.values import digest
from backend.app.core.business_operation import current_business_operation
from backend.app.repositories.business_change_repository import record_change
from backend.app.repositories.business_operation_repository import begin_operation, finish_operation
from backend.app.domain.notification_preferences import NOTIFICATION_TYPES, PREFERENCE_NAMES, reception_since, effective_preferences
from backend.app.storage.sqlite import connect
from backend.app.storage.notification_database import (
    NOTIFICATION_DATABASE_SCHEMA,
    ACCOUNT_PREFERENCES_TABLE,
)


def timestamp(value=None):
    return (
        (value or local_now())
        .astimezone()
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
)


class NotificationRepository:
    def __init__(self, paths):
        self.paths = paths
        self._ready = set()
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
        self.initialize(actor)
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
            with connect(path) as db:
                db.execute("BEGIN IMMEDIATE")
                exists = NOTIFICATION_DATABASE_SCHEMA.validate_existing(path)
                if not exists:
                    NOTIFICATION_DATABASE_SCHEMA.create(db)
                db.execute(
                    "INSERT OR IGNORE INTO account_preferences (singleton_id,notifications_updated_at) VALUES (1,?)",
                    (timestamp(),),
                )
                from backend.app.repositories.preference_changes import record_initial_preference
                record_initial_preference(db, account, "notification_preference")
            self._ready.add(account)

    def preferences(self, account):
        self.initialize(account)
        with connect(self.paths.notifications_db(account)) as db:
            row = effective_preferences(db.execute(
                "SELECT * FROM account_preferences WHERE singleton_id=1"
            ).fetchone())
        row.pop("singleton_id")
        for name in PREFERENCE_NAMES:
            row[f"{name}_enabled"] = bool(row[f"{name}_enabled"])
        return row

    def set_preferences(self, account, changes):
        self.preferences(account)
        operation = current_business_operation()
        with connect(self.paths.notifications_db(account)) as db:
            db.execute("BEGIN IMMEDIATE")
            replay = begin_operation(db, account, operation.operation_id,
                                     {"domain": "notification_preference", "action": "update", "values": changes})
            if replay is not None:
                return replay
            row = db.execute(
                "SELECT * FROM account_preferences WHERE singleton_id=1"
            ).fetchone()
            row = effective_preferences(row)
            type_keys = [f"{name}_enabled" for name in NOTIFICATION_TYPES]
            if "notifications_enabled" in changes:
                changes = {key: changes["notifications_enabled"] for key in type_keys}
            states = {key: changes.get(key, bool(row[key])) for key in type_keys}
            changes = {**states, "notifications_enabled": any(states.values())}
            updates = {}
            at = timestamp()
            for key, enabled in changes.items():
                if bool(row[key]) != enabled:
                    if key != "notifications_enabled":
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
            current = effective_preferences(db.execute("SELECT * FROM account_preferences WHERE singleton_id=1").fetchone())
            fields = [key for key in current if key.endswith("_enabled") or key.endswith("_enabled_since")]
            record_change(db, actor_account_id=account, operation_id=operation.operation_id,
                          scope_kind="account", member_id=None, resource_type="notification_preference", resource_id="1",
                          before={f"/{key}": row[key] for key in fields}, after={f"/{key}": current[key] for key in fields},
                          context={"preference_kind": "notification"}, origin_kind=operation.origin_kind)
            current.pop("singleton_id")
            for name in PREFERENCE_NAMES:
                current[f"{name}_enabled"] = bool(current[f"{name}_enabled"])
            return finish_operation(db, account, operation.operation_id, current)

    def rows(self, account, *, status="pending", before=None, limit=500, at=None):
        path = self.paths.notifications_db(account)
        if not path.exists():
            return []
        self.initialize(account)
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
        self.initialize(account)
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
        self.initialize(account)
        with connect(path) as db:
            return {
                (row["member_id"], row["resource_id"])
                for row in db.execute(
                    "SELECT member_id,resource_id FROM notifications WHERE notification_type=?",
                    (notification_type,),
                )
            }

    def deliver(self, account, event_id, content, *, admission=None, journal_context=None):
        self.initialize(account)
        notification_id = digest([event_id, account])
        with connect(self.paths.notifications_db(account)) as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT * FROM notifications WHERE notification_id=?",
                (notification_id,),
            ).fetchone()
            pref = db.execute(
                "SELECT * FROM account_preferences WHERE singleton_id=1"
            ).fetchone()
            if old:
                if old["status"] == "cancelled":
                    return "skipped"
            else:
                since = reception_since(pref, content["notification_type"]) if pref else None
                if since is None or datetime.fromisoformat(content["occurred_at"]) < since:
                    return "skipped"
                if admission is not None and not admission(db, content):
                    return "waiting"
            operation_id = "notification-delivery/" + digest([event_id])
            command = {"domain": "notification", "action": "receive", "event_id": event_id,
                       "content": {key: content[key] for key in CONTENT}}
            replay = begin_operation(db, account, operation_id, command)
            if replay is not None:
                return replay["outcome"]
            before = dict(old) if old else None
            if old:
                NOTIFICATION_DATABASE_SCHEMA.table_by_name['notifications'].validate_values({**dict(old), **content})
                fields = [
                    key for key in CONTENT if key not in ("occurred_at", "available_at")
                ]
                db.execute(
                    f"UPDATE notifications SET {','.join(key + '=?' for key in fields)},updated_at=? WHERE notification_id=?",
                    (*(content[key] for key in fields), timestamp(), notification_id),
                )
            else:
                value = {
                    "notification_id": notification_id,
                    **{key: content[key] for key in CONTENT},
                    "status": "pending",
                    "created_at": timestamp(),
                    "updated_at": timestamp(),
                }
                self.insert(db, "notifications", value)
            current = dict(db.execute("SELECT * FROM notifications WHERE notification_id=?", (notification_id,)).fetchone())
            context = journal_context(current) if journal_context else {}
            context = {**context, "notification_event_id": event_id, "notification_type": current["notification_type"]}
            member = current["member_id"] or context.get("source_member_id")
            keys = (*CONTENT, "status", "created_at")
            record_change(db, actor_account_id=account, operation_id=operation_id,
                scope_kind="member" if member else "account", member_id=member, resource_type="notification", resource_id=notification_id,
                before={"/"+key: before[key] for key in keys} if before else None,
                after={"/"+key: current[key] for key in keys}, context=context, origin_kind="application_notification")
            finish_operation(db, account, operation_id, {"outcome": "delivered", "notification_id": notification_id})
        return "delivered"

    @staticmethod
    def insert(db, table, value):
        contract = NOTIFICATION_DATABASE_SCHEMA.table_by_name[table.rsplit('.', 1)[-1]]
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

    def checkpoint(self, account, task_name, lower, upper):
        self.initialize(account)
        path = self.paths.notifications_db(account)
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
        with connect(self.paths.notifications_db(account)) as db:
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

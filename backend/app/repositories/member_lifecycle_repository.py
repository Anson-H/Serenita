from datetime import timedelta
from uuid import uuid4

from backend.app.core.time import local_now, local_now_iso
from backend.app.storage.member_lifecycle_database import MEMBER_LIFECYCLE_DATABASE
from backend.app.storage.sqlite import connect, UnsupportedSchemaError


class MemberLifecycleRepository:
    def __init__(self, paths):
        self.path = paths.auth_db.with_name("member_lifecycle.db")

    def initialize(self):
        if not MEMBER_LIFECYCLE_DATABASE.validate_existing(self.path):
            with connect(self.path) as db:
                db.execute("BEGIN IMMEDIATE")
                MEMBER_LIFECYCLE_DATABASE.create(db)

    def enqueue(self, connection, owner, member, sessions, *, delete_files=False):
        if not connection.in_transaction:
            raise ValueError("成员后续任务必须与成员变更使用同一事务。")
        connection.execute("ATTACH DATABASE ? AS member_lifecycle", (str(self.path),))
        for database in connection.execute("PRAGMA database_list").fetchall():
            schema = '"' + str(database[1]).replace('"', '""') + '"'
            if database[1] == "temp":
                continue
            journal_mode = connection.execute(f"PRAGMA {schema}.journal_mode").fetchone()[0]
            synchronous = connection.execute(f"PRAGMA {schema}.synchronous").fetchone()[0]
            if journal_mode != "delete" or synchronous < 2:
                raise UnsupportedSchemaError(
                    "成员变更与后续任务的跨库事务要求 DELETE 日志模式和 FULL 同步级别。"
                )
        at = local_now_iso()
        rows = [(str(uuid4()), owner, member, actor, session, "interrupt_session", at, at, at)
                for actor, session in set(sessions)]
        if delete_files:
            rows.append((str(uuid4()), owner, member, owner, None, "delete_files", at, at, at))
        connection.executemany(
            "INSERT INTO member_lifecycle.member_lifecycle_tasks "
            "(task_id,owner_account_id,member_id,actor_account_id,session_id,operation,next_attempt_at,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)", rows,
        )

    def pending(self, *, limit=100):
        if not self.path.exists():
            return []
        with connect(self.path) as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM member_lifecycle_tasks WHERE next_attempt_at<=? "
                "ORDER BY next_attempt_at,task_id LIMIT ?", (local_now_iso(), limit),
            )]

    def finish(self, task):
        with connect(self.path) as db:
            db.execute("DELETE FROM member_lifecycle_tasks WHERE task_id=?", (task["task_id"],))

    def retry(self, task, error):
        attempts = task["attempt_count"] + 1
        next_at = (local_now() + timedelta(seconds=min(300, 2 ** min(attempts, 8)))).isoformat()
        with connect(self.path) as db:
            db.execute(
                "UPDATE member_lifecycle_tasks SET attempt_count=?,next_attempt_at=?,last_error=?,updated_at=? WHERE task_id=?",
                (attempts, next_at, str(error)[:1000], local_now_iso(), task["task_id"]),
            )

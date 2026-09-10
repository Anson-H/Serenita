from contextlib import contextmanager
from uuid import uuid4

from backend.app.core.time import local_now
from backend.app.core.pagination import seek_cursor, seek_position
from backend.app.storage.medical_log_database import MEDICAL_LOG_DATABASE_SCHEMA
from backend.app.storage.sqlite import connect


class MedicalLogRepository:
    def __init__(self, account_id, paths):
        self.account_id, self.paths = account_id, paths

    def init_db(self):
        path = self.paths.medical_logs_db(self.account_id)
        exists = MEDICAL_LOG_DATABASE_SCHEMA.validate_existing(path)
        if not exists:
            with connect(path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                MEDICAL_LOG_DATABASE_SCHEMA.create(connection)

    @contextmanager
    def transaction(self, *, write=False):
        self.init_db()
        with connect(self.paths.medical_logs_db(self.account_id)) as connection:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection

    def _detail(self, connection, member_id, medical_log_id):
        row = connection.execute(
            "SELECT * FROM medical_logs WHERE member_id = ? AND medical_log_id = ?",
            (member_id, medical_log_id),
        ).fetchone()
        if row is None:
            raise LookupError("健康日记已不存在或不属于当前成员。")
        return dict(row)

    def read(self, member_id, filters):
        return self._page(member_id, filters, full_content=True)

    def catalog(self, member_id, filters):
        return self._page(member_id, filters, full_content=False)

    def _page(self, member_id, filters, *, full_content):
        clauses, values = ["member_id = ?"], [member_id]
        scope = ["log_content" if full_content else "log_catalog", self.account_id, member_id, {key: value for key, value in filters.items() if key not in ("cursor", "limit")}]
        position = seek_position(filters["cursor"], scope=scope, size=3)
        for key, operator in (("after_date", ">="), ("before_date", "<=")):
            if filters[key]:
                clauses.append(f"recorded_on {operator} ?")
                values.append(filters[key])
        if query := filters["query"].strip():
            clauses.append("(instr(lower(title), lower(?)) > 0 OR instr(lower(content), lower(?)) > 0)")
            values.extend((query, query))
        ids = filters.get("medical_log_ids")
        if ids is not None:
            placeholders = ", ".join("?" for _ in ids)
            clauses.append(f"medical_log_id IN ({placeholders})")
            values.extend(ids)
        with self.transaction() as connection:
            if ids is not None:
                matched = connection.execute(
                    f"SELECT count(*) FROM medical_logs WHERE member_id = ? AND medical_log_id IN ({placeholders})",
                    [member_id, *ids],
                ).fetchone()[0]
                if matched != len(ids):
                    raise LookupError("健康日记已不存在或不属于当前成员。")
            total = connection.execute("SELECT count(*) FROM medical_logs WHERE " + " AND ".join(clauses), values).fetchone()[0]
            if position:
                clauses.append("(recorded_on, created_at, medical_log_id) < (?, ?, ?)")
                values.extend(position)
            columns = "*" if full_content else (
                "medical_log_id, member_id, recorded_on, title, substr(content, 1, 121) AS summary, created_at, updated_at"
            )
            rows = connection.execute(
                f"SELECT {columns} FROM medical_logs WHERE " + " AND ".join(clauses)
                + " ORDER BY recorded_on DESC, created_at DESC, medical_log_id DESC LIMIT ?", [*values, filters["limit"] + 1],
            ).fetchall()
        items = []
        for row in rows[:filters["limit"]]:
            item = dict(row)
            if not full_content:
                content = " ".join(item["summary"].split())
                item["summary"] = content[:120] + ("…" if len(content) > 120 else "")
            items.append(item)
        following = seek_cursor(scope, [items[-1][key] for key in ("recorded_on", "created_at", "medical_log_id")]) if len(rows) > filters["limit"] else None
        return {"medical_logs": items, "total": total, "next_cursor": following}

    def create(self, member_id, values):
        medical_log_id, timestamp = str(uuid4()), local_now().isoformat()
        with self.transaction(write=True) as connection:
            connection.execute("INSERT INTO medical_logs VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (medical_log_id, member_id, values["recorded_on"], values["title"], values["content"], timestamp, timestamp))
            return self._detail(connection, member_id, medical_log_id)

    def update(self, member_id, medical_log_id, values):
        with self.transaction(write=True) as connection:
            current = self._detail(connection, member_id, medical_log_id)
            changes = {key: value for key, value in values.items() if value != current[key]}
            if changes:
                changes["updated_at"] = local_now().isoformat()
                connection.execute("UPDATE medical_logs SET " + ", ".join(f"{key} = ?" for key in changes)
                                   + " WHERE member_id = ? AND medical_log_id = ?", (*changes.values(), member_id, medical_log_id))
            return self._detail(connection, member_id, medical_log_id)

    def delete(self, member_id, medical_log_id):
        with self.transaction(write=True) as connection:
            self._detail(connection, member_id, medical_log_id)
            connection.execute("DELETE FROM medical_logs WHERE member_id = ? AND medical_log_id = ?", (member_id, medical_log_id))
        return {"member_id": member_id, "medical_log_id": medical_log_id, "deleted": True}

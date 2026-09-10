from backend.app.core.time import local_now_iso
from backend.app.schemas.medical_history import MEDICAL_HISTORY_FIELDS
from backend.app.storage.member_database import require_member_database
from backend.app.storage.sqlite import connect


class MedicalHistoryRepository:
    def __init__(self, paths):
        self.paths = paths

    @staticmethod
    def _read(connection, member_id, fields):
        if connection.execute("SELECT 1 FROM members WHERE member_id = ?", (member_id,)).fetchone() is None:
            raise LookupError("成员已不存在。")
        row = connection.execute("SELECT * FROM medical_history WHERE member_id = ?", (member_id,)).fetchone()
        return {"member_id": member_id, "history": {
            name: {"text": row[name] if row else None,
                   "updated_at": row[f"{name}_updated_at"] if row else None}
            for name in fields
        }}

    def read(self, access, fields):
        with connect(require_member_database(access.account_id, self.paths)) as connection:
            connection.execute("BEGIN")
            return self._read(connection, access.member_id, fields)

    def update(self, access, values):
        with connect(require_member_database(access.account_id, self.paths)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = self._read(connection, access.member_id, MEDICAL_HISTORY_FIELDS)
            changed = {name: value for name, value in values.items()
                       if previous["history"][name]["text"] != value}
            if changed:
                connection.execute("INSERT OR IGNORE INTO medical_history(member_id) VALUES (?)", (access.member_id,))
                timestamp = local_now_iso()
                assignments = ", ".join(f"{name} = ?, {name}_updated_at = ?" for name in changed)
                parameters = [part for value in changed.values() for part in (value, timestamp)]
                connection.execute(f"UPDATE medical_history SET {assignments} WHERE member_id = ?", (*parameters, access.member_id))
            return self._read(connection, access.member_id, MEDICAL_HISTORY_FIELDS)

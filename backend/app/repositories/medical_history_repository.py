from backend.app.core.business_operation import current_business_operation
from backend.app.repositories.business_change_repository import record_change
from backend.app.repositories.business_operation_repository import begin_operation, finish_operation
from backend.app.core.time import local_now_iso
from backend.app.schemas.medical_history import MEDICAL_HISTORY_FIELDS
from backend.app.storage.member_database import require_member_database
from backend.app.storage.sqlite import connect, connect_read_only


class MedicalHistoryRepository:
    def __init__(self, paths, *, read_only=False):
        self.paths = paths
        self.read_only = read_only

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
        open_database = connect_read_only if self.read_only else connect
        with open_database(require_member_database(access.account_id, self.paths)) as connection:
            connection.execute("BEGIN")
            return self._read(connection, access.member_id, fields)

    def update(self, access, values):
        if self.read_only:
            raise PermissionError("只读来源核对不能修改业务记录。")
        operation = current_business_operation()
        command = {"domain": "medical_history", "action": "update", "member_id": access.member_id, "values": values}
        with connect(require_member_database(access.account_id, self.paths)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous_result = begin_operation(connection, access.actor_account_id, operation.operation_id, command)
            if previous_result is not None:
                return previous_result
            previous = self._read(connection, access.member_id, MEDICAL_HISTORY_FIELDS)
            previous_row = connection.execute("SELECT * FROM medical_history WHERE member_id = ?", (access.member_id,)).fetchone()
            changed = {name: value for name, value in values.items()
                       if previous["history"][name]["text"] != value}
            if changed:
                connection.execute("INSERT OR IGNORE INTO medical_history(member_id) VALUES (?)", (access.member_id,))
                timestamp = local_now_iso()
                assignments = ", ".join(f"{name} = ?, {name}_updated_at = ?" for name in changed)
                parameters = [part for value in changed.values() for part in (value, timestamp)]
                connection.execute(f"UPDATE medical_history SET {assignments} WHERE member_id = ?", (*parameters, access.member_id))
            result = self._read(connection, access.member_id, MEDICAL_HISTORY_FIELDS)
            after_row = connection.execute("SELECT * FROM medical_history WHERE member_id = ?", (access.member_id,)).fetchone()
            name = connection.execute("SELECT member_name FROM members WHERE member_id = ?", (access.member_id,)).fetchone()[0]
            record_change(connection, actor_account_id=access.actor_account_id, operation_id=operation.operation_id,
                          scope_kind="member", member_id=access.member_id, resource_type="medical_history", resource_id=access.member_id,
                          before={f"/{field}": previous_row[field] for field in MEDICAL_HISTORY_FIELDS} if previous_row else None,
                          after={f"/{field}": after_row[field] for field in MEDICAL_HISTORY_FIELDS} if after_row else None,
                          context={"member_id": access.member_id, "member_name": name}, origin_kind=operation.origin_kind)
            return finish_operation(connection, access.actor_account_id, operation.operation_id, result)

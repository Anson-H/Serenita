"""Read committed business changes and receive authorized evidence reliably."""
from backend.app.repositories.business_source_generation import business_generation
import json

from backend.app.repositories.memory.sources.source_access import MemorySourceAccess
from backend.app.domain.memory.sources import SOURCE_REGISTRATIONS, BUSINESS_SOURCE_DATABASES
from backend.app.core.errors import SerenitaError
from backend.app.domain.memory.change_scope import memory_change_fields
from backend.app.repositories.business_change_repository import read_change_fields
from backend.app.schemas.memory.source_identity import memory_source_id



class MemoryBusinessSourceRepository:
    """Read registered business ledger identities and pending reception metadata."""
    def __init__(self, repository):
        self.repository, self.members = repository, repository.members
        self.sources = MemorySourceAccess(repository.members, repository.paths)

    @staticmethod
    def _registration(database, resource_type):
        result = SOURCE_REGISTRATIONS.get(resource_type)
        if database not in BUSINESS_SOURCE_DATABASES or result is None or result.database != database:
            raise SerenitaError("invalid_input", "MEMORY_SOURCE_UNREGISTERED", "业务来源不属于已登记的资料范围。")
        return result

    def identity(self, access, database, change):
        registration = self._registration(database, change["resource_type"])
        category = next(iter(registration.categories))
        with self.sources._database(access.account_id, database) as connection:
            generation = business_generation(connection, change["resource_type"], change["resource_id"],
                change["member_id"], at_sequence=change["change_sequence"])
        if generation is None:
            raise SerenitaError("missing", "MEMORY_SOURCE_GENERATION_UNAVAILABLE", "来源缺少可核对的创建身份。")
        return {
            "source_id": memory_source_id(access.member_id, source_account_id=access.account_id,
                source_database=database, resource_type=change['resource_type'], resource_id=change['resource_id'], source_generation=generation),
            "source_account_id": access.account_id,
            "source_generation": generation,
            "source_member_id": access.member_id if change["scope_kind"] == "member" else None,
            "source_category": category, "resource_type": change["resource_type"], "resource_id": change["resource_id"],
            "source_database": database, "title": str(change["context"].get("title") or change["context"].get("original_filename") or change["resource_type"]),
        }

    def change(self, access, database, change_id):
        if database not in BUSINESS_SOURCE_DATABASES:
            raise SerenitaError("invalid_input", "MEMORY_SOURCE_UNREGISTERED", "业务库未登记。")
        try:
            with self.sources._database(access.account_id, database) as connection:
                row = connection.execute("SELECT * FROM business_changes WHERE change_id=? AND "
                                         "((scope_kind='member' AND member_id=?) OR scope_kind='account')",
                                         (change_id, access.member_id)).fetchone()
                if row is None:
                    raise LookupError()
                change = dict(row)
                change["context"] = json.loads(change.pop("context_json"))
                change["fields"] = read_change_fields(connection, change_id)
        except (LookupError, FileNotFoundError) as exc:
            raise SerenitaError("missing", "MEMORY_SOURCE_CHANGE_UNAVAILABLE", "来源变化不存在或当前不可访问。") from exc
        return change

    def find_processing(self, actor, member, database, change_id):
        with self.repository._transaction(actor, member) as (access, db):
            if db is None:
                return None
            row = db.execute("SELECT p.attempt_id FROM processing_attempts p "
                "JOIN commits c ON c.commit_id=p.commit_id "
                "WHERE p.account_id=? AND p.member_id=? AND p.task_kind='event_formation' "
                "AND p.source_database=? AND p.change_id=? "
                "ORDER BY c.sequence DESC LIMIT 1", (access.account_id, member, database, change_id)).fetchone()
            if row is None:
                return None
            value=self.repository._record(db, access, 'processing_attempt', row[0])
            if not self.repository._visible(db,access,value):
                return None
            return self.repository._project(db, access, value, self.repository._cutoff(db, access))


    def pending_changes(self, account, member, database, after_sequence, limit):
        with self.sources._database(account, database) as db:
            rows = db.execute("SELECT * FROM business_changes WHERE member_id=? AND change_sequence>? "
                "AND memory_status IN ('pending','processing','failed') ORDER BY change_sequence LIMIT ?",
                (member, after_sequence, limit + 1)).fetchall()
            eligible = {row['change_id'] for row in rows[:limit] if memory_change_fields(row['resource_type'],
                db.execute('SELECT field_path FROM business_change_fields WHERE change_id=?', (row['change_id'],)).fetchall())}
            return rows, eligible

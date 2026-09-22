"""Live existence and permissions for explicitly registered memory sources.

This callback authorizes already delivered content. It never opens a source for
the caller, forms memory, initializes a database, repairs JSONL, or scans files.
Resource identifiers are documented in the current memory interface contract.
"""

from contextlib import contextmanager
import hashlib
from pathlib import Path
import sqlite3
from uuid import UUID

from backend.app.core.errors import SerenitaError
from backend.app.domain.member_access import MemberAccess
from backend.app.storage.source_paths import safe_existing_file, registered_source_path
from backend.app.repositories.business_source_generation import business_generation


from backend.app.domain.memory.sources import SOURCE_REGISTRATIONS


class MemorySourceAccess:
    def __init__(self, members, paths):
        self.members, self.paths = members, paths

    def check(self, access: MemberAccess, source: dict) -> bool:
        try:
            with self.members.access_guard(access.actor_account_id, access.member_id) as live:
                return self._check(live, source)
        except (SerenitaError, LookupError, PermissionError, ValueError, TypeError,
                KeyError, OSError, sqlite3.Error):
            return False

    def _check(self, access, source):
        if not isinstance(source, dict):
            return False
        registration = SOURCE_REGISTRATIONS.get(source.get("resource_type"))
        if (registration is None or registration.scope == "unavailable"
                or source.get("source_database") != registration.database
                or source.get("source_category") not in registration.categories
                or source.get("account_id") != access.account_id
                or source.get("member_id") != access.member_id
                or not isinstance(source.get("source_generation"), str)
                or not source["source_generation"].strip()):
            return False
        source_account = source["source_account_id"]
        if not isinstance(source_account, str) or str(UUID(source_account)) != source_account:
            return False
        source_member = source.get("source_member_id")
        if registration.scope == "member":
            if source_member != access.member_id or source_account != access.account_id:
                return False
        elif registration.scope in {"catalog"}:
            if source_member is not None:
                return False
        elif source_member not in {None, access.member_id}:
            return False
        if not self._account_exists(source_account):
            return False
        if registration.scope != "member":
            shared_catalog = registration.scope == "catalog" and source_account == access.account_id
            if source_account != access.actor_account_id and not shared_catalog:
                return False
        allowed = self._ordinary(access, source, registration)
        return allowed



    @contextmanager
    def _database(self, account, database):
        # AppPaths account_root applies tree hardening; source reads must not
        # trigger its recursive scan. Only these registered locations are used.
        if database not in {item.database for item in SOURCE_REGISTRATIONS.values()}:
            raise ValueError("Unregistered source database")
        path = registered_source_path(self.paths, account, database)
        if not safe_existing_file(path, self.paths.root):
            raise FileNotFoundError("Source database is unavailable")
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("BEGIN")
            yield connection
        finally:
            connection.close()

    def _account_exists(self, account):
        path = self.paths.root / "all_users/auth/user_auth.db"
        if not safe_existing_file(path, self.paths.root):
            return False
        return self.members.authorization.account_exists(account)

    def _account_root(self, account):
        if not isinstance(account, str) or str(UUID(account)) != account:
            raise ValueError("Invalid source account")
        return self.paths.root / "accounts" / account

    def _ordinary(self, access, source, registration):
        account, resource = source["source_account_id"], source["resource_id"]
        if not isinstance(resource, str) or not resource:
            return False
        if registration.primary_key == "singleton_id" and resource != "1":
            return False
        with self._database(account, registration.database) as connection:
            where, parameters = f"{registration.primary_key}=?", [resource]
            if registration.scope == "member":
                where += " AND member_id=?"
                parameters.append(access.member_id)
            # Table/column names come solely from the fixed registry above.
            row = connection.execute(f"SELECT * FROM {registration.table} WHERE {where}", parameters).fetchone()
            if row is None:
                return False
            kind = source["resource_type"]
            if kind in {"medication", "medication_source"}:
                medication_id = row["medication_id"]
                linked = connection.execute(
                    "SELECT 1 FROM medication_plans WHERE member_id=? AND medication_id=? "
                    "UNION ALL SELECT 1 FROM medication_inventory WHERE member_id=? AND medication_id=? LIMIT 1",
                    (access.member_id, medication_id, access.member_id, medication_id),
                ).fetchone()
                if linked is None:
                    return False
            generation = business_generation(connection, kind, resource,
                                                  access.member_id if registration.scope == "member" else None)
            if generation is None or source.get("source_generation") != generation:
                return False
            if kind == "report_source":
                return self._file(account, row["relative_path"], "reports/attachments", row["size_bytes"], row["sha256"])
            if kind == "medication_source":
                parent = connection.execute("SELECT 1 FROM medications WHERE medication_id=?", (row["medication_id"],)).fetchone()
                relative = "medications/files/" + row["relative_path"]
                return parent is not None and self._file(account, relative, "medications/files", row["size_bytes"], row["sha256"])
            if kind == "body_file":
                parent = connection.execute("SELECT 1 FROM body_records WHERE record_id=? AND member_id=?", (row["record_id"], access.member_id)).fetchone()
                return parent is not None and bool(row["image_bytes"]) and hashlib.sha256(row["image_bytes"]).hexdigest() == row["sha256"]
            if kind in {"medication_plan", "medication_batch"}:
                return connection.execute("SELECT 1 FROM medications WHERE medication_id=?", (row["medication_id"],)).fetchone() is not None
            return True

    def _file(self, account, relative, allowed_directory, size, sha256=None):
        root = self._account_root(account)
        if not isinstance(relative, str) or "\\" in relative or Path(relative).is_absolute():
            return False
        path = root / relative
        boundary = root / allowed_directory
        if not safe_existing_file(path, boundary):
            return False
        if not safe_existing_file(path, self.paths.root) or path.stat().st_size != size:
            return False
        if sha256 is not None:
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest() == sha256
        return True


    def resolve_generation(self, source):
        """Resolve an existing trusted source's generation without returning content."""
        try:
            registration = SOURCE_REGISTRATIONS[source["resource_type"]]
            if source["source_database"] != registration.database or registration.scope == "unavailable":
                return None
            with self._database(source["source_account_id"], registration.database) as connection:
                parameters = [source["resource_id"]]
                condition = f"{registration.primary_key}=?"
                if registration.scope == "member":
                    condition += " AND member_id=?"
                    parameters.append(source["source_member_id"])
                if connection.execute(f"SELECT 1 FROM {registration.table} WHERE {condition}", parameters).fetchone() is None:
                    return None
                return business_generation(connection, source["resource_type"], source["resource_id"],
                                                source["source_member_id"] if registration.scope == "member" else None)
        except (KeyError, ValueError, TypeError, OSError, sqlite3.Error, SerenitaError):
            return None


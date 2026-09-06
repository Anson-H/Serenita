from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

from backend.app.core.member_errors import member_error
from backend.app.repositories.member_references import member_reference_stores

from backend.app.core.time import local_now_iso
from backend.app.core.member_lifecycle import member_lifecycle_change
from backend.app.repositories.member_data_store import (
    MemberDataStoreParticipant,
    default_member_data_store_participants,
    validate_member_data_store_participants,
)
from backend.app.storage.config_database import require_config_database
from backend.app.storage.member_database import (
    initialize_member_database,
    require_member_database,
)
from backend.app.storage.paths import AppPaths, app_paths
from backend.app.storage.sqlite import UnsupportedSchemaError, connect

_PREFERENCE_UNSET = object()

# Re-entrant service reads share the same short authorization transaction.
# Opening a second reader while a revocation waits to commit can deadlock the
# original reader. The guard is scoped to synchronous data operations only.
_active_access: ContextVar[tuple["MemberAccess", ...]] = ContextVar(
    "member_access", default=()
)


@dataclass(frozen=True)
class MemberAccess:
    actor_account_id: str
    account_id: str
    actor_account: str
    owner_account: str
    member_id: str
    permission: str
    is_default: bool
    access_repository: MemberRepository = field(repr=False, compare=False)

    @property
    def can_edit(self) -> bool:
        return self.permission in {"owner", "edit"}

    def guard(self, *, write: bool = False):
        return self.access_repository.access_guard(
            self.actor_account_id, self.member_id, write=write
        )

    def check(self, *, write: bool = False) -> MemberAccess:
        with self.guard(write=write) as live:
            return live


class MemberRepository:
    def __init__(
        self,
        *,
        paths: AppPaths | None = None,
        data_stores: Iterable[MemberDataStoreParticipant] | None = None,
    ) -> None:
        self.paths = paths or app_paths()
        self.private_references = member_reference_stores(self.paths)
        self._data_stores = (
            validate_member_data_store_participants(data_stores)
            if data_stores is not None
            else None
        )

    def member_exists(self, member_id: str) -> bool:
        with connect(self.paths.auth_db) as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM member_ownerships WHERE member_id = ?", (member_id,)
                ).fetchone()
                is not None
            )

    def _delete_participants(self) -> tuple[MemberDataStoreParticipant, ...]:
        if self._data_stores is not None:
            return self._data_stores
        return default_member_data_store_participants(self.paths)

    @contextmanager
    def private_reference_guard(self):
        with connect(self.paths.auth_db) as connection:
            connection.execute("BEGIN")
            connection.execute("SELECT account_id FROM accounts LIMIT 1").fetchone()
            yield connection

    def historical_member_name(
        self, actor_account_id: str, source: str, source_id: str
    ) -> str | None:
        store = next(
            (item for item in self.private_references if item.source == source), None
        )
        if store is None:
            raise ValueError("unsupported private reference")
        with self.private_reference_guard() as auth:
            member_id = store.member_id_for_reference(actor_account_id, source_id)
            if member_id is None:
                return None
            owner = auth.execute(
                "SELECT account_id FROM member_ownerships WHERE member_id = ?",
                (member_id,),
            ).fetchone()
            if owner is None:
                return None
            with connect(
                require_member_database(owner["account_id"], self.paths)
            ) as connection:
                profile = connection.execute(
                    "SELECT member_name FROM members WHERE member_id = ?", (member_id,)
                ).fetchone()
            return profile["member_name"] if profile else None

    def _detach_private_references(
        self, connection, member_id: str
    ) -> list[tuple[str, str]]:
        sessions = []
        for account in connection.execute("SELECT account_id FROM accounts").fetchall():
            account_id = str(account["account_id"])
            changed = False
            for store in self.private_references:
                references = store.references(account_id, member_id)
                if not references:
                    continue
                alias = f"private_{len(connection.execute('PRAGMA database_list').fetchall())}"
                try:
                    connection.execute(
                        f'ATTACH DATABASE ? AS "{alias}"',
                        (str(store.path_for_account(account_id)),),
                    )
                except sqlite3.OperationalError as exc:
                    member_error(
                        "MEMBER_DELETE_FAILED",
                        f"删除事务无法附加关联数据库：{exc}",
                        "conflict",
                    )
                store.detach(connection, alias, member_id)
                if store.interrupts_sessions:
                    sessions.extend((account_id, reference) for reference in references)
                changed = True
            if changed:
                connection.execute(
                    "UPDATE accounts SET access_revision = access_revision + 1 WHERE account_id = ?",
                    (account_id,),
                )
        return sessions

    def _attach_member_database(
        self,
        connection,
        owner_account_id: str,
        *,
        schema_alias: str,
    ) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", schema_alias):
            raise ValueError("member database schema alias is invalid")
        database_path = require_member_database(owner_account_id, self.paths)
        connection.execute(
            f'ATTACH DATABASE ? AS "{schema_alias}"', (str(database_path),)
        )
        return schema_alias

    def _attach_config_database(
        self,
        connection,
        account_id: str,
        *,
        schema_alias: str,
    ) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", schema_alias):
            raise ValueError("configuration database schema alias is invalid")
        database_path = require_config_database(account_id, self.paths)
        connection.execute(
            f'ATTACH DATABASE ? AS "{schema_alias}"', (str(database_path),)
        )
        return schema_alias

    @staticmethod
    def _preference_on_connection(
        connection,
        *,
        schema_alias: str,
    ):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", schema_alias):
            raise ValueError("configuration database schema alias is invalid")
        rows = connection.execute(
            f'SELECT * FROM "{schema_alias}".member_preferences'
        ).fetchall()
        if len(rows) != 1 or int(rows[0]["singleton_id"]) != 1:
            raise UnsupportedSchemaError(
                "UNSUPPORTED_SCHEMA: account configuration has invalid member preferences."
            )
        return rows[0]

    def _require_member_profile(self, access: MemberAccess) -> None:
        with connect(
            require_member_database(access.account_id, self.paths)
        ) as connection:
            profile = connection.execute(
                "SELECT 1 FROM members WHERE member_id = ?", (access.member_id,)
            ).fetchone()
        if profile is None:
            raise UnsupportedSchemaError(
                "UNSUPPORTED_SCHEMA: member registry points to a missing member profile."
            )

    @staticmethod
    def _require_owner_profile_consistency(
        connection,
        owner_account_id: str,
        *,
        schema_alias: str,
    ) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", schema_alias):
            raise ValueError("member database schema alias is invalid")
        registered = {
            str(row[0])
            for row in connection.execute(
                "SELECT member_id FROM member_ownerships WHERE account_id = ?",
                (owner_account_id,),
            ).fetchall()
        }
        profiles = {
            str(row[0])
            for row in connection.execute(
                f'SELECT member_id FROM "{schema_alias}".members'
            ).fetchall()
        }
        if registered != profiles:
            raise UnsupportedSchemaError(
                "UNSUPPORTED_SCHEMA: member registry and member database are inconsistent."
            )

    def _access(
        self, connection, actor_account_id: str, member_id: str, *, write: bool = False
    ) -> MemberAccess:
        row = connection.execute(
            """SELECT p.*, owner.account AS owner_account, actor.account AS actor_account,
                g.permission FROM member_ownerships p
                JOIN accounts owner ON owner.account_id = p.account_id
                JOIN accounts actor ON actor.account_id = ?
                LEFT JOIN member_grants g ON g.member_id = p.member_id AND g.account_id = actor.account_id
                WHERE p.member_id = ?""",
            (actor_account_id, member_id),
        ).fetchone()
        if row is None or (
            row["account_id"] != actor_account_id and row["permission"] is None
        ):
            member_error("MEMBER_ACCESS_UNAVAILABLE", "该成员的健康档案已不可访问。")
        permission = (
            "owner" if row["account_id"] == actor_account_id else str(row["permission"])
        )
        if write and permission == "read":
            member_error("MEMBER_READ_ONLY", "该健康档案为只读，不能保存或删除内容。")
        return MemberAccess(
            actor_account_id,
            row["account_id"],
            row["actor_account"],
            row["owner_account"],
            member_id,
            permission,
            False,
            self,
        )

    @contextmanager
    def access_guard(
        self, actor_account_id: str, member_id: str, *, write: bool = False
    ) -> Iterator[MemberAccess]:
        # Hold a shared authentication DB lock until the short data operation has
        # committed. A revocation cannot commit ahead of an already authorized
        # operation; after revocation commits, subsequent guards see no grant.
        # No guard is held across a model request.
        for access in _active_access.get():
            if (
                access.access_repository.paths.root.resolve()
                == self.paths.root.resolve()
                and access.actor_account_id == actor_account_id
                and access.member_id == member_id
            ):
                if write and not access.can_edit:
                    member_error(
                        "MEMBER_READ_ONLY", "该健康档案为只读，不能保存或删除内容。"
                    )
                yield access
                return
        with connect(self.paths.auth_db) as connection:
            connection.execute("BEGIN")
            access = self._access(connection, actor_account_id, member_id, write=write)
            self._require_member_profile(access)
            token = _active_access.set((*_active_access.get(), access))
            try:
                yield access
            finally:
                _active_access.reset(token)

    def resolve(
        self, actor_account_id: str, member_id: str, *, write: bool = False
    ) -> MemberAccess:
        with self.access_guard(actor_account_id, member_id, write=write) as access:
            return access

    @staticmethod
    def default_member_id(
        actor_account_id: str,
        paths: AppPaths | None = None,
    ) -> str | None:
        with connect(require_config_database(actor_account_id, paths)) as connection:
            rows = connection.execute(
                "SELECT singleton_id, default_member_id FROM member_preferences"
            ).fetchall()
        if len(rows) != 1 or int(rows[0]["singleton_id"]) != 1:
            raise UnsupportedSchemaError(
                "UNSUPPORTED_SCHEMA: account configuration has invalid member preferences."
            )
        row = rows[0]
        return str(row["default_member_id"]) if row["default_member_id"] else None

    def _set_default(
        self,
        connection,
        actor_id: str,
        member_id: str,
        *,
        preference_schema: str,
        member_schema: str | None = None,
    ) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", preference_schema):
            raise ValueError("configuration database schema alias is invalid")
        access = self._access(connection, actor_id, member_id)
        schema_alias = member_schema or self._attach_member_database(
            connection,
            access.account_id,
            schema_alias="selected_member_data",
        )
        if not re.fullmatch(r"[a-z][a-z0-9_]*", schema_alias):
            raise ValueError("member database schema alias is invalid")
        profile = connection.execute(
            f'SELECT 1 FROM "{schema_alias}".members WHERE member_id = ?',
            (member_id,),
        ).fetchone()
        if profile is None:
            member_error("MEMBER_NOT_FOUND", "成员不存在。", "missing")
        updated = connection.execute(
            f'UPDATE "{preference_schema}".member_preferences '
            "SET default_member_id = ? WHERE singleton_id = 1",
            (member_id,),
        )
        if not updated.rowcount:
            raise UnsupportedSchemaError(
                "UNSUPPORTED_SCHEMA: account configuration has invalid member preferences."
            )

    def create_on_connection(
        self,
        connection,
        account_id: str,
        values: dict[str, Any],
        *,
        set_as_default: bool = False,
    ) -> str:
        member_id = str(uuid.uuid4())
        timestamp = local_now_iso()
        config_schema = self._attach_config_database(
            connection,
            account_id,
            schema_alias="account_config",
        )
        preference = self._preference_on_connection(
            connection,
            schema_alias=config_schema,
        )
        member_schema = self._attach_member_database(
            connection,
            account_id,
            schema_alias="member_data",
        )
        self._require_owner_profile_consistency(
            connection,
            account_id,
            schema_alias=member_schema,
        )
        connection.execute(
            "INSERT INTO member_ownerships(member_id, account_id, created_at) VALUES (?, ?, ?)",
            (member_id, account_id, timestamp),
        )
        connection.execute(
            """INSERT INTO member_data.members
                (member_id, member_name, sex, birth_date, blood_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                member_id,
                values["member_name"],
                values.get("sex"),
                values.get("birth_date"),
                values.get("blood_type"),
                timestamp,
                timestamp,
            ),
        )
        if set_as_default or preference["default_member_id"] is None:
            connection.execute(
                f'UPDATE "{config_schema}".member_preferences '
                "SET default_member_id = ? WHERE singleton_id = 1",
                (member_id,),
            )
        connection.execute(
            "UPDATE accounts SET access_revision = access_revision + 1 WHERE account_id = ?",
            (account_id,),
        )
        return member_id

    def create(
        self,
        actor_account_id: str,
        values: dict[str, Any],
        *,
        set_as_default: bool = False,
    ) -> str:
        with connect(self.paths.auth_db) as connection:
            connection.execute("BEGIN EXCLUSIVE")
            owner = connection.execute(
                "SELECT account_id FROM accounts WHERE account_id = ?",
                (actor_account_id,),
            ).fetchone()
            if owner is None:
                member_error("UNAUTHORIZED", "账号不存在。", "unauthenticated")
            existing_member = connection.execute(
                "SELECT 1 FROM member_ownerships WHERE account_id = ? LIMIT 1",
                (actor_account_id,),
            ).fetchone()
            if existing_member is None:
                initialize_member_database(actor_account_id, self.paths)
            else:
                require_member_database(actor_account_id, self.paths)
            return self.create_on_connection(
                connection, actor_account_id, values, set_as_default=set_as_default
            )

    @staticmethod
    def detail(
        access: MemberAccess,
        paths: AppPaths | None = None,
        *,
        is_default: bool | None = None,
    ) -> dict[str, Any]:
        with connect(
            require_member_database(
                access.account_id, paths or access.access_repository.paths
            )
        ) as connection:
            row = connection.execute(
                "SELECT * FROM members WHERE member_id = ?", (access.member_id,)
            ).fetchone()
        if row is None:
            raise UnsupportedSchemaError(
                "UNSUPPORTED_SCHEMA: member registry points to a missing member profile."
            )
        return {
            **dict(row),
            "account_id": access.account_id,
            "owner_account": access.owner_account,
            "is_default": access.is_default if is_default is None else is_default,
            "permission": access.permission,
            "can_edit": access.can_edit,
            "is_owned": access.actor_account_id == access.account_id,
        }

    def list_accessible(self, actor_account_id: str) -> dict[str, Any]:
        actor_id = actor_account_id
        with connect(self.paths.auth_db) as connection:
            connection.execute("BEGIN")
            ids = connection.execute(
                """SELECT p.member_id FROM member_ownerships p
                    LEFT JOIN member_grants g ON g.member_id = p.member_id AND g.account_id = ?
                    WHERE p.account_id = ? OR g.account_id IS NOT NULL
                    ORDER BY (p.account_id = ?) DESC, p.created_at, p.member_id""",
                (actor_id, actor_id, actor_id),
            ).fetchall()
            config_schema = self._attach_config_database(
                connection,
                actor_id,
                schema_alias="actor_config",
            )
            preference = self._preference_on_connection(
                connection,
                schema_alias=config_schema,
            )
            default = preference["default_member_id"]
            members = [
                self.detail(
                    self._access(connection, actor_id, row["member_id"]),
                    self.paths,
                    is_default=row["member_id"] == default,
                )
                for row in ids
            ]
            revision = connection.execute(
                "SELECT access_revision FROM accounts WHERE account_id = ?", (actor_id,)
            ).fetchone()[0]
        valid_ids = {item["member_id"] for item in members}
        if (members and default not in valid_ids) or (
            not members and default is not None
        ):
            member_error("DEFAULT_MEMBER_UNAVAILABLE", "默认成员不可访问。", "conflict")
        last = preference["last_member_id"]
        mode = preference["startup_mode"]
        normalized_last = last if last is None or last in valid_ids else default
        return {
            "members": members,
            "default_member_id": default,
            "startup_mode": mode,
            "last_member_id": normalized_last,
            "initial_member_id": normalized_last if mode == "last_used" else default,
            "access_revision": revision,
        }

    def update(
        self,
        access: MemberAccess,
        values: dict[str, Any],
        *,
        set_as_default: bool = False,
    ) -> None:
        if set(values) - {"member_name", "sex", "birth_date", "blood_type"}:
            member_error(
                "MEMBER_FIELDS_INVALID", "包含不可修改的成员字段。", "invalid_input"
            )
        with connect(self.paths.auth_db) as connection:
            # Wait for existing short authorization guards before locking member
            # data; prevent new guards from creating a cross-database deadlock.
            connection.execute("BEGIN EXCLUSIVE")
            live = self._access(
                connection, access.actor_account_id, access.member_id, write=True
            )
            self._attach_member_database(
                connection,
                live.account_id,
                schema_alias="member_data",
            )
            if values:
                assignments = ", ".join(f"{field} = ?" for field in values)
                updated = connection.execute(
                    f"UPDATE member_data.members SET {assignments}, updated_at = ? WHERE member_id = ?",
                    (*values.values(), local_now_iso(), live.member_id),
                )
                if not updated.rowcount:
                    member_error("MEMBER_NOT_FOUND", "成员不存在。", "missing")
            if set_as_default:
                config_schema = self._attach_config_database(
                    connection,
                    live.actor_account_id,
                    schema_alias="actor_config",
                )
                self._set_default(
                    connection,
                    live.actor_account_id,
                    live.member_id,
                    preference_schema=config_schema,
                    member_schema="member_data",
                )
            if values:
                self._touch_member(connection, live.member_id)
            elif set_as_default:
                connection.execute(
                    "UPDATE accounts SET access_revision = access_revision + 1 "
                    "WHERE account_id = ?",
                    (live.actor_account_id,),
                )

    @staticmethod
    def _touch_member(connection, member_id: str) -> None:
        connection.execute(
            """UPDATE accounts SET access_revision = access_revision + 1 WHERE account_id IN (
                SELECT account_id FROM member_ownerships WHERE member_id = ?
                UNION SELECT account_id FROM member_grants WHERE member_id = ?)""",
            (member_id, member_id),
        )

    def touch_member(self, member_id: str) -> None:
        with connect(self.paths.auth_db) as connection:
            connection.execute(
                """UPDATE accounts SET access_revision = access_revision + 1 WHERE account_id IN (
                    SELECT account_id FROM member_ownerships WHERE member_id = ?
                    UNION SELECT account_id FROM member_grants WHERE member_id = ?)""",
                (member_id, member_id),
            )

    def save_preferences(
        self,
        actor_account_id: str,
        *,
        startup_mode: str | None = None,
        default_member_id: str | None | object = _PREFERENCE_UNSET,
        last_member_id: str | None | object = _PREFERENCE_UNSET,
    ) -> None:
        actor_id = actor_account_id
        with connect(self.paths.auth_db) as connection:
            config_schema = self._attach_config_database(
                connection,
                actor_id,
                schema_alias="actor_config",
            )
            # Reserve both databases before reading preferences. Attaching the
            # configuration DB after BEGIN leaves it with a deferred read lock;
            # a concurrent settings write can then make the upgrade fail.
            connection.execute("BEGIN IMMEDIATE")
            self._preference_on_connection(
                connection,
                schema_alias=config_schema,
            )
            if default_member_id is not _PREFERENCE_UNSET:
                if default_member_id is None:
                    member_error(
                        "DEFAULT_MEMBER_REQUIRED",
                        "存在可访问成员时默认成员不能为空。",
                        "invalid_structure",
                    )
                self._set_default(
                    connection,
                    actor_id,
                    default_member_id,
                    preference_schema=config_schema,
                )
            if last_member_id is not _PREFERENCE_UNSET:
                if last_member_id is not None:
                    access = self._access(connection, actor_id, last_member_id)
                    self._require_member_profile(access)
                connection.execute(
                    f'UPDATE "{config_schema}".member_preferences '
                    "SET last_member_id = ? WHERE singleton_id = 1",
                    (last_member_id,),
                )
            if startup_mode is not None:
                connection.execute(
                    f'UPDATE "{config_schema}".member_preferences '
                    "SET startup_mode = ? WHERE singleton_id = 1",
                    (startup_mode,),
                )
            if (
                default_member_id is not _PREFERENCE_UNSET
                or last_member_id is not _PREFERENCE_UNSET
                or startup_mode is not None
            ):
                connection.execute(
                    "UPDATE accounts SET access_revision = access_revision + 1 WHERE account_id = ?",
                    (actor_id,),
                )

    @staticmethod
    def _replacement_member_id(
        connection, actor_id: str, excluded_member_id: str
    ) -> str | None:
        replacement = connection.execute(
            """SELECT p.member_id FROM member_ownerships p
                LEFT JOIN member_grants g
                    ON g.member_id = p.member_id AND g.account_id = ?
                WHERE p.member_id <> ?
                    AND (p.account_id = ? OR g.account_id IS NOT NULL)
                ORDER BY (p.account_id = ?) DESC, p.created_at, p.member_id
                LIMIT 1""",
            (actor_id, excluded_member_id, actor_id, actor_id),
        ).fetchone()
        return str(replacement["member_id"]) if replacement else None

    @staticmethod
    def _ensure_default_if_accessible(
        connection,
        actor_id: str,
        *,
        preference_schema: str,
    ) -> None:
        preference = MemberRepository._preference_on_connection(
            connection,
            schema_alias=preference_schema,
        )
        if preference["default_member_id"] is not None:
            return
        replacement = MemberRepository._replacement_member_id(connection, actor_id, "")
        if replacement is not None:
            connection.execute(
                f'UPDATE "{preference_schema}".member_preferences '
                "SET default_member_id = ? WHERE singleton_id = 1",
                (replacement,),
            )

    @staticmethod
    def _replace_unavailable_selection(
        connection,
        actor_id: str,
        member_id: str,
        *,
        preference_schema: str,
    ) -> None:
        preference = MemberRepository._preference_on_connection(
            connection,
            schema_alias=preference_schema,
        )
        default = preference["default_member_id"]
        if default == member_id:
            default = MemberRepository._replacement_member_id(
                connection, actor_id, member_id
            )
        connection.execute(
            f"""UPDATE "{preference_schema}".member_preferences SET default_member_id = ?,
                last_member_id = CASE WHEN last_member_id = ? THEN ? ELSE last_member_id END
                WHERE singleton_id = 1""",
            (default, member_id, default),
        )

    @member_lifecycle_change
    def delete(
        self, actor_account_id: str, member_id: str
    ) -> tuple[str, list[tuple[str, str]]]:
        actor_id = actor_account_id
        with connect(self.paths.auth_db) as connection:
            connection.execute("BEGIN EXCLUSIVE")
            access = self._access(connection, actor_id, member_id)
            if access.permission != "owner":
                member_error(
                    "MEMBER_OWNER_REQUIRED",
                    "只有健康档案所有者账号可以删除该成员及其健康档案。",
                )
            sessions = self._detach_private_references(connection, member_id)
            affected = {
                actor_id,
                *(
                    str(row[0])
                    for row in connection.execute(
                        "SELECT account_id FROM member_grants WHERE member_id = ?",
                        (member_id,),
                    )
                ),
            }
            attached_config_paths = set()
            for index, account_id in enumerate(sorted(affected)):
                config_schema = self._attach_config_database(
                    connection,
                    account_id,
                    schema_alias=f"account_config_{index}",
                )
                attached_config_paths.add(self.paths.config_db(account_id).resolve())
                self._replace_unavailable_selection(
                    connection,
                    account_id,
                    member_id,
                    preference_schema=config_schema,
                )
                connection.execute(
                    "UPDATE accounts SET access_revision = access_revision + 1 WHERE account_id = ?",
                    (account_id,),
                )
            self._attach_member_database(
                connection,
                access.account_id,
                schema_alias="member_data",
            )
            member_database_path = self.paths.members_db(access.account_id).resolve()
            attached_paths = {member_database_path, *attached_config_paths}
            account_root = self.paths.account_root(access.account_id).resolve()
            for participant in self._delete_participants():
                database_path = participant.path_for_owner(access.account_id)
                if not database_path.exists() and not database_path.is_symlink():
                    continue
                if not database_path.is_file():
                    raise UnsupportedSchemaError(
                        "UNSUPPORTED_SCHEMA: registered member data store is not a database file."
                    )
                resolved_path = database_path.resolve()
                if not resolved_path.is_relative_to(account_root):
                    raise ValueError(
                        "member data store database must stay inside its owner account directory"
                    )
                if resolved_path in attached_paths:
                    raise ValueError("member data store database paths must be unique")
                participant.validate_existing(access.account_id)
                connection.execute(
                    f'ATTACH DATABASE ? AS "{participant.schema_alias}"',
                    (str(database_path),),
                )
                participant.delete_member_data(
                    connection,
                    participant.schema_alias,
                    access.account_id,
                    member_id,
                )
                attached_paths.add(resolved_path)
            removed = connection.execute(
                "DELETE FROM member_data.members WHERE member_id = ?", (member_id,)
            )
            if not removed.rowcount:
                member_error("MEMBER_NOT_FOUND", "成员不存在。", "missing")
            connection.execute(
                "DELETE FROM member_grants WHERE member_id = ?", (member_id,)
            )
            connection.execute(
                "DELETE FROM member_ownerships WHERE member_id = ?", (member_id,)
            )
        return access.account_id, sessions

    def grants(self, actor_account_id: str) -> list[dict[str, Any]]:
        actor_id = actor_account_id
        with connect(self.paths.auth_db) as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """SELECT g.*, a.account AS grantee_account,
                           a.account_name AS grantee_account_name
                    FROM member_grants g JOIN member_ownerships p ON p.member_id = g.member_id
                    JOIN accounts a ON a.account_id = g.account_id
                    WHERE p.account_id = ? ORDER BY g.updated_at, g.member_id, a.account""",
                    (actor_id,),
                ).fetchall()
            ]

    def set_grants(
        self, actor_account_id: str, grantee_account: str, grants: list[dict[str, str]]
    ) -> None:
        actor_id = actor_account_id
        with connect(self.paths.auth_db) as connection:
            connection.execute("BEGIN IMMEDIATE")
            target = connection.execute(
                "SELECT account_id FROM accounts WHERE account = ?", (grantee_account,)
            ).fetchone()
            if target is None:
                member_error("ACCOUNT_NOT_FOUND", "该用户标识不存在。", "missing")
            target_account_id = str(target["account_id"])
            if target_account_id == actor_id:
                member_error(
                    "INVALID_MEMBER_GRANT", "无需向自己的账号授权。", "invalid_input"
                )
            for grant in grants:
                access = self._access(connection, actor_id, grant["member_id"])
                if access.permission != "owner":
                    member_error(
                        "MEMBER_OWNER_REQUIRED", "只有健康档案所有者账号可以管理授权。"
                    )
                self._require_member_profile(access)
            for grant in grants:
                connection.execute(
                    """INSERT INTO member_grants(member_id, account_id, permission, updated_at) VALUES (?, ?, ?, ?)
                        ON CONFLICT(member_id, account_id) DO UPDATE SET permission = excluded.permission, updated_at = excluded.updated_at""",
                    (
                        grant["member_id"],
                        target_account_id,
                        grant["permission"],
                        local_now_iso(),
                    ),
                )
            config_schema = self._attach_config_database(
                connection,
                target_account_id,
                schema_alias="grantee_config",
            )
            self._ensure_default_if_accessible(
                connection,
                target_account_id,
                preference_schema=config_schema,
            )
            connection.execute(
                "UPDATE accounts SET access_revision = access_revision + 1 WHERE account_id IN (?, ?)",
                (actor_id, target_account_id),
            )

    @member_lifecycle_change
    def revoke(
        self, actor_account_id: str, member_id: str, account_id: str
    ) -> list[tuple[str, str]]:
        actor_id = actor_account_id
        with connect(self.paths.auth_db) as connection:
            connection.execute("BEGIN IMMEDIATE")
            access = self._access(connection, actor_id, member_id)
            if access.permission != "owner":
                member_error(
                    "MEMBER_OWNER_REQUIRED", "只有健康档案所有者账号可以管理授权。"
                )
            config_schema = self._attach_config_database(
                connection,
                account_id,
                schema_alias="grantee_config",
            )
            connection.execute(
                "DELETE FROM member_grants WHERE member_id = ? AND account_id = ?",
                (member_id, account_id),
            )
            self._replace_unavailable_selection(
                connection,
                account_id,
                member_id,
                preference_schema=config_schema,
            )
            connection.execute(
                "UPDATE accounts SET access_revision = access_revision + 1 WHERE account_id IN (?, ?)",
                (actor_id, account_id),
            )
        return [
            (account_id, reference)
            for store in self.private_references
            if store.interrupts_sessions
            for reference in store.references(account_id, member_id)
        ]

    @staticmethod
    def revision(actor_account_id: str, paths: AppPaths | None = None) -> int:
        with connect((paths or app_paths()).auth_db) as connection:
            row = connection.execute(
                "SELECT access_revision FROM accounts WHERE account_id = ?",
                (actor_account_id,),
            ).fetchone()
        if row is None:
            member_error("UNAUTHORIZED", "账号不存在。", "unauthenticated")
        return int(row[0])

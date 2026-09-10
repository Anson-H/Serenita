from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from backend.app.storage.paths import AppPaths, app_paths
from backend.app.storage.sqlite import UnsupportedSchemaError


DeleteMemberData = Callable[[sqlite3.Connection, str, str, str], None]
ValidateMemberDataStore = Callable[[str], None]


@dataclass(frozen=True)
class MemberDataStoreParticipant:
    """A member-scoped peer store that joins the hard-delete transaction."""

    name: str
    schema_alias: str
    path_for_owner: Callable[[str], Path]
    validate_existing: ValidateMemberDataStore
    delete_member_data: DeleteMemberData

    def __post_init__(self) -> None:
        if (
            not re.fullmatch(r"[a-z][a-z0-9_]*", self.schema_alias)
            or self.schema_alias in {"main", "temp", "member_data"}
        ):
            raise ValueError("member data store schema alias is invalid")


def validate_member_data_store_participants(
    participants: Iterable[MemberDataStoreParticipant],
) -> tuple[MemberDataStoreParticipant, ...]:
    resolved = tuple(participants)
    names = [participant.name for participant in resolved]
    aliases = [participant.schema_alias for participant in resolved]
    if len(names) != len(set(names)):
        raise ValueError("member data store participant names must be unique")
    if len(aliases) != len(set(aliases)):
        raise ValueError("member data store schema aliases must be unique")
    return resolved


def report_member_data_store_participant(
    paths: AppPaths | None = None,
) -> MemberDataStoreParticipant:
    resolved_paths = paths or app_paths()

    def repository(owner_account_id: str):
        from backend.app.repositories.report_repository import ReportRepository

        return ReportRepository(owner_account_id, resolved_paths)

    def validate_existing(owner_account_id: str) -> None:
        if not repository(owner_account_id).validate_existing_database():
            raise UnsupportedSchemaError(
                "UNSUPPORTED_SCHEMA: registered report database is missing its current schema."
            )

    def delete_member_data(
        connection: sqlite3.Connection,
        schema_alias: str,
        owner_account_id: str,
        member_id: str,
    ) -> None:
        repository(owner_account_id).delete_member_on_connection(
            connection,
            member_id,
            schema_alias=schema_alias,
        )

    return MemberDataStoreParticipant(
        name="reports",
        schema_alias="report_data",
        path_for_owner=resolved_paths.reports_db,
        validate_existing=validate_existing,
        delete_member_data=delete_member_data,
    )


def medical_log_member_data_store_participant(paths=None):
    from backend.app.storage.medical_log_database import MEDICAL_LOG_DATABASE_SCHEMA
    resolved_paths = paths or app_paths()

    def validate_existing(owner_account_id):
        if not MEDICAL_LOG_DATABASE_SCHEMA.validate_existing(resolved_paths.medical_logs_db(owner_account_id)):
            raise UnsupportedSchemaError("UNSUPPORTED_SCHEMA: medical log database is missing its current schema.")

    def delete_member_data(connection, schema_alias, owner_account_id, member_id):
        connection.execute(f'DELETE FROM "{schema_alias}".medical_logs WHERE member_id = ?', (member_id,))

    return MemberDataStoreParticipant(
        name="medical_logs", schema_alias="medical_log_data",
        path_for_owner=resolved_paths.medical_logs_db,
        validate_existing=validate_existing, delete_member_data=delete_member_data,
    )


def medication_member_data_store_participant(paths=None):
    from backend.app.storage.medication_database import MEDICATION_DATABASE_SCHEMA
    resolved = paths or app_paths()
    def validate(owner):
        if not MEDICATION_DATABASE_SCHEMA.validate_existing(resolved.medications_db(owner)):
            raise UnsupportedSchemaError("UNSUPPORTED_SCHEMA: medication database is missing its current schema.")
    def delete(db, alias, owner, member):
        db.execute(f'DELETE FROM "{alias}".medication_plans WHERE member_id=?', (member,))
        db.execute(f'DELETE FROM "{alias}".medication_inventory WHERE member_id=?', (member,))
        db.execute(f'DELETE FROM "{alias}".medication_requests WHERE member_id=?', (member,))
    return MemberDataStoreParticipant(name="medications", schema_alias="medication_data",
        path_for_owner=resolved.medications_db, validate_existing=validate, delete_member_data=delete)


def body_metric_member_data_store_participant(paths=None):
    from backend.app.storage.body_metric_database import BODY_METRIC_DATABASE_SCHEMA
    resolved = paths or app_paths()
    def validate(owner):
        if not BODY_METRIC_DATABASE_SCHEMA.validate_existing(resolved.body_metrics_db(owner)):
            raise UnsupportedSchemaError("身体指标数据库结构缺失。")
    def delete(db, alias, owner, member):
        for table in ('body_imports', 'body_records', 'body_exclusions'):
            db.execute(f'DELETE FROM "{alias}".{table} WHERE member_id=?', (member,))
    return MemberDataStoreParticipant(name="body_metrics", schema_alias="body_metric_data",
        path_for_owner=resolved.body_metrics_db, validate_existing=validate, delete_member_data=delete)


def default_member_data_store_participants(
    paths: AppPaths | None = None,
) -> tuple[MemberDataStoreParticipant, ...]:
    return (report_member_data_store_participant(paths), medical_log_member_data_store_participant(paths), medication_member_data_store_participant(paths), body_metric_member_data_store_participant(paths))

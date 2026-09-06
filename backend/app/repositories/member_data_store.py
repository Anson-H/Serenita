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


def default_member_data_store_participants(
    paths: AppPaths | None = None,
) -> tuple[MemberDataStoreParticipant, ...]:
    return (report_member_data_store_participant(paths),)

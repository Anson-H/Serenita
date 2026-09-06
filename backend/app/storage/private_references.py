"""Transaction participants for operator-owned references to a member."""

from dataclasses import dataclass
from typing import Callable
from pathlib import Path
import re
from backend.app.storage.sqlite import connect, UnsupportedSchemaError


@dataclass(frozen=True)
class PrivateReferenceStore:
    source: str
    table: str
    id_column: str
    path_for_account: Callable[[str], Path]
    validate_existing: Callable[[str], bool]
    interrupts_sessions: bool = False

    def __post_init__(self):
        for identifier in (self.table, self.id_column):
            if not re.fullmatch(r"[a-z][a-z0-9_]*", identifier):
                raise ValueError("invalid private reference identifier")

    def member_id_for_reference(self, account_id, reference_id):
        path = self.path_for_account(account_id)
        self.validate_existing(account_id)
        if not path.is_file():
            return None
        with connect(path) as connection:
            row = connection.execute(
                f"SELECT member_id FROM {self.table} WHERE {self.id_column} = ?",
                (reference_id,),
            ).fetchone()
        return row["member_id"] if row is not None else None

    def references(self, account_id, member_id):
        path = self.path_for_account(account_id)
        if not path.exists():
            return []
        if not self.validate_existing(account_id):
            raise UnsupportedSchemaError(
                "UNSUPPORTED_SCHEMA: existing private database is uninitialized."
            )
        with connect(path) as connection:
            return [
                str(row[0])
                for row in connection.execute(
                    f"SELECT {self.id_column} FROM {self.table} WHERE member_id = ?",
                    (member_id,),
                )
            ]

    def detach(self, connection, alias, member_id):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", alias):
            raise ValueError("invalid private database alias")
        connection.execute(
            f'UPDATE "{alias}".{self.table} SET member_id = NULL WHERE member_id = ?',
            (member_id,),
        )

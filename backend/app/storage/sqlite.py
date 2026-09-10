import sqlite3
from contextlib import contextmanager
from pathlib import Path

from backend.app.storage.paths import ensure_private_directory, ensure_private_file


class UnsupportedSchemaError(RuntimeError):
    code = "UNSUPPORTED_SCHEMA"




def _secure_sqlite_files(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        ensure_private_file(path.with_name(f"{path.name}{suffix}"))


@contextmanager
def connect(path: Path | str | None = None):
    path = Path(path) if path is not None else None
    if path is not None:
        ensure_private_directory(path.parent)
        _secure_sqlite_files(path)
    connection = sqlite3.connect(str(path) if path is not None else ":memory:")
    if path is not None:
        _secure_sqlite_files(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
        if path is not None:
            _secure_sqlite_files(path)

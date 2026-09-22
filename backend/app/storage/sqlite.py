import sqlite3
from contextlib import contextmanager, nullcontext
from backend.app.core.cancellation import current_tool_cancellation, tool_cancellation_scope
from pathlib import Path

from backend.app.storage.paths import ensure_private_directory, ensure_private_file


@contextmanager
def connect_read_only(path: Path | str):
    """Open an existing database without creating files or allowing writes."""
    cancellation = current_tool_cancellation()
    if cancellation is not None:
        cancellation.raise_if_cancelled()
    connection = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    unregister = cancellation.register(connection.interrupt) if cancellation is not None else lambda: None
    if cancellation is not None:
        connection.set_progress_handler(lambda: int(cancellation.is_cancelled), 1000)
    try:
        connection.execute('PRAGMA query_only = ON')
        yield connection
        if cancellation is not None:
            cancellation.raise_if_cancelled()
    except Exception:
        if cancellation is not None:
            cancellation.raise_if_cancelled()
        raise
    finally:
        unregister()
        connection.close()


class UnsupportedSchemaError(RuntimeError):
    code = "UNSUPPORTED_SCHEMA"


class CommitConnection(sqlite3.Connection):
    """Synchronous effects run only after this connection commits and closes."""

    def after_commit(self, key, callback):
        if not hasattr(self, '_commit_effects'):
            self._commit_effects = {}
        self._commit_effects[key] = callback

def _secure_sqlite_files(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        ensure_private_file(path.with_name(f"{path.name}{suffix}"))


@contextmanager
def connect(path: Path | str | None = None):
    cancellation = current_tool_cancellation()
    if cancellation is not None:
        cancellation.raise_if_cancelled()
    path = Path(path) if path is not None else None
    if path is not None:
        ensure_private_directory(path.parent)
        _secure_sqlite_files(path)
    connection = sqlite3.connect(str(path) if path is not None else ":memory:", factory=CommitConnection)
    if path is not None:
        _secure_sqlite_files(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    committed = False
    unregister = cancellation.register(connection.interrupt) if cancellation is not None else lambda: None
    if cancellation is not None:
        connection.set_progress_handler(lambda: int(cancellation.is_cancelled), 1000)
    try:
        yield connection
        with cancellation.commit_guard() if cancellation is not None else nullcontext():
            connection.commit()
        committed = True
    except Exception:
        connection.set_progress_handler(None, 0)
        connection.rollback()
        if cancellation is not None:
            cancellation.raise_if_cancelled()
        raise
    finally:
        unregister()
        connection.close()
        if path is not None:
            _secure_sqlite_files(path)
    if committed:
        with tool_cancellation_scope(None):
            for callback in tuple(getattr(connection, '_commit_effects', {}).values()):
                callback()

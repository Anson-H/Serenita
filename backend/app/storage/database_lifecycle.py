"""Validate each database identity and SQLite schema generation once."""

from collections import OrderedDict
from contextlib import closing
from pathlib import Path
from threading import RLock
import sqlite3

from backend.app.storage.sqlite import connect

_lock = RLock()
_validated = OrderedDict()


def _identity(path: Path):
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    if stat.st_size == 0:
        return None
    try:
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
            schema_version = db.execute("PRAGMA schema_version").fetchone()[0]
    except sqlite3.DatabaseError:
        # The full validator supplies the existing invalid-database error.
        return None
    # SQLite reads the committed cookie from both the database and WAL. Physical
    # identity still invalidates atomic replacement/recreation of the same path.
    return (stat.st_dev, stat.st_ino, getattr(stat, "st_birthtime", None), schema_version)


def invalidate_database(path) -> None:
    """Call before deliberately replacing an open database in place."""
    resolved = Path(path).resolve()
    with _lock:
        for key in tuple(_validated):
            if key[0] == resolved:
                _validated.pop(key, None)


def ensure_database(schema, path) -> None:
    path = Path(path)
    key = (path.resolve(), schema)
    with _lock:
        while True:
            identity = _identity(path)
            if identity is not None and _validated.get(key) == identity:
                _validated.move_to_end(key)
                return
            _validated.pop(key, None)
            if not schema.validate_existing(path):
                with connect(path) as db:
                    db.execute("BEGIN IMMEDIATE")
                    schema.create(db)
                continue
            if _identity(path) != identity:
                # A concurrent DDL/replacement must be validated before its
                # identity can enter the cache.
                continue
            if identity is not None:
                _validated[key] = identity
                while len(_validated) > 256:
                    _validated.popitem(last=False)
            return

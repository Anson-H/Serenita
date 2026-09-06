"""Serialize short member lifecycle changes with conversation scheduling."""

from functools import wraps
from threading import local
from contextlib import contextmanager
import fcntl
import sqlite3

from backend.app.storage.paths import app_paths, ensure_private_file
from backend.app.core.errors import raise_error


_state = local()


@contextmanager
def member_lifecycle_guard(*, exclusive: bool = False, paths=None):
    path = (paths or app_paths()).auth_db.with_name("member_lifecycle.lock").resolve()
    active = getattr(_state, "locks", None)
    if active is None:
        active = _state.locks = {}
    if path in active:
        if exclusive and not active[path]:
            raise RuntimeError("member lifecycle lock cannot be upgraded")
        yield
        return
    ensure_private_file(path)
    with path.open("a") as handle:
        ensure_private_file(path)
        fcntl.flock(handle, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        active[path] = exclusive
        try:
            yield
        finally:
            active.pop(path)
            fcntl.flock(handle, fcntl.LOCK_UN)


def member_lifecycle_operation(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with member_lifecycle_guard(paths=args[0].paths):
            return function(*args, **kwargs)

    return wrapped


def member_lifecycle_change(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with member_lifecycle_guard(exclusive=True, paths=args[0].paths):
            try:
                return function(*args, **kwargs)
            except sqlite3.OperationalError as exc:
                raise_error(
                    "conflict", "MEMBER_CHANGE_FAILED", f"成员变更无法完成：{exc}"
                )

    return wrapped

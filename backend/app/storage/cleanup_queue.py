"""Bounded cleanup batches that advance past failures without changing audit dates."""

from collections import OrderedDict
from threading import Lock
import re

_lock = Lock()
_positions = OrderedDict()


def cleanup_batch(db, table, *, scope, where="1 = 1", parameters=(), limit=100):
    if not re.fullmatch(r"[a-z][a-z0-9_]*", table):
        raise ValueError("invalid cleanup table")
    key = (str(scope), table, where, tuple(parameters))
    with _lock:
        after = _positions.get(key, "")
        rows = db.execute(
            f"SELECT * FROM {table} WHERE ({where}) AND cleanup_id > ? ORDER BY cleanup_id LIMIT ?",
            (*parameters, after, limit),
        ).fetchall()
        if not rows and after:
            rows = db.execute(
                f"SELECT * FROM {table} WHERE {where} ORDER BY cleanup_id LIMIT ?",
                (*parameters, limit),
            ).fetchall()
        if rows:
            _positions[key] = str(rows[-1]["cleanup_id"])
            _positions.move_to_end(key)
            while len(_positions) > 256:
                _positions.popitem(last=False)
        else:
            _positions.pop(key, None)
        return [dict(row) for row in rows]


def drain_cleanup_batch(jobs, perform, on_failure=lambda job: None):
    """Each job owns its integrity rules; one failure never blocks later jobs."""
    for job in jobs:
        try:
            perform(job)
        except Exception:
            try:
                on_failure(job)
            except Exception:
                pass

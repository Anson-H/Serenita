"""Reuse a live memory transaction for nested source checks, including writes."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from threading import Lock, RLock
from weakref import WeakValueDictionary
import logging
import time

from backend.app.repositories.memory.reading.read_cache import access_key


@dataclass(frozen=True)
class MemoryTransaction:
    connection: object
    access: object
    committed_sequence: int


_active = ContextVar('memory_source_transaction', default=None)
_locks = WeakValueDictionary()
_locks_guard = Lock()
_logger = logging.getLogger(__name__)
_operation = ContextVar('memory_database_operation', default={})
_observer = ContextVar('memory_transaction_observer', default=None)


@contextmanager
def memory_operation(name, **identifiers):
    token = _operation.set({**_operation.get(), 'operation': name, **identifiers})
    try:
        yield
    finally:
        _operation.reset(token)


@contextmanager
def observe_memory_transactions(callback):
    token = _observer.set(callback)
    try:
        yield
    finally:
        _observer.reset(token)


@contextmanager
def memory_database_guard(path, *, write=False):
    """Serialize short reads and writes before opening SQLite transactions.

    A writer waiting to commit blocks new SQLite readers. Serializing at the
    database boundary lets an active detail read finish its nested checks
    without entering that lock cycle. Reentrant reads stay on the same thread.
    """
    key = str(path.resolve())
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = RLock()
            _locks[key] = lock
    started = time.monotonic()
    lock.acquire()
    acquired = time.monotonic()
    try:
        yield
    finally:
        finished = time.monotonic()
        lock.release()
        from backend.app.core.time import local_now
        details = {**_operation.get(), 'write': write, 'database': path.name,
                   'recorded_at': local_now().isoformat(),
                   'lock_wait_seconds': acquired - started, 'lock_held_seconds': finished - acquired}
        callback = _observer.get()
        if callback is not None:
            callback(details)
        level = logging.WARNING if acquired - started >= 1 or finished - acquired >= 1 else logging.DEBUG
        _logger.log(level, 'memory_transaction %s', details)


@contextmanager
def memory_transaction_scope(connection, access):
    sequence = connection.execute('SELECT COALESCE(max(sequence),0) FROM commits').fetchone()[0]
    token = _active.set(MemoryTransaction(connection, access, sequence))
    try:
        yield
    finally:
        _active.reset(token)


def current_memory_transaction(access):
    current = _active.get()
    return current if current is not None and access_key(current.access) == access_key(access) else None

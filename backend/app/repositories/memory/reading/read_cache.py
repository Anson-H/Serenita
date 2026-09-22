"""Read-transaction data reuse with mandatory fresh source checks at return."""
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar


_active = ContextVar("memory_immutable_read_cache", default=None)
MAX_ROWS = 16384
MAX_DEPENDENCIES = 32768
MAX_CHECKED_SOURCES = 32768


def access_key(access):
    return (access.actor_account_id, access.account_id, access.member_id,
            access.permission, access.grant_updated_at)


class MemoryReadCache:
    def __init__(self, connection, access):
        self.connection = connection
        self.scope = access_key(access)
        self.rows = OrderedDict()
        self.checked_changes = {}

    @staticmethod
    def save(values, key, value, maximum):
        values[key] = value
        values.move_to_end(key)
        while len(values) > maximum:
            values.popitem(last=False)


@contextmanager
def immutable_read_scope(connection, access, *, write):
    # A nested write must not see a cached absence before its own insert.
    cache = None if write else MemoryReadCache(connection, access)
    token = _active.set(cache)
    try:
        yield cache
    finally:
        _active.reset(token)


def current_read_cache(connection, access):
    cache = _active.get()
    if cache is not None and cache.connection is connection and cache.scope == access_key(access):
        return cache
    return None

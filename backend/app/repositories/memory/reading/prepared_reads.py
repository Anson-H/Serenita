"""Execution-local immutable content; authorization is never retained here."""
from contextlib import contextmanager
from contextvars import ContextVar

from backend.app.core.errors import SerenitaError
from backend.app.repositories.memory.reading.read_cache import access_key


_active = ContextVar('memory_prepared_reads', default=None)


class PreparedMemoryReads:
    def __init__(self, repository, actor, member):
        self.repository, self.actor, self.member = repository, actor, member
        self.rows, self.changes, self.source_texts = {}, {}, {}
        self.index_snapshots, self.episode_contexts = {}, {}
        self.execution_requests = {}

    @staticmethod
    def save(values, key, value, maximum):
        if key not in values and len(values) >= maximum:
            raise SerenitaError('resource_limit', 'MEMORY_STAGE_INPUT_LIMIT', '处理所需资料超过输入预算，尚未处理完成。')
        values[key] = value


@contextmanager
def prepared_read_scope(repository, actor, member):
    current = prepared_reads(repository)
    if current is not None and (current.actor, current.member) == (actor, member):
        yield current
        return
    prepared = PreparedMemoryReads(repository, actor, member)
    token = _active.set(prepared)
    try:
        yield prepared
    finally:
        _active.reset(token)


def prepared_reads(repository=None, access=None):
    prepared = _active.get()
    if prepared is None or repository is not None and prepared.repository is not repository:
        return None
    if access is not None and (access.actor_account_id, access.member_id) != (prepared.actor, prepared.member):
        return None
    return prepared


def prepared_row_key(access, kind, identity, version, item):
    return (*access_key(access), kind, identity, version, item)

"""Own the active draft view and temporary access to the committed view."""
from contextvars import ContextVar
from contextlib import contextmanager

_active = ContextVar('memory_staging', default=None)


def staging(repo=None, actor=None, member=None):
    value = _active.get()
    if value is None or repo is not None and value.repo is not repo:
        return None
    if actor is not None and (actor, member) != (value.actor, value.member):
        return None
    return value


@contextmanager
def published_memory():
    """Read live permissions and execution ownership outside a draft view."""
    from backend.app.repositories.memory.reading.prepared_reads import _active as prepared
    from backend.app.repositories.memory.transaction import _active as transaction
    token, reads, tx = _active.set(None), prepared.set(None), transaction.set(None)
    try:
        yield
    finally:
        transaction.reset(tx)
        prepared.reset(reads)
        _active.reset(token)


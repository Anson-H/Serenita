"""Serialization for SAG extraction saves."""
from contextlib import contextmanager
import fcntl
import time

from backend.app.repositories.memory.transaction import memory_database_guard


@contextmanager
def entity_save_guard(repository, actor, member, check_running):
    with repository.members.access_guard(actor, member, write=True) as access:
        path = repository.path_for_account(access.account_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Serialize lookup plus append across workers without changing the
        # append-only rows or keeping a second copy of the database.
        with memory_database_guard(path), (path.parent / 'sag-entities.lock').open('a') as lock:
            while True:
                check_running()
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(.02)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


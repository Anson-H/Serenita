"""One ordered formation execution per member, including direct retry callers."""
from contextlib import contextmanager
import fcntl


def formation_head(repository, actor, member):
    with repository._transaction(actor, member) as (access, db):
        if db is None:
            return None
        rows = db.execute(
            "WITH RECURSIVE scoped AS ("
            "SELECT p.*, c.sequence FROM processing_attempts p JOIN commits c USING(commit_id) "
            "WHERE p.account_id=? AND p.member_id=? AND p.task_kind='event_formation'), "
            "queue(attempt_id,registration_sequence) AS ("
            "SELECT p.attempt_id,p.sequence FROM scoped p WHERE p.previous_attempt_id IS NULL "
            "UNION ALL SELECT n.attempt_id,q.registration_sequence FROM scoped n "
            "JOIN queue q ON n.previous_attempt_id=q.attempt_id) "
            "SELECT p.attempt_id FROM scoped p JOIN queue q USING(attempt_id) "
            "WHERE p.processing_status IN ('pending','running','failed','cancelled') "
            "AND NOT EXISTS(SELECT 1 FROM scoped n WHERE n.previous_attempt_id=p.attempt_id) "
            "ORDER BY q.registration_sequence,p.sequence", (access.account_id, member))
        for row in rows:
            task = repository._record(db, access, 'processing_attempt', row['attempt_id'])
            if repository._visible(db, access, task):
                return task
            # Losing access to the earliest task cannot advance later work.
            return None
    return None


@contextmanager
def formation_guard(repository, actor, member):
    # Do not retain the authorization/database lock during model requests.
    with repository.members.access_guard(actor, member, write=True) as access:
        directory = repository.path_for_account(access.account_id).parent
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / ('formation-' + access.member_id + '.lock')
    with path.open('a') as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def execution_guard(repository, actor, member, attempt_id):
    """A process-held claim releases automatically when its executor exits."""
    from uuid import UUID
    identity = str(UUID(attempt_id))
    with repository.members.access_guard(actor, member, write=True) as access:
        directory = repository.path_for_account(access.account_id).parent
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / ('execution-' + identity + '.lock')
    with path.open('a') as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def execution_active(repository, actor, member, attempt_id):
    with execution_guard(repository, actor, member, attempt_id) as acquired:
        return not acquired

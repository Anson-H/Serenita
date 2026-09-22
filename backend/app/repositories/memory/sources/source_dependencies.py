"""Live original permissions retained from real read-tool results."""
import sqlite3
from contextlib import contextmanager

from backend.app.repositories.memory.sources.source_access import MemorySourceAccess
from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.source_identity import BusinessResourceIdentity
from backend.app.schemas.memory.source_identity import memory_source_id
from backend.app.repositories.memory.sources.restrictions import source_restrictions_allow


@contextmanager
def restriction_connection(repo, access):
    from backend.app.repositories.memory.transaction import current_memory_transaction
    active = current_memory_transaction(access)
    if active is not None:
        yield active.connection
    else:
        with repo._transaction(access.actor_account_id, access.member_id) as (_, connection):
            yield connection


def source_dependencies_visible(repo, access, sources):
    if not isinstance(sources, list) or len(sources) > 2000:
        return False
    try:
        with restriction_connection(repo, access) as connection:
            return _dependencies_visible(repo, connection, access, sources)
    except (SerenitaError, ValueError, LookupError, PermissionError, OSError, sqlite3.Error):
        return False


def _dependencies_visible(repo, connection, access, sources):
    if not source_restrictions_allow(connection, access):
        return False
    callback = repo.source_access_check or MemorySourceAccess(repo.members, repo.paths).check
    for source in sources:
        try:
            BusinessResourceIdentity.model_validate({key: value for key, value in source.items() if key not in {'account_id', 'member_id'}})
        except (TypeError, ValueError, AttributeError):
            return False
        expected_id = memory_source_id(access.member_id, **{key: source[key] for key in
            ('source_account_id', 'source_database', 'resource_type', 'resource_id', 'source_generation')})
        if source['source_id'] != expected_id or not source_restrictions_allow(connection, access, source['source_id']):
            return False
        if source.get('account_id') != access.account_id or source.get('member_id') != access.member_id or not callback(access, source):
            return False
    return True



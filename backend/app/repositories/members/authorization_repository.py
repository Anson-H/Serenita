"""Short, reentrant account authorization snapshots under the member lifecycle lock."""
from contextlib import contextmanager
from contextvars import ContextVar
import threading

from backend.app.core.runtime.member_lifecycle import member_lifecycle_guard
from backend.app.storage.sqlite import connect

_active_authorization_reads: ContextVar[tuple] = ContextVar('member_authorization_reads', default=())


class MemberAuthorizationRepository:
    def __init__(self, paths):
        self.paths = paths

    @contextmanager
    def read(self):
        """Reuse this synchronous authorization snapshot for nested checks.

        A second SQLite reader can wait behind a writer which is itself waiting
        for the outer reader. Sharing the existing read transaction preserves
        the revocation boundary without that lock cycle.
        """
        scope = (self.paths.auth_db.resolve(), threading.get_ident())
        for registered_scope, connection in _active_authorization_reads.get():
            if registered_scope == scope:
                yield connection
                return
        # All nested member/source reads and writes follow lifecycle -> auth ->
        # memory. Acquiring this after an outer auth guard could deadlock an
        # exclusive deletion that is waiting for that existing auth reader.
        with member_lifecycle_guard(paths=self.paths), connect(self.paths.auth_db) as connection:
            connection.execute('BEGIN')
            token = _active_authorization_reads.set((*_active_authorization_reads.get(), (scope, connection)))
            try:
                yield connection
            finally:
                _active_authorization_reads.reset(token)

    def account_exists(self, account_id: str) -> bool:
        with self.read() as connection:
            return connection.execute('SELECT 1 FROM accounts WHERE account_id=?', (account_id,)).fetchone() is not None

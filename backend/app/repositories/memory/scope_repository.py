"""Read registered owner scopes and accounts for background scheduling."""
class MemoryScopeRepository:
    def __init__(self, members):
        self.members = members

    def owners(self):
        if not self.members.paths.auth_db.exists():
            return []
        with self.members.authorization.read() as db:
            return [tuple(row) for row in db.execute(
                'SELECT account_id,member_id FROM member_ownerships ORDER BY account_id,member_id')]

    def accounts(self):
        if not self.members.paths.auth_db.exists():
            return []
        with self.members.authorization.read() as db:
            return [row[0] for row in db.execute('SELECT account_id FROM accounts ORDER BY account_id')]

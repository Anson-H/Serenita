"""Account permissions belong to user_auth.db; personal provider credentials are unrelated."""
from backend.app.storage.auth_database import initialize_auth_database
from backend.app.storage.sqlite import connect


class ModelServiceAccessRepository:
    def __init__(self, *, paths):
        self.paths = paths
        initialize_auth_database(paths)

    def get(self, account_id):
        with connect(self.paths.auth_db) as connection:
            row = connection.execute("SELECT is_enabled, daily_request_limit FROM model_service_access WHERE account_id = ?", (account_id,)).fetchone()
        return {"is_enabled": bool(row["is_enabled"]) if row else True,
                "daily_request_limit": row["daily_request_limit"] if row else None}

    def accounts(self):
        with connect(self.paths.auth_db) as connection:
            return [dict(row) for row in connection.execute(
                "SELECT a.account_id, a.account, a.account_name, COALESCE(p.is_enabled, 1) AS is_enabled, p.daily_request_limit "
                "FROM accounts a LEFT JOIN model_service_access p USING (account_id) ORDER BY a.created_at, a.account_id")]

    def save(self, account_id, *, is_enabled, daily_request_limit, timestamp):
        with connect(self.paths.auth_db) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO model_service_access (account_id, daily_request_limit, is_enabled, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(account_id) DO UPDATE SET daily_request_limit = excluded.daily_request_limit, "
                "is_enabled = excluded.is_enabled, updated_at = excluded.updated_at",
                (account_id, daily_request_limit, int(is_enabled), timestamp, timestamp))


from __future__ import annotations

import sqlite3

from backend.app.storage.auth_database import initialize_auth_database
from backend.app.storage.config_database import (
    initialize_config_database,
    require_config_database,
)
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect


class AccountConflictError(RuntimeError):
    pass


class AccountNotFoundError(RuntimeError):
    pass


class CredentialsChangedError(RuntimeError):
    pass


def _is_account_conflict(exc: sqlite3.IntegrityError) -> bool:
    message = str(exc)
    return "accounts.account" in message or "accounts.account_id" in message


class AuthRepository:
    def __init__(self, *, paths=None) -> None:
        self.paths = paths or app_paths()
        initialize_auth_database(self.paths)

    def account_by_login(self, account: str) -> sqlite3.Row | None:
        with connect(self.paths.auth_db) as connection:
            return connection.execute(
                "SELECT * FROM accounts WHERE account = ?", (account,)
            ).fetchone()

    def account_by_id(self, account_id: str) -> sqlite3.Row | None:
        with connect(self.paths.auth_db) as connection:
            return connection.execute(
                "SELECT * FROM accounts WHERE account_id = ?", (account_id,)
            ).fetchone()

    @staticmethod
    def _insert_session(
        connection: sqlite3.Connection,
        *,
        session_token_hash: str,
        account_id: str,
        expires_at: str,
        timestamp: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO login_sessions (
                session_token_hash, account_id, expires_at, revoked_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, NULL, ?, ?)
            """,
            (session_token_hash, account_id, expires_at, timestamp, timestamp),
        )

    def create_account_with_session(
        self,
        *,
        account_id: str,
        account: str,
        password_hash: str,
        account_name: str,
        session_token_hash: str,
        expires_at: str,
        timestamp: str,
    ) -> None:
        initialize_config_database(account_id, self.paths)
        try:
            with connect(self.paths.auth_db) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    'ATTACH DATABASE ? AS "account_config"',
                    (str(require_config_database(account_id, self.paths)),),
                )
                connection.execute(
                    """
                    INSERT INTO accounts (
                        account_id, account, account_name, password_hash,
                        access_revision, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        account_id,
                        account,
                        account_name,
                        password_hash,
                        timestamp,
                        timestamp,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO account_config.member_preferences (
                        singleton_id, default_member_id, last_member_id, startup_mode
                    ) VALUES (1, NULL, NULL, 'last_used')
                    """
                )
                self._insert_session(
                    connection,
                    session_token_hash=session_token_hash,
                    account_id=account_id,
                    expires_at=expires_at,
                    timestamp=timestamp,
                )
        except sqlite3.IntegrityError as exc:
            if _is_account_conflict(exc):
                raise AccountConflictError from exc
            raise

    def create_session(
        self,
        *,
        session_token_hash: str,
        account_id: str,
        verified_password_hash: str,
        expires_at: str,
        timestamp: str,
    ) -> None:
        with connect(self.paths.auth_db) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT password_hash FROM accounts WHERE account_id = ?", (account_id,)
            ).fetchone()
            if current is None or current["password_hash"] != verified_password_hash:
                raise CredentialsChangedError
            self._insert_session(
                connection,
                session_token_hash=session_token_hash,
                account_id=account_id,
                expires_at=expires_at,
                timestamp=timestamp,
            )

    def session(self, session_token_hash: str) -> sqlite3.Row | None:
        with connect(self.paths.auth_db) as connection:
            return connection.execute(
                """
                SELECT s.session_token_hash, s.account_id, s.expires_at,
                       s.revoked_at, a.account, a.account_name
                FROM login_sessions s
                JOIN accounts a ON a.account_id = s.account_id
                WHERE s.session_token_hash = ?
                """,
                (session_token_hash,),
            ).fetchone()

    def revoke_session(self, session_token_hash: str, timestamp: str) -> None:
        with connect(self.paths.auth_db) as connection:
            connection.execute(
                """
                UPDATE login_sessions
                SET revoked_at = COALESCE(revoked_at, ?), updated_at = ?
                WHERE session_token_hash = ?
                """,
                (timestamp, timestamp, session_token_hash),
            )

    def update_identity(
        self,
        *,
        account_id: str,
        account: str,
        account_name: str,
        timestamp: str,
    ) -> sqlite3.Row:
        try:
            with connect(self.paths.auth_db) as connection:
                row = connection.execute(
                    """
                    UPDATE accounts
                    SET account = ?, account_name = ?, updated_at = ?
                    WHERE account_id = ?
                    RETURNING account_id, account, account_name
                    """,
                    (account, account_name, timestamp, account_id),
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            if _is_account_conflict(exc):
                raise AccountConflictError from exc
            raise
        if row is None:
            raise AccountNotFoundError
        return row

    def change_password(
        self,
        *,
        account_id: str,
        password_hash: str,
        verified_password_hash: str,
        current_session_token_hash: str,
        timestamp: str,
    ) -> None:
        with connect(self.paths.auth_db) as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """
                UPDATE accounts
                SET password_hash = ?, updated_at = ?
                WHERE account_id = ? AND password_hash = ?
                """,
                (password_hash, timestamp, account_id, verified_password_hash),
            )
            if not updated.rowcount:
                raise CredentialsChangedError
            connection.execute(
                """
                UPDATE login_sessions
                SET revoked_at = ?, updated_at = ?
                WHERE account_id = ?
                  AND session_token_hash != ?
                  AND revoked_at IS NULL
                """,
                (
                    timestamp,
                    timestamp,
                    account_id,
                    current_session_token_hash,
                ),
            )

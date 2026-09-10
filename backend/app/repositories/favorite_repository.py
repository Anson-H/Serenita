import sqlite3
from backend.app.core.favorite_errors import FavoriteSourceConflictError
from backend.app.storage.favorite_database import initialize_favorites_database, FAVORITES_DATABASE_SCHEMA
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect


class FavoriteRepository:
    def __init__(self, *, paths=None):
        self.paths = paths or app_paths()

    def _connection(self, account_id):
        paths = self.paths
        initialize_favorites_database(account_id, self.paths)
        return connect(paths.favorites_db(account_id))

    def get(self, account_id, favorite_id):
        with self._connection(account_id) as connection:
            return connection.execute(
                "SELECT * FROM favorites WHERE favorite_id = ?", (favorite_id,)
            ).fetchone()

    def list(self, account_id):
        with self._connection(account_id) as connection:
            return connection.execute(
                "SELECT * FROM favorites ORDER BY created_at DESC, favorite_id DESC"
            ).fetchall()

    def create(self, account_id, values):
        FAVORITES_DATABASE_SCHEMA.table_by_name['favorites'].validate_values(values)
        try:
            with self._connection(account_id) as connection:
                connection.execute(
                    """INSERT INTO favorites (
                    favorite_id, member_id, source_type, source_session_id, source_id,
                    title, content_snapshot, tags, created_at, updated_at
                ) VALUES (:favorite_id, :member_id, :source_type, :source_session_id, :source_id,
                    :title, :content_snapshot, :tags, :created_at, :updated_at)""",
                    values,
                )
        except sqlite3.IntegrityError as exc:
            message = str(exc)
            if message in {
                "UNIQUE constraint failed: favorites.source_session_id, favorites.source_id",
                "UNIQUE constraint failed: favorites.member_id, favorites.source_id",
            }:
                raise FavoriteSourceConflictError from exc
            raise

    def update(self, account_id, favorite_id, title, tags, updated_at):
        FAVORITES_DATABASE_SCHEMA.table_by_name['favorites'].validate_values(dict(favorite_id=favorite_id, title=title, tags=tags, updated_at=updated_at), partial=True)
        with self._connection(account_id) as connection:
            connection.execute(
                "UPDATE favorites SET title = ?, tags = ?, updated_at = ? WHERE favorite_id = ?",
                (title, tags, updated_at, favorite_id),
            )

    def delete_many(self, account_id, favorite_ids):
        deleted, missing = [], []
        with self._connection(account_id) as connection:
            for favorite_id in favorite_ids:
                row = connection.execute(
                    "SELECT favorite_id FROM favorites WHERE favorite_id = ?",
                    (favorite_id,),
                ).fetchone()
                if row is None:
                    missing.append(favorite_id)
                else:
                    connection.execute(
                        "DELETE FROM favorites WHERE favorite_id = ?", (favorite_id,)
                    )
                    deleted.append(favorite_id)
        return deleted, missing

"""Transactions for model service metadata; account references are checked by services."""
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
from uuid import uuid4
from backend.app.storage.paths import app_paths, ensure_private_file
from backend.app.storage.sqlite import connect
from backend.app.storage.models.connection_database import CONNECTION_DATABASE
from backend.app.repositories.account_configuration_repository import initialize_config_database
from backend.app.core.time import local_now, local_now_iso, parse_local_datetime
from backend.app.storage.models.authorization_database import AUTHORIZATION_DATABASE
from backend.app.repositories.models.provider_repository import ModelProviderTransaction


@dataclass(frozen=True)
class AuthorizationClaim:
    operation_id: str
    generation: int
    state: dict


class ModelConnectionRepository:
    def __init__(self, *, paths=None, account_id):
        self.paths = paths or app_paths()
        self.account_id = account_id
        self.schema = CONNECTION_DATABASE
        self.path = self.paths.config_db(account_id).parent / self.schema.name

    @contextmanager
    def _transaction(self, *, write=False, with_models=False, with_authorization=False):
        if self.account_id:
            self.paths.require_account_tree(self.account_id)
        exists = self.schema.validate_existing(self.path)
        if with_models:
            initialize_config_database(self.account_id, self.paths)
        authorization_path = self.path.with_name(AUTHORIZATION_DATABASE.name)
        if with_authorization:
            with connect(authorization_path) as claims:
                claims.execute("BEGIN IMMEDIATE")
                if not AUTHORIZATION_DATABASE.validate_existing(authorization_path):
                    AUTHORIZATION_DATABASE.create(claims)
                    claims.execute("INSERT INTO authorization_operation (singleton_id, updated_at) VALUES (1, ?)", (local_now_iso(),))
        with connect(self.path) as connection:
            databases = ["main"]
            if with_models:
                connection.execute("ATTACH DATABASE ? AS model_config", (str(self.paths.config_db(self.account_id)),))
                databases.append("model_config")
            if with_authorization:
                connection.execute("ATTACH DATABASE ? AS authorization", (str(authorization_path),))
                databases.append("authorization")
            for schema in databases:
                mode = connection.execute(f"PRAGMA {schema}.journal_mode").fetchone()[0]
                synchronous = connection.execute(f"PRAGMA {schema}.synchronous").fetchone()[0]
                if mode.lower() != "delete" or synchronous < 2:
                    raise RuntimeError("Model authorization transactions require DELETE journal mode and FULL synchronous durability.")
            connection.execute("BEGIN IMMEDIATE" if write or not exists else "BEGIN")
            if not exists:
                self.schema.create(connection)
                if self.account_id:
                    connection.execute("INSERT OR IGNORE INTO model_connection (singleton_id, updated_at) VALUES (1, ?)", (local_now_iso(),))
            yield connection

    @contextmanager
    def catalog_transaction(self):
        """Expose catalog and grant operations in one durable transaction."""
        with self._transaction(write=True, with_models=True) as connection:
            yield ModelConnectionTransaction(connection)

    def local_state(self):
        with self._transaction() as connection:
            return dict(connection.execute("SELECT * FROM model_connection WHERE singleton_id = 1").fetchone())

    def update_local(self, **values):
        values["updated_at"] = local_now_iso()
        table = self.schema.table_by_name["model_connection"]
        if set(values) - set(table.column_names):
            raise ValueError("Unknown model connection field")
        with self._transaction(write=True) as connection:
            previous = dict(connection.execute("SELECT * FROM model_connection WHERE singleton_id = 1").fetchone())
            table.validate_values({**previous, **values})
            connection.execute("UPDATE model_connection SET " + ", ".join(f"{key} = ?" for key in values) + " WHERE singleton_id = 1", tuple(values.values()))

    @contextmanager
    def authorization_operation(self, kind):
        """Serialize device exchanges across processes without holding a SQLite lock.

        The OS releases this lock when a worker exits. The next holder replaces the
        durable claim and retries the saved private device code, whose remote exchange
        is idempotent. Disconnect invalidates generations without waiting for this lock.
        """
        self.paths.require_account_tree(self.account_id)
        lock_path = self.path.with_suffix(".authorization.lock")
        ensure_private_file(lock_path)
        with lock_path.open("a+b") as handle:
            ensure_private_file(lock_path)
            fcntl.flock(handle, fcntl.LOCK_EX)
            claim = None
            try:
                with self._transaction(write=True, with_authorization=True) as connection:
                    row = connection.execute("SELECT generation FROM authorization.authorization_operation WHERE singleton_id=1").fetchone()
                    identifier = str(uuid4())
                    connection.execute("UPDATE authorization.authorization_operation SET operation_id=?, operation_kind=?, updated_at=? WHERE singleton_id=1", (identifier, kind, local_now_iso()))
                    state = dict(connection.execute("SELECT * FROM model_connection WHERE singleton_id=1").fetchone())
                    claim = AuthorizationClaim(identifier, row["generation"], state)
                yield claim
            finally:
                if claim is not None:
                    with self._transaction(write=True, with_authorization=True) as connection:
                        connection.execute("UPDATE authorization.authorization_operation SET operation_id=NULL, operation_kind=NULL, updated_at=? WHERE singleton_id=1 AND operation_id=? AND generation=?", (local_now_iso(), claim.operation_id, claim.generation))
                fcntl.flock(handle, fcntl.LOCK_UN)

    @staticmethod
    def _device_reset():
        return dict(encrypted_device_code=None, user_code=None, verification_uri=None,
                    device_expires_at=None, next_poll_at=None)

    def _write_state(self, connection, values):
        values = {**values, "updated_at": local_now_iso()}
        table = self.schema.table_by_name["model_connection"]
        previous = dict(connection.execute("SELECT * FROM model_connection WHERE singleton_id=1").fetchone())
        table.validate_values({**previous, **values})
        connection.execute("UPDATE model_connection SET " + ", ".join(f"{key}=?" for key in values) + " WHERE singleton_id=1", tuple(values.values()))

    def commit_authorization(self, claim, *, clear_device=False, **values):
        """Commit a response only while its durable generation and claim still own it."""
        with self._transaction(write=True, with_authorization=True) as connection:
            current = connection.execute("SELECT operation_id, generation FROM authorization.authorization_operation WHERE singleton_id=1").fetchone()
            if current["operation_id"] != claim.operation_id or current["generation"] != claim.generation:
                return False
            self._write_state(connection, {**(self._device_reset() if clear_device else {}), **values})
            return True

    def expire_device(self):
        with self._transaction(write=True, with_authorization=True) as connection:
            state = dict(connection.execute("SELECT * FROM model_connection WHERE singleton_id=1").fetchone())
            if state["device_expires_at"] and parse_local_datetime(state["device_expires_at"]) <= local_now():
                self._invalidate_authorization(connection)
                self._write_state(connection, self._device_reset())
                state.update(self._device_reset())
            return state

    @staticmethod
    def _invalidate_authorization(connection):
        connection.execute("UPDATE authorization.authorization_operation SET generation=generation+1, operation_id=NULL, operation_kind=NULL, updated_at=? WHERE singleton_id=1", (local_now_iso(),))

    def disconnect_local(self, *, delete_models):
        """Invalidate in-flight claims and clear the grant and its models atomically."""
        with self._transaction(write=True, with_models=True, with_authorization=True) as connection:
            state = dict(connection.execute("SELECT * FROM model_connection WHERE singleton_id=1").fetchone())
            self._invalidate_authorization(connection)
            if delete_models:
                ModelProviderTransaction(connection).delete_provider("serenita")
            self._write_state(connection, {**self._device_reset(), "official_account_id": None,
                "official_account_name": None, "connection_id": None, "encrypted_token": None, "expires_at": None})
            return state


class ModelConnectionTransaction:
    """Connection metadata and the model catalog share one commit boundary."""

    def __init__(self, connection):
        self._connection = connection
        self.models = ModelProviderTransaction(connection)

    def state(self):
        return dict(self._connection.execute("SELECT * FROM model_connection WHERE singleton_id=1").fetchone())

    def clear_grant(self):
        self.models.delete_provider("serenita")
        self._connection.execute("UPDATE model_connection SET official_account_id=NULL, official_account_name=NULL, connection_id=NULL, encrypted_token=NULL, expires_at=NULL, updated_at=? WHERE singleton_id=1", (local_now_iso(),))

    def complete_onboarding(self):
        self._connection.execute("UPDATE model_connection SET onboarding_status='completed', updated_at=? WHERE singleton_id=1", (local_now_iso(),))

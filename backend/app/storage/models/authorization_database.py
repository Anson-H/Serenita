"""Durable claims for account-local device authorization; no credentials are stored here."""
from backend.app.storage.schema import Column as C, ColumnGroup as G, Table, Database, CheckConstraint


AUTHORIZATION_DATABASE = Database(name="model_authorization.db", tables=(
    Table(name="authorization_operation", columns=(
        C("singleton_id", "INTEGER", G.PRIMARY_KEY, nullable=False),
        C("operation_id", "TEXT", G.DATA),
        C("operation_kind", "TEXT", G.DATA),
        C("generation", "INTEGER", G.STATE, nullable=False, default="0"),
        C("updated_at", "DATETIME", G.AUDIT, nullable=False),
    ), primary_key=("singleton_id",), checks=(
        CheckConstraint("singleton_id = 1"),
        CheckConstraint("generation >= 0"),
        CheckConstraint("operation_kind IS NULL OR operation_kind IN ('start', 'poll', 'cancel')"),
        CheckConstraint("(operation_id IS NULL) = (operation_kind IS NULL)"),
    )),
))

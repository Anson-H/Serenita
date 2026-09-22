"""Account-local authorization to Serenita models."""
from backend.app.storage.schema import Column as C, ColumnGroup as G, Table, Database, CheckConstraint


CONNECTION_DATABASE = Database(name="model_connection.db", tables=(
    Table(name="model_connection", columns=(
        C("singleton_id", "INTEGER", G.PRIMARY_KEY, nullable=False),
        C("official_account_id", "TEXT", G.SCOPE),
        C("connection_id", "TEXT", G.REFERENCE),
        C("official_account_name", "TEXT", G.DATA),
        C("encrypted_token", "BLOB", G.DATA),
        C("encrypted_device_code", "BLOB", G.DATA),
        C("user_code", "TEXT", G.DATA),
        C("verification_uri", "TEXT", G.DATA),
        C("official_url", "TEXT", G.DATA),
        C("onboarding_status", "TEXT", G.STATE, nullable=False, default="'pending'"),
        C("poll_interval", "INTEGER", G.STATE, nullable=False, default="5"),
        C("expires_at", "DATETIME", G.STATE),
        C("device_expires_at", "DATETIME", G.STATE),
        C("next_poll_at", "DATETIME", G.STATE),
        C("updated_at", "DATETIME", G.AUDIT, nullable=False),
    ), primary_key=("singleton_id",), checks=(CheckConstraint("singleton_id = 1"), CheckConstraint("onboarding_status IN ('pending', 'completed', 'skipped')"), CheckConstraint("poll_interval >= 5"))),
))

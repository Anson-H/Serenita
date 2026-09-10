"""Durable post-commit work for member deletion and access revocation."""
from backend.app.storage.schema import Column, ColumnGroup as G, Database, Table, CheckConstraint as Check, Index

MEMBER_LIFECYCLE_DATABASE = Database("member_lifecycle.db", (
    Table("member_lifecycle_tasks", (
        Column("task_id", "TEXT", G.PRIMARY_KEY, nullable=False),
        Column("owner_account_id", "TEXT", G.SCOPE, nullable=False),
        Column("member_id", "TEXT", G.REFERENCE, nullable=False),
        Column("actor_account_id", "TEXT", G.REFERENCE, nullable=False),
        Column("session_id", "TEXT", G.REFERENCE),
        Column("operation", "TEXT", G.DATA, nullable=False),
        Column("attempt_count", "INTEGER", G.STATE, nullable=False, default="0"),
        Column("next_attempt_at", "TEXT", G.STATE, nullable=False),
        Column("last_error", "TEXT", G.STATE),
        Column("created_at", "TEXT", G.AUDIT, nullable=False),
        Column("updated_at", "TEXT", G.AUDIT, nullable=False),
    ), ("task_id",), checks=(
        Check("operation IN ('interrupt_session', 'delete_files')"),
        Check("(operation = 'interrupt_session') = (session_id IS NOT NULL)"),
        Check("attempt_count >= 0"),
    ), indexes=(Index("member_lifecycle_ready", ("next_attempt_at", "task_id")),)),
))

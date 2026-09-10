from backend.app.storage.schema import (
    CheckConstraint, Column, ColumnGroup as G, Database, Index, Table,
)

MEDICAL_LOG_DATABASE_SCHEMA = Database(
    name="medical_logs.db",
    tables=(
        Table(
            name="medical_logs",
            columns=(
                Column("medical_log_id", "TEXT", G.PRIMARY_KEY, nullable=False),
                Column("member_id", "TEXT", G.SCOPE, nullable=False),
                Column("recorded_on", "TEXT", G.DATA, nullable=False),
                Column("title", "TEXT", G.DATA, nullable=False),
                Column("content", "TEXT", G.DATA, nullable=False),
                Column("created_at", "TEXT", G.AUDIT, nullable=False),
                Column("updated_at", "TEXT", G.AUDIT, nullable=False),
            ),
            primary_key=("medical_log_id",),
            checks=(
                CheckConstraint("length(trim(recorded_on)) > 0"),
                CheckConstraint("length(trim(title)) > 0"),
                CheckConstraint("length(trim(content)) > 0"),
            ),
            indexes=(Index("medical_logs_member_date", ("member_id", "recorded_on", "created_at")),),
        ),
    ),
)

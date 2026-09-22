from backend.app.storage.schema import (
    CheckConstraint, Column, ColumnGroup as G, Database, Index, Table,
)

from backend.app.storage.business_change_database import BUSINESS_CHANGE_TABLES


MEDICAL_LOG_DATABASE_SCHEMA = Database(
    name="medical_logs.db",
    tables=(
        Table(
            name="medical_logs",
            columns=(
                Column("medical_log_id", "TEXT", G.PRIMARY_KEY, nullable=False),
                Column("member_id", "TEXT", G.SCOPE, nullable=False),
                Column("recorded_on", "DATE", G.DATA, nullable=False),
                Column("title", "TEXT", G.DATA, nullable=False),
                Column("content", "TEXT", G.DATA, nullable=False),
                Column("created_at", "DATETIME", G.AUDIT, nullable=False),
                Column("updated_at", "DATETIME", G.AUDIT, nullable=False),
            ),
            primary_key=("medical_log_id",),
            checks=(
                CheckConstraint("length(trim(recorded_on)) > 0"),
                CheckConstraint("length(trim(title)) > 0"),
                CheckConstraint("length(trim(content)) > 0"),
            ),
            indexes=(Index("medical_logs_member_date", ("member_id", "recorded_on", "created_at")),),
        ),
        *BUSINESS_CHANGE_TABLES,
    ),
)

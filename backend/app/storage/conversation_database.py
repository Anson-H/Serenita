from backend.app.storage.schema import (
    CheckConstraint,
    Column,
    ColumnGroup,
    Database,
    ForeignKey,
    Index,
    STORED_FILE_DATA_COLUMNS,
    Table,
    UniqueConstraint,
)


CONVERSATION_DATABASE_SCHEMA = Database(
    name="conversations.db",
    tables=(
        Table(
            name="conversations",
            columns=(
                Column("session_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("member_id", "TEXT", ColumnGroup.SCOPE),
                Column("parent_session_id", "TEXT", ColumnGroup.REFERENCE),
                Column("title", "TEXT", ColumnGroup.DATA, nullable=False),
                Column("relative_path", "TEXT", ColumnGroup.DATA, nullable=False),
                Column(
                    "seed_event_count",
                    "INTEGER",
                    ColumnGroup.STATE,
                    nullable=False,
                    default="0",
                ),
                Column(
                    "is_pinned",
                    "INTEGER",
                    ColumnGroup.STATE,
                    nullable=False,
                    default="0",
                ),
                Column(
                    "is_title_manual",
                    "INTEGER",
                    ColumnGroup.STATE,
                    nullable=False,
                    default="0",
                ),
                Column("created_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
                Column("last_active_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
            ),
            primary_key=("session_id",),
            checks=(
                CheckConstraint(
                    "seed_event_count >= 0",
                ),
                CheckConstraint(
                    "is_pinned IN (0, 1)",
                ),
                CheckConstraint(
                    "is_title_manual IN (0, 1)",
                ),
            ),
        ),
        Table(
            name="conversation_turns",
            columns=(
                Column("session_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("turn_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("user_message_id", "TEXT", ColumnGroup.REFERENCE),
                Column(
                    "final_assistant_message_id",
                    "TEXT",
                    ColumnGroup.REFERENCE,
                ),
                Column("stream_id", "TEXT", ColumnGroup.REFERENCE),
                Column("status", "TEXT", ColumnGroup.STATE, nullable=False),
                Column("error_code", "TEXT", ColumnGroup.STATE),
                Column("error_message", "TEXT", ColumnGroup.STATE),
                Column("created_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
                Column("updated_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
            ),
            primary_key=("session_id", "turn_id"),
            foreign_keys=(
                ForeignKey(
                    ("session_id",),
                    "conversations",
                    ("session_id",),
                ),
            ),
            checks=(
                CheckConstraint(
                    "status IN ('queued', 'streaming', 'completed', 'failed', "
                    "'cancelled')",
                ),
            ),
            indexes=(
                Index(
                    "uidx_conversation_turns__active_session",
                    ("session_id",),
                    unique=True,
                    where="status IN ('queued', 'streaming')",
                ),
            ),
        ),
        Table(
            name="conversation_resources",
            columns=(
                Column("session_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("resource_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("original_filename", "TEXT", ColumnGroup.DATA, nullable=False),
                *STORED_FILE_DATA_COLUMNS,
                Column(
                    "storage_status",
                    "TEXT",
                    ColumnGroup.STATE,
                    nullable=False,
                ),
                Column(
                    "lifecycle_status",
                    "TEXT",
                    ColumnGroup.STATE,
                    nullable=False,
                    default="'pending'",
                ),
                Column("expires_at", "TEXT", ColumnGroup.STATE),
                Column("created_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
                Column("updated_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
            ),
            primary_key=("session_id", "resource_id"),
            foreign_keys=(
                ForeignKey(
                    ("session_id",),
                    "conversations",
                    ("session_id",),
                ),
            ),
            checks=(
                CheckConstraint(
                    "size_bytes >= 0",
                ),
                CheckConstraint(
                    "storage_status IN ('writing', 'ready')",
                ),
                CheckConstraint(
                    "lifecycle_status IN ('pending', 'attached', 'expired', 'deleted')",
                ),
                CheckConstraint(
                    "(storage_status = 'writing' AND lifecycle_status = 'pending' "
                    "AND expires_at IS NULL) OR (storage_status = 'ready' AND "
                    "(lifecycle_status != 'pending' OR expires_at IS NOT NULL))",
                ),
            ),
            indexes=(
                Index(
                    "idx_conversation_resources__write_recovery",
                    ("storage_status", "updated_at"),
                ),
                Index(
                    "idx_conversation_resources__expiry",
                    ("storage_status", "lifecycle_status", "expires_at"),
                ),
            ),
        ),
        Table(
            name="conversation_resource_cleanup_outbox",
            columns=(
                Column("cleanup_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("relative_path", "TEXT", ColumnGroup.DATA, nullable=False),
                Column(
                    "attempt_count",
                    "INTEGER",
                    ColumnGroup.STATE,
                    nullable=False,
                    default="0",
                ),
                Column("last_attempt_at", "TEXT", ColumnGroup.STATE),
                Column("created_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
            ),
            primary_key=("cleanup_id",),
            unique_constraints=(
                UniqueConstraint(
                    ("relative_path",),
                ),
            ),
            checks=(
                CheckConstraint(
                    "attempt_count >= 0",
                ),
            ),
            indexes=(
                Index(
                    "idx_conversation_resource_cleanup_outbox__retry",
                    ("attempt_count", "created_at"),
                ),
            ),
        ),
    ),
)


def conversation_member_references(paths):
    from backend.app.storage.private_references import PrivateReferenceStore

    return PrivateReferenceStore(
        source="conversation",
        table="conversations",
        id_column="session_id",
        path_for_account=paths.conversations_db,
        validate_existing=lambda account_id: (
            CONVERSATION_DATABASE_SCHEMA.validate_existing(
                paths.conversations_db(account_id)
            )
        ),
        interrupts_sessions=True,
    )

from backend.app.storage.memory.chunk_index_database import CHUNK_INDEX_TABLES, CHUNK_INDEX_COLLECTIONS
from backend.app.storage.memory.semantic_index_database import SEMANTIC_INDEX_TABLES, SEMANTIC_INDEX_COLLECTIONS
"""The only SQLite declaration for immutable member memory."""
from backend.app.storage.memory.progress_database import PROGRESS_TABLE
from backend.app.storage.memory.recovery_database import RECOVERY_RECORDS_TABLE
from backend.app.storage.memory.execution_database import EXECUTION_TABLES, EXECUTION_COLLECTIONS
from backend.app.storage.memory.episode_database import EPISODE_TABLES, EPISODE_COLLECTIONS
from backend.app.storage.memory.relations import MEMORY_RELATION_TABLES, MEMORY_RELATION_COLLECTIONS
from backend.app.schemas.memory.append import SOURCE_CATEGORIES
from backend.app.storage.memory.index_database import MEMORY_INDEX_TABLES, MEMORY_INDEX_COLLECTIONS
from backend.app.storage.schema import CheckConstraint, Column, ColumnGroup as G, Database, ForeignKey, Index, Table, UniqueConstraint


def text(name, group=G.DATA, *, nullable=False, json_kind=None):
    return Column(name, "TEXT", group, nullable=nullable, json_kind=json_kind)


def timestamp(name, group=G.DATA, *, nullable=False):
    return Column(name, "DATETIME", group, nullable=nullable)


def integer(name, group=G.DATA, *, nullable=False):
    return Column(name, "INTEGER", group, nullable=nullable)


def scope(*, member_primary=False):
    return (text("account_id", G.SCOPE),) + (() if member_primary else (text("member_id", G.SCOPE),))


def commit_reference():
    return ForeignKey(("commit_id", "account_id", "member_id"), "commits", ("commit_id", "account_id", "member_id"))


def reference(column, target, target_column=None):
    return ForeignKey((column, "account_id", "member_id"), target, (target_column or column, "account_id", "member_id"))


def values(name, choices):
    return CheckConstraint(f"{name} IN ({','.join(repr(v) for v in choices)})")


def object_table(name, primary, data, *, references=(), indexes=(), checks=(), mutable_columns=()):
    return Table(name=name, columns=(text(primary, G.PRIMARY_KEY), *scope(), *data),
                 primary_key=(primary,), foreign_keys=(commit_reference(), *references),
                 unique_constraints=(UniqueConstraint((primary, "account_id", "member_id")),),
                 indexes=indexes, checks=checks, append_only=True, mutable_columns=mutable_columns)




_TABLES = (
    Table(name="commits", columns=(
        text("commit_id", G.PRIMARY_KEY), *scope(), text("actor_account_id", G.REFERENCE), text("operation_id"),
        text("request_hash"), integer("sequence", G.STATE), timestamp("submitted_at", G.AUDIT),
    ), primary_key=("commit_id",), unique_constraints=(UniqueConstraint(("account_id", "member_id", "operation_id")), UniqueConstraint(("sequence",)), UniqueConstraint(("commit_id", "account_id", "member_id"))),
    checks=(CheckConstraint("sequence > 0"), CheckConstraint("length(request_hash) = 64 AND request_hash NOT GLOB '*[^0-9a-f]*'"),),
    indexes=(Index("commit_member_sequence", ("account_id", "member_id", "sequence")),), append_only=True),
    object_table("events", "event_id", (
        text("title"),
        text("summary"),
        text("content"),
        text("text_hash"),
        text("category"),
        text("priority"),
        text("occurrence_time_json", nullable=True, json_kind="object"),
        text("commit_id", G.AUDIT),
    ), indexes=(Index("event_commit", ("account_id", "member_id", "commit_id", "event_id")),),
       checks=(CheckConstraint("length(text_hash) = 64 AND text_hash NOT GLOB '*[^0-9a-f]*'"),
               CheckConstraint("priority IN ('HIGH', 'MEDIUM', 'LOW')"))),
    Table(name="event_evidence", columns=(
        text("event_id", G.PRIMARY_KEY),
        text("source_database", G.PRIMARY_KEY),
        text("change_id", G.PRIMARY_KEY),
        Column("field_path", "TEXT", G.PRIMARY_KEY, nullable=False, non_blank=False),
        *scope(),
        text("commit_id", G.AUDIT),
    ),
        primary_key=("event_id", "source_database", "change_id", "field_path"),
        foreign_keys=(commit_reference(), reference("event_id", "events")),
        checks=(CheckConstraint("field_path = '' OR (substr(field_path,1,1)='/' AND instr(replace(replace(field_path,'~0',''),'~1',''),'~')=0)"),),
        indexes=(Index("evidence_change", ("account_id", "member_id", "source_database", "change_id", "event_id")),), append_only=True),
    object_table("processing_attempts", "attempt_id", (
        text("source_account_id", G.REFERENCE, nullable=True),
        text("source_database", G.REFERENCE, nullable=True),
        text("change_id", G.REFERENCE, nullable=True),
        text("previous_attempt_id", G.REFERENCE, nullable=True),
        text("model_id", G.REFERENCE, nullable=True),
        integer("input_sequence"),
        text("task_kind"),
        text("purpose"),
        integer("change_sequence", nullable=True),
        text("target_time_json", json_kind="object"),
        text("coverage_json", json_kind="array"),
        text("input_references_json", json_kind="array"),
        text("result_references_json", json_kind="array"),
        text("outcome_reason", nullable=True),
        text("gaps_json", json_kind="array"),
        text("processing_status", G.STATE),
        text("error_code", G.STATE, nullable=True),
        text("error_message", G.STATE, nullable=True),
        timestamp("retry_after", G.STATE, nullable=True),
        text("commit_id", G.AUDIT),
        text("started_commit_id", G.AUDIT, nullable=True),
        text("updated_commit_id", G.AUDIT),
    ), mutable_columns=('model_id','result_references_json','outcome_reason','gaps_json','processing_status','error_code','error_message','retry_after','started_commit_id','updated_commit_id'), references=(reference("previous_attempt_id", "processing_attempts", "attempt_id"), ForeignKey(("started_commit_id", "account_id", "member_id"), "commits", ("commit_id", "account_id", "member_id")), ForeignKey(("updated_commit_id", "account_id", "member_id"), "commits", ("commit_id", "account_id", "member_id"))),
       indexes=(Index("attempt_member", ("account_id", "member_id", "task_kind", "attempt_id")), Index("formation_initial", ("account_id", "member_id", "source_database", "change_id"), unique=True, where="task_kind='event_formation' AND change_id IS NOT NULL AND previous_attempt_id IS NULL"), Index("formation_successor", ("previous_attempt_id",), unique=True, where="task_kind='event_formation' AND previous_attempt_id IS NOT NULL"), Index("attempt_delivery", ("account_id", "member_id", "source_account_id", "source_database", "change_id")), Index("delivery_initial", ("account_id", "member_id", "source_account_id", "source_database", "change_id"), unique=True, where="task_kind='intake_review' AND source_account_id IS NOT NULL AND previous_attempt_id IS NULL"), Index("delivery_successor", ("previous_attempt_id",), unique=True, where="task_kind='intake_review' AND source_account_id IS NOT NULL AND previous_attempt_id IS NOT NULL")),
       checks=(values("processing_status", ("pending", "running", "completed", "failed", "cancelled")),
       CheckConstraint("(processing_status='failed' AND error_code IS NOT NULL AND error_message IS NOT NULL) OR (processing_status<>'failed' AND error_code IS NULL AND error_message IS NULL)"),
       CheckConstraint("retry_after IS NULL OR processing_status='failed'"),
       CheckConstraint("(model_id IS NULL) OR (model_id IS NOT NULL AND started_commit_id IS NOT NULL)"), CheckConstraint("input_sequence >= 0"), CheckConstraint("(source_account_id IS NULL AND source_database IS NULL AND change_id IS NULL AND change_sequence IS NULL) OR (source_account_id IS NOT NULL AND source_database IS NOT NULL AND change_id IS NOT NULL AND change_sequence > 0)"), values("task_kind", ("intake_review", "event_formation", "memory_query", "relation_review", "vector_index")))),
    object_table("access_restrictions", "restriction_id", (
        text("source_id", G.REFERENCE, nullable=True),
        text("restricted_actor_account_id", G.REFERENCE, nullable=True),
        text("grant_reference", G.REFERENCE, nullable=True),
        text("trigger_resource_type"),
        text("trigger_resource_id"),
        text("restriction_kind"),
        text("reason"),
        timestamp("effective_at", G.DATA),
        text("commit_id", G.AUDIT),
    ), indexes=(Index("restriction_scope", ("account_id", "member_id", "restriction_kind")), Index("restriction_source", ("account_id", "member_id", "source_id"))),
       checks=(values("restriction_kind", ("source_deleted", "member_deleted", "grant_revoked", "source_access_revoked")), CheckConstraint("restriction_kind NOT IN ('source_deleted','source_access_revoked') OR source_id IS NOT NULL"), CheckConstraint("restriction_kind <> 'member_deleted' OR source_id IS NULL"), CheckConstraint("restriction_kind <> 'grant_revoked' OR (restricted_actor_account_id IS NOT NULL AND grant_reference IS NOT NULL)"))),
    Table(name="settings_history", columns=(
        text("member_id", G.PRIMARY_KEY),
        text("setting_id", G.PRIMARY_KEY),
        *scope(member_primary=True),
        text("embedding_model_id", G.REFERENCE, nullable=True),
        text("previous_setting_id", G.REFERENCE, nullable=True),
        text("source_categories_json", json_kind="array"),
        text("reason"),
        timestamp("effective_at", G.DATA),
        text("formation_state", G.STATE),
        text("commit_id", G.AUDIT),
    ), primary_key=("member_id", "setting_id"),
        foreign_keys=(commit_reference(), ForeignKey(("member_id", "previous_setting_id"), "settings_history", ("member_id", "setting_id"))),
        indexes=(Index("setting_initial", ("member_id",), unique=True, where="previous_setting_id IS NULL"), Index("setting_successor", ("member_id", "previous_setting_id"), unique=True, where="previous_setting_id IS NOT NULL")),
        checks=(values("formation_state", ("disabled", "enabled", "paused")), CheckConstraint("formation_state <> 'enabled' OR json_array_length(source_categories_json) > 0")), append_only=True),
    *MEMORY_INDEX_TABLES,
    *SEMANTIC_INDEX_TABLES,
    *CHUNK_INDEX_TABLES,
    *MEMORY_RELATION_TABLES,
    *EPISODE_TABLES,
    *EXECUTION_TABLES,
    PROGRESS_TABLE,
    RECOVERY_RECORDS_TABLE,
)

# Explicit dispatch metadata contains identities and value encoding, not a
# second table definition. Every column is still owned by the schema above.
MEMORY_COLLECTIONS = {
    "processing_steps": ("processing_steps", None, None),
    "events": ("events", "event", "event_id"),
    "event_evidence": ("event_evidence", None, None),
    "attempts": ("processing_attempts", "processing_attempt", "attempt_id"),
    "restrictions": ("access_restrictions", "access_restriction", "restriction_id"),
    "settings": ("settings_history", "memory_setting", "setting_id"),
}
MEMORY_COLLECTIONS.update(MEMORY_INDEX_COLLECTIONS)
MEMORY_COLLECTIONS.update(MEMORY_RELATION_COLLECTIONS)
MEMORY_COLLECTIONS.update(EPISODE_COLLECTIONS)
MEMORY_COLLECTIONS.update(EXECUTION_COLLECTIONS)
MEMORY_COLLECTIONS.update(SEMANTIC_INDEX_COLLECTIONS)
MEMORY_COLLECTIONS.update(CHUNK_INDEX_COLLECTIONS)
MEMORY_OBJECTS = {kind: (table, primary) for table, kind, primary in MEMORY_COLLECTIONS.values() if kind is not None}

# Public declaration order follows evidence, entities, SAG, events, episodes and runtime.
_TABLE_ORDER = ('entities', 'entity_names', 'vector_spaces', 'event_vectors', 'event_vector_statuses', 'entity_vectors', 'entity_vector_statuses', 'event_entity_vectors', 'event_entity_vector_statuses', 'source_chunks', 'source_chunk_statuses', 'events', 'event_entities', 'event_evidence', 'event_relations', 'episodes', 'episode_revisions', 'episode_revision_inputs', 'event_episode', 'commits', 'processing_attempts', 'vector_requests', 'execution_entries', 'processing_steps', 'access_restrictions', 'settings_history', 'recovery_records')
_TABLE_BY_NAME = {table.name: table for table in _TABLES}
MEMORY_DATABASE_SCHEMA = Database(name="memory.db", tables=tuple(_TABLE_BY_NAME[name] for name in _TABLE_ORDER))

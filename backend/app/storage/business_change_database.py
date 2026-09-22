"""Business receipts and facts are fixed; their memory processing status is mutable."""
from backend.app.domain.business_memory_status import MEMORY_STATUSES

from backend.app.storage.schema import (
    CheckConstraint, Column, ColumnGroup as G, ForeignKey, Index, Table,
    UniqueConstraint,
)


BUSINESS_OPERATIONS = Table(
    name="business_operations",
    columns=(
        Column("operation_id", "TEXT", G.PRIMARY_KEY, nullable=False),
        Column("actor_account_id", "TEXT", G.SCOPE, nullable=False),
        Column("command_hash", "TEXT", G.DATA, nullable=False),
        Column("original_command_json", "TEXT", G.DATA, nullable=False, json_kind="object"),
        Column("recorded_at", "DATETIME", G.AUDIT, nullable=False),
    ),
    primary_key=("operation_id",),
    unique_constraints=(UniqueConstraint(("operation_id", "actor_account_id")),),
    checks=(CheckConstraint("length(command_hash) = 64 AND command_hash NOT GLOB '*[^0-9a-f]*'"),),
    append_only=True,
)

BUSINESS_OPERATION_RESULTS = Table(
    name="business_operation_results",
    columns=(
        Column("operation_id", "TEXT", G.PRIMARY_KEY, nullable=False),
        Column("result_json", "TEXT", G.DATA, nullable=False, json_kind="object"),
        Column("recorded_at", "DATETIME", G.AUDIT, nullable=False),
    ),
    primary_key=("operation_id",),
    foreign_keys=(ForeignKey(("operation_id",), "business_operations", ("operation_id",)),),
    append_only=True,
)

BUSINESS_CHANGES = Table(
    name="business_changes",
    columns=(
        Column("change_id", "TEXT", G.PRIMARY_KEY, nullable=False),
        Column("scope_kind", "TEXT", G.SCOPE, nullable=False),
        Column("member_id", "TEXT", G.SCOPE),
        Column("actor_account_id", "TEXT", G.SCOPE, nullable=False),
        Column("operation_id", "TEXT", G.REFERENCE, nullable=False),
        Column("resource_type", "TEXT", G.REFERENCE, nullable=False),
        Column("resource_id", "TEXT", G.REFERENCE, nullable=False),
        Column("operation_kind", "TEXT", G.DATA, nullable=False),
        Column("origin_kind", "TEXT", G.DATA, nullable=False),
        Column("context_json", "TEXT", G.DATA, nullable=False, json_kind="object"),
        Column("memory_status", "TEXT", G.STATE, nullable=False),
        Column("change_sequence", "INTEGER", G.AUDIT, nullable=False),
        Column("recorded_at", "DATETIME", G.AUDIT, nullable=False),
    ),
    primary_key=("change_id",),
    foreign_keys=(ForeignKey(
        ("operation_id", "actor_account_id"),
        "business_operations", ("operation_id", "actor_account_id"),
    ),),
    unique_constraints=(UniqueConstraint(("change_sequence",)),),
    checks=(
        CheckConstraint("(scope_kind = 'account' AND member_id IS NULL) OR "
                        "(scope_kind = 'member' AND member_id IS NOT NULL)"),
        CheckConstraint("operation_kind IN ('create', 'update', 'delete')"),
        CheckConstraint('memory_status IN (' + ','.join(repr(value) for value in MEMORY_STATUSES) + ')'),
        CheckConstraint("typeof(change_sequence) = 'integer' AND change_sequence > 0"),
    ),
    indexes=(
        Index("business_changes_member_sequence", ("member_id", "change_sequence")),
        Index("business_changes_operation", ("operation_id", "change_sequence")),
        Index("business_changes_resource", ("resource_type", "resource_id", "change_sequence")),
        Index("business_changes_memory_status", ("member_id", "memory_status", "change_sequence")),
    ),
    append_only=True,
    mutable_columns=("memory_status",),
)

BUSINESS_CHANGE_FIELDS = Table(
    name="business_change_fields",
    columns=(
        Column("change_id", "TEXT", G.PRIMARY_KEY, nullable=False),
        Column("field_path", "TEXT", G.PRIMARY_KEY, nullable=False),
        Column("after_json", "TEXT", G.DATA),
    ),
    primary_key=("change_id", "field_path"),
    foreign_keys=(ForeignKey(("change_id",), "business_changes", ("change_id",)),),
    checks=(
        CheckConstraint("substr(field_path, 1, 1) = '/' AND "
                        "instr(replace(replace(field_path, '~0', ''), '~1', ''), '~') = 0"),
        CheckConstraint("after_json IS NULL OR json_valid(after_json)"),
    ),
    append_only=True,
)

BUSINESS_CHANGE_TABLES = (
    BUSINESS_OPERATIONS, BUSINESS_OPERATION_RESULTS,
    BUSINESS_CHANGES, BUSINESS_CHANGE_FIELDS,
)

"""Append access restrictions inside an existing authorization transaction."""
from backend.app.core.time import local_now

import hashlib
import json
import re

from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.append import AccessRestrictionInput, canonical_uuid, stable_memory_id
from backend.app.storage.memory.database import MEMORY_DATABASE_SCHEMA


def source_restrictions_allow(connection, access, source_id=None):
    """Apply live source/member restrictions even before a Source is ingested."""
    if connection is None:
        return True
    restrictions = connection.execute(
        "SELECT restriction_kind, restricted_actor_account_id, grant_reference FROM access_restrictions "
        "WHERE account_id=? AND member_id=? AND (source_id=? OR restriction_kind IN ('member_deleted','grant_revoked'))",
        (access.account_id, access.member_id, source_id),
    ).fetchall()
    for restriction in restrictions:
        if restriction['restriction_kind'] in {'member_deleted', 'source_deleted', 'source_access_revoked'}:
            return False
        if restriction['restricted_actor_account_id'] == access.actor_account_id:
            live_grant = access.grant_updated_at.isoformat() if access.grant_updated_at else 'owner'
            if restriction['grant_reference'] == live_grant:
                return False
    return True


def append_restriction_on_connection(
    connection, schema_alias, owner_account_id, member_id, actor_account_id,
    restriction: AccessRestrictionInput, operation_id,
):
    """Trusted lifecycle code holds authorization and validates its trigger.

    Member/grant changes use the caller's authorization transaction. Source
    deletion delivery instead supplies a committed business deletion receipt.
    """
    if not re.fullmatch(r"[a-z][a-z0-9_]*", schema_alias):
        raise ValueError("记忆数据库别名无效。")
    for value in (owner_account_id, member_id, actor_account_id):
        canonical_uuid(value)
    restriction = AccessRestrictionInput.model_validate(restriction)
    payload = restriction.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    scope = {"account_id": owner_account_id, "member_id": member_id}
    existing = connection.execute(
        f'SELECT * FROM "{schema_alias}".commits WHERE account_id=? AND member_id=? AND operation_id=?',
        (owner_account_id, member_id, operation_id),
    ).fetchone()
    if existing is not None:
        if existing["request_hash"] != digest:
            raise SerenitaError("conflict", "MEMORY_OPERATION_CONFLICT", "该记忆操作标识已用于不同参数。")
        return dict(existing)
    timestamp = local_now().isoformat(timespec="microseconds")
    commit_id = stable_memory_id(member_id, operation_id, "commit", "access_control")
    sequence = connection.execute(f'SELECT COALESCE(max(sequence),0)+1 FROM "{schema_alias}".commits').fetchone()[0]
    commit = {
        "commit_id": commit_id, **scope, "actor_account_id": actor_account_id,
        "operation_id": operation_id, "request_hash": digest, 
        "sequence": sequence, "submitted_at": timestamp,
    }
    for table_name, row in (
        ("commits", commit),
        ("access_restrictions", {**payload, **scope, "commit_id": commit_id}),
    ):
        table = MEMORY_DATABASE_SCHEMA.table_by_name[table_name]
        table.validate_values(row)
        connection.execute(
            f'INSERT INTO "{schema_alias}".{table_name} ({",".join(table.column_names)}) VALUES ({",".join("?" for _ in table.columns)})',
            tuple(row.get(name) for name in table.column_names),
        )
    return commit


def restrict_deleted_member(connection, schema_alias, owner_account_id, member_id):
    operation_id = f"member_deleted:{member_id}"
    restriction = AccessRestrictionInput(
        restriction_id=stable_memory_id(member_id, operation_id, "access_restriction", "member"),
        trigger_resource_type="member", trigger_resource_id=member_id,
        restriction_kind="member_deleted", reason="健康档案所有者删除成员，相关记忆立即限制访问。",
        effective_at=local_now().isoformat(),
    )
    return append_restriction_on_connection(connection, schema_alias, owner_account_id, member_id,
                                            owner_account_id, restriction, operation_id)


def restrict_revoked_grant(connection, paths, owner_account_id, member_id, actor_account_id, grantee_account_id, grant_reference):
    path = paths.memory_db(owner_account_id)
    if not MEMORY_DATABASE_SCHEMA.validate_existing(path):
        return
    alias = "revoked_memory"
    connection.execute(f'ATTACH DATABASE ? AS "{alias}"', (str(path),))
    operation_id = f"grant_revoked:{member_id}:{grantee_account_id}:{grant_reference}"
    restriction = AccessRestrictionInput(
        restriction_id=stable_memory_id(member_id, operation_id, "access_restriction", "grant"),
        restricted_actor_account_id=grantee_account_id, grant_reference=grant_reference,
        trigger_resource_type="member_grant", trigger_resource_id=member_id,
        restriction_kind="grant_revoked", reason="健康档案所有者撤销共享授权。",
        effective_at=local_now().isoformat(),
    )
    return append_restriction_on_connection(connection, alias, owner_account_id, member_id,
                                            actor_account_id, restriction, operation_id)

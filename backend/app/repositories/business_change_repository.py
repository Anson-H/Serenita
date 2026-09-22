"""Append actual object and field changes in a registered business command."""
from __future__ import annotations
import json
import re
import sqlite3
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid5

from backend.app.core.errors import SerenitaError
from backend.app.repositories.business_operation_repository import (
    invalid_business_value, business_text, business_json, business_object,
    transaction_schema, recorded_time, ledger_row, insert_ledger_row,
    require_operation, operation_effects,
)
from backend.app.storage.business_change_database import BUSINESS_CHANGE_FIELDS, BUSINESS_CHANGES

_NAMESPACE = UUID("460cc5b8-6f2e-4c4b-b155-fde290cfe47e")
_ALIAS = re.compile(r"[a-z][a-z0-9_]*\Z")
_BAD_POINTER_ESCAPE = re.compile(r"~(?![01])")


def _snapshot(value: Mapping[str, Any] | None, name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise invalid_business_value(f"{name} 必须是稳定字段 JSON Pointer 到实际值的映射。")
    result = {}
    for path, content in value.items():
        if not isinstance(path, str) or not path.startswith("/") or _BAD_POINTER_ESCAPE.search(path):
            raise invalid_business_value("字段路径必须是以 / 开始且正确转义的 JSON Pointer。")
        business_text(path, "field_path")
        result[path] = business_json(content)
    return result


def record_change(
    conn: sqlite3.Connection, *, actor_account_id: str, operation_id: str,
    scope_kind: str, member_id: str | None, resource_type: str, resource_id: str,
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None,
    context: dict, origin_kind: str, schema_alias: str = "main",
) -> dict | None:
    """Append actual changed fields for one object, returning the row and fields.

    None denotes an absent object; missing mapping keys denote absent fields.
    A present key whose value is None is encoded as JSON null. Stable detail
    identifiers in pointers are provided by the business Repository.
    """
    alias = transaction_schema(conn, schema_alias)
    require_operation(conn, alias, actor_account_id, operation_id)
    if ledger_row(conn, f"SELECT operation_id FROM {alias}.business_operation_results WHERE operation_id = ?", (operation_id,)) is not None:
        raise SerenitaError("conflict", "BUSINESS_OPERATION_FINISHED", "命令已保存完整回执，不能继续追加变化。")
    business_text(resource_type, "resource_type")
    business_text(resource_id, "resource_id")
    business_text(origin_kind, "origin_kind")
    if scope_kind == "member":
        business_text(member_id, "member_id")
    elif scope_kind != "account" or member_id is not None:
        raise invalid_business_value("成员作用域必须提供成员标识；账号作用域不填写成员标识。")
    context_json = business_object(context, "context")
    before_fields, after_fields = _snapshot(before, "before"), _snapshot(after, "after")
    changed = [path for path in sorted(before_fields.keys() | after_fields.keys())
               if before_fields.get(path) != after_fields.get(path)]
    if not changed:
        return None
    change_id = str(uuid5(_NAMESPACE, business_json([
        "business_change", actor_account_id, operation_id, scope_kind,
        member_id, resource_type, resource_id,
    ])))
    fields = [{"change_id": change_id, "field_path": path,
               "after_json": after_fields.get(path)} for path in changed]
    record = {
        "change_id": change_id, "scope_kind": scope_kind, "member_id": member_id,
        "actor_account_id": actor_account_id, "operation_id": operation_id,
        "resource_type": resource_type, "resource_id": resource_id,
        "operation_kind": "create" if before is None else "delete" if after is None else "update",
        "origin_kind": origin_kind, "context_json": context_json,
    }
    old = ledger_row(conn, f"SELECT * FROM {alias}.business_changes WHERE change_id = ?", (change_id,))
    if old is not None:
        old_fields = _read_fields(conn, alias, change_id)
        if any(old[key] != value for key, value in record.items()) or fields != old_fields:
            raise SerenitaError("conflict", "BUSINESS_CHANGE_CONFLICT", "同一命令中同一对象只能登记一次最终实际变化。")
        return {**old, "fields": old_fields}
    record["change_sequence"] = conn.execute(f"SELECT COALESCE(MAX(change_sequence), 0) + 1 FROM {alias}.business_changes").fetchone()[0]
    record["recorded_at"] = recorded_time()
    from backend.app.repositories.business_memory_status_repository import status_at_creation
    record['memory_status'] = status_at_creation(conn, record, fields, schema_alias)
    BUSINESS_CHANGES.validate_values(record)
    for field in fields:
        BUSINESS_CHANGE_FIELDS.validate_values(field)
    insert_ledger_row(conn, alias, BUSINESS_CHANGES, record)
    for field in fields:
        insert_ledger_row(conn, alias, BUSINESS_CHANGE_FIELDS, field)
    effects = operation_effects(conn, schema_alias)
    if effects is not None:
        effects.change_recorded(conn, record)
    return {**record, "fields": fields}


def _read_fields(conn: sqlite3.Connection, alias: str, change_id: str) -> list[dict]:
    cursor = conn.execute(f"SELECT change_id, field_path, after_json FROM {alias}.business_change_fields WHERE change_id = ? ORDER BY field_path", (change_id,))
    return [dict(zip(("change_id", "field_path", "after_json"), row)) for row in cursor.fetchall()]


def read_change_fields(conn: sqlite3.Connection, change_id: str, *, schema_alias: str = "main") -> list[dict]:
    """Read this change's saved field values without reconstructing prior state.

    SQL NULL denotes an absent field; JSON null denotes a present empty value.
    """
    if not isinstance(schema_alias, str) or not _ALIAS.fullmatch(schema_alias):
        raise invalid_business_value("数据库别名必须是合法的标识符。")
    alias = f'"{schema_alias}"'
    return [{"field_path": field["field_path"],
             "after_exists": field["after_json"] is not None,
             "after_value": json.loads(field["after_json"]) if field["after_json"] is not None else None}
            for field in _read_fields(conn, alias, change_id)]

"""Register commands and append complete receipts in the caller's transaction.

Business effects are supplied by the owning transaction through a connection
and schema scoped interface. Receipt storage has no dependency on those effects.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
import sqlite3
from typing import Any, Protocol

from backend.app.core.errors import SerenitaError
from backend.app.core.time import local_now
from backend.app.storage.business_change_database import BUSINESS_OPERATIONS, BUSINESS_OPERATION_RESULTS
from backend.app.storage.schema import Table

_ALIAS = re.compile(r"[a-z][a-z0-9_]*\Z")


class BusinessOperationEffects(Protocol):
    """Effects registered by the owner of this actual connection and schema."""

    def operation_replayed(self, connection, operation_id: str) -> None: ...

    def change_recorded(self, connection, record: dict) -> None: ...


def bind_operation_effects(connection, effects: BusinessOperationEffects, *, schema_alias: str):
    transaction_schema(connection, schema_alias)
    connection._business_operation_effects = {
        **getattr(connection, '_business_operation_effects', {}), schema_alias: effects}


def operation_effects(connection, schema_alias) -> BusinessOperationEffects | None:
    return getattr(connection, '_business_operation_effects', {}).get(schema_alias)


def invalid_business_value(message: str) -> SerenitaError:
    return SerenitaError("invalid_input", "BUSINESS_CHANGE_INVALID", message)


def business_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise invalid_business_value(f"{name} 必须是非空文本。")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise invalid_business_value(f"{name} 必须能够完整编码为 UTF-8。") from exc
    return value


def business_json(value: Any) -> str:
    def validate(item: Any, ancestors: set[int]) -> None:
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float:
            if math.isfinite(item):
                return
            raise invalid_business_value("JSON 数字必须有限。")
        if type(item) not in (dict, list):
            raise invalid_business_value("值必须使用 JSON 对象、数组或标量。")
        identity = id(item)
        if identity in ancestors:
            raise invalid_business_value("JSON 内容不能循环引用。")
        ancestors.add(identity)
        if type(item) is dict:
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise invalid_business_value("JSON 对象键必须是文本。")
                validate(nested, ancestors)
        else:
            for nested in item:
                validate(nested, ancestors)
        ancestors.remove(identity)

    try:
        validate(value, set())
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False)
        encoded.encode("utf-8")
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise invalid_business_value("内容必须能够完整编码为 UTF-8 JSON。") from exc
    return encoded


def business_object(value: Any, name: str) -> str:
    if type(value) is not dict:
        raise invalid_business_value(f"{name} 必须是 JSON 对象。")
    return business_json(value)


def transaction_schema(conn: sqlite3.Connection, schema_alias: str) -> str:
    if not isinstance(schema_alias, str) or not _ALIAS.fullmatch(schema_alias):
        raise invalid_business_value("数据库别名必须是合法的标识符。")
    if not conn.in_transaction:
        raise SerenitaError("conflict", "BUSINESS_TRANSACTION_REQUIRED",
                            "业务变更必须在调用方的写入事务中完成。")
    return f'"{schema_alias}"'


def recorded_time() -> str:
    return local_now().isoformat(timespec="microseconds")


def ledger_row(conn: sqlite3.Connection, sql: str, values: tuple) -> dict | None:
    cursor = conn.execute(sql, values)
    result = cursor.fetchone()
    return dict(zip((column[0] for column in cursor.description), result)) if result is not None else None


def insert_ledger_row(conn: sqlite3.Connection, alias: str, table: Table, values: dict) -> None:
    table.validate_values(values)
    names = table.column_names
    conn.execute(
        f"INSERT INTO {alias}.{table.name} ({', '.join(names)}) "
        f"VALUES ({', '.join('?' for _ in names)})",
        tuple(values.get(name) for name in names),
    )


def require_operation(conn: sqlite3.Connection, alias: str, actor: str, operation_id: str) -> dict:
    business_text(actor, "actor_account_id")
    business_text(operation_id, "operation_id")
    row = ledger_row(conn, f"SELECT * FROM {alias}.business_operations WHERE operation_id = ?", (operation_id,))
    if row is None:
        raise SerenitaError("conflict", "BUSINESS_OPERATION_REQUIRED", "请先登记本次业务命令。")
    if row["actor_account_id"] != actor:
        raise SerenitaError("conflict", "BUSINESS_OPERATION_CONFLICT", "操作标识已由另一条命令使用。")
    return row


def begin_operation(
    conn: sqlite3.Connection, actor_account_id: str, operation_id: str,
    original_command: dict, *, schema_alias: str = "main",
) -> dict | None:
    """Register a command, or return its committed result after verifying identity.

    The original command includes the domain, member and actual command inputs.
    The caller supplies an authorized actor and excludes runtime credentials.
    A pending receipt is an error, never authorization to repeat business writes.
    """
    alias = transaction_schema(conn, schema_alias)
    business_text(actor_account_id, "actor_account_id")
    business_text(operation_id, "operation_id")
    command_json = business_object(original_command, "original_command")
    fingerprint = hashlib.sha256(business_json([actor_account_id, original_command]).encode("utf-8")).hexdigest()
    old = ledger_row(conn, f"SELECT * FROM {alias}.business_operations WHERE operation_id = ?", (operation_id,))
    if old is not None:
        if old["actor_account_id"] != actor_account_id or old["command_hash"] != fingerprint or old["original_command_json"] != command_json:
            raise SerenitaError("conflict", "BUSINESS_OPERATION_CONFLICT", "相同操作标识的命令参数不一致。")
        receipt = ledger_row(conn, f"SELECT result_json FROM {alias}.business_operation_results WHERE operation_id = ?", (operation_id,))
        if receipt is None:
            raise SerenitaError("conflict", "BUSINESS_OPERATION_INCOMPLETE", "本次业务命令缺少完整回执，请回滚并检查事务。")
        effects = operation_effects(conn, schema_alias)
        if effects is not None:
            effects.operation_replayed(conn, operation_id)
        return json.loads(receipt["result_json"])
    insert_ledger_row(conn, alias, BUSINESS_OPERATIONS, {
        "operation_id": operation_id, "actor_account_id": actor_account_id,
        "command_hash": fingerprint, "original_command_json": command_json,
        "recorded_at": recorded_time(),
    })
    return None


def finish_operation(
    conn: sqlite3.Connection, actor_account_id: str, operation_id: str,
    result: dict, *, schema_alias: str = "main",
) -> dict:
    """Append the exact command result without committing the caller's transaction."""
    alias = transaction_schema(conn, schema_alias)
    require_operation(conn, alias, actor_account_id, operation_id)
    result_json = business_object(result, "result")
    old = ledger_row(conn, f"SELECT result_json FROM {alias}.business_operation_results WHERE operation_id = ?", (operation_id,))
    if old is not None:
        if old["result_json"] != result_json:
            raise SerenitaError("conflict", "BUSINESS_OPERATION_CONFLICT", "命令已保存的结果与本次回执不一致。")
        return json.loads(old["result_json"])
    insert_ledger_row(conn, alias, BUSINESS_OPERATION_RESULTS, {
        "operation_id": operation_id, "result_json": result_json, "recorded_at": recorded_time(),
    })
    return json.loads(result_json)

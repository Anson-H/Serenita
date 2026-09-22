"""Trusted execution metadata shared by HTTP and generic Harness tool calls."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import json
from typing import Iterator
from uuid import NAMESPACE_URL, uuid4, uuid5


@dataclass(frozen=True)
class BusinessOperation:
    operation_id: str
    origin_kind: str


_operation: ContextVar[BusinessOperation | None] = ContextVar("business_operation", default=None)


def validate_operation_id(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 200 or any(
        ord(char) < 33 or ord(char) > 126 for char in value
    ):
        raise ValueError("操作标识应为不含空白的可打印 ASCII 文本，最多 200 个字符。")
    return value


@contextmanager
def operation_scope(operation_id: str, origin_kind: str) -> Iterator[BusinessOperation]:
    operation = BusinessOperation(validate_operation_id(operation_id), origin_kind)
    if not origin_kind or not origin_kind.strip():
        raise ValueError("操作产生方式不能为空。")
    token = _operation.set(operation)
    try:
        yield operation
    finally:
        _operation.reset(token)


def current_business_operation() -> BusinessOperation:
    """Repositories call once per command; direct service calls receive a fresh id."""
    return _operation.get() or BusinessOperation(str(uuid4()), "manual")


def bind_business_operation(function):
    """Keep one operation across a command's participants, including direct calls."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        operation = current_business_operation()
        with operation_scope(operation.operation_id, operation.origin_kind):
            return function(*args, **kwargs)
    return wrapped


def tool_operation_id(account_id: str, session_id: str | None, turn_id: str | None, call_id: str) -> str:
    # An ephemeral Harness execution has no durable retry identity.
    execution = turn_id if turn_id else str(uuid4())
    identity = json.dumps(["serenita-tool-operation", account_id, session_id, execution, call_id],
                          ensure_ascii=False, separators=(",", ":"))
    return str(uuid5(NAMESPACE_URL, identity))

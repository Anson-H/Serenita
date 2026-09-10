"""One safe error shape for execution and result preparation failures."""
from typing import Any

from backend.app.core.cancellation import OperationCancelledError


def tool_failure(error: Exception) -> dict[str, Any]:
    detail = getattr(error, "detail", None)
    structured = detail if isinstance(detail, dict) else {}
    details = structured.get("details", getattr(error, "details", None))
    return {
        "code": str(structured.get("code") or getattr(error, "code", None) or type(error).__name__.upper()),
        "message": str(structured.get("message") or str(error) or "工具执行失败。"),
        "details": details if isinstance(details, dict) else None,
    }


def stops_execution(error: Exception) -> bool:
    return isinstance(error, (OperationCancelledError, PermissionError)) or getattr(error, "status_code", None) in {401, 403}

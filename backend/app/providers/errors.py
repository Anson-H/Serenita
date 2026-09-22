import json
import re
from typing import Any
from urllib.error import URLError

import httpx


class ProviderModelListError(Exception):
    def __init__(
        self, message: str, *, code: str = "MODEL_ERROR",
        upstream_status: int | None = None, request_id: str | None = None,
        cause_type: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.upstream_status = upstream_status
        self.request_id = request_id
        self.cause_type = cause_type


class ProviderChatCompletionError(Exception):
    """A provider failure with an optional, provider-independent error code."""

    CONTEXT_WINDOW_EXCEEDED = "CONTEXT_WINDOW_EXCEEDED"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        upstream_status: int | None = None,
        capability_rejected: bool = False,
        request_id: str | None = None,
        cause_type: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.upstream_status = upstream_status
        self.capability_rejected = capability_rejected
        self.request_id = request_id
        self.cause_type = cause_type

    @property
    def is_context_overflow(self) -> bool:
        return self.code == self.CONTEXT_WINDOW_EXCEEDED


def connection_error(error: BaseException) -> ProviderChatCompletionError:
    """Keep the transport failure type without exposing URLs or credentials."""
    cause = (
        error.reason
        if isinstance(error, URLError) and isinstance(error.reason, BaseException)
        else error
    )
    timed_out = isinstance(cause, (TimeoutError, httpx.TimeoutException))
    cause_type = type(cause).__name__
    return ProviderChatCompletionError(
        f"{'连接超时' if timed_out else '模型服务连接失败'}（{cause_type}）",
        code="MODEL_TIMEOUT" if timed_out else "MODEL_CONNECTION_FAILED",
        cause_type=cause_type,
    )


def model_list_error(error: ProviderChatCompletionError) -> ProviderModelListError:
    converted = ProviderModelListError(
        str(error), code=error.code or "MODEL_ERROR",
        upstream_status=error.upstream_status, request_id=error.request_id,
        cause_type=error.cause_type,
    )
    for name in ("retry_attempts", "retry_max_attempts"):
        value = getattr(error, name, None)
        if value is not None:
            setattr(converted, name, value)
    return converted


def request_failure_message(error):
    """Expose safe failure facts when a probe exhausts its request allowance."""
    message = str(error)
    attempts = getattr(error, "retry_attempts", None)
    if attempts is None:
        return message
    facts = [f"已尝试 {attempts} 次"]
    if getattr(error, "code", None):
        facts.append(error.code)
    if getattr(error, "upstream_status", None) is not None:
        facts.append(f"HTTP {error.upstream_status}")
    return message + "（" + "，".join(facts) + "）"


def _request_id(headers: Any) -> str | None:
    if headers is None:
        return None
    value = headers.get("x-request-id") or headers.get("x-dashscope-request-id")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:128] if re.fullmatch(r"[A-Za-z0-9_.:/-]+", value) else None


_CONTEXT_OVERFLOW_MESSAGES = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:context length|context window)(?: limit)? (?:has been |is )?exceeded\b",
        r"\b(?:input|prompt|message|messages|total message token) (?:length |token count )?"
        r"exceeds? (?:the )?(?:model(?:'s)? )?(?:maximum |max )?"
        r"(?:context (?:length|window)|(?:input )?(?:length |token )?limit)\b",
        r"^\s*(?:the )?(?:input|prompt) is too long\b",
        r"\bmaximum context length is [\d,]+ tokens[\s\S]{0,120}?"
        r"(?:however,? you requested|but you requested|but your messages resulted in) [\d,]+ tokens\b",
    )
)


def _decode_error_body(body: bytes) -> Any:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _completion_error_details(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("error")
    if isinstance(nested, dict):
        return nested
    if isinstance(nested, str):
        return {**payload, "message": nested}
    return payload


def _can_classify_context_error(details: dict[str, Any]) -> bool:
    for value in (details.get("code"), details.get("type")):
        if isinstance(value, int) and value not in (400, 413, 422, 500, 502):
            return False
        if isinstance(value, str) and value.lower() in {
            "401",
            "403",
            "408",
            "429",
            "504",
            "authentication_error",
            "invalid_api_key",
            "invalidapikey",
            "permission_error",
            "permission_denied",
            "access_denied",
            "timeout",
            "timeout_error",
            "request_timeout",
            "rate_limit_exceeded",
        }:
            return False
    return True


def _completion_error_message(
    status: int | None, details: dict[str, Any], headers: Any
) -> str:
    """Return safe diagnostics without exposing the upstream message or prompt."""

    if status == 401:
        return "模型服务认证失败"
    request_id = _request_id(headers)
    upstream_code = ""
    candidate = details.get("code")
    if (
        isinstance(candidate, str)
        and candidate.replace("_", "").replace("-", "").isalnum()
    ):
        upstream_code = candidate[:80]
    diagnostics = []
    if upstream_code:
        diagnostics.append(f"上游代码 {upstream_code}")
    if request_id:
        diagnostics.append(f"请求 ID {request_id[:128]}")
    suffix = f"（{'；'.join(diagnostics)}）" if diagnostics else ""
    prefix = "模型服务网关拒绝请求" if status == 403 else "模型服务调用失败"
    http_status = f"，HTTP {status}" if status is not None else ""
    return f"{prefix}{http_status}{suffix}"


def _http_error_code(status: int | None) -> str:
    if status in {401, 403}:
        return "PROVIDER_AUTH_FAILED"
    if status in {408, 504}:
        return "MODEL_TIMEOUT"
    return "MODEL_ERROR"


def is_context_overflow(details: dict[str, Any]) -> bool:
    if not _can_classify_context_error(details):
        return False
    codes = (details.get("code"), details.get("type"))
    if any(
        isinstance(code, str)
        and code.lower() in {"context_length_exceeded", "context_window_exceeded"}
        for code in codes
    ):
        return True
    message = details.get("message")
    if not isinstance(message, str):
        return False
    # Match affirmative API rejections, never a finish_reason or assistant text.
    return any(pattern.search(message) for pattern in _CONTEXT_OVERFLOW_MESSAGES)


class ProviderErrorParser:
    def __init__(self, classify_context_error):
        self.classify_context_error = classify_context_error

    def completion_error(
        self, status: int | None, payload: Any, headers: Any = None
    ) -> ProviderChatCompletionError:
        details = _completion_error_details(payload)
        # Transport/authentication failures must not acquire a context category
        # from incidental text in an upstream response.
        can_classify = status in (None, 400, 413, 422, 500, 502)
        if can_classify and self.classify_context_error(details):
            return ProviderChatCompletionError(
                "模型请求超出上下文窗口限制",
                code=ProviderChatCompletionError.CONTEXT_WINDOW_EXCEEDED,
                upstream_status=status,
                request_id=_request_id(headers),
            )
        return ProviderChatCompletionError(
            _completion_error_message(status, details, headers),
            code=_http_error_code(status),
            upstream_status=status,
            request_id=_request_id(headers),
            capability_rejected=status in {400, 422}
            and any(
                marker in str(details.get("message") or "").lower()
                for marker in (
                    "not supported",
                    "does not support",
                    "unsupported feature",
                    "unsupported parameter",
                )
            ),
        )

    def raise_payload_error(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        if payload.get("error") is not None or (
            payload.get("code") is not None and isinstance(payload.get("message"), str)
        ):
            raise self.completion_error(None, payload)

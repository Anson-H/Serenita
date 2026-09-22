"""One request owner for model retries, cancellation and safe diagnostics."""
from contextlib import contextmanager
from contextvars import ContextVar
import logging
from threading import Event
import time
from urllib.error import URLError
from uuid import uuid4

import httpx

from backend.app.core.cancellation import OperationCancelledError
from backend.app.core.time import local_now_iso


MAX_MODEL_ATTEMPTS = 10
MODEL_RETRY_DELAY_SECONDS = 5
_active_request = ContextVar("model_retry_owner", default=False)
_attempt = ContextVar("model_retry_attempt", default=1)
logger = logging.getLogger("serenita.model_requests")


def configure_model_request_logging():
    """Keep standalone/title diagnostics in the backend runtime log."""
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(name)s %(message)s"))
        logger.addHandler(handler)


@contextmanager
def retry_scope():
    """An execution recorder or stage owns retries of the enclosed request."""
    token = _active_request.set(True)
    try:
        yield
    finally:
        _active_request.reset(token)


def current_retry_attempt():
    return _attempt.get()


@contextmanager
def request_attempt_scope(attempt):
    """Expose a durable owner's actual attempt to transports and statistics."""
    token = _attempt.set(attempt)
    try:
        yield
    finally:
        _attempt.reset(token)


def retry_scope_active():
    return _active_request.get()


def transient_network_error(error):
    """Classify transport facts; local errors never inherit a retryable cause."""
    if isinstance(error, OperationCancelledError):
        return False
    code = getattr(error, "code", None)
    if code in {"MODEL_CONNECTION_FAILED", "MODEL_TIMEOUT", "MODEL_STREAM_INCOMPLETE",
                "MEMORY_MODEL_STREAM_INCOMPLETE"}:
        return True
    if code not in {None, "MODEL_ERROR"}:
        return False
    status = getattr(error, "upstream_status", None)
    if status is not None:
        return status in {408, 429} or 500 <= status < 600
    if isinstance(error, (httpx.TransportError, URLError, ConnectionError, TimeoutError)):
        return True
    # Inspect only known provider/domain envelopes, never arbitrary local errors.
    from backend.app.core.errors import SerenitaError
    from backend.app.providers.errors import ProviderChatCompletionError, ProviderModelListError
    if not isinstance(error, (SerenitaError, ProviderChatCompletionError, ProviderModelListError)):
        return False
    seen = {id(error)}
    current = error.__cause__ or error.__context__
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (httpx.TransportError, URLError, ConnectionError, TimeoutError)):
            return True
        status = getattr(current, "upstream_status", None)
        if status is not None:
            return status in {408, 429} or 500 <= status < 600
        current = current.__cause__ or current.__context__
    return False


def error_details(error):
    """Only safe structured diagnostics; never include raw transport messages."""
    from backend.app.core.errors import SerenitaError
    from backend.app.providers.errors import ProviderChatCompletionError, ProviderModelListError
    trusted = isinstance(error, (SerenitaError, ProviderChatCompletionError, ProviderModelListError))
    result = {"type": type(error).__name__,
              "message": str(error) if trusted else "模型请求发生连接或传输错误。"}
    for name in ("code", "upstream_status", "cause_type", "request_id", "retry_attempts", "retry_max_attempts"):
        value = getattr(error, name, None)
        if value is not None:
            result[name] = value
    cause = error.__cause__ or error.__context__
    if cause is not None:
        result.setdefault("cause_type", type(cause).__name__)
    return result


def wait_before_retry(*, check_running=None, cancellation_token=None):
    """Wait five seconds while allowing cancellation and live access checks."""
    wake = Event()
    unregister = cancellation_token.register(wake.set) if cancellation_token else lambda: None
    deadline = time.monotonic() + MODEL_RETRY_DELAY_SECONDS
    try:
        while True:
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
            if check_running is not None:
                check_running()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            wake.wait(min(remaining, 0.25))
    finally:
        unregister()


def run_model_request(invoke, *, check_running=None, cancellation_token=None, on_retry=None,
                      operation="model_request"):
    """Retry a complete model attempt; enclosed adapters send exactly once.

    on_retry(error, attempt) runs after a retryable failure and before waiting.
    Durable execution owners may enforce a smaller remaining shared budget in
    check_running/invoke (including repairs and requests before recovery).
    """
    sent = 0
    def check():
        try:
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
            if check_running is not None:
                check_running()
        except Exception as error:
            if not hasattr(error, "retry_attempts"):
                error.retry_attempts = sent
            error.retry_max_attempts = MAX_MODEL_ATTEMPTS
            raise

    check()
    if _active_request.get():
        return invoke()
    operation_id = str(uuid4())
    with retry_scope():
        for attempt in range(1, MAX_MODEL_ATTEMPTS + 1):
            check()
            attempt_token = _attempt.set(attempt)
            started_at = local_now_iso()
            started = time.monotonic()
            try:
                sent = attempt
                output = invoke()
                logger.info("model_request %s", {"operation": operation, "operation_id": operation_id,
                    "attempt": attempt, "max_attempts": MAX_MODEL_ATTEMPTS,
                    "started_at": started_at, "finished_at": local_now_iso(),
                    "elapsed_seconds": time.monotonic() - started, "status": "completed",
                    "usage": getattr(output, "usage", None)})
                return output
            except Exception as error:
                error.retry_attempts = getattr(error, "memory_request_attempt", attempt)
                error.retry_max_attempts = MAX_MODEL_ATTEMPTS
                logger.info("model_request %s", {"operation": operation, "operation_id": operation_id,
                    "attempt": attempt, "max_attempts": MAX_MODEL_ATTEMPTS,
                    "started_at": started_at, "finished_at": local_now_iso(),
                    "elapsed_seconds": time.monotonic() - started, "status": "failed",
                    "error": error_details(error)})
                check()
                if attempt == MAX_MODEL_ATTEMPTS or not transient_network_error(error):
                    raise
                if on_retry is not None:
                    on_retry(error, attempt)
                wait_before_retry(check_running=check, cancellation_token=cancellation_token)
            finally:
                _attempt.reset(attempt_token)

from backend.app.core.errors import SerenitaError
from backend.app.core.model_retry import error_details


def raise_provider_error(error) -> None:
    code = error.code or "MODEL_ERROR"
    kind = "timeout" if code == "MODEL_TIMEOUT" else "upstream_failure"
    converted = SerenitaError(kind, code, str(error) or "模型服务调用失败。",
                              details=error_details(error))
    for name in ("upstream_status", "cause_type", "request_id", "retry_attempts", "retry_max_attempts"):
        value = getattr(error, name, None)
        if value is not None:
            setattr(converted, name, value)
    raise converted from error

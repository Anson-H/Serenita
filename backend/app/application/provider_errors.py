from backend.app.core.errors import raise_error


def raise_provider_error(error) -> None:
    code = error.code or "MODEL_ERROR"
    kind = "timeout" if code == "MODEL_TIMEOUT" else "upstream_failure"
    raise_error(kind, code, str(error) or "模型服务调用失败。")

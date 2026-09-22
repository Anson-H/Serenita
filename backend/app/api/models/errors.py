from backend.app.core.errors import SerenitaError
from backend.app.providers.errors import ProviderChatCompletionError, ProviderModelListError

def safe_model_error(error):
    if isinstance(error, SerenitaError):
        return error.detail
    if isinstance(error, (ProviderChatCompletionError, ProviderModelListError)):
        # Upstream diagnostics can echo submitted content. Do not proxy that text.
        message = {"MODEL_TIMEOUT": "官方模型请求超时。", "MODEL_CONNECTION_FAILED": "无法连接官方模型的上游服务。"}.get(error.code)
        if not message:
            message = f"官方模型的上游请求失败，HTTP {error.upstream_status}。" if error.upstream_status else "官方模型的上游请求失败。"
        return {"code": error.code or "MODEL_ERROR", "message": message,
            "upstream_status": error.upstream_status}
    return {"code": "MODEL_ERROR", "message": "官方模型请求未完成。"}



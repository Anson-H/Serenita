from typing import Any

from backend.app.agent_runtime.model_types import ModelRequest
from backend.app.providers.base import ModelProvider
from backend.app.providers.errors import (
    ProviderChatCompletionError,
    ProviderModelListError,
)
from backend.app.providers.types import ProviderConnectionResult


DEEPSEEK_IMAGE_FILE_MIME_TYPES = (
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
)


class DeepSeekProvider(ModelProvider):
    provider_id = "deepseek"
    provider_name = "深度求索"
    default_api_url = "https://api.deepseek.com"
    default_official_url = "https://platform.deepseek.com/top_up"

    def native_attachment_mime_types(self) -> set[str]:
        return set(DEEPSEEK_IMAGE_FILE_MIME_TYPES)

    def test_connection(self, api_url: str, api_key: str) -> ProviderConnectionResult:
        try:
            models = self.list_models(api_url, api_key)
        except ProviderModelListError as exc:
            return self.failure(str(exc))
        if not models:
            return self.failure("模型服务未返回可用模型")

        connection_model = models[0]
        request = ModelRequest.build(
            system="",
            messages=[{"role": "user", "content": "仅回复 OK"}],
            model_config={"max_tokens": 32},
        )
        try:
            self.complete_chat(
                api_url,
                api_key,
                connection_model.remote_model_id,
                request,
                thinking_mode="off",
                timeout_seconds=self.timeout_seconds,
            )
        except ProviderChatCompletionError as exc:
            return self.failure(str(exc))
        return ProviderConnectionResult(
            provider_id=self.provider_id,
            reachable=True,
            message="连接测试成功",
        )

    def thinking_mode_payload(
        self,
        remote_model_id: str,
        thinking_mode: str,
    ) -> dict[str, Any]:
        if thinking_mode == "off":
            return {"thinking": {"type": "disabled"}}
        if thinking_mode == "default":
            return {}
        return {
            "thinking": {"type": "enabled"},
            "reasoning_effort": thinking_mode,
        }

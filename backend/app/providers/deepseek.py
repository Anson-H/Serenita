from typing import Any

from backend.app.providers.base import ModelProvider


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
    connection_test_path = "/user/balance"

    def native_attachment_mime_types(self) -> set[str]:
        return set(DEEPSEEK_IMAGE_FILE_MIME_TYPES)

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

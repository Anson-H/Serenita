from backend.app.providers.base import ModelProvider
from backend.app.model_capabilities import ModelCapabilityProfile


class DeepSeekProvider(ModelProvider):
    provider_id = "deepseek"
    display_name = "深度求索"
    default_base_url = "https://api.deepseek.com"
    default_official_url = "https://platform.deepseek.com/top_up"

    def normalize_capabilities(self, raw_model, remote_model_id: str) -> ModelCapabilityProfile:
        model_id = remote_model_id.lower()
        is_reasoning_model = (
            "reasoner" in model_id
            or "deepseek-r1" in model_id
            or _is_deepseek_v4_or_newer(model_id)
        )
        return ModelCapabilityProfile(
            supports_text=True,
            file_mime_types=[],
            thinking_modes=["default", "high", "xhigh"] if is_reasoning_model else ["default"],
            supports_tool_calling=True,
            supports_json_output=True,
            context_window_tokens=1_000_000 if _is_deepseek_v4_or_newer(model_id) else None,
        )


def _is_deepseek_v4_or_newer(model_id: str) -> bool:
    marker = "deepseek-v"
    if marker not in model_id:
        return False
    suffix = model_id.split(marker, 1)[1]
    version = suffix.split("-", 1)[0].split(".", 1)[0]
    return version.isdigit() and int(version) >= 4

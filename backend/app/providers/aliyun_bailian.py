import re

from backend.app.providers.base import ModelProvider
from backend.app.model_capabilities import ModelCapabilityProfile


ALIYUN_IMAGE_FILE_MIME_TYPES = [
    "image/bmp",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
    "image/heic",
]

ALIYUN_AUDIO_FILE_MIME_TYPES = [
    "audio/amr",
    "audio/wav",
    "audio/x-wav",
    "audio/3gpp",
    "audio/3gpp2",
    "audio/aac",
    "audio/mpeg",
    "audio/mp3",
]

ALIYUN_VIDEO_FILE_MIME_TYPES = [
    "video/mp4",
    "video/x-msvideo",
    "video/x-matroska",
    "video/mov",
    "video/quicktime",
    "video/x-flv",
    "video/x-ms-wmv",
]


class AliyunBailianProvider(ModelProvider):
    provider_id = "aliyun_bailian"
    display_name = "阿里云百炼"
    default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    default_official_url = "https://bailian.console.aliyun.com/?tab=model#/api-key"

    def native_attachment_mime_types(self) -> set[str]:
        return {
            *ALIYUN_IMAGE_FILE_MIME_TYPES,
            *ALIYUN_AUDIO_FILE_MIME_TYPES,
            *ALIYUN_VIDEO_FILE_MIME_TYPES,
        }

    def normalize_capabilities(self, raw_model, remote_model_id: str) -> ModelCapabilityProfile:
        model_id = remote_model_id.lower()
        file_mime_types = _attachment_mime_types(model_id)

        thinking_modes = ["default"]
        if _is_thinking_only_model(model_id) or _is_hybrid_thinking_model(model_id):
            thinking_modes = ["default", "high"]

        return ModelCapabilityProfile(
            supports_text=True,
            file_mime_types=file_mime_types,
            thinking_modes=thinking_modes,
            supports_tool_calling=_likely_supports_tool_calling(model_id),
            supports_json_output=True,
        )


def _is_thinking_only_model(model_id: str) -> bool:
    return any(marker in model_id for marker in ("-thinking", "qwq", "qvq", "deepseek-r1", "kimi-k2-thinking"))


def _attachment_mime_types(model_id: str) -> list[str]:
    if _is_omni_model(model_id):
        return [
            *ALIYUN_IMAGE_FILE_MIME_TYPES,
            *ALIYUN_AUDIO_FILE_MIME_TYPES,
            *ALIYUN_VIDEO_FILE_MIME_TYPES,
        ]
    if _is_vision_video_model(model_id):
        return [*ALIYUN_IMAGE_FILE_MIME_TYPES, *ALIYUN_VIDEO_FILE_MIME_TYPES]
    return []


def _is_omni_model(model_id: str) -> bool:
    return any(marker in model_id for marker in ("qwen3.5-omni", "qwen3-omni", "qwen-omni"))


def _is_vision_video_model(model_id: str) -> bool:
    if any(
        marker in model_id
        for marker in (
            "qwen-vl",
            "qwen2-vl",
            "qwen2.5-vl",
            "qwen3-vl",
            "qvq",
        )
    ):
        return True
    return bool(re.search(r"\bqwen3\.[56](?:-[\w.-]+)?\b", model_id))


def _is_hybrid_thinking_model(model_id: str) -> bool:
    if model_id.startswith(("qwen-plus", "qwen-flash", "qwen-turbo", "qwen3-max")):
        return True
    if model_id.startswith("qwen3") and not any(marker in model_id for marker in ("instruct", "embedding", "rerank")):
        return True
    return any(marker in model_id for marker in ("deepseek-v3", "glm-5", "glm-4.6", "glm-4.7"))


def _likely_supports_tool_calling(model_id: str) -> bool:
    if any(marker in model_id for marker in ("embedding", "rerank", "asr", "tts", "image")):
        return False
    return model_id.startswith(("qwen", "deepseek-v3", "glm", "kimi"))

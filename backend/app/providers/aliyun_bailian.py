import re
from typing import Any

from backend.app.providers.base import ModelProvider
from backend.app.providers.errors import _can_classify_context_error


ALIYUN_IMAGE_FILE_MIME_TYPES = (
    "image/bmp",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
    "image/heic",
)

ALIYUN_AUDIO_FILE_MIME_TYPES = (
    "audio/amr",
    "audio/wav",
    "audio/x-wav",
    "audio/3gpp",
    "audio/3gpp2",
    "audio/aac",
    "audio/mpeg",
    "audio/mp3",
)

ALIYUN_VIDEO_FILE_MIME_TYPES = (
    "video/mp4",
    "video/x-msvideo",
    "video/x-matroska",
    "video/mov",
    "video/quicktime",
    "video/x-flv",
    "video/x-ms-wmv",
)


class AliyunBailianProvider(ModelProvider):
    provider_id = "aliyun_bailian"
    provider_name = "阿里云百炼"
    default_api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    default_official_url = "https://bailian.console.aliyun.com/?tab=model#/api-key"

    def is_context_overflow(self, details: dict[str, Any]) -> bool:
        if not _can_classify_context_error(details):
            return False
        if super().is_context_overflow(details):
            return True
        code = details.get("code")
        if isinstance(code, str) and code in {
            "InputTooLong",
            "InvalidParameter.InputTooLong",
        }:
            return True
        message = details.get("message")
        # DashScope documents this specific input-range error as input overflow.
        # The similarly worded max_tokens range error is an output parameter error.
        return isinstance(message, str) and bool(
            re.search(
                r"\bRange of input length should be \[1,\s*\d+\]",
                message,
                re.IGNORECASE,
            )
        )

    def native_attachment_mime_types(self) -> set[str]:
        return {
            *ALIYUN_IMAGE_FILE_MIME_TYPES,
            *ALIYUN_AUDIO_FILE_MIME_TYPES,
            *ALIYUN_VIDEO_FILE_MIME_TYPES,
        }

    def thinking_mode_payload(
        self,
        remote_model_id: str,
        thinking_mode: str,
    ) -> dict[str, object]:
        if thinking_mode == "off":
            return {"enable_thinking": False}
        if thinking_mode == "default":
            return {}
        return {
            "enable_thinking": True,
            "reasoning_effort": thinking_mode,
        }

    def capability_probe_tool_choice(self, state: str) -> Any:
        if state == "thinking":
            return "auto"
        return super().capability_probe_tool_choice(state)

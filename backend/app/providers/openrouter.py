from typing import Any

from backend.app.providers.base import ModelProvider, _data_url
from backend.app.model_capabilities import (
    AUDIO_FILE_MIME_TYPES,
    DEFAULT_CAPABILITY_PROFILE,
    IMAGE_FILE_MIME_TYPES,
    ModelCapabilityProfile,
    NATIVE_DOCUMENT_FILE_MIME_TYPES,
    VIDEO_FILE_MIME_TYPES,
)

OPENROUTER_IMAGE_FILE_MIME_TYPES = [*IMAGE_FILE_MIME_TYPES, "image/gif"]


class OpenRouterProvider(ModelProvider):
    provider_id = "openrouter"
    display_name = "OpenRouter"
    default_base_url = "https://openrouter.ai/api/v1"
    default_official_url = "https://openrouter.ai/settings/credits"

    def native_attachment_mime_types(self) -> set[str]:
        return {
            *OPENROUTER_IMAGE_FILE_MIME_TYPES,
            *NATIVE_DOCUMENT_FILE_MIME_TYPES,
            *AUDIO_FILE_MIME_TYPES,
            *VIDEO_FILE_MIME_TYPES,
        }

    def _serialize_file_part(self, part: dict[str, Any]) -> dict[str, Any]:
        mime_type = str(part.get("mime_type", ""))
        return {
            "type": "file",
            "file": {
                "filename": str(part.get("name") or "attachment"),
                "file_data": _data_url(mime_type, str(part.get("data_base64", ""))),
            },
        }

    def normalize_capabilities(self, raw_model, remote_model_id: str) -> ModelCapabilityProfile:
        architecture = raw_model.get("architecture") if isinstance(raw_model.get("architecture"), dict) else {}
        input_modalities = _string_set(architecture.get("input_modalities"))
        output_modalities = _string_set(architecture.get("output_modalities"))
        supported_parameters = _string_set(raw_model.get("supported_parameters"))

        file_mime_types: list[str] = []
        if "image" in input_modalities:
            file_mime_types.extend(OPENROUTER_IMAGE_FILE_MIME_TYPES)
        if "file" in input_modalities:
            file_mime_types.extend(NATIVE_DOCUMENT_FILE_MIME_TYPES)
        if "audio" in input_modalities:
            file_mime_types.extend(AUDIO_FILE_MIME_TYPES)
        if "video" in input_modalities:
            file_mime_types.extend(VIDEO_FILE_MIME_TYPES)

        supports_text = "text" in output_modalities or not output_modalities
        supports_tool_calling = bool({"tools", "tool_choice"} & supported_parameters)
        supports_json_output = bool({"response_format", "structured_outputs"} & supported_parameters)
        thinking_modes = (
            ["default", "low", "medium", "high"]
            if {"reasoning", "include_reasoning"} & supported_parameters
            else DEFAULT_CAPABILITY_PROFILE.thinking_modes
        )

        top_provider = raw_model.get("top_provider") if isinstance(raw_model.get("top_provider"), dict) else {}
        return ModelCapabilityProfile(
            supports_text=supports_text,
            file_mime_types=file_mime_types,
            thinking_modes=thinking_modes,
            supports_tool_calling=supports_tool_calling,
            supports_json_output=supports_json_output,
            context_window_tokens=_positive_int(raw_model.get("context_length")),
            max_output_tokens=_positive_int(top_provider.get("max_completion_tokens")),
        )


def _string_set(value) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item.lower() for item in value if isinstance(item, str)}


def _positive_int(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None

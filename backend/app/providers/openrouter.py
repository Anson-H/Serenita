import json
from typing import Any

from backend.app.model_capabilities import (
    AUDIO_FILE_MIME_TYPES,
    DEFAULT_CAPABILITY_PROFILE,
    IMAGE_FILE_MIME_TYPES,
    ModelCapabilityProfile,
    NATIVE_DOCUMENT_FILE_MIME_TYPES,
    VIDEO_FILE_MIME_TYPES,
)
from backend.app.providers.base import ModelProvider
from backend.app.providers.message_codec import _data_url
from backend.app.providers.errors import (
    _can_classify_context_error,
    _completion_error_details,
)

OPENROUTER_IMAGE_FILE_MIME_TYPES = (*IMAGE_FILE_MIME_TYPES, "image/gif")


class OpenRouterProvider(ModelProvider):
    provider_id = "openrouter"
    provider_name = "OpenRouter"
    default_api_url = "https://openrouter.ai/api/v1"
    default_official_url = "https://openrouter.ai/settings/credits"

    def is_context_overflow(self, details: dict[str, Any]) -> bool:
        if not _can_classify_context_error(details):
            return False
        if super().is_context_overflow(details):
            return True
        metadata = details.get("metadata")
        raw = metadata.get("raw") if isinstance(metadata, dict) else None
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return False
        # Inspect only the forwarded API error, not arbitrary metadata text.
        return super().is_context_overflow(_completion_error_details(raw))

    def native_attachment_mime_types(self) -> set[str]:
        return {
            *OPENROUTER_IMAGE_FILE_MIME_TYPES,
            *NATIVE_DOCUMENT_FILE_MIME_TYPES,
            *AUDIO_FILE_MIME_TYPES,
            *VIDEO_FILE_MIME_TYPES,
        }

    def serialize_file_part(self, part: dict[str, Any]) -> dict[str, Any]:
        mime_type = str(part.get("mime_type", ""))
        return {
            "type": "file",
            "file": {
                "filename": str(part.get("name") or "attachment"),
                "file_data": _data_url(mime_type, str(part.get("data_base64", ""))),
            },
        }

    def normalize_capabilities(
        self,
        raw_model: dict[str, Any],
        remote_model_id: str,
    ) -> ModelCapabilityProfile:
        del remote_model_id
        architecture = (
            raw_model.get("architecture")
            if isinstance(raw_model.get("architecture"), dict)
            else {}
        )
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
        reasoning = (
            raw_model.get("reasoning")
            if isinstance(raw_model.get("reasoning"), dict)
            else {}
        )
        supported_efforts = (
            [
                effort
                for effort in reasoning.get("supported_efforts", [])
                if effort in {"minimal", "low", "medium", "high", "xhigh", "max"}
            ]
            if isinstance(reasoning.get("supported_efforts"), list)
            else []
        )
        supports_reasoning = bool(reasoning) or bool(
            {"reasoning", "include_reasoning"} & supported_parameters
        )
        mandatory_reasoning = bool(reasoning.get("mandatory"))
        thinking_modes = DEFAULT_CAPABILITY_PROFILE.thinking_modes
        if supports_reasoning:
            thinking_modes = [
                "default",
                *([] if mandatory_reasoning else ["off"]),
                *(supported_efforts or ["low", "medium", "high"]),
            ]

        top_provider = (
            raw_model.get("top_provider")
            if isinstance(raw_model.get("top_provider"), dict)
            else {}
        )
        return ModelCapabilityProfile(
            supports_text=supports_text,
            file_mime_types=file_mime_types,
            thinking_modes=thinking_modes,
            supports_tool_calling=supports_tool_calling,
            default_thinking_state=(
                "thinking"
                if bool(reasoning.get("default_enabled")) or mandatory_reasoning
                else "non_thinking"
            ),
            context_window_tokens=_positive_int(raw_model.get("context_length")),
            max_output_tokens=_positive_int(top_provider.get("max_completion_tokens")),
        )

    def capability_declarations(
        self,
        raw_model: dict[str, Any],
        remote_model_id: str,
    ) -> dict[str, bool]:
        declarations = super().capability_declarations(raw_model, remote_model_id)
        architecture = (
            raw_model.get("architecture")
            if isinstance(raw_model.get("architecture"), dict)
            else {}
        )
        input_modalities = _string_set(architecture.get("input_modalities"))
        if input_modalities:
            declarations.update(
                {
                    "image_input": "image" in input_modalities,
                    "pdf_input": "file" in input_modalities,
                    "audio_input": "audio" in input_modalities,
                    "video_input": "video" in input_modalities,
                }
            )
        output_modalities = _string_set(architecture.get("output_modalities"))
        if output_modalities:
            declarations["text"] = "text" in output_modalities
        supported_parameters = _string_set(raw_model.get("supported_parameters"))
        if supported_parameters:
            declarations["tool_calling"] = bool(
                {"tools", "tool_choice"} & supported_parameters
            )
        reasoning = (
            raw_model.get("reasoning")
            if isinstance(raw_model.get("reasoning"), dict)
            else {}
        )
        if "reasoning" in raw_model or isinstance(
            raw_model.get("supported_parameters"),
            list,
        ):
            declarations["thinking"] = bool(reasoning) or bool(
                {"reasoning", "include_reasoning"} & supported_parameters
            )
        return declarations

    def thinking_mode_payload(
        self,
        remote_model_id: str,
        thinking_mode: str,
    ) -> dict[str, Any]:
        if thinking_mode == "off":
            return {"reasoning": {"effort": "none"}}
        if not thinking_mode or thinking_mode == "default":
            return {}
        return {"reasoning": {"effort": thinking_mode}}


def _string_set(value) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item.lower() for item in value if isinstance(item, str)}


def _positive_int(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None

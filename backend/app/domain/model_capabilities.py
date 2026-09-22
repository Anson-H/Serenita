"""生成模型与向量模型的能力结构、输入格式和默认用途判断。"""

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool


IMAGE_FILE_MIME_TYPES = [
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/webp",
]

AUDIO_FILE_MIME_TYPES = [
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/aiff",
    "audio/x-aiff",
    "audio/aac",
    "audio/ogg",
    "audio/flac",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
]

VIDEO_FILE_MIME_TYPES = [
    "video/mp4",
    "video/mpeg",
    "video/mov",
    "video/quicktime",
    "video/webm",
]

NATIVE_DOCUMENT_FILE_MIME_TYPES = [
    "application/pdf",
]

LEGACY_UPLOAD_FILE_MIME_TYPES = [
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword",
    "application/vnd.ms-excel",
]

DOCUMENT_FILE_MIME_TYPES = [
    *NATIVE_DOCUMENT_FILE_MIME_TYPES,
    *LEGACY_UPLOAD_FILE_MIME_TYPES,
]


DEFAULT_CONTEXT_WINDOW_TOKENS = 131_072


ProbeStatus = Literal["supported", "unsupported", "unverified", "not_applicable"]
ModelType = Literal["generation", "embedding", "unknown"]


class EmbeddingCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supports_text: StrictBool = False
    file_mime_types: list[str] = Field(default_factory=list)
    independent: ProbeStatus = "unverified"
    fusion: ProbeStatus = "unverified"
    dimensions: dict[str, ProbeStatus] = Field(default_factory=dict)
    protocol: Literal["compatible", "aliyun_multimodal"] | None = None


@dataclass(frozen=True)
class ModelCapabilityProfile:
    supports_text: bool = True
    file_mime_types: list[str] = field(default_factory=list)
    thinking_modes: list[str] = field(default_factory=lambda: ["default"])
    supports_tool_calling: bool = False
    default_thinking_state: str = "non_thinking"
    context_window_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None


@dataclass(frozen=True)
class ModelModeCapabilityProfile:
    availability: str = "unverified"
    supports_text: bool = False
    file_mime_types: list[str] = field(default_factory=list)
    supports_tool_calling: bool = False


@dataclass(frozen=True)
class ModelCapabilityProfiles:
    default_state: str = "non_thinking"
    non_thinking: ModelModeCapabilityProfile = field(
        default_factory=ModelModeCapabilityProfile
    )
    thinking: ModelModeCapabilityProfile = field(
        default_factory=lambda: ModelModeCapabilityProfile(availability="unavailable")
    )


DEFAULT_CAPABILITY_PROFILE = ModelCapabilityProfile()

MODEL_DEFAULT_PURPOSES = ("chat", "title", "vision_parse", "compact", "memory_generation", "text_embedding", "multimodal_embedding")
MODEL_DEFAULT_COLUMN_BY_PURPOSE = {
    "chat": "chat_model_id",
    "title": "title_model_id",
    "vision_parse": "vision_parse_model_id",
    "compact": "compact_model_id",
    "memory_generation": "memory_generation_model_id",
    "text_embedding": "text_embedding_model_id",
    "multimodal_embedding": "multimodal_embedding_model_id",
}


def capability_response(
    profile: ModelCapabilityProfile,
    profiles: ModelCapabilityProfiles | None = None,
) -> dict[str, Any]:
    resolved_profiles = profiles or profiles_from_profile(profile)
    return {
        "supports_text": profile.supports_text,
        "file_mime_types": profile.file_mime_types,
        "thinking_modes": profile.thinking_modes,
        "supports_tool_calling": profile.supports_tool_calling,
        "capability_profiles": capability_profiles_response(resolved_profiles),
        "context_window_tokens": profile.context_window_tokens,
        "max_output_tokens": profile.max_output_tokens,
    }


def profiles_from_profile(profile: ModelCapabilityProfile) -> ModelCapabilityProfiles:
    default_state = _thinking_state(profile.default_thinking_state)
    has_non_thinking = (
        "off" in profile.thinking_modes or default_state == "non_thinking"
    )
    has_thinking = default_state == "thinking" or any(
        mode not in {"default", "off"} for mode in profile.thinking_modes
    )

    def mode_profile(available: bool) -> ModelModeCapabilityProfile:
        if not available:
            return ModelModeCapabilityProfile(availability="unavailable")
        return ModelModeCapabilityProfile(
            availability="available",
            supports_text=profile.supports_text,
            file_mime_types=list(profile.file_mime_types),
            supports_tool_calling=profile.supports_tool_calling,
        )

    return ModelCapabilityProfiles(
        default_state=default_state,
        non_thinking=mode_profile(has_non_thinking),
        thinking=mode_profile(has_thinking),
    )


def aggregate_capability_profile(
    profiles: ModelCapabilityProfiles,
    *,
    thinking_modes: list[str],
    context_window_tokens: Optional[int],
    max_output_tokens: Optional[int],
) -> ModelCapabilityProfile:
    applicable = [
        profile
        for profile in (profiles.non_thinking, profiles.thinking)
        if profile.availability != "unavailable"
    ]
    return ModelCapabilityProfile(
        supports_text=any(profile.supports_text for profile in applicable),
        file_mime_types=list(
            dict.fromkeys(
                mime_type
                for profile in applicable
                for mime_type in profile.file_mime_types
            )
        ),
        thinking_modes=list(thinking_modes) or ["default"],
        supports_tool_calling=any(
            profile.supports_tool_calling for profile in applicable
        ),
        default_thinking_state=profiles.default_state,
        context_window_tokens=context_window_tokens,
        max_output_tokens=max_output_tokens,
    )


def capability_profiles_response(
    profiles: ModelCapabilityProfiles,
) -> dict[str, Any]:
    def mode_value(profile: ModelModeCapabilityProfile) -> dict[str, Any]:
        return {
            "availability": profile.availability,
            "supports_text": profile.supports_text,
            "file_mime_types": profile.file_mime_types,
            "supports_tool_calling": profile.supports_tool_calling,
        }

    return {
        "default_state": profiles.default_state,
        "non_thinking": mode_value(profiles.non_thinking),
        "thinking": mode_value(profiles.thinking),
    }


def capability_profiles_from_mapping(
    payload: Any,
    fallback: ModelCapabilityProfiles | None = None,
) -> ModelCapabilityProfiles:
    base = fallback or profiles_from_profile(DEFAULT_CAPABILITY_PROFILE)
    if not isinstance(payload, dict):
        return base

    def mode_value(
        key: str,
        current: ModelModeCapabilityProfile,
    ) -> ModelModeCapabilityProfile:
        value = payload.get(key)
        if not isinstance(value, dict):
            return current
        availability = str(value.get("availability") or current.availability)
        if availability not in {"available", "unavailable", "unverified"}:
            availability = current.availability
        if availability == "unavailable":
            return ModelModeCapabilityProfile(availability="unavailable")
        return ModelModeCapabilityProfile(
            availability=availability,
            supports_text=_bool_value(
                value, "supports_text", fallback=current.supports_text
            ),
            file_mime_types=normalize_capability_strings(
                value.get("file_mime_types"), current.file_mime_types
            ),
            supports_tool_calling=_bool_value(
                value,
                "supports_tool_calling",
                fallback=current.supports_tool_calling,
            ),
        )

    return ModelCapabilityProfiles(
        default_state=_thinking_state(
            str(payload.get("default_state") or base.default_state)
        ),
        non_thinking=mode_value("non_thinking", base.non_thinking),
        thinking=mode_value("thinking", base.thinking),
    )


def profile_for_thinking_state(
    profiles: ModelCapabilityProfiles,
    state: str,
) -> ModelModeCapabilityProfile:
    return profiles.thinking if state == "thinking" else profiles.non_thinking




def normalize_capability_strings(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _bool_value(payload: dict[str, Any], *keys: str, fallback: bool) -> bool:
    for key in keys:
        if key in payload and isinstance(payload[key], bool):
            return payload[key]
    return fallback


def normalize_optional_integer(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    return None




def _thinking_state(value: str) -> str:
    return value if value in {"thinking", "non_thinking", "unknown"} else "unknown"


def supported_embedding_modalities(capabilities: dict[str, Any]) -> set[str]:
    """将向量模型支持的文本与文件格式归为可用于默认用途的模态。"""
    modalities = {"text"} if capabilities.get("supports_text") is True else set()
    for mime in capabilities.get("file_mime_types", []):
        prefix = mime.split("/", 1)[0]
        modalities.add(prefix if prefix in {"image", "audio", "video"} else "document")
    return modalities


def eligible_for_default(model: dict[str, Any], purpose: str) -> bool:
    """判断模型类型及已确认能力是否满足所选默认用途。"""
    if model.get("service_status", "available") != "available":
        return False
    if purpose in {"chat", "title", "vision_parse", "compact", "memory_generation"}:
        if model["model_type"] != "generation" or not model["supports_text"]:
            return False
        if purpose == "vision_parse":
            return any(mime.startswith("image/") for mime in model["file_mime_types"])
        return True
    if model["model_type"] != "embedding":
        return False
    modalities = supported_embedding_modalities(model["embedding_capabilities"] or {})
    if purpose == "text_embedding":
        return "text" in modalities
    return purpose == "multimodal_embedding" and len(modalities) >= 2


def minimum_thinking_mode(model: dict[str, Any]) -> str:
    """Prefer disabled thinking, then the lowest supported effort for this model."""
    modes = model.get("thinking_modes") or ["default"]
    if "off" in modes:
        return "off"
    profiles = model.get("capability_profiles") or {}
    if "default" in modes and profiles.get("default_state") == "non_thinking":
        return "default"
    for mode in ("minimal", "low", "medium", "high", "xhigh", "max"):
        if mode in modes:
            return mode
    return "default"

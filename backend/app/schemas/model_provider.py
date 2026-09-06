from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict


class ModelProviderSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    api_url: Optional[str] = None
    official_url: Optional[str] = None
    api_key: Optional[str] = None


class ModelProviderPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_url: Optional[str] = None
    official_url: Optional[str] = None
    api_key: Optional[str] = None


class ModelProviderTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_url: Optional[str] = None
    api_key: Optional[str] = None


class ModelModeCapabilityProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    availability: Literal["available", "unavailable", "unverified"]
    supports_text: bool
    file_mime_types: list[str]
    supports_tool_calling: bool


class ModelCapabilityProfilesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_state: Literal["thinking", "non_thinking", "unknown"]
    non_thinking: ModelModeCapabilityProfileRequest
    thinking: ModelModeCapabilityProfileRequest


class AddModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    remote_model_id: str
    thinking_modes: Optional[list[str]] = None
    capability_profiles: Optional[ModelCapabilityProfilesRequest] = None
    context_window_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None


class ModelDefaultsPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat: Optional[str] = None
    title: Optional[str] = None
    vision_parse: Optional[str] = None
    compact: Optional[str] = None


class ModelPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: Optional[str] = None
    thinking_modes: Optional[list[str]] = None
    capability_profiles: Optional[ModelCapabilityProfilesRequest] = None
    context_window_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None

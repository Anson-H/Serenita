from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from backend.app.domain.model_capabilities import EmbeddingCapabilities, ModelType


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


class ModelDefaultsPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat: Optional[str] = None
    title: Optional[str] = None
    vision_parse: Optional[str] = None
    compact: Optional[str] = None
    text_embedding: Optional[str] = None
    multimodal_embedding: Optional[str] = None


class ModelPatchRequest(BaseModel):
    model_type: ModelType | None = None
    embedding_capabilities: EmbeddingCapabilities | None = None
    embedding_dimensions: StrictInt | None = Field(default=None, gt=0)
    max_input_tokens: StrictInt | None = Field(default=None, gt=0)
    max_batch_size: StrictInt | None = Field(default=None, gt=0)
    model_config = ConfigDict(extra="forbid")

    model_name: Optional[str] = None
    thinking_modes: Optional[list[str]] = None
    capability_profiles: Optional[ModelCapabilityProfilesRequest] = None
    context_window_tokens: StrictInt | None = Field(default=None, gt=0)
    max_output_tokens: StrictInt | None = Field(default=None, gt=0)


class ModelProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    probe_id: str | None = Field(default=None, min_length=1, max_length=100)

from dataclasses import dataclass, field
from typing import Optional

from backend.app.domain.model_capabilities import (
    ModelCapabilityProfiles,
    ModelCapabilityProfile,
)


@dataclass(frozen=True)
class ProviderModel:
    remote_model_id: str
    model_name: str
    created_at: Optional[int] = None
    model_type: str = "unknown"
    embedding_dimensions: list[int] = field(default_factory=list)
    supports_text: bool = True
    file_mime_types: list[str] = field(default_factory=list)
    thinking_modes: list[str] = field(default_factory=lambda: ["default"])
    supports_tool_calling: bool = False
    default_thinking_state: str = "non_thinking"
    context_window_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    capability_declarations: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_profile(
        cls,
        *,
        remote_model_id: str,
        model_name: str,
        profile: ModelCapabilityProfile,
        capability_declarations: Optional[dict[str, bool]] = None,
        created_at: Optional[int] = None,
        model_type: str = "unknown",
        embedding_dimensions: list[int] | None = None,
    ) -> "ProviderModel":
        return cls(
            remote_model_id=remote_model_id,
            model_name=model_name,
            created_at=created_at,
            model_type=model_type,
            embedding_dimensions=embedding_dimensions or [],
            supports_text=profile.supports_text,
            file_mime_types=list(profile.file_mime_types),
            thinking_modes=list(profile.thinking_modes),
            supports_tool_calling=profile.supports_tool_calling,
            default_thinking_state=profile.default_thinking_state,
            context_window_tokens=profile.context_window_tokens,
            max_output_tokens=profile.max_output_tokens,
            capability_declarations=dict(capability_declarations or {}),
        )

    def capability_profile(self) -> ModelCapabilityProfile:
        return ModelCapabilityProfile(
            supports_text=self.supports_text,
            file_mime_types=list(self.file_mime_types),
            thinking_modes=list(self.thinking_modes),
            supports_tool_calling=self.supports_tool_calling,
            default_thinking_state=self.default_thinking_state,
            context_window_tokens=self.context_window_tokens,
            max_output_tokens=self.max_output_tokens,
        )


@dataclass(frozen=True)
class ProviderConnectionResult:
    provider_id: str
    reachable: bool
    message: str
    code: str | None = None


@dataclass(frozen=True)
class ModelCapabilityProbeResult:
    profiles: ModelCapabilityProfiles
    checks: dict[str, dict[str, str]]
    errors: dict[str, dict[str, str]] = field(default_factory=dict)

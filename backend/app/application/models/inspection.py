"""Shared model type recognition and capability inspection for all upstreams."""
from dataclasses import dataclass
from typing import Any

from backend.app.domain.model_capabilities import (
    DEFAULT_CAPABILITY_PROFILE, ModelCapabilityProfile, ModelCapabilityProfiles,
    ModelModeCapabilityProfile, aggregate_capability_profile,
    capability_profiles_from_mapping, capability_response, profiles_from_profile,
)
from backend.app.providers.capability_probe import THINKING_MODE_PROBE_ORDER
from backend.app.providers.model_type_probe import detect_model_type, probe_embeddings
from backend.app.providers.types import ProviderModel

def remote_model_payload(model: ProviderModel) -> dict[str, Any]:
    return {
        "remote_model_id": model.remote_model_id,
        "model_name": model.model_name,
        "created_at": model.created_at,
        "model_type": model.model_type,
        "embedding_capabilities": None, "embedding_dimensions": None, "max_input_tokens": None, "max_batch_size": None,
        **capability_response(model.capability_profile()),
    }


def _probe_metadata_baseline(
    *,
    remote_model: ProviderModel | None,
    metadata_result: dict,
    current_profile: ModelCapabilityProfile,
    current_profiles: ModelCapabilityProfiles,
) -> tuple[ModelCapabilityProfile, ModelCapabilityProfiles, dict[str, str], dict[str, bool]]:
    if remote_model is None:
        return current_profile, current_profiles, metadata_result, {}
    listed_profile = remote_model.capability_profile()
    declarations = dict(remote_model.capability_declarations)
    metadata_profile = ModelCapabilityProfile(
        supports_text=listed_profile.supports_text
        if "text" in declarations
        else current_profile.supports_text,
        file_mime_types=_merge_declared_file_mime_types(
            current_profile.file_mime_types,
            listed_profile.file_mime_types,
            declarations,
        ),
        thinking_modes=listed_profile.thinking_modes
        if "thinking" in declarations
        else current_profile.thinking_modes,
        supports_tool_calling=listed_profile.supports_tool_calling
        if "tool_calling" in declarations
        else current_profile.supports_tool_calling,
        default_thinking_state=listed_profile.default_thinking_state
        if "thinking" in declarations
        else current_profile.default_thinking_state,
        context_window_tokens=current_profile.context_window_tokens
        if current_profile.context_window_tokens is not None
        else listed_profile.context_window_tokens,
        max_output_tokens=current_profile.max_output_tokens
        if current_profile.max_output_tokens is not None
        else listed_profile.max_output_tokens,
    )
    def merge_state(current):
        return ModelModeCapabilityProfile(
            availability=current.availability,
            supports_text=listed_profile.supports_text if "text" in declarations else current.supports_text,
            file_mime_types=_merge_declared_file_mime_types(
                current.file_mime_types, listed_profile.file_mime_types, declarations,
            ),
            supports_tool_calling=listed_profile.supports_tool_calling
            if "tool_calling" in declarations else current.supports_tool_calling,
        )

    return (
        metadata_profile,
        ModelCapabilityProfiles(
            default_state=metadata_profile.default_thinking_state if "thinking" in declarations else current_profiles.default_state,
            non_thinking=merge_state(current_profiles.non_thinking),
            thinking=merge_state(current_profiles.thinking),
        ),
        {"status": "refreshed", "message": "已刷新供应商元数据。"},
        declarations,
    )


def _merge_declared_file_mime_types(
    current: list[str], listed: list[str], declarations: dict[str, bool]
) -> list[str]:
    merged: list[str] = []
    for capability, predicate in (
        ("image_input", lambda mime_type: mime_type.startswith("image/")),
        ("pdf_input", lambda mime_type: mime_type == "application/pdf"),
        ("audio_input", lambda mime_type: mime_type.startswith("audio/")),
        ("video_input", lambda mime_type: mime_type.startswith("video/")),
    ):
        source = listed if capability in declarations else current
        merged.extend((mime_type for mime_type in source if predicate(mime_type)))
    return list(dict.fromkeys(merged))


def _profile_with_probed_thinking_modes(
    profile: ModelCapabilityProfile,
    profiles: ModelCapabilityProfiles,
    thinking_mode_checks: dict[str, str],
) -> ModelCapabilityProfile:
    current_modes = set(profile.thinking_modes)
    thinking_modes = [
        "default",
        *[
            mode
            for mode in THINKING_MODE_PROBE_ORDER
            if thinking_mode_checks.get(mode) == "supported"
            or (
                thinking_mode_checks.get(mode) == "unverified" and mode in current_modes
            )
        ],
    ]
    return ModelCapabilityProfile(
        supports_text=profile.supports_text,
        file_mime_types=list(profile.file_mime_types),
        thinking_modes=thinking_modes,
        supports_tool_calling=profile.supports_tool_calling,
        default_thinking_state=profiles.default_state,
        context_window_tokens=profile.context_window_tokens,
        max_output_tokens=profile.max_output_tokens,
    )



@dataclass(frozen=True)
class ModelInspection:
    model_type: str
    parameters: dict
    metadata: dict
    checks: dict
    errors: dict

    def definition(self, model_name):
        result = {
            "model_type": self.model_type, "model_name": model_name,
            "supports_text": False, "file_mime_types": [], "supports_tool_calling": False,
            "thinking_modes": None, "capability_profiles": None,
            "context_window_tokens": None, "max_output_tokens": None,
            "embedding_capabilities": None, "embedding_dimensions": None,
            "max_input_tokens": None, "max_batch_size": None,
        }
        if self.model_type == "generation":
            profile, profiles = self.parameters["profile"], self.parameters["profiles"]
            aggregate = aggregate_capability_profile(profiles, thinking_modes=profile.thinking_modes,
                context_window_tokens=profile.context_window_tokens, max_output_tokens=profile.max_output_tokens)
            result.update(capability_response(aggregate, profiles))
        elif self.model_type == "embedding":
            result.update(self.parameters)
        return result

    def report(self):
        return {"metadata": self.metadata, "checks": self.checks, "errors": self.errors}


def inspect_model(provider, model, *, api_url, api_key, cancellation_token):
    """Inspect one configured model while preserving explicit parameter values."""
    arguments = dict(api_url=api_url, api_key=api_key,
        remote_model_id=model["remote_model_id"], cancellation_token=cancellation_token)
    kind, type_checks, type_errors, successes, metadata, listed, conflict = detect_model_type(provider, **arguments)
    if kind == "unknown" and model["model_type"] != "unknown":
        kind = model["model_type"]
    checks = {"type": type_checks, "thinking_modes": {}, "aggregate": {}, "non_thinking": {}, "thinking": {}}
    errors = {"type": type_errors, "thinking_modes": {}, "non_thinking": {}, "thinking": {}}
    parameters = {}
    if kind == "generation":
        current_profile = DEFAULT_CAPABILITY_PROFILE
        current_profiles = profiles_from_profile(current_profile)
        if model["model_type"] == "generation" and model.get("capability_profiles"):
            current_profiles = capability_profiles_from_mapping(model["capability_profiles"])
            current_profile = aggregate_capability_profile(current_profiles,
                thinking_modes=model["thinking_modes"] or ["default"],
                context_window_tokens=model["context_window_tokens"], max_output_tokens=model["max_output_tokens"])
        probe_profile, probe_profiles, generation_metadata, declarations = _probe_metadata_baseline(
            remote_model=listed, metadata_result=metadata,
            current_profile=current_profile, current_profiles=current_profiles)
        result = provider.probe_capabilities(**arguments, current_profiles=probe_profiles,
            thinking_modes=probe_profile.thinking_modes, capability_declarations=declarations)
        parameters = {"profile": _profile_with_probed_thinking_modes(
            probe_profile, result.profiles, result.checks["thinking_modes"]), "profiles": result.profiles}
        checks.update(result.checks)
        errors.update(result.errors)
        if not conflict:
            metadata = generation_metadata
    elif kind == "embedding":
        caps, output_dimensions, embedding_checks, embedding_errors = probe_embeddings(
            provider, **arguments, successes=successes,
            dimensions=model.get("embedding_dimensions"), declared_dimensions=listed.embedding_dimensions if listed else ())
        checks["embedding"], errors["embedding"] = embedding_checks, embedding_errors
        max_batch_size = model.get("max_batch_size")
        if embedding_checks["batch"] == "unsupported":
            max_batch_size = 1
        elif embedding_checks["batch"] == "supported" and max_batch_size == 1:
            max_batch_size = None
        parameters = {"embedding_capabilities": caps,
            "embedding_dimensions": output_dimensions if output_dimensions is not None else model.get("embedding_dimensions"),
            "max_input_tokens": model.get("max_input_tokens"), "max_batch_size": max_batch_size}
    cancellation_token.raise_if_cancelled()
    return ModelInspection(kind, parameters, metadata, checks, errors)

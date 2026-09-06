"""Persisted model capability encoding and row decoding."""

import json
from typing import Any, Iterable
from backend.app.storage.sqlite import UnsupportedSchemaError
from backend.app.model_capabilities import (
    ModelCapabilityProfile,
    ModelCapabilityProfiles,
    profiles_from_profile,
    normalize_saved_context_window_tokens,
    normalize_optional_integer,
    normalize_capability_strings,
    aggregate_capability_profile,
    capability_profiles_response,
    capability_profiles_from_mapping,
    capability_response,
)


def capability_column_values(
    profile: ModelCapabilityProfile,
    profiles: ModelCapabilityProfiles | None = None,
) -> tuple[Any, ...]:
    resolved_profiles = profiles or profiles_from_profile(profile)
    return (
        _serialize_list(profile.thinking_modes),
        _serialize_capability_profiles(resolved_profiles),
        normalize_saved_context_window_tokens(profile.context_window_tokens),
        profile.max_output_tokens,
    )


def profile_from_row(row) -> ModelCapabilityProfile:
    profiles = capability_profiles_from_row(row)
    thinking_modes = _deserialize_list(row["thinking_modes"]) or ["default"]
    aggregate = aggregate_capability_profile(
        profiles,
        thinking_modes=thinking_modes,
        context_window_tokens=normalize_saved_context_window_tokens(
            row["context_window_tokens"]
        ),
        max_output_tokens=normalize_optional_integer(row["max_output_tokens"]),
    )
    return aggregate


def capability_profiles_from_row(row) -> ModelCapabilityProfiles:
    return _deserialize_capability_profiles(row["capability_profiles"])


def _serialize_list(values: Iterable[str]) -> str:
    return "\n".join(normalize_capability_strings(list(values), []))


def _deserialize_list(value: Any) -> list[str]:
    if not isinstance(value, str) or not value:
        return []
    return normalize_capability_strings(value.splitlines(), [])


def _serialize_capability_profiles(profiles: ModelCapabilityProfiles) -> str:
    return json.dumps(
        capability_profiles_response(profiles),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _deserialize_capability_profiles(value: Any) -> ModelCapabilityProfiles:
    if not isinstance(value, str) or not value:
        raise UnsupportedSchemaError(
            "UNSUPPORTED_SCHEMA: model capability profiles are missing."
        )
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise UnsupportedSchemaError(
            "UNSUPPORTED_SCHEMA: model capability profiles are invalid."
        ) from exc
    return capability_profiles_from_mapping(payload)


def model_response(row) -> dict[str, Any]:
    profiles = capability_profiles_from_row(row)
    profile = profile_from_row(row)
    return {
        "model_id": row["model_id"],
        "provider_id": row["provider_id"],
        "remote_model_id": row["remote_model_id"],
        "model_name": row["model_name"],
        **capability_response(profile, profiles),
    }

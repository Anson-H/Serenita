import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from backend.app.domain.model_capabilities import (
    ModelCapabilityProfiles,
    ModelModeCapabilityProfile,
    profile_for_thinking_state,
)
from backend.app.agent_runtime.model_types import (
    AssistantModelOutput,
    ModelRequest,
    ToolSchema,
)
from backend.app.core.cancellation import (
    CancellationToken,
)


from backend.app.providers.errors import ProviderChatCompletionError
from backend.app.providers.types import ModelCapabilityProbeResult

_CAPABILITY_PROBE_ASSET_ROOT = Path(__file__).with_name("probe_assets")


def _read_capability_probe_asset_base64(filename: str) -> str:
    return base64.b64encode(
        (_CAPABILITY_PROBE_ASSET_ROOT / filename).read_bytes()
    ).decode("ascii")


_CAPABILITY_PROBE_PNG_BASE64 = _read_capability_probe_asset_base64("image.png")


_CAPABILITY_PROBE_PDF_BASE64 = _read_capability_probe_asset_base64("document.pdf")


_CAPABILITY_PROBE_WAV_BASE64 = _read_capability_probe_asset_base64("audio.wav")


_CAPABILITY_PROBE_MP4_BASE64 = _read_capability_probe_asset_base64("video.mp4")


_PROBE_CAPABILITIES = (
    "text",
    "tool_calling",
    "image_input",
    "pdf_input",
    "audio_input",
    "video_input",
)


THINKING_MODE_PROBE_ORDER = (
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)


_THINKING_MODES = {"default", *THINKING_MODE_PROBE_ORDER}


@dataclass(frozen=True)
class _MediaCapabilityProbe:
    capability: str
    mime_type_prefix: str
    sample_mime_type: str
    part_type: str
    sample_base64: str
    prompt: str
    expected_answer: Optional[str] = None
    filename: Optional[str] = None


_MEDIA_CAPABILITY_PROBES = (
    _MediaCapabilityProbe(
        capability="image_input",
        mime_type_prefix="image/",
        sample_mime_type="image/png",
        part_type="image",
        sample_base64=_CAPABILITY_PROBE_PNG_BASE64,
        prompt="只用一个英文单词回答图片的主要颜色。",
        expected_answer="purple",
    ),
    _MediaCapabilityProbe(
        capability="pdf_input",
        mime_type_prefix="application/pdf",
        sample_mime_type="application/pdf",
        part_type="file",
        sample_base64=_CAPABILITY_PROBE_PDF_BASE64,
        prompt="只回复这个 PDF 中的大写英文。",
        expected_answer="pdf",
        filename="capability-probe.pdf",
    ),
    _MediaCapabilityProbe(
        capability="audio_input",
        mime_type_prefix="audio/",
        sample_mime_type="audio/wav",
        part_type="audio",
        sample_base64=_CAPABILITY_PROBE_WAV_BASE64,
        prompt="用一个词描述这段音频。",
    ),
    _MediaCapabilityProbe(
        capability="video_input",
        mime_type_prefix="video/",
        sample_mime_type="video/mp4",
        part_type="video",
        sample_base64=_CAPABILITY_PROBE_MP4_BASE64,
        prompt="用一个词描述这段视频。",
    ),
)


def _optional_probe_failure_status(error: ProviderChatCompletionError) -> str:
    return "unsupported" if error.capability_rejected else "unverified"


def _thinking_mode_probe_failure_status(error: ProviderChatCompletionError) -> str:
    return (
        "unsupported"
        if error.capability_rejected or error.upstream_status in {400, 422}
        else "unverified"
    )


def _fatal_thinking_mode_probe_failure(error: ProviderChatCompletionError) -> bool:
    return error.code == "PROVIDER_AUTH_FAILED" or error.upstream_status == 404


def _fatal_probe_failure(error: ProviderChatCompletionError) -> bool:
    return _fatal_thinking_mode_probe_failure(error) or error.code == "MODEL_TIMEOUT"


def _aggregate_probe_status(*statuses: str) -> str:
    applicable = [status for status in statuses if status != "not_applicable"]
    if not applicable:
        return "not_applicable"
    if "supported" in applicable:
        return "supported"
    if "unverified" in applicable:
        return "unverified"
    return "unsupported"


def _profiles_for_probed_thinking_modes(
    profiles: ModelCapabilityProfiles,
    thinking_modes: list[str],
) -> ModelCapabilityProfiles:
    explicit_thinking = any(mode not in {"default", "off"} for mode in thinking_modes)
    non_thinking = "off" in thinking_modes
    default_state = profiles.default_state
    if default_state == "thinking":
        explicit_thinking = True
    elif default_state == "non_thinking":
        non_thinking = True
    elif explicit_thinking and not non_thinking:
        default_state = "thinking"
    elif non_thinking and not explicit_thinking:
        default_state = "non_thinking"
    elif not explicit_thinking and not non_thinking:
        default_state = "non_thinking"
        non_thinking = True

    def resolved(
        profile: ModelModeCapabilityProfile,
        available: bool,
    ) -> ModelModeCapabilityProfile:
        if not available:
            return ModelModeCapabilityProfile(availability="unavailable")
        if profile.availability != "unavailable":
            return profile
        return ModelModeCapabilityProfile(
            availability="unverified",
            supports_text=profile.supports_text,
            file_mime_types=list(profile.file_mime_types),
            supports_tool_calling=profile.supports_tool_calling,
        )

    return ModelCapabilityProfiles(
        default_state=default_state,
        non_thinking=resolved(profiles.non_thinking, non_thinking),
        thinking=resolved(profiles.thinking, explicit_thinking),
    )


def _probe_thinking_mode(
    state: str,
    thinking_modes: list[str],
    default_state: str,
) -> str:
    if state == "non_thinking":
        return "off" if "off" in thinking_modes else "default"
    for mode in ("high", "medium", "low", "minimal", "xhigh", "max"):
        if mode in thinking_modes:
            return mode
    if default_state == "thinking" and "default" in thinking_modes:
        return "default"
    return "default"


class ProviderCapabilityProbe:
    def __init__(self, provider):
        self.provider = provider

    def probe_capabilities(
        self,
        *,
        api_url: str,
        api_key: str,
        remote_model_id: str,
        current_profiles: ModelCapabilityProfiles,
        thinking_modes: list[str],
        capability_declarations: Optional[dict[str, bool]] = None,
        cancellation_token: CancellationToken | None = None,
    ) -> ModelCapabilityProbeResult:
        """Probe thinking modes first, then capabilities for each available state."""

        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()
        declarations = dict(capability_declarations or {})
        (
            probed_thinking_modes,
            thinking_mode_checks,
            thinking_mode_errors,
        ) = self._probe_thinking_modes(
            api_url=api_url,
            api_key=api_key,
            remote_model_id=remote_model_id,
            current_thinking_modes=thinking_modes,
            cancellation_token=cancellation_token,
        )
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()
        if "thinking" not in declarations:
            current_profiles = ModelCapabilityProfiles(
                default_state="unknown",
                non_thinking=current_profiles.non_thinking,
                thinking=current_profiles.thinking,
            )
        current_profiles = _profiles_for_probed_thinking_modes(
            current_profiles,
            probed_thinking_modes,
        )
        if "thinking" not in declarations:
            declarations.pop("text", None)
        mode_checks: dict[str, dict[str, str]] = {}
        mode_errors: dict[str, dict[str, str]] = {}
        updated_profiles: dict[str, ModelModeCapabilityProfile] = {}

        mode_futures = {}
        with ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="model-capability-mode",
        ) as mode_executor:
            for state in ("non_thinking", "thinking"):
                current = profile_for_thinking_state(current_profiles, state)
                if current.availability == "unavailable":
                    mode_checks[state] = {
                        capability: "not_applicable"
                        for capability in _PROBE_CAPABILITIES
                    }
                    mode_errors[state] = {}
                    updated_profiles[state] = current
                    continue
                mode_futures[state] = mode_executor.submit(
                    self._probe_mode_capabilities,
                    api_url=api_url,
                    api_key=api_key,
                    remote_model_id=remote_model_id,
                    state=state,
                    thinking_mode=_probe_thinking_mode(
                        state,
                        probed_thinking_modes,
                        current_profiles.default_state,
                    ),
                    current=current,
                    capability_declarations=declarations,
                    cancellation_token=cancellation_token,
                )

            for state in ("non_thinking", "thinking"):
                if state not in mode_futures:
                    continue
                profile, checks, errors = mode_futures[state].result()
                if cancellation_token is not None:
                    cancellation_token.raise_if_cancelled()
                updated_profiles[state] = profile
                mode_checks[state] = checks
                mode_errors[state] = errors

        profiles = ModelCapabilityProfiles(
            default_state=current_profiles.default_state,
            non_thinking=updated_profiles["non_thinking"],
            thinking=updated_profiles["thinking"],
        )
        aggregate_checks = {
            capability: _aggregate_probe_status(
                mode_checks["non_thinking"][capability],
                mode_checks["thinking"][capability],
            )
            for capability in _PROBE_CAPABILITIES
        }
        return ModelCapabilityProbeResult(
            profiles=profiles,
            checks={
                "thinking_modes": thinking_mode_checks,
                "aggregate": aggregate_checks,
                "non_thinking": mode_checks["non_thinking"],
                "thinking": mode_checks["thinking"],
            },
            errors={
                "thinking_modes": thinking_mode_errors,
                **mode_errors,
            },
        )

    def _complete_capability_probe(
        self,
        *,
        api_url: str,
        api_key: str,
        remote_model_id: str,
        model_request: ModelRequest,
        thinking_mode: str,
        cancellation_token: CancellationToken | None,
    ) -> AssistantModelOutput:
        completion_arguments: dict[str, Any] = {
            "thinking_mode": thinking_mode,
            "timeout_seconds": self.provider.attachment_timeout_seconds,
        }
        completion_arguments["cancellation_token"] = cancellation_token
        return self.provider.complete_chat(
            api_url,
            api_key,
            remote_model_id,
            model_request,
            **completion_arguments,
        )

    def _probe_thinking_modes(
        self,
        *,
        api_url: str,
        api_key: str,
        remote_model_id: str,
        current_thinking_modes: list[str],
        cancellation_token: CancellationToken | None = None,
    ) -> tuple[list[str], dict[str, str], dict[str, str]]:
        """Probe every explicit effort concurrently before other capabilities."""

        probe_request = ModelRequest.build(
            system="",
            messages=[{"role": "user", "content": "仅回复 OK"}],
            model_config={"max_tokens": 32},
            transport_mode="thinking_mode_probe",
        )

        def complete(mode: str) -> AssistantModelOutput:
            return self._complete_capability_probe(
                api_url=api_url,
                api_key=api_key,
                remote_model_id=remote_model_id,
                model_request=probe_request,
                thinking_mode=mode,
                cancellation_token=cancellation_token,
            )

        outcomes: dict[str, AssistantModelOutput | ProviderChatCompletionError] = {}
        with ThreadPoolExecutor(
            max_workers=len(THINKING_MODE_PROBE_ORDER),
            thread_name_prefix="model-thinking-mode",
        ) as mode_executor:
            futures = {
                mode: mode_executor.submit(complete, mode)
                for mode in THINKING_MODE_PROBE_ORDER
            }
            for mode in THINKING_MODE_PROBE_ORDER:
                try:
                    outcomes[mode] = futures[mode].result()
                except ProviderChatCompletionError as exc:
                    outcomes[mode] = exc
                if cancellation_token is not None:
                    cancellation_token.raise_if_cancelled()

        checks: dict[str, str] = {}
        errors: dict[str, str] = {}
        current_modes = set(current_thinking_modes)
        resolved_modes = ["default"]
        for mode in THINKING_MODE_PROBE_ORDER:
            outcome = outcomes[mode]
            if isinstance(outcome, ProviderChatCompletionError):
                message = str(outcome)
                if _fatal_thinking_mode_probe_failure(outcome):
                    raise outcome
                status = _thinking_mode_probe_failure_status(outcome)
                checks[mode] = status
                errors[mode] = message
                if status == "unverified" and mode in current_modes:
                    resolved_modes.append(mode)
                continue

            observed_output = bool(outcome.content or outcome.tool_calls)
            checks[mode] = "supported" if observed_output else "unverified"
            if observed_output or mode in current_modes:
                resolved_modes.append(mode)
            if not observed_output:
                errors[mode] = "模型未返回可用文本。"

        return list(dict.fromkeys(resolved_modes)), checks, errors

    def _probe_mode_capabilities(
        self,
        *,
        api_url: str,
        api_key: str,
        remote_model_id: str,
        state: str,
        thinking_mode: str,
        current: ModelModeCapabilityProfile,
        capability_declarations: dict[str, bool],
        cancellation_token: CancellationToken | None = None,
    ) -> tuple[ModelModeCapabilityProfile, dict[str, str], dict[str, str]]:
        checks: dict[str, str] = {}
        errors: dict[str, str] = {}
        thinking_probe = state == "thinking"
        max_tokens = 1024 if thinking_probe else 32

        def complete(model_request: ModelRequest) -> AssistantModelOutput:
            return self._complete_capability_probe(
                api_url=api_url,
                api_key=api_key,
                remote_model_id=remote_model_id,
                model_request=model_request,
                thinking_mode=thinking_mode,
                cancellation_token=cancellation_token,
            )

        probe_requests: dict[str, ModelRequest] = {}
        if "text" not in capability_declarations:
            probe_requests["text"] = ModelRequest.build(
                system="",
                messages=[{"role": "user", "content": "仅回复 OK"}],
                model_config={"max_tokens": max_tokens},
            )
        probe_tool = ToolSchema(
            name="capability_probe",
            description="用于确认模型是否支持工具调用。",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )
        if "tool_calling" not in capability_declarations:
            probe_requests["tool_calling"] = ModelRequest.build(
                system="",
                messages=[
                    {
                        "role": "user",
                        "content": "必须调用 capability_probe 工具完成本次请求，不要直接回答。",
                    }
                ],
                tools=[probe_tool],
                tool_choice=self.provider.capability_probe_tool_choice(state),
                model_config={"max_tokens": max_tokens},
            )
        for probe in _MEDIA_CAPABILITY_PROBES:
            if probe.capability in capability_declarations:
                continue
            attachment_part = {
                "type": probe.part_type,
                "mime_type": probe.sample_mime_type,
                "data_base64": probe.sample_base64,
            }
            if probe.filename:
                attachment_part["name"] = probe.filename
            probe_requests[probe.capability] = ModelRequest.build(
                system="",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": probe.prompt},
                            attachment_part,
                        ],
                    }
                ],
                model_config={"max_tokens": max_tokens},
                transport_mode="capability_probe",
            )

        outcomes: dict[
            str,
            AssistantModelOutput | ProviderChatCompletionError,
        ] = {}
        if probe_requests:
            with ThreadPoolExecutor(
                max_workers=len(probe_requests),
                thread_name_prefix=f"model-capability-{state}",
            ) as capability_executor:
                capability_futures = {
                    capability: capability_executor.submit(complete, model_request)
                    for capability, model_request in probe_requests.items()
                }
                for capability in probe_requests:
                    try:
                        outcomes[capability] = capability_futures[capability].result()
                    except ProviderChatCompletionError as exc:
                        outcomes[capability] = exc
                    if cancellation_token is not None:
                        cancellation_token.raise_if_cancelled()

        supports_text = current.supports_text
        if "text" in capability_declarations:
            supports_text = capability_declarations["text"]
            checks["text"] = "supported" if supports_text else "unsupported"
        else:
            text_outcome = outcomes["text"]
            if isinstance(text_outcome, ProviderChatCompletionError):
                if _fatal_probe_failure(text_outcome):
                    raise text_outcome
                status = _optional_probe_failure_status(text_outcome)
                checks["text"] = status
                errors["text"] = str(text_outcome)
                if status == "unsupported":
                    supports_text = False
            else:
                observed_text = bool(text_outcome.content or text_outcome.tool_calls)
                checks["text"] = "supported" if observed_text else "unverified"
                if observed_text:
                    supports_text = True
                else:
                    errors["text"] = "模型未返回可用文本。"

        supports_tool_calling = current.supports_tool_calling
        if "tool_calling" in capability_declarations:
            supports_tool_calling = capability_declarations["tool_calling"]
            checks["tool_calling"] = (
                "supported" if supports_tool_calling else "unsupported"
            )
        else:
            tool_outcome = outcomes["tool_calling"]
            if isinstance(tool_outcome, ProviderChatCompletionError):
                status = _optional_probe_failure_status(tool_outcome)
                checks["tool_calling"] = status
                errors["tool_calling"] = str(tool_outcome)
                if status == "unsupported":
                    supports_tool_calling = False
            else:
                observed = any(
                    call.name == "capability_probe" for call in tool_outcome.tool_calls
                )
                checks["tool_calling"] = "supported" if observed else "unverified"
                if observed:
                    supports_tool_calling = True
                else:
                    errors["tool_calling"] = "模型未返回工具调用。"

        file_mime_types = list(dict.fromkeys(current.file_mime_types))
        for probe in _MEDIA_CAPABILITY_PROBES:
            current_types = [
                mime_type
                for mime_type in file_mime_types
                if mime_type.startswith(probe.mime_type_prefix)
            ]
            native_types = sorted(
                mime_type
                for mime_type in self.provider.native_attachment_mime_types()
                if mime_type.startswith(probe.mime_type_prefix)
            )
            supported_types = list(dict.fromkeys([*current_types, *native_types])) or [
                probe.sample_mime_type
            ]
            without_current = [
                mime_type
                for mime_type in file_mime_types
                if not mime_type.startswith(probe.mime_type_prefix)
            ]
            if probe.capability in capability_declarations:
                declared_supported = capability_declarations[probe.capability]
                checks[probe.capability] = (
                    "supported" if declared_supported else "unsupported"
                )
                file_mime_types = (
                    [*without_current, *supported_types]
                    if declared_supported
                    else without_current
                )
                continue
            media_outcome = outcomes[probe.capability]
            if isinstance(media_outcome, ProviderChatCompletionError):
                status = _optional_probe_failure_status(media_outcome)
                checks[probe.capability] = status
                errors[probe.capability] = str(media_outcome)
                file_mime_types = (
                    without_current
                    if status == "unsupported"
                    else [*without_current, *current_types]
                )
            else:
                media_output = media_outcome
                observed = (
                    media_output.content.strip().strip(' .。!！\"\'`').casefold() == probe.expected_answer
                    if probe.expected_answer is not None
                    else bool(media_output.content or media_output.tool_calls)
                )
                if observed:
                    checks[probe.capability] = "supported"
                    file_mime_types = [*without_current, *dict.fromkeys([*current_types, probe.sample_mime_type])]
                else:
                    checks[probe.capability] = "unverified"
                    errors[probe.capability] = "模型未正确回答样本内容，读取能力尚未确认。"
                    file_mime_types = [*without_current, *current_types]

        availability = current.availability
        if checks["text"] == "supported":
            availability = "available"
        elif checks["text"] == "unsupported":
            availability = "unavailable"

        return (
            ModelModeCapabilityProfile(
                availability=availability,
                supports_text=supports_text,
                file_mime_types=list(dict.fromkeys(file_mime_types)),
                supports_tool_calling=supports_tool_calling,
            ),
            checks,
            errors,
        )

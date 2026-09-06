from typing import Any, List, Optional
from urllib import request

from backend.app.model_capabilities import (
    DEFAULT_CAPABILITY_PROFILE,
    ModelCapabilityProfiles,
    ModelCapabilityProfile,
)
from backend.app.agent_runtime.model_types import (
    AssistantModelOutput,
    ModelRequest,
)
from backend.app.core.cancellation import (
    CancellationToken,
)


from backend.app.providers.types import (
    ModelCapabilityProbeResult,
    ProviderConnectionResult,
    ProviderModel,
)
from backend.app.providers.errors import ProviderChatCompletionError
from backend.app.providers.capability_probe import _THINKING_MODES
from backend.app.providers.errors import ProviderErrorParser, is_context_overflow
from backend.app.providers.responses import ProviderResponseParser
from backend.app.providers.message_codec import ProviderMessageCodec
from backend.app.providers.transport import ProviderTransport
from backend.app.providers.capability_probe import ProviderCapabilityProbe


class ModelProvider:
    provider_id = "provider"
    provider_name = "Provider"
    default_api_url = ""
    default_official_url = ""
    timeout_seconds = 10
    attachment_timeout_seconds = 300

    def __init__(self, urlopen=request.urlopen, stream_client_factory=None):
        self.errors = ProviderErrorParser(self.is_context_overflow)
        self.responses = ProviderResponseParser(self.errors)
        self.codec = ProviderMessageCodec(self)
        self.transport = ProviderTransport(
            self,
            self.errors,
            self.responses,
            urlopen=urlopen,
            stream_client_factory=stream_client_factory,
        )
        self.probe = ProviderCapabilityProbe(self)

    def test_connection(self, api_url: str, api_key: str) -> ProviderConnectionResult:
        return self.transport.test_connection(api_url=api_url, api_key=api_key)

    def list_models(
        self,
        api_url: str,
        api_key: str,
        cancellation_token: CancellationToken | None = None,
    ) -> List[ProviderModel]:
        return self.transport.list_models(
            api_url=api_url, api_key=api_key, cancellation_token=cancellation_token
        )

    def complete_chat(
        self,
        api_url: str,
        api_key: str,
        remote_model_id: str,
        model_request: ModelRequest,
        thinking_mode: str = "default",
        timeout_seconds: Optional[float] = None,
        cancellation_token: CancellationToken | None = None,
    ) -> AssistantModelOutput:
        return self.transport.complete_chat(
            api_url=api_url,
            api_key=api_key,
            remote_model_id=remote_model_id,
            model_request=model_request,
            thinking_mode=thinking_mode,
            timeout_seconds=timeout_seconds,
            cancellation_token=cancellation_token,
        )

    def stream_chat_payload(
        self,
        *,
        api_url: str,
        api_key: str,
        provider_payload: dict[str, Any],
        timeout_seconds: float | None = None,
        cancellation_token: CancellationToken | None = None,
    ):
        yield from self.transport.stream_chat_payload(
            api_url=api_url,
            api_key=api_key,
            provider_payload=provider_payload,
            timeout_seconds=timeout_seconds,
            cancellation_token=cancellation_token,
        )

    def build_chat_payload(
        self,
        *,
        remote_model_id: str,
        model_request: ModelRequest,
        thinking_mode: str,
        stream: bool,
    ) -> dict[str, Any]:
        return self.codec.build_chat_payload(
            remote_model_id=remote_model_id,
            model_request=model_request,
            thinking_mode=thinking_mode,
            stream=stream,
        )

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
        return self.probe.probe_capabilities(
            api_url=api_url,
            api_key=api_key,
            remote_model_id=remote_model_id,
            current_profiles=current_profiles,
            thinking_modes=thinking_modes,
            capability_declarations=capability_declarations,
            cancellation_token=cancellation_token,
        )

    def is_context_overflow(self, details):
        return is_context_overflow(details)

    def stream_chat(
        self,
        api_url: str,
        api_key: str,
        remote_model_id: str,
        model_request: ModelRequest,
        thinking_mode: str = "default",
        timeout_seconds: float | None = None,
        cancellation_token: CancellationToken | None = None,
    ):
        payload = self.build_chat_payload(
            remote_model_id=remote_model_id,
            model_request=model_request,
            thinking_mode=thinking_mode,
            stream=True,
        )
        yield from self.stream_chat_payload(
            api_url=api_url,
            api_key=api_key,
            provider_payload=payload,
            timeout_seconds=timeout_seconds,
            cancellation_token=cancellation_token,
        )

    def parse_model_payload(self, payload: Any) -> List[ProviderModel]:
        if isinstance(payload, dict):
            raw_models = payload.get("data") or payload.get("models") or []
        elif isinstance(payload, list):
            raw_models = payload
        else:
            raw_models = []

        models: List[ProviderModel] = []
        for item in raw_models:
            if not isinstance(item, dict):
                continue
            remote_model_id = (
                item.get("id") or item.get("model") or item.get("remote_model_id")
            )
            if not isinstance(remote_model_id, str) or not remote_model_id.strip():
                continue
            model_name = item.get("name") or item.get("display_name") or remote_model_id
            raw_created_at = item.get("created_at") or item.get("created")
            created_at = (
                int(raw_created_at)
                if isinstance(raw_created_at, (int, float))
                and not isinstance(raw_created_at, bool)
                else None
            )
            profile = self.normalize_capabilities(item, remote_model_id)
            models.append(
                ProviderModel.from_profile(
                    remote_model_id=remote_model_id,
                    model_name=model_name
                    if isinstance(model_name, str)
                    else remote_model_id,
                    profile=profile,
                    created_at=created_at,
                    capability_declarations=self.capability_declarations(
                        item,
                        remote_model_id,
                    ),
                )
            )
        return models

    def normalize_capabilities(
        self,
        raw_model: dict[str, Any],
        remote_model_id: str,
    ) -> ModelCapabilityProfile:
        del remote_model_id
        thinking_modes = [
            mode
            for mode in _string_list(raw_model.get("thinking_modes"))
            if mode in _THINKING_MODES
        ]
        default_thinking_state = str(
            raw_model.get("default_thinking_state")
            or DEFAULT_CAPABILITY_PROFILE.default_thinking_state
        )
        if default_thinking_state not in {"thinking", "non_thinking", "unknown"}:
            default_thinking_state = "unknown"
        return ModelCapabilityProfile(
            supports_text=_first_bool(
                raw_model,
                "supports_text",
                "text",
                fallback=DEFAULT_CAPABILITY_PROFILE.supports_text,
            ),
            file_mime_types=_string_list(raw_model.get("file_mime_types")),
            thinking_modes=thinking_modes
            or list(DEFAULT_CAPABILITY_PROFILE.thinking_modes),
            supports_tool_calling=_first_bool(
                raw_model,
                "supports_tool_calling",
                "tool_calling",
                fallback=DEFAULT_CAPABILITY_PROFILE.supports_tool_calling,
            ),
            default_thinking_state=default_thinking_state,
            context_window_tokens=_first_nonnegative_int(
                raw_model,
                "context_window_tokens",
                "context_length",
            ),
            max_output_tokens=_first_nonnegative_int(
                raw_model,
                "max_output_tokens",
                "max_completion_tokens",
            ),
        )

    def capability_declarations(
        self,
        raw_model: dict[str, Any],
        remote_model_id: str,
    ) -> dict[str, bool]:
        """Return only capabilities explicitly described by provider metadata."""

        del remote_model_id
        declarations: dict[str, bool] = {}
        for capability, keys in (
            ("text", ("supports_text", "text")),
            ("tool_calling", ("supports_tool_calling", "tool_calling")),
        ):
            value = next(
                (
                    raw_model[key]
                    for key in keys
                    if key in raw_model and isinstance(raw_model[key], bool)
                ),
                None,
            )
            if isinstance(value, bool):
                declarations[capability] = value

        declared_mime_types = _nonempty_string_set(raw_model.get("file_mime_types"))
        if declared_mime_types:
            declarations.update(
                {
                    "image_input": any(
                        mime_type.startswith("image/")
                        for mime_type in declared_mime_types
                    ),
                    "pdf_input": "application/pdf" in declared_mime_types,
                    "audio_input": any(
                        mime_type.startswith("audio/")
                        for mime_type in declared_mime_types
                    ),
                    "video_input": any(
                        mime_type.startswith("video/")
                        for mime_type in declared_mime_types
                    ),
                }
            )
        for key in ("supports_vision", "vision"):
            if key in raw_model and isinstance(raw_model[key], bool):
                declarations["image_input"] = raw_model[key]
                break
        thinking_modes = _string_list(raw_model.get("thinking_modes"))
        if thinking_modes:
            declarations["thinking"] = any(
                mode not in {"default", "off"} for mode in thinking_modes
            )
        else:
            for key in ("supports_thinking", "thinking", "reasoning"):
                if key in raw_model and isinstance(raw_model[key], bool):
                    declarations["thinking"] = raw_model[key]
                    break
        return declarations

    def capability_probe_tool_choice(self, state: str) -> Any:
        return {
            "type": "function",
            "function": {"name": "capability_probe"},
        }

    def thinking_mode_payload(
        self,
        remote_model_id: str,
        thinking_mode: str,
    ) -> dict[str, Any]:
        if not thinking_mode or thinking_mode == "default":
            return {}
        return {"reasoning_effort": _reasoning_effort(thinking_mode)}

    def native_attachment_mime_types(self) -> set[str]:
        return set()

    def supports_native_attachment(self, mime_type: str) -> bool:
        return mime_type in self.native_attachment_mime_types()

    def request_extra_payload(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {}

    def serialize_file_part(self, part: dict[str, Any]) -> dict[str, Any]:
        raise ProviderChatCompletionError(
            "当前模型服务不支持该附件类型。", capability_rejected=True
        )

    def failure(
        self, message: str, *, code: str = "MODEL_ERROR"
    ) -> ProviderConnectionResult:
        return ProviderConnectionResult(
            provider_id=self.provider_id,
            reachable=False,
            message=message,
            code=code,
        )


def _nonempty_string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {
        item.strip().lower() for item in value if isinstance(item, str) and item.strip()
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(
        dict.fromkeys(
            item.strip().lower()
            for item in value
            if isinstance(item, str) and item.strip()
        )
    )


def _first_bool(
    payload: dict[str, Any],
    *keys: str,
    fallback: bool,
) -> bool:
    return next(
        (
            payload[key]
            for key in keys
            if key in payload and isinstance(payload[key], bool)
        ),
        fallback,
    )


def _first_nonnegative_int(
    payload: dict[str, Any],
    *keys: str,
) -> Optional[int]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def _reasoning_effort(thinking_mode: str) -> str:
    if thinking_mode in {"minimal", "low", "medium", "high", "xhigh", "max"}:
        return thinking_mode
    if thinking_mode == "off":
        return "none"
    return thinking_mode

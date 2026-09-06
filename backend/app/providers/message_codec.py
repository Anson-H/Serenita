from typing import Any

from backend.app.agent_runtime.model_types import (
    ModelRequest,
)


from backend.app.providers.errors import ProviderChatCompletionError


def _data_url(mime_type: str, data_base64: str) -> str:
    return f"data:{mime_type};base64,{data_base64}"


def _audio_format(mime_type: str) -> str:
    return {
        "audio/amr": "amr",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/3gpp": "3gpp",
        "audio/3gpp2": "3gpp2",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/aiff": "aiff",
        "audio/x-aiff": "aiff",
        "audio/aac": "aac",
        "audio/ogg": "ogg",
        "audio/flac": "flac",
        "audio/mp4": "m4a",
        "audio/m4a": "m4a",
        "audio/x-m4a": "m4a",
    }.get(mime_type, mime_type.split("/")[-1])


def _canonical_video_mime_type(mime_type: str) -> str:
    return "video/mov" if mime_type == "video/quicktime" else mime_type


class ProviderMessageCodec:
    def __init__(self, policy):
        self.policy = policy

    def _serialize_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        capability_probe: bool = False,
    ) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role", "user")
            item: dict[str, Any] = {
                "role": role,
                "content": self._serialize_content(
                    message.get("content", ""),
                    capability_probe=capability_probe,
                ),
            }
            if role == "assistant" and isinstance(message.get("tool_calls"), list):
                item["tool_calls"] = list(message["tool_calls"])
            if role == "tool":
                item["tool_call_id"] = str(message.get("tool_call_id") or "")
                if message.get("name"):
                    item["name"] = str(message["name"])
            serialized.append(item)
        return serialized

    def _serialize_request_messages(
        self, model_request: ModelRequest
    ) -> list[dict[str, Any]]:
        messages = [dict(item) for item in model_request.messages]
        if model_request.system:
            messages.insert(0, {"role": "system", "content": model_request.system})
        return self._serialize_messages(
            messages,
            capability_probe=model_request.transport_mode == "capability_probe",
        )

    def build_chat_payload(
        self,
        *,
        remote_model_id: str,
        model_request: ModelRequest,
        thinking_mode: str,
        stream: bool,
    ) -> dict[str, Any]:
        """Build the exact credential-free payload used by the wire transport."""

        serialized_messages = self._serialize_request_messages(model_request)
        payload: dict[str, Any] = {
            "model": remote_model_id,
        }
        if model_request.tools:
            payload["tools"] = [item.as_dict() for item in model_request.tools]
            if model_request.tool_choice is not None:
                payload["tool_choice"] = model_request.tool_choice
        payload["messages"] = serialized_messages
        payload["stream"] = bool(stream)
        payload.update(self.policy.request_extra_payload(serialized_messages))
        configured_output_limit = model_request.model_config.get("max_output_tokens")
        if (
            isinstance(configured_output_limit, int)
            and not isinstance(configured_output_limit, bool)
            and configured_output_limit > 0
            and "max_tokens" not in model_request.model_config
            and "max_completion_tokens" not in model_request.model_config
        ):
            payload["max_tokens"] = configured_output_limit
        allowed_config = {
            "temperature",
            "top_p",
            "max_tokens",
            "max_completion_tokens",
            "presence_penalty",
            "frequency_penalty",
            "seed",
            "enable_thinking",
            "thinking",
            "reasoning",
            "reasoning_effort",
        }
        for key, value in model_request.model_config.items():
            if key in allowed_config and value is not None:
                payload[key] = value
        payload.update(
            self.policy.thinking_mode_payload(remote_model_id, thinking_mode)
        )
        return payload

    def _serialize_content(
        self,
        content: Any,
        *,
        capability_probe: bool = False,
    ) -> Any:
        if not isinstance(content, list):
            return content
        return [
            self._serialize_content_part(
                part,
                capability_probe=capability_probe,
            )
            for part in content
        ]

    def _serialize_content_part(
        self,
        part: Any,
        *,
        capability_probe: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(part, dict):
            raise ProviderChatCompletionError(
                "模型服务不支持该消息内容格式", capability_rejected=True
            )
        part_type = part.get("type")
        if part_type == "text":
            return {"type": "text", "text": str(part.get("text", ""))}
        if part_type == "image":
            mime_type = str(part.get("mime_type", ""))
            if not capability_probe and not self.policy.supports_native_attachment(
                mime_type
            ):
                raise ProviderChatCompletionError(
                    "当前模型服务不支持该附件类型。", capability_rejected=True
                )
            return {
                "type": "image_url",
                "image_url": {
                    "url": _data_url(mime_type, str(part.get("data_base64", "")))
                },
            }
        if part_type == "file":
            mime_type = str(part.get("mime_type", ""))
            if capability_probe:
                return self._serialize_capability_probe_file_part(part)
            if not self.policy.supports_native_attachment(mime_type):
                raise ProviderChatCompletionError(
                    "当前模型服务不支持该附件类型。", capability_rejected=True
                )
            return self.policy.serialize_file_part(part)
        if part_type == "audio":
            mime_type = str(part.get("mime_type", ""))
            if not capability_probe and not self.policy.supports_native_attachment(
                mime_type
            ):
                raise ProviderChatCompletionError(
                    "当前模型服务不支持该附件类型。", capability_rejected=True
                )
            return {
                "type": "input_audio",
                "input_audio": {
                    "data": str(part.get("data_base64", "")),
                    "format": _audio_format(mime_type),
                },
            }
        if part_type == "video":
            mime_type = str(part.get("mime_type", ""))
            if not capability_probe and not self.policy.supports_native_attachment(
                mime_type
            ):
                raise ProviderChatCompletionError(
                    "当前模型服务不支持该附件类型。", capability_rejected=True
                )
            return {
                "type": "video_url",
                "video_url": {
                    "url": _data_url(
                        _canonical_video_mime_type(mime_type),
                        str(part.get("data_base64", "")),
                    )
                },
            }
        raise ProviderChatCompletionError(
            "模型服务不支持该消息内容格式", capability_rejected=True
        )

    def _serialize_capability_probe_file_part(
        self,
        part: dict[str, Any],
    ) -> dict[str, Any]:
        mime_type = str(part.get("mime_type", ""))
        return {
            "type": "file",
            "file": {
                "filename": str(part.get("name") or "capability-probe"),
                "file_data": _data_url(
                    mime_type,
                    str(part.get("data_base64", "")),
                ),
            },
        }

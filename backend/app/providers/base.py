from dataclasses import dataclass, field
import json
import socket
from typing import Any, List, Optional
from urllib import error, request

from backend.app.model_capabilities import (
    DEFAULT_CAPABILITY_PROFILE,
    ModelCapabilityProfile,
)


@dataclass(frozen=True)
class ProviderModel:
    remote_model_id: str
    model_name: str
    supports_text: bool = True
    file_mime_types: list[str] = field(default_factory=list)
    thinking_modes: list[str] = field(default_factory=lambda: ["default"])
    supports_tool_calling: bool = False
    supports_json_output: bool = False
    context_window_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None

    @classmethod
    def from_profile(
        cls,
        *,
        remote_model_id: str,
        model_name: str,
        profile: ModelCapabilityProfile,
    ) -> "ProviderModel":
        return cls(
            remote_model_id=remote_model_id,
            model_name=model_name,
            supports_text=profile.supports_text,
            file_mime_types=profile.file_mime_types,
            thinking_modes=profile.thinking_modes,
            supports_tool_calling=profile.supports_tool_calling,
            supports_json_output=profile.supports_json_output,
            context_window_tokens=profile.context_window_tokens,
            max_output_tokens=profile.max_output_tokens,
        )


@dataclass(frozen=True)
class ProviderConnectionResult:
    provider_id: str
    reachable: bool
    message: str


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    thinking_content: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    stop_reason: str = "end_turn"


@dataclass(frozen=True)
class ChatCompletionChunk:
    content_delta: str = ""
    thinking_delta: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    stop_reason: Optional[str] = None


class ProviderModelListError(Exception):
    pass


class ProviderChatCompletionError(Exception):
    pass


class ModelProvider:
    provider_id = "provider"
    display_name = "Provider"
    default_base_url = ""
    default_official_url = ""
    timeout_seconds = 10
    attachment_timeout_seconds = 300

    def __init__(self, urlopen=request.urlopen):
        self._urlopen = urlopen

    def test_connection(self, base_url: str, api_key: str) -> ProviderConnectionResult:
        normalized_base_url = (base_url or self.default_base_url).rstrip("/")
        if not normalized_base_url:
            return self._failure("缺少 API 地址")
        if not api_key.strip():
            return self._failure("缺少 API key")

        connection_request = request.Request(
            f"{normalized_base_url}/models",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="GET",
        )

        try:
            with self._urlopen(connection_request, timeout=self.timeout_seconds) as response:
                status = response.status if hasattr(response, "status") else response.getcode()
        except error.HTTPError as exc:
            if exc.code in (401, 403):
                return self._failure("模型服务认证失败")
            return self._failure(f"模型服务连接失败，HTTP {exc.code}")
        except (TimeoutError, socket.timeout):
            return self._failure("连接超时")
        except error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                return self._failure("连接超时")
            return self._failure("模型服务连接失败")

        if 200 <= status < 300:
            return ProviderConnectionResult(
                provider_id=self.provider_id,
                reachable=True,
                message="连接测试成功",
            )
        if status in (401, 403):
            return self._failure("模型服务认证失败")
        return self._failure(f"模型服务连接失败，HTTP {status}")

    def list_models(self, base_url: str, api_key: str) -> List[ProviderModel]:
        normalized_base_url = (base_url or self.default_base_url).rstrip("/")
        if not normalized_base_url:
            raise ProviderModelListError("缺少 API 地址")
        if not api_key.strip():
            raise ProviderModelListError("缺少 API key")

        model_request = request.Request(
            f"{normalized_base_url}/models",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="GET",
        )

        try:
            with self._urlopen(model_request, timeout=self.timeout_seconds) as response:
                status = response.status if hasattr(response, "status") else response.getcode()
                body = response.read()
        except error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ProviderModelListError("模型服务认证失败") from exc
            raise ProviderModelListError(f"模型服务连接失败，HTTP {exc.code}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ProviderModelListError("连接超时") from exc
        except error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ProviderModelListError("连接超时") from exc
            raise ProviderModelListError("模型服务连接失败") from exc

        if not 200 <= status < 300:
            if status in (401, 403):
                raise ProviderModelListError("模型服务认证失败")
            raise ProviderModelListError(f"模型服务连接失败，HTTP {status}")

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderModelListError("模型服务返回的模型列表不是有效 JSON") from exc

        return self._parse_model_payload(payload)

    def complete_chat(
        self,
        base_url: str,
        api_key: str,
        remote_model_id: str,
        messages: list[dict[str, Any]],
        thinking_mode: str = "default",
    ) -> ChatCompletionResult:
        normalized_base_url = (base_url or self.default_base_url).rstrip("/")
        if not normalized_base_url:
            raise ProviderChatCompletionError("缺少 API 地址")
        if not api_key.strip():
            raise ProviderChatCompletionError("缺少 API key")
        if not remote_model_id.strip():
            raise ProviderChatCompletionError("缺少模型 ID")

        serialized_messages = self._serialize_messages(messages)
        payload = {
            "model": remote_model_id,
            "messages": serialized_messages,
            "stream": False,
            **self._request_extra_payload(serialized_messages),
        }
        if thinking_mode and thinking_mode != "default":
            payload["reasoning_effort"] = _reasoning_effort(thinking_mode)
        request_timeout_seconds = self._chat_completion_timeout_seconds(serialized_messages)

        completion_request = request.Request(
            f"{normalized_base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        attempts = 3
        for attempt in range(attempts):
            try:
                with self._urlopen(completion_request, timeout=request_timeout_seconds) as response:
                    status = response.status if hasattr(response, "status") else response.getcode()
                    body = response.read()
            except error.HTTPError as exc:
                if exc.code in (401, 403):
                    raise ProviderChatCompletionError("模型服务认证失败") from exc
                if 500 <= exc.code < 600 and attempt < attempts - 1:
                    continue
                raise ProviderChatCompletionError(f"模型服务调用失败，HTTP {exc.code}") from exc
            except (TimeoutError, socket.timeout) as exc:
                if attempt < attempts - 1:
                    continue
                raise ProviderChatCompletionError("连接超时") from exc
            except error.URLError as exc:
                if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                    if attempt < attempts - 1:
                        continue
                    raise ProviderChatCompletionError("连接超时") from exc
                if attempt < attempts - 1:
                    continue
                raise ProviderChatCompletionError("模型服务调用失败") from exc

            if 200 <= status < 300:
                break
            if status in (401, 403):
                raise ProviderChatCompletionError("模型服务认证失败")
            if 500 <= status < 600 and attempt < attempts - 1:
                continue
            raise ProviderChatCompletionError(f"模型服务调用失败，HTTP {status}")

        try:
            completion_payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderChatCompletionError("模型服务返回的对话结果不是有效 JSON") from exc

        return self._parse_chat_completion(completion_payload)

    def stream_chat(
        self,
        base_url: str,
        api_key: str,
        remote_model_id: str,
        messages: list[dict[str, Any]],
        thinking_mode: str = "default",
    ):
        normalized_base_url = (base_url or self.default_base_url).rstrip("/")
        if not normalized_base_url:
            raise ProviderChatCompletionError("缺少 API 地址")
        if not api_key.strip():
            raise ProviderChatCompletionError("缺少 API key")
        if not remote_model_id.strip():
            raise ProviderChatCompletionError("缺少模型 ID")

        serialized_messages = self._serialize_messages(messages)
        payload = {
            "model": remote_model_id,
            "messages": serialized_messages,
            "stream": True,
            **self._request_extra_payload(serialized_messages),
        }
        if thinking_mode and thinking_mode != "default":
            payload["reasoning_effort"] = _reasoning_effort(thinking_mode)
        request_timeout_seconds = self._chat_completion_timeout_seconds(serialized_messages)

        completion_request = request.Request(
            f"{normalized_base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with self._urlopen(completion_request, timeout=request_timeout_seconds) as response:
                status = response.status if hasattr(response, "status") else response.getcode()
                if not 200 <= status < 300:
                    if status in (401, 403):
                        raise ProviderChatCompletionError("模型服务认证失败")
                    raise ProviderChatCompletionError(f"模型服务调用失败，HTTP {status}")
                yield from self._iter_stream_chunks(response)
        except error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ProviderChatCompletionError("模型服务认证失败") from exc
            raise ProviderChatCompletionError(f"模型服务调用失败，HTTP {exc.code}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ProviderChatCompletionError("连接超时") from exc
        except error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ProviderChatCompletionError("连接超时") from exc
            raise ProviderChatCompletionError("模型服务调用失败") from exc

    def _iter_stream_chunks(self, response):
        for raw_line in response:
            line = _decode_stream_line(raw_line)
            if not line or line.startswith(":") or not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if data == "[DONE]":
                break
            try:
                payload = json.loads(data)
            except json.JSONDecodeError as exc:
                raise ProviderChatCompletionError("模型服务返回的流式片段不是有效 JSON") from exc
            chunk = _parse_chat_stream_chunk(payload)
            if chunk:
                yield chunk

    def _parse_chat_completion(self, payload: Any) -> ChatCompletionResult:
        if not isinstance(payload, dict):
            raise ProviderChatCompletionError("模型服务返回的对话结果格式不正确")

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderChatCompletionError("模型服务未返回对话内容")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ProviderChatCompletionError("模型服务返回的对话结果格式不正确")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ProviderChatCompletionError("模型服务未返回助手消息")

        content = _content_text(message.get("content"))
        if not content:
            raise ProviderChatCompletionError("模型服务返回了空回复")

        return ChatCompletionResult(
            content=content,
            thinking_content=_thinking_text(message),
            usage=_usage_payload(payload.get("usage")),
            stop_reason=choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else "end_turn",
        )

    def _parse_model_payload(self, payload: Any) -> List[ProviderModel]:
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
            remote_model_id = item.get("id") or item.get("model") or item.get("remote_model_id")
            if not isinstance(remote_model_id, str) or not remote_model_id.strip():
                continue
            model_name = item.get("name") or item.get("display_name") or remote_model_id
            profile = self.normalize_capabilities(item, remote_model_id)
            models.append(
                ProviderModel.from_profile(
                    remote_model_id=remote_model_id,
                    model_name=model_name if isinstance(model_name, str) else remote_model_id,
                    profile=profile,
                )
            )
        return models

    def normalize_capabilities(
        self,
        raw_model: dict[str, Any],
        remote_model_id: str,
    ) -> ModelCapabilityProfile:
        return DEFAULT_CAPABILITY_PROFILE

    def native_attachment_mime_types(self) -> set[str]:
        return set()

    def supports_native_attachment(self, mime_type: str) -> bool:
        return mime_type in self.native_attachment_mime_types()

    def _request_extra_payload(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {}

    def _chat_completion_timeout_seconds(self, messages: list[dict[str, Any]]) -> int:
        if _messages_include_native_attachment(messages):
            return max(self.timeout_seconds, self.attachment_timeout_seconds)
        return self.timeout_seconds

    def _serialize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"role": message.get("role", "user"), "content": self._serialize_content(message.get("content", ""))}
            for message in messages
        ]

    def _serialize_content(self, content: Any) -> Any:
        if not isinstance(content, list):
            return content
        return [self._serialize_content_part(part) for part in content]

    def _serialize_content_part(self, part: Any) -> dict[str, Any]:
        if not isinstance(part, dict):
            raise ProviderChatCompletionError("模型服务不支持该消息内容格式")
        part_type = part.get("type")
        if part_type == "text":
            return {"type": "text", "text": str(part.get("text", ""))}
        if part_type == "image":
            mime_type = str(part.get("mime_type", ""))
            if not self.supports_native_attachment(mime_type):
                raise ProviderChatCompletionError("当前模型服务不支持该附件类型。")
            return {
                "type": "image_url",
                "image_url": {"url": _data_url(mime_type, str(part.get("data_base64", "")))},
            }
        if part_type == "file":
            mime_type = str(part.get("mime_type", ""))
            if not self.supports_native_attachment(mime_type):
                raise ProviderChatCompletionError("当前模型服务不支持该附件类型。")
            return self._serialize_file_part(part)
        if part_type == "audio":
            mime_type = str(part.get("mime_type", ""))
            if not self.supports_native_attachment(mime_type):
                raise ProviderChatCompletionError("当前模型服务不支持该附件类型。")
            return {
                "type": "input_audio",
                "input_audio": {
                    "data": str(part.get("data_base64", "")),
                    "format": _audio_format(mime_type),
                },
            }
        if part_type == "video":
            mime_type = str(part.get("mime_type", ""))
            if not self.supports_native_attachment(mime_type):
                raise ProviderChatCompletionError("当前模型服务不支持该附件类型。")
            return {
                "type": "video_url",
                "video_url": {
                    "url": _data_url(
                        _canonical_video_mime_type(mime_type),
                        str(part.get("data_base64", "")),
                    )
                },
            }
        raise ProviderChatCompletionError("模型服务不支持该消息内容格式")

    def _serialize_file_part(self, part: dict[str, Any]) -> dict[str, Any]:
        raise ProviderChatCompletionError("当前模型服务不支持该附件类型。")

    def _failure(self, message: str) -> ProviderConnectionResult:
        return ProviderConnectionResult(
            provider_id=self.provider_id,
            reachable=False,
            message=message,
        )


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return ""


def _messages_include_native_attachment(messages: list[dict[str, Any]]) -> bool:
    attachment_types = {"image_url", "file", "input_audio", "video_url"}
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") in attachment_types:
                return True
    return False


def _content_delta_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def _thinking_text(message: dict[str, Any]) -> str:
    for key in ("reasoning_content", "thinking_content", "reasoning"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            text = _content_text(value)
            if text:
                return text
        if isinstance(value, dict):
            for nested_key in ("content", "summary", "text"):
                nested_value = value.get(nested_key)
                if isinstance(nested_value, str) and nested_value.strip():
                    return nested_value.strip()
    return ""


def _thinking_delta_text(message: dict[str, Any]) -> str:
    for key in ("reasoning_content", "thinking_content", "reasoning"):
        value = message.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return _content_delta_text(value)
        if isinstance(value, dict):
            for nested_key in ("content", "summary", "text"):
                nested_value = value.get(nested_key)
                if isinstance(nested_value, str):
                    return nested_value
    return ""


def _parse_chat_stream_chunk(payload: Any) -> Optional[ChatCompletionChunk]:
    if not isinstance(payload, dict):
        raise ProviderChatCompletionError("模型服务返回的流式片段格式不正确")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        usage = _usage_payload(payload.get("usage"))
        return ChatCompletionChunk(usage=usage) if usage else None
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ProviderChatCompletionError("模型服务返回的流式片段格式不正确")
    delta = choice.get("delta")
    if not isinstance(delta, dict):
        delta = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    usage = _usage_payload(payload.get("usage"))
    stop_reason = choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None
    return ChatCompletionChunk(
        content_delta=_content_delta_text(delta.get("content")),
        thinking_delta=_thinking_delta_text(delta),
        usage=usage,
        stop_reason=stop_reason,
    )


def _decode_stream_line(raw_line: Any) -> str:
    if isinstance(raw_line, bytes):
        return raw_line.decode("utf-8").strip()
    return str(raw_line).strip()


def _usage_payload(usage: Any) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {}
    return {key: value for key, value in usage.items() if isinstance(key, str)}


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


def _reasoning_effort(thinking_mode: str) -> str:
    if thinking_mode in {"low", "medium", "high"}:
        return thinking_mode
    if thinking_mode in {"fast"}:
        return "low"
    if thinking_mode in {"xhigh"}:
        return "high"
    return thinking_mode

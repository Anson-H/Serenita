import json
from typing import Any, Optional

from backend.app.agent_runtime.model_types import (
    AssistantModelOutput,
    ModelStreamChunk,
    ToolCall,
    ToolCallDelta,
)


from backend.app.providers.errors import ProviderChatCompletionError


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


def _parse_chat_stream_chunk(payload: Any) -> Optional[ModelStreamChunk]:
    if not isinstance(payload, dict):
        raise ProviderChatCompletionError("模型服务返回的流式片段格式不正确")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        usage = _usage_payload(payload.get("usage"))
        return ModelStreamChunk(usage=usage) if usage else None
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ProviderChatCompletionError("模型服务返回的流式片段格式不正确")
    delta = choice.get("delta")
    if not isinstance(delta, dict):
        delta = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    usage = _usage_payload(payload.get("usage"))
    stop_reason = (
        choice.get("finish_reason")
        if isinstance(choice.get("finish_reason"), str)
        else None
    )
    return ModelStreamChunk(
        content_delta=_content_delta_text(delta.get("content")),
        reasoning_delta=_thinking_delta_text(delta),
        tool_call_deltas=_parse_tool_call_deltas(delta.get("tool_calls")),
        usage=usage,
        stop_reason=stop_reason,
    )


def parse_tool_calls(value: Any) -> tuple[ToolCall, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ProviderChatCompletionError("模型服务返回的工具调用格式不正确")
    calls: list[ToolCall] = []
    for item in value:
        if not isinstance(item, dict):
            raise ProviderChatCompletionError("模型服务返回的工具调用格式不正确")
        function = item.get("function")
        if not isinstance(function, dict):
            raise ProviderChatCompletionError("模型服务返回的工具调用缺少函数信息")
        call_id = str(item.get("id") or "").strip()
        name = str(function.get("name") or "").strip()
        raw_arguments = function.get("arguments", "{}")
        if isinstance(raw_arguments, dict):
            arguments = dict(raw_arguments)
        elif isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments or "{}")
            except json.JSONDecodeError as exc:
                raise ProviderChatCompletionError(
                    "模型服务返回的工具参数不是有效 JSON"
                ) from exc
        else:
            raise ProviderChatCompletionError("模型服务返回的工具参数格式不正确")
        if not isinstance(arguments, dict):
            raise ProviderChatCompletionError("模型服务返回的工具参数必须是 JSON 对象")
        try:
            calls.append(ToolCall(id=call_id, name=name, arguments=arguments))
        except (TypeError, ValueError) as exc:
            raise ProviderChatCompletionError(str(exc)) from exc
    return tuple(calls)


def _parse_tool_call_deltas(value: Any) -> tuple[ToolCallDelta, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ProviderChatCompletionError("模型服务返回的流式工具调用格式不正确")
    deltas: list[ToolCallDelta] = []
    for fallback_index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ProviderChatCompletionError("模型服务返回的流式工具调用格式不正确")
        function = item.get("function")
        if not isinstance(function, dict):
            function = {}
        index = item.get("index", fallback_index)
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise ProviderChatCompletionError("模型服务返回的工具调用索引无效")
        arguments = function.get("arguments")
        deltas.append(
            ToolCallDelta(
                index=index,
                id=str(item.get("id") or ""),
                name_delta=str(function.get("name") or ""),
                arguments_delta=(
                    json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
                    if isinstance(arguments, dict)
                    else str(arguments or "")
                ),
            )
        )
    return tuple(deltas)


def _decode_stream_line(raw_line: Any) -> str:
    if isinstance(raw_line, bytes):
        return raw_line.decode("utf-8").strip()
    return str(raw_line).strip()


def _usage_payload(usage: Any) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {}
    return {key: value for key, value in usage.items() if isinstance(key, str)}


class ProviderResponseParser:
    def __init__(self, errors):
        self.errors = errors

    def stream(self, response, cancellation_token=None):
        for raw_line in response:
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
            line = _decode_stream_line(raw_line)
            if not line or line.startswith(":") or not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if data == "[DONE]":
                break
            try:
                payload = json.loads(data)
            except json.JSONDecodeError as exc:
                raise ProviderChatCompletionError(
                    "模型服务返回的流式片段不是有效 JSON"
                ) from exc
            self.errors.raise_payload_error(payload)
            chunk = _parse_chat_stream_chunk(payload)
            if chunk:
                yield chunk

    def completion(self, payload: Any) -> AssistantModelOutput:
        if not isinstance(payload, dict):
            raise ProviderChatCompletionError("模型服务返回的对话结果格式不正确")

        self.errors.raise_payload_error(payload)
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
        tool_calls = parse_tool_calls(message.get("tool_calls"))
        if not content and not tool_calls:
            raise ProviderChatCompletionError("模型服务返回了空回复")

        return AssistantModelOutput(
            content=content,
            reasoning=_thinking_text(message),
            tool_calls=tool_calls,
            usage=_usage_payload(payload.get("usage")),
            stop_reason=choice.get("finish_reason")
            if isinstance(choice.get("finish_reason"), str)
            else "end_turn",
        )

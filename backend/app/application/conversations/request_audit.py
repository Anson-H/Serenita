"""构造模型请求审计事件，隐藏附件二进制内容并检查输入覆盖情况。"""

from backend.app.core.time import local_now_iso as now_iso
import json
from typing import Any


from backend.app.agent_runtime.prompts import (
    RUNTIME_CONTEXT_PREFIX,
    SKILL_CATALOG_PREFIX,
)
from backend.app.agent_runtime.model_types import (
    ModelRequest,
)
from backend.app.application.model_provider_service import (
    PreparedProviderRequest,
)
from backend.app.domain.model_capabilities import DEFAULT_CONTEXT_WINDOW_TOKENS


class ModelRequestAudit:
    def request_event_specifications(
        self,
        *,
        turn,
        call_id: str,
        purpose: str,
        model: dict[str, Any],
        model_request: ModelRequest,
        thinking_mode: str,
        step: int,
        prepared_request: PreparedProviderRequest,
        durable_provider_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        injections = self.provider_payload_contexts(durable_provider_payload)
        self.assert_provider_context_coverage(
            durable_provider_payload,
            injections,
        )
        specifications: list[dict[str, Any]] = [
            {
                "type": "step/start",
                "data": {
                    "turn_id": turn["turn_id"],
                    "step": step,
                    "purpose": purpose,
                },
            }
        ]
        request_header_specification = {
            "type": "request/header",
            "data": {
                "turn_id": turn["turn_id"],
                "step": step,
                "call_id": call_id,
                "purpose": purpose,
                "header": {
                    "model": {
                        "model_id": model.get("model_id"),
                        "provider_id": model.get("provider_id"),
                        "remote_model_id": model.get("remote_model_id"),
                        "model_name": model.get("model_name"),
                        "context_window_tokens": int(
                            model.get("context_window_tokens")
                            or DEFAULT_CONTEXT_WINDOW_TOKENS
                        ),
                    },
                    "thinking_mode": thinking_mode,
                    "transport_mode": prepared_request.transport_mode,
                    "model_config": dict(model_request.model_config),
                    "parent_tool_call_id": model_request.model_config.get(
                        "parent_tool_call_id"
                    ),
                    "provider_payload": durable_provider_payload,
                },
            },
        }
        created_at = now_iso()
        for index, injection in enumerate(injections):
            record_id = f"context_{call_id}_{index}"
            specifications.append(
                {
                    "type": "request/context",
                    "data": {
                        "turn_id": turn["turn_id"],
                        "step": step,
                        "call_id": call_id,
                        "context": {
                            "record_id": record_id,
                            "context_id": f"{call_id}:{index}",
                            "purpose": purpose,
                            "step": step,
                            "transport_mode": prepared_request.transport_mode,
                            "parent_tool_call_id": model_request.model_config.get(
                                "parent_tool_call_id"
                            ),
                            "context_type": injection["context_type"],
                            "label": injection["label"],
                            "content": injection["content"],
                            "provider_source": injection["provider_source"],
                            "status": "completed",
                            "duration_ms": 0,
                            "created_at": created_at,
                        },
                    },
                }
            )
        specifications.append(request_header_specification)
        return specifications

    @classmethod
    def provider_payload_contexts(
        cls,
        provider_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Project one payload into exact, source-addressable semantic records."""

        messages = provider_payload.get("messages")
        provider_messages = messages if isinstance(messages, list) else []
        last_user_index = next(
            (
                index
                for index in range(len(provider_messages) - 1, -1, -1)
                if isinstance(provider_messages[index], dict)
                and provider_messages[index].get("role") == "user"
                and cls.provider_tool_observation(provider_messages[index]) is None
            ),
            -1,
        )

        primary_system: list[dict[str, Any]] = []
        tool_system: list[dict[str, Any]] = []
        skill_system: list[dict[str, Any]] = []
        supplemental_system: list[dict[str, Any]] = []
        system_metadata: list[dict[str, Any]] = []
        message_contexts: list[dict[str, Any]] = []

        for index, message in enumerate(provider_messages):
            path = f"/messages/{index}"
            if (
                isinstance(message, dict)
                and message.get("role") == "system"
                and isinstance(message.get("content"), str)
            ):
                for context in cls.system_payload_contexts(
                    message["content"],
                    f"{path}/content",
                ):
                    context_type = context["context_type"]
                    if context_type == "system_prompt":
                        primary_system.append(context)
                    elif context_type == "tool_catalog":
                        tool_system.append(context)
                    elif context_type == "skill_catalog":
                        skill_system.append(context)
                    else:
                        supplemental_system.append(context)
                for key, value in message.items():
                    if key == "content":
                        continue
                    system_metadata.append(
                        {
                            "context_type": "provider_message_metadata",
                            "label": f"系统消息字段 · {key}",
                            "content": value,
                            "provider_source": {
                                "path": f"{path}/{cls.json_pointer_token(key)}"
                            },
                        }
                    )
                continue
            message_contexts.append(
                cls.provider_message_context(
                    message=message,
                    index=index,
                    path=path,
                    current_user=index == last_user_index,
                )
            )

        tool_contexts: list[dict[str, Any]] = []
        if "tools" in provider_payload:
            tools = provider_payload["tools"]
            count = len(tools) if isinstance(tools, list) else 0
            tool_contexts.append(
                {
                    "context_type": "tool_catalog",
                    "label": f"{count} 个可用工具",
                    "content": tools,
                    "provider_source": {"path": "/tools"},
                }
            )

        if "messages" in provider_payload and not provider_messages:
            message_contexts.append(
                {
                    "context_type": "provider_messages",
                    "label": "Provider 消息列表",
                    "content": messages,
                    "provider_source": {"path": "/messages"},
                }
            )

        parameter_contexts = [
            {
                "context_type": "provider_parameter",
                "label": cls.provider_parameter_label(key),
                "content": value,
                "provider_source": {"path": f"/{cls.json_pointer_token(str(key))}"},
            }
            for key, value in provider_payload.items()
            if key not in {"messages", "tools"}
        ]
        return [
            *primary_system,
            *system_metadata,
            *tool_system,
            *tool_contexts,
            *skill_system,
            *supplemental_system,
            *message_contexts,
            *parameter_contexts,
        ]

    @classmethod
    def system_payload_contexts(
        cls,
        content: str,
        path: str,
    ) -> list[dict[str, Any]]:
        marker_specs = (
            ("TEXT_TOOL_PROTOCOL\n", "tool_catalog", "可用工具"),
            (SKILL_CATALOG_PREFIX, "skill_catalog", "可用技能"),
            (RUNTIME_CONTEXT_PREFIX, "runtime_context", "运行时元数据"),
        )
        starts = {0}
        for marker, _context_type, _label in marker_specs:
            offset = 0
            while (position := content.find(marker, offset)) >= 0:
                starts.add(position)
                offset = position + len(marker)
        ordered_starts = sorted(starts)
        contexts: list[dict[str, Any]] = []
        for index, start in enumerate(ordered_starts):
            end = (
                ordered_starts[index + 1]
                if index + 1 < len(ordered_starts)
                else len(content)
            )
            segment = content[start:end]
            context_type = "system_prompt" if index == 0 else "system_content"
            label = "系统提示词" if index == 0 else "系统内容"
            for marker, candidate_type, candidate_label in marker_specs:
                if segment.startswith(marker):
                    context_type = candidate_type
                    label = candidate_label
                    if candidate_type == "tool_catalog":
                        count = cls.text_tool_schema_count(segment)
                        label = f"{count} 个可用工具"
                    elif candidate_type == "skill_catalog":
                        count = cls.catalog_entry_count(segment, marker)
                        label = f"{count} 个可用技能"
                    break
            contexts.append(
                {
                    "context_type": context_type,
                    "label": label,
                    "content": segment,
                    "provider_source": {
                        "path": path,
                        "start": start,
                        "end": end,
                    },
                }
            )
        return contexts

    @staticmethod
    def catalog_entry_count(content: str, prefix: str) -> int:
        if not content.startswith(prefix):
            return 0
        return sum(1 for line in content[len(prefix) :].splitlines() if line.strip())

    @staticmethod
    def text_tool_schema_count(content: str) -> int:
        marker = "AVAILABLE_TOOL_SCHEMAS\n"
        marker_index = content.find(marker)
        if marker_index < 0:
            return 0
        try:
            schemas = json.loads(content[marker_index + len(marker) :].strip())
        except (TypeError, ValueError):
            return 0
        return len(schemas) if isinstance(schemas, list) else 0

    @classmethod
    def provider_message_context(
        cls,
        *,
        message: Any,
        index: int,
        path: str,
        current_user: bool,
    ) -> dict[str, Any]:
        context_type = "provider_message"
        label = f"Provider 消息 · {index}"
        if isinstance(message, dict):
            observation = cls.provider_tool_observation(message)
            role = str(message.get("role") or "unknown")
            if observation is not None:
                tool_call_id, name = observation
                context_type = "tool_observation"
                label = f"工具调用结果 · {name or tool_call_id or index}"
            elif role == "assistant" and cls.provider_tool_calls(message):
                context_type = "model_tool_request"
                label = "模型请求工具调用 · 历史"
            elif role == "user":
                context_type = (
                    "current_user_message" if current_user else "conversation_history"
                )
                label = "当前用户消息" if current_user else "历史用户消息"
            elif role == "assistant":
                context_type = "conversation_history"
                label = "历史模型消息"
            elif role == "system":
                context_type = "system_content"
                label = "系统消息"
            else:
                label = f"Provider 消息 · {role}"
        return {
            "context_type": context_type,
            "label": label,
            "content": message,
            "provider_source": {"path": path},
        }

    @staticmethod
    def provider_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
        calls = message.get("tool_calls")
        if isinstance(calls, list):
            return [item for item in calls if isinstance(item, dict)]
        content = message.get("content")
        if not isinstance(content, str):
            return []
        try:
            payload = json.loads(content)
        except (TypeError, ValueError):
            return []
        if not isinstance(payload, dict):
            return []
        if payload.get("type") == "tool_calls" and isinstance(
            payload.get("calls"), list
        ):
            return [item for item in payload["calls"] if isinstance(item, dict)]
        if payload.get("type") == "tool_call":
            return [payload]
        return []

    @staticmethod
    def provider_tool_observation(
        message: dict[str, Any],
    ) -> tuple[str, str] | None:
        if message.get("role") == "tool":
            return (
                str(message.get("tool_call_id") or ""),
                str(message.get("name") or ""),
            )
        content = message.get("content")
        prefix = "TOOL_OBSERVATION\n"
        if (
            message.get("role") != "user"
            or not isinstance(content, str)
            or not content.startswith(prefix)
        ):
            return None
        try:
            payload = json.loads(content[len(prefix) :])
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        return (
            str(payload.get("tool_call_id") or ""),
            str(payload.get("name") or ""),
        )

    @staticmethod
    def provider_parameter_label(key: str) -> str:
        return {
            "model": "Provider 参数 · model",
            "stream": "Provider 参数 · stream",
            "tool_choice": "Provider 参数 · tool_choice",
            "reasoning_effort": "Provider 参数 · reasoning_effort",
        }.get(str(key), f"Provider 参数 · {key}")

    @staticmethod
    def json_pointer_token(value: str) -> str:
        return value.replace("~", "~0").replace("/", "~1")

    @classmethod
    def assert_provider_context_coverage(
        cls,
        provider_payload: dict[str, Any],
        contexts: list[dict[str, Any]],
    ) -> None:
        sources: list[tuple[str, int | None, int | None]] = []
        for context in contexts:
            source = context.get("provider_source")
            if not isinstance(source, dict) or not isinstance(source.get("path"), str):
                raise ValueError("上下文装配缺少 Provider 来源。")
            path = source["path"]
            resolved = cls.resolve_json_pointer(provider_payload, path)
            start = source.get("start")
            end = source.get("end")
            if start is None and end is None:
                expected = resolved
            elif (
                isinstance(resolved, str)
                and isinstance(start, int)
                and not isinstance(start, bool)
                and isinstance(end, int)
                and not isinstance(end, bool)
                and 0 <= start <= end <= len(resolved)
            ):
                expected = resolved[start:end]
            else:
                raise ValueError("上下文装配的 Provider 字符区间无效。")
            if context.get("content") != expected:
                raise ValueError("上下文装配内容与 Provider 输入不一致。")
            sources.append((path, start, end))

        for path, value in cls.provider_leaf_values(provider_payload):
            non_range_covered = any(
                start is None
                and (source_path == path or path.startswith(source_path + "/"))
                for source_path, start, _end in sources
            )
            if non_range_covered:
                continue
            ranges = sorted(
                (int(start), int(end))
                for source_path, start, end in sources
                if source_path == path and start is not None and end is not None
            )
            if isinstance(value, str) and ranges:
                covered_until = 0
                for start, end in ranges:
                    if start > covered_until:
                        break
                    covered_until = max(covered_until, end)
                if covered_until >= len(value):
                    continue
            raise ValueError(f"Provider 输入未被上下文装配覆盖：{path or '/'}")

    @classmethod
    def provider_leaf_values(
        cls,
        value: Any,
        path: str = "",
    ) -> list[tuple[str, Any]]:
        if isinstance(value, dict) and value:
            leaves: list[tuple[str, Any]] = []
            for key, item in value.items():
                leaves.extend(
                    cls.provider_leaf_values(
                        item,
                        f"{path}/{cls.json_pointer_token(str(key))}",
                    )
                )
            return leaves
        if isinstance(value, list) and value:
            leaves = []
            for index, item in enumerate(value):
                leaves.extend(cls.provider_leaf_values(item, f"{path}/{index}"))
            return leaves
        return [(path, value)]

    @staticmethod
    def resolve_json_pointer(value: Any, path: str) -> Any:
        if path == "":
            return value
        if not path.startswith("/"):
            raise ValueError("Provider 来源必须使用 JSON Pointer。")
        current = value
        for token in path[1:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(current, list):
                current = current[int(token)]
            elif isinstance(current, dict):
                current = current[token]
            else:
                raise ValueError("Provider 来源无法解析。")
        return current

    @staticmethod
    def redact_provider_payload(value: Any, *, parent_key: str = "") -> Any:
        if isinstance(value, list):
            return [
                ModelRequestAudit.redact_provider_payload(item, parent_key=parent_key)
                for item in value
            ]
        if isinstance(value, dict):
            return {
                key: (
                    "<attachment-binary-redacted>"
                    if (
                        key in {"data_base64", "file_data"}
                        or (key == "data" and parent_key == "input_audio")
                    )
                    and isinstance(item, str)
                    else ModelRequestAudit.redact_provider_payload(item, parent_key=key)
                )
                for key, item in value.items()
            }
        if isinstance(value, str) and value.startswith("data:") and ";base64," in value:
            prefix = value.split(",", 1)[0]
            return prefix + ",<attachment-binary-redacted>"
        return value

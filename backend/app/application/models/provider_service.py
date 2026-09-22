from backend.app.domain.model_capabilities import supported_embedding_modalities
from backend.app.storage.paths import app_paths
from backend.app.application.models.provider_errors import raise_provider_error
import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.app.agent_runtime.model_types import (
    AssistantModelOutput,
    ModelRequest,
    ModelStreamChunk,
    ToolCall,
    ToolCallDelta,
)
from backend.app.core.errors import raise_error
from backend.app.core.cancellation import CancellationToken
from backend.app.core.model_retry import run_model_request
from backend.app.providers.base import ModelProvider
from backend.app.providers.errors import ProviderChatCompletionError
from backend.app.providers.default_registry import create_default_provider_registry
from backend.app.repositories.models.provider_repository import ModelProviderRepository
from backend.app.storage.models.codec import model_response
from backend.app.storage.models.provider_secrets import provider_secret_from_row
from backend.app.application.models.provider_resolution import resolve_provider, configured_provider_row


@dataclass(frozen=True)
class PreparedProviderRequest:
    """One provider request prepared once for both audit and transport."""

    provider: ModelProvider = field(repr=False)
    provider_id: str
    remote_model_id: str
    transport_request: ModelRequest
    provider_payload: dict[str, Any]
    transport_mode: str
    thinking_mode: str
    api_url: str
    api_key: str = field(repr=False)


class ModelProviderService:
    def __init__(self, provider_registry=None, repository=None, *, paths=None, official_service=None):
        self.paths = paths or getattr(repository, "paths", None) or app_paths()
        self.provider_registry = provider_registry
        self.official_service = official_service
        self.repository = repository or ModelProviderRepository(paths=self.paths)
        self._auth_repository = None

    def default_model_for_account(
        self, account_id: str, purpose: str = "chat"
    ) -> Optional[dict[str, Any]]:
        row = self.repository.default_model(account_id, purpose)
        return {**model_response(row), "default_purpose": purpose} if row else None

    def model_for_account(
        self, account_id: str, model_id: str
    ) -> Optional[dict[str, Any]]:
        row = self.repository.get_model(account_id, model_id)
        return model_response(row) if row else None

    @staticmethod
    def _require_model_type(model, model_type):
        if model["model_type"] != model_type:
            raise_error("invalid_structure", "INVALID_MODEL_TYPE", "模型类型不符合当前调用用途。")

    def complete_embedding_for_account(self, account_id, model_id, inputs, *, mode="independent", dimensions=None, cancellation_token=None, timeout_seconds=None, model_snapshot=None, check_running=None):
        inputs = deepcopy(inputs)
        model = self.model_for_account(account_id, model_id)
        if not model:
            raise_error("missing", "MODEL_NOT_FOUND", "模型不存在或未添加。")
        self._require_model_type(model, "embedding")
        if model_snapshot is not None:
            if model_snapshot.get("model_id") != model_id:
                raise_error("invalid_structure", "INVALID_MODEL_SNAPSHOT", "模型快照与请求模型标识不一致。")
            model = deepcopy(model_snapshot)
            self._require_model_type(model, "embedding")
        else:
            model = deepcopy(model)
        caps = model["embedding_capabilities"] or {}
        protocol = caps.get("protocol")
        if not protocol:
            raise_error("invalid_structure", "EMBEDDING_PROTOCOL_UNCONFIRMED", "请先检测向量接口。")
        if caps.get(mode) != "supported" or any(item["modality"] not in supported_embedding_modalities(caps) for item in inputs):
            raise_error("invalid_structure", "INVALID_EMBEDDING_INPUT", "输入模态或生成方式尚未确认支持。")
        input_count = 1 if mode == "fusion" else len(inputs)
        if model["max_batch_size"] and input_count > model["max_batch_size"]:
            raise_error("invalid_structure", "INVALID_EMBEDDING_INPUT", "输入数量超过已配置的批量输入上限。")
        provider = self._provider(model["provider_id"], account_id)
        row = self._provider_row(account_id, model["provider_id"])
        if not row or not row["is_configured"]:
            raise_error("invalid_structure", "MODEL_NOT_CONFIGURED", "请先配置该模型服务。")
        try:
            from backend.app.core.runtime.model_call_scope import observe_model_call
            return observe_model_call(account_id=account_id, kind="embedding", model=model,
                payload={"inputs": inputs, "mode": mode, "dimensions": dimensions},
                timeout_seconds=timeout_seconds,
                invoke=lambda remaining: self._run_account_request(
                    account_id=account_id, model=model,
                    api_url=row["api_url"] or provider.default_api_url,
                    check_running=check_running, cancellation_token=cancellation_token,
                    invoke=lambda api_key: provider.complete_embedding(
                        api_url=row["api_url"] or provider.default_api_url,
                        api_key=api_key, remote_model_id=model["remote_model_id"],
                        inputs=inputs, mode=mode,
                        purpose=model.get("default_purpose") or ("text_embedding" if all(item["modality"] == "text" for item in inputs) else "multimodal_embedding"),
                        dimensions=dimensions if dimensions is not None else model["embedding_dimensions"],
                        protocol=protocol, cancellation_token=cancellation_token, timeout_seconds=remaining,
                    ),
                ))
        except ProviderChatCompletionError as exc:
            raise_provider_error(exc)

    def complete_chat_for_account(
        self,
        account_id: str,
        model: dict[str, Any],
        model_request: ModelRequest,
        thinking_mode: str,
        timeout_seconds: Optional[float] = None,
        cancellation_token: CancellationToken | None = None,
        check_running=None,
    ):
        model = deepcopy(model)
        model_request = deepcopy(model_request)
        from backend.app.core.runtime.model_call_scope import current_model_stream_observer
        stream_observer = current_model_stream_observer()
        if stream_observer is not None:
            prepared = self.prepare_stream_chat_for_account(account_id=account_id, model=model,
                model_request=model_request, thinking_mode=thinking_mode)
            return stream_observer(account_id=account_id, kind='chat', model=model,
                payload=prepared.provider_payload, timeout_seconds=timeout_seconds,
                invoke=lambda remaining, token: self.stream_prepared_chat_for_account(
                    prepared_request=prepared, timeout_seconds=remaining, cancellation_token=token))
        self._require_model_type(model, "generation")
        provider_id = model["provider_id"]
        provider = self._provider(provider_id, account_id)
        row = self._provider_row(account_id, provider_id)
        if not row or not row["is_configured"]:
            raise_error(
                "invalid_structure", "MODEL_NOT_CONFIGURED", "请先配置该模型服务。"
            )
        api_key = self._api_key_from_row(account_id, row)
        if not api_key and provider.requires_api_key:
            raise_error(
                "invalid_structure", "MODEL_NOT_CONFIGURED", "请先输入或保存 API key。"
            )

        try:
            wire_request = self.prepare_transport_request(
                model,
                model_request,
                thinking_mode,
            )
            completion_arguments = {
                "api_url": row["api_url"] or provider.default_api_url,
                "api_key": api_key,
                "remote_model_id": model["remote_model_id"],
                "model_request": wire_request,
                "thinking_mode": thinking_mode,
            }
            completion_arguments["timeout_seconds"] = timeout_seconds
            completion_arguments["cancellation_token"] = cancellation_token
            from backend.app.core.runtime.model_call_scope import observe_model_call
            result = observe_model_call(account_id=account_id, kind="chat", model=model,
                payload={"system": wire_request.system, "messages": list(wire_request.messages),
                         "tools": [tool.as_dict() for tool in wire_request.tools]},
                timeout_seconds=timeout_seconds,
                invoke=lambda remaining: self._run_account_request(
                    account_id=account_id, model=model,
                    api_url=completion_arguments["api_url"],
                    check_running=check_running, cancellation_token=cancellation_token,
                    invoke=lambda current_api_key: provider.complete_chat(**{
                        **completion_arguments, "timeout_seconds": remaining, "api_key": current_api_key,
                    }),
                ))
            return self._transport_result(wire_request, model_request, result)
        except ProviderChatCompletionError as exc:
            raise_provider_error(exc)

    def _account_access_revision(self, account_id):
        from backend.app.repositories.auth_repository import AuthRepository

        if not self.paths.auth_db.is_file():
            raise_error("unauthenticated", "ACCOUNT_NOT_FOUND", "账号不存在。")
        if self._auth_repository is None:
            self._auth_repository = AuthRepository(paths=self.paths)
        account = self._auth_repository.account_by_id(account_id)
        if account is None:
            raise_error("unauthenticated", "ACCOUNT_NOT_FOUND", "账号不存在。")
        return account["access_revision"]

    def _run_account_request(
        self, *, account_id, model, api_url, invoke,
        cancellation_token=None, check_running=None,
    ):
        """Keep request inputs fixed while checking live access for every attempt."""
        access_revision = self._account_access_revision(account_id)
        credentials = {}

        def check():
            if check_running is not None:
                check_running()
            available = self.ensure_model_available(account_id, model)
            if available["access_revision"] != access_revision:
                raise_error("forbidden", "ACCOUNT_ACCESS_CHANGED", "账号访问权限已变更。")
            if available["api_url"].rstrip("/") != api_url.rstrip("/"):
                raise_error("conflict", "MODEL_PROVIDER_CHANGED", "模型服务地址已变更，请重新发起请求。")
            credentials["api_key"] = available["api_key"]

        return run_model_request(
            lambda: invoke(credentials["api_key"]), check_running=check,
            cancellation_token=cancellation_token,
        )

    def ensure_model_available(self, account_id, model):
        """Check live account/model/provider access without changing the snapshot."""
        revision = self._account_access_revision(account_id)
        current = self.model_for_account(account_id, model["model_id"])
        if current is None:
            raise_error("missing", "MODEL_NOT_FOUND", "模型不存在或未添加。")
        self._require_model_type(current, model["model_type"])
        provider = self._provider(model["provider_id"], account_id)
        row = self._provider_row(account_id, model["provider_id"])
        if not row or not row["is_configured"]:
            raise_error("invalid_structure", "MODEL_NOT_CONFIGURED", "请先配置该模型服务。")
        api_key = self._api_key_from_row(account_id, row)
        if not api_key and provider.requires_api_key:
            raise_error("invalid_structure", "MODEL_NOT_CONFIGURED", "请先输入或保存 API key。")
        return {"access_revision": revision,
                "api_url": row["api_url"] or provider.default_api_url, "api_key": api_key}

    def prepare_stream_chat_for_account(
        self,
        *,
        account_id: str,
        model: dict[str, Any],
        model_request: ModelRequest,
        thinking_mode: str,
    ) -> PreparedProviderRequest:
        """Prepare the exact streaming payload without sending it."""

        self._require_model_type(model, "generation")
        provider_id = str(model["provider_id"])
        provider = self._provider(provider_id, account_id)
        row = self._provider_row(account_id, provider_id)
        if not row or not row["is_configured"]:
            raise_error(
                "invalid_structure", "MODEL_NOT_CONFIGURED", "请先配置该模型服务。"
            )
        api_key = self._api_key_from_row(account_id, row)
        if not api_key and provider.requires_api_key:
            raise_error(
                "invalid_structure", "MODEL_NOT_CONFIGURED", "请先输入或保存 API key。"
            )
        transport_request = self.prepare_transport_request(
            model,
            model_request,
            thinking_mode,
        )
        payload = provider.build_chat_payload(
            remote_model_id=str(model["remote_model_id"]),
            model_request=transport_request,
            thinking_mode=thinking_mode,
            stream=True,
        )
        return PreparedProviderRequest(
            provider=provider,
            provider_id=provider_id,
            remote_model_id=str(model["remote_model_id"]),
            transport_request=transport_request,
            provider_payload=payload,
            transport_mode=transport_request.transport_mode,
            thinking_mode=thinking_mode,
            api_url=str(row["api_url"] or provider.default_api_url),
            api_key=api_key,
        )

    def stream_prepared_chat_for_account(
        self,
        *,
        prepared_request: PreparedProviderRequest,
        timeout_seconds: float | None = None,
        cancellation_token: CancellationToken | None = None,
    ):
        """Send an already prepared payload without serializing it again."""

        stream_arguments = {
            "api_url": prepared_request.api_url,
            "api_key": prepared_request.api_key,
            "provider_payload": prepared_request.provider_payload,
            "timeout_seconds": timeout_seconds,
        }
        stream_arguments["cancellation_token"] = cancellation_token
        stream = prepared_request.provider.stream_chat_payload(**stream_arguments)
        if prepared_request.transport_mode != "text_tool":
            return stream
        return self._stream_text_tool_result(stream)

    @staticmethod
    def prepare_transport_request(
        model: dict[str, Any],
        model_request: ModelRequest,
        thinking_mode: str,
    ) -> ModelRequest:
        model_config = dict(model_request.model_config)
        model_config.setdefault("purpose", model.get("default_purpose", "chat"))
        if (
            "max_output_tokens" not in model_config
            and "max_tokens" not in model_config
            and "max_completion_tokens" not in model_config
        ):
            max_output_tokens = model.get("max_output_tokens")
            if isinstance(max_output_tokens, int) and max_output_tokens > 0:
                model_config["max_output_tokens"] = max_output_tokens
        if not model_request.tools or _mode_supports(
            model,
            thinking_mode,
            "supports_tool_calling",
        ):
            return ModelRequest.build(
                system=model_request.system,
                messages=model_request.messages,
                tools=model_request.tools,
                context_sections=model_request.context_sections,
                tool_choice=model_request.tool_choice,
                model_config=model_config,
                transport_mode="native",
                output_schema=model_request.output_schema,
                supports_json_schema_output=model_request.supports_json_schema_output,
            )
        protocol = (
            "TEXT_TOOL_PROTOCOL\n"
            "当前 Provider 不支持原生工具调用。你仍只能使用下面列出的工具。"
            "严格输出一个 JSON 对象，不能输出 Markdown 或额外文字。"
            '调用工具：{"type":"tool_call","name":"工具名","arguments":{}}；'
            '结束回答：{"type":"final","content":"给用户的回答"}。\n'
            "AVAILABLE_TOOL_SCHEMAS\n"
            + json.dumps(
                [item.as_dict() for item in model_request.tools],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        translated: list[dict[str, Any]] = []
        for message in model_request.messages:
            role = str(message.get("role") or "user")
            if role == "assistant" and message.get("tool_calls"):
                calls = message.get("tool_calls")
                translated.append(
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "type": "tool_calls",
                                "calls": calls,
                                "content": message.get("content"),
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    }
                )
                continue
            if role == "tool":
                translated.append(
                    {
                        "role": "user",
                        "content": "TOOL_OBSERVATION\n"
                        + json.dumps(
                            {
                                "tool_call_id": message.get("tool_call_id"),
                                "name": message.get("name"),
                                "content": message.get("content"),
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    }
                )
                continue
            translated.append(dict(message))
        return ModelRequest.build(
            system=ModelProviderService._text_tool_system(
                model_request.system,
                protocol,
            ),
            messages=translated,
            tools=(),
            tool_choice=None,
            model_config=model_config,
            transport_mode="text_tool",
            output_schema=model_request.output_schema,
            supports_json_schema_output=model_request.supports_json_schema_output,
        )

    @staticmethod
    def _text_tool_system(system: str, protocol: str) -> str:
        """Place the real text Tool contract before Skill and runtime context."""

        if not system:
            return protocol
        markers = (
            "SKILL_CATALOG\n",
            "RUNTIME_CONTEXT\n",
        )
        positions = [
            position for marker in markers if (position := system.find(marker)) >= 0
        ]
        if not positions:
            return f"{system}\n\n{protocol}"
        insertion = min(positions)
        prefix = system[:insertion].rstrip()
        suffix = system[insertion:].lstrip()
        return "\n\n".join(item for item in (prefix, protocol, suffix) if item)

    @classmethod
    def _transport_result(
        cls,
        transport_request: ModelRequest,
        logical_request: ModelRequest,
        result: AssistantModelOutput,
    ) -> AssistantModelOutput:
        if not logical_request.tools or transport_request.transport_mode != "text_tool":
            return result
        parsed = cls._parse_text_tool_output(result.content)
        return AssistantModelOutput(
            content=parsed.content,
            reasoning=result.reasoning,
            tool_calls=parsed.tool_calls,
            usage=result.usage,
            stop_reason=("tool_calls" if parsed.tool_calls else result.stop_reason),
            raw_content=result.content,
        )

    @classmethod
    def _stream_text_tool_result(cls, stream):
        raw_parts: list[str] = []
        last_stop_reason: str | None = None
        for chunk in stream:
            if chunk.reasoning_delta:
                yield ModelStreamChunk(reasoning_delta=chunk.reasoning_delta)
            if chunk.content_delta:
                raw_parts.append(chunk.content_delta)
                yield ModelStreamChunk(raw_content_delta=chunk.content_delta)
            if chunk.usage:
                yield ModelStreamChunk(usage=dict(chunk.usage))
            if chunk.stop_reason:
                last_stop_reason = chunk.stop_reason
        parsed = cls._parse_text_tool_output("".join(raw_parts))
        if parsed.tool_calls:
            for index, call in enumerate(parsed.tool_calls):
                yield ModelStreamChunk(
                    tool_call_deltas=(
                        ToolCallDelta(
                            index=index,
                            id=call.id,
                            name_delta=call.name,
                            arguments_delta=json.dumps(
                                call.arguments,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        ),
                    ),
                )
            yield ModelStreamChunk(
                stop_reason="tool_calls",
            )
            return
        if parsed.content:
            yield ModelStreamChunk(content_delta=parsed.content)
        yield ModelStreamChunk(
            stop_reason=last_stop_reason or "stop",
        )

    @staticmethod
    def _parse_text_tool_output(value: str) -> AssistantModelOutput:
        text = str(value or "").strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderChatCompletionError(
                "文本工具协议返回的内容不是有效 JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderChatCompletionError("文本工具协议必须返回 JSON 对象")
        output_type = payload.get("type")
        if output_type == "final":
            if set(payload) != {"type", "content"}:
                raise ProviderChatCompletionError("文本工具协议 final 字段无效")
            content = str(payload.get("content") or "").strip()
            if not content:
                raise ProviderChatCompletionError("文本工具协议返回了空回答")
            return AssistantModelOutput(content=content, raw_content=value)
        if output_type == "tool_call":
            if set(payload) != {"type", "name", "arguments"}:
                raise ProviderChatCompletionError("文本工具协议 tool_call 字段无效")
            name = str(payload.get("name") or "").strip()
            arguments = payload.get("arguments")
            if not name or not isinstance(arguments, dict):
                raise ProviderChatCompletionError("文本工具协议工具名或参数无效")
            import uuid

            return AssistantModelOutput(
                tool_calls=(
                    ToolCall(
                        id=f"call_{uuid.uuid4().hex}",
                        name=name,
                        arguments=dict(arguments),
                    ),
                ),
                stop_reason="tool_calls",
                raw_content=value,
            )
        raise ProviderChatCompletionError("文本工具协议 type 必须是 tool_call 或 final")

    def provider_supports_native_attachment(
        self, model: dict[str, Any], mime_type: str
    ) -> bool:
        provider = self._provider(model["provider_id"])
        return provider.supports_native_attachment(mime_type)

    def _provider(self, provider_id: str, account_id=None):
        return resolve_provider(provider_id, account_id=account_id, repository=self.repository,
            registry=self.provider_registry or create_default_provider_registry(), paths=self.paths, official_service=self.official_service)

    def _provider_row(self, account_id: str, provider_id: str):
        provider = self._provider(provider_id, account_id)
        if provider_id == "serenita":
            return provider.connection_row()
        return configured_provider_row(provider, self.repository.get_provider(account_id, provider_id))

    def _api_key_from_row(self, account_id: str, row) -> str:
        if row and row["provider_id"] == "serenita":
            return self._provider("serenita", account_id).access_token()
        return provider_secret_from_row(account_id, row, paths=self.paths)


def _mode_supports(
    model: dict[str, Any],
    thinking_mode: str,
    capability: str,
) -> bool:
    profiles = model.get("capability_profiles")
    if not isinstance(profiles, dict):
        return bool(model.get(capability))
    if thinking_mode == "off":
        state = "non_thinking"
    elif thinking_mode == "default":
        state = str(profiles.get("default_state") or "unknown")
    else:
        state = "thinking"
    profile = profiles.get(state)
    if not isinstance(profile, dict):
        return bool(model.get(capability))
    return profile.get("availability") != "unavailable" and bool(
        profile.get(capability)
    )

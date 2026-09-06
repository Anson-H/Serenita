"""Deterministic model adapters shared by conversation tests."""

import threading
from backend.app.agent_runtime.model_types import AssistantModelOutput, ModelStreamChunk
from backend.app.application.model_provider_service import ModelProviderService, PreparedProviderRequest
from backend.app.providers.base import ModelProvider


class ConversationModelCatalog:
    model = {
        "model_id": "model_1",
        "provider_id": "test",
        "remote_model_id": "test-model",
        "model_name": "Test Model",
        "thinking_modes": ["default"],
        "file_mime_types": [],
        "supports_tool_calling": True,
    }

    def default_model_for_account(self, _account, purpose="chat"):
        return self.model if purpose in {"chat", "title"} else None

    def model_for_account(self, _account, model_id):
        return self.model if model_id == self.model["model_id"] else None

    def prepare_stream_chat_for_account(self, **kwargs):
        model = kwargs["model"]
        model_request = kwargs["model_request"]
        thinking_mode = kwargs["thinking_mode"]
        provider = ModelProvider()
        transport_request = ModelProviderService.prepare_transport_request(
            model,
            model_request,
            thinking_mode,
        )
        payload = provider.build_chat_payload(
            remote_model_id=model["remote_model_id"],
            model_request=transport_request,
            thinking_mode=thinking_mode,
            stream=True,
        )
        return PreparedProviderRequest(
            provider=provider,
            provider_id=model["provider_id"],
            remote_model_id=model["remote_model_id"],
            transport_request=transport_request,
            provider_payload=payload,
            transport_mode=transport_request.transport_mode,
            thinking_mode=thinking_mode,
            api_url="https://provider.example/v1",
            api_key="test-key",
        )

    def stream_prepared_chat_for_account(self, **kwargs):
        model_request = kwargs["prepared_request"].transport_request
        if model_request.model_config.get("purpose") == "agent_action":
            content = "核心结论：测试回答。"
        else:
            content = "测试会话"
        yield ModelStreamChunk(content_delta=content)
        yield ModelStreamChunk(stop_reason="end_turn")

    def complete_chat_for_account(self, **_kwargs):
        return AssistantModelOutput(content="测试会话", stop_reason="end_turn")

    def provider_supports_native_attachment(self, _model, _mime_type):
        return False


class BlockingConversationModelCatalog(ConversationModelCatalog):
    def __init__(self):
        self.first_chunk_persisted = threading.Event()
        self.release = threading.Event()

    def stream_prepared_chat_for_account(self, **kwargs):
        chunks = list(super().stream_prepared_chat_for_account(**kwargs))
        content = chunks[0].content_delta or ""
        split_at = min(8, max(1, len(content) // 2))
        yield ModelStreamChunk(content_delta=content[:split_at])
        self.first_chunk_persisted.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("test did not release the blocked provider stream")
        if content[split_at:]:
            yield ModelStreamChunk(content_delta=content[split_at:])
        yield ModelStreamChunk(stop_reason="end_turn")


class CompactCatalog:
    def __init__(self, model):
        self.model = model
        self.requests = []

    def default_model_for_account(self, _account, purpose="chat"):
        return self.model if purpose == "compact" else None

    def prepare_stream_chat_for_account(self, **kwargs):
        model_request = kwargs["model_request"]
        self.requests.append(model_request)
        provider = ModelProvider()
        transport_request = ModelProviderService.prepare_transport_request(
            kwargs["model"], model_request, kwargs["thinking_mode"]
        )
        payload = provider.build_chat_payload(
            remote_model_id=kwargs["model"]["remote_model_id"],
            model_request=transport_request,
            thinking_mode=kwargs["thinking_mode"],
            stream=True,
        )
        return PreparedProviderRequest(
            provider=provider,
            provider_id=kwargs["model"]["provider_id"],
            remote_model_id=kwargs["model"]["remote_model_id"],
            transport_request=transport_request,
            provider_payload=payload,
            transport_mode=transport_request.transport_mode,
            thinking_mode=kwargs["thinking_mode"],
            api_url="https://provider.example/v1",
            api_key="test-key",
        )

    def stream_prepared_chat_for_account(self, **_kwargs):
        yield ModelStreamChunk(
            content_delta="保留的医学事实：2026-01-01 ALT 45 U/L，来源为报告 r1；仍不确定。"
        )
        yield ModelStreamChunk(stop_reason="stop")

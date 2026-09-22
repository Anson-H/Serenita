"""Account-scoped access to the official, administrator-published model catalog."""
from dataclasses import asdict
import json
import httpx

from backend.app.agent_runtime.model_types import AssistantModelOutput, ModelStreamChunk, ToolCall, ToolCallDelta
from backend.app.core.errors import raise_error, SerenitaError
from backend.app.core.model_retry import current_retry_attempt, run_model_request
from backend.app.core.model_service_config import ModelServiceConfig
from backend.app.core.time import local_now, parse_local_datetime
from backend.app.domain.model_capabilities import IMAGE_FILE_MIME_TYPES, AUDIO_FILE_MIME_TYPES, VIDEO_FILE_MIME_TYPES, NATIVE_DOCUMENT_FILE_MIME_TYPES
from backend.app.providers.base import ModelProvider
from backend.app.providers.official_service import OfficialModelService
from backend.app.providers.embeddings import EmbeddingResult
from backend.app.providers.errors import ProviderChatCompletionError, connection_error
from backend.app.repositories.models.connection_repository import ModelConnectionRepository
from backend.app.schemas.model_service import GenerationRequest, EmbeddingRequest
from backend.app.storage.crypto import unseal_secret
from backend.app.storage.paths import app_paths


def official_http(url, path, *, token="", payload=None, method=None, cancellation_token=None, timeout_seconds=30):
    """One transport attempt. Redirects never receive the application token."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
            unregister = cancellation_token.register(client.close) if cancellation_token else lambda: None
            try:
                if cancellation_token:
                    cancellation_token.raise_if_cancelled()
                body = {"data": payload} if path in {"/api/serenita/device/authorize", "/api/serenita/device/token"} else {"json": payload}
                response = client.request(method or ("POST" if payload is not None else "GET"), url + path, **body, headers=headers)
                if response.is_redirect:
                    raise ProviderChatCompletionError("官方服务地址发生重定向，请检查部署配置。", code="OFFICIAL_URL_CHANGED")
                try:
                    value = response.json()
                except ValueError:
                    official_error({}, response.status_code)
                if not isinstance(value, dict):
                    official_error({}, response.status_code)
                if response.is_error and not (path.endswith("/device/token") and "error" in value):
                    official_error(value, response.status_code)
                return value
            finally:
                unregister()
    except httpx.TransportError as error:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        raise connection_error(error) from error


def official_error(value, status=None):
    detail = value.get("detail", value.get("error", {}))
    if not isinstance(detail, dict):
        detail = {}
    raise ProviderChatCompletionError(detail.get("message", "官方模型服务请求失败。"),
        code=detail.get("code", "MODEL_ERROR"), upstream_status=detail.get("upstream_status", status),
        capability_rejected=detail.get("code") in {"INVALID_THINKING_MODE", "MODEL_CAPABILITY_UNAVAILABLE", "INVALID_EMBEDDING_INPUT", "VECTOR_DIMENSIONS_FIXED"})


class SerenitaProvider(ModelProvider):
    provider_id = "serenita"
    provider_name = "Serenita"
    provider_kind = "managed"
    requires_api_key = False

    def __init__(self, *, account_id=None, paths=None, official_service: OfficialModelService | None = None):
        super().__init__()
        self.inspection_model = None
        self.account_id = account_id
        self.official_service = official_service
        self.paths = paths or app_paths()
        self.config = ModelServiceConfig.from_environment()
        self.default_api_url = self.config.official_url
        self.default_official_url = self.config.official_url

    def native_attachment_mime_types(self):
        from backend.app.providers.default_registry import create_default_provider_registry
        types = set(IMAGE_FILE_MIME_TYPES + AUDIO_FILE_MIME_TYPES + VIDEO_FILE_MIME_TYPES + NATIVE_DOCUMENT_FILE_MIME_TYPES)
        for provider in create_default_provider_registry().providers():
            types.update(provider.native_attachment_mime_types())
        return types

    def connection_row(self):
        configured = self.config.official and bool(self.account_id)
        if not configured and self.account_id:
            state = ModelConnectionRepository(paths=self.paths, account_id=self.account_id).local_state()
            configured = bool(self.config.official_url and state["official_url"] == self.config.official_url and state["encrypted_token"]
                and state["expires_at"] and parse_local_datetime(state["expires_at"]) > local_now())
        return {"provider_id": self.provider_id, "provider_name": self.provider_name, "api_url": self.default_api_url,
            "official_url": self.default_official_url, "is_configured": configured, "encrypted_api_key": None}

    def public_summary(self):
        row = self.connection_row()
        return {key: value for key, value in {**row, "provider_kind": self.provider_kind, "has_api_key": False,
            "default_api_url": self.default_api_url, "default_official_url": self.default_official_url,
            "native_attachment_mime_types": sorted(self.native_attachment_mime_types())}.items() if key != "encrypted_api_key"}

    def access_token(self):
        if self.config.official:
            return ""
        if not self.connection_row()["is_configured"]:
            raise_error("unauthenticated", "OFFICIAL_LOGIN_REQUIRED", "请先连接官方账号以使用 Serenita 免费模型。")
        state = ModelConnectionRepository(paths=self.paths, account_id=self.account_id).local_state()
        return unseal_secret(self.account_id, "serenita-token", state["encrypted_token"], paths=self.paths)

    def _service(self) -> OfficialModelService:
        if self.official_service is None:
            raise RuntimeError("Official deployment requires an injected model service")
        return self.official_service

    def catalog(self, cancellation_token=None):
        return run_model_request(lambda: self._service().catalog(self.account_id) if self.config.official else
            official_http(self.default_api_url, "/api/serenita/models", token=self.access_token(), cancellation_token=cancellation_token),
            cancellation_token=cancellation_token)

    def list_models(self, *, cancellation_token=None, **_):
        from backend.app.providers.types import ProviderModel
        return [ProviderModel(remote_model_id=item["remote_model_id"], model_name=item["model_name"],
            model_type=item["model_type"], embedding_dimensions=[item["embedding_dimensions"]] if item["embedding_dimensions"] else [],
            supports_text=item["supports_text"], file_mime_types=item["file_mime_types"],
            thinking_modes=item["thinking_modes"] or ["default"], supports_tool_calling=item["supports_tool_calling"],
            default_thinking_state=(item["capability_profiles"] or {}).get("default_state", "unknown"),
            context_window_tokens=item["context_window_tokens"], max_output_tokens=item["max_output_tokens"])
            for item in self.catalog(cancellation_token)["models"]]

    def embedding_modalities(self, protocol):
        return {"text", "image", "audio", "video", "document"}

    def test_access(self, cancellation_token=None):
        catalog = self.catalog(cancellation_token)
        return asdict(self.success(f"已连接，当前开放 {len(catalog['models'])} 个模型。"))

    def build_chat_payload(self, *, remote_model_id, model_request, thinking_mode, stream):
        if self.inspection_model:
            config = dict(model_request.model_config)
            maximum = self.inspection_model["max_output_tokens"]
            if maximum is not None and isinstance(config.get("max_tokens"), int):
                config["max_tokens"] = min(config["max_tokens"], maximum)
            model_request = type(model_request).build(**{**model_request.canonical_dict(), "tools": model_request.tools, "model_config": config})
        return {"model_id": remote_model_id, "request": model_request.canonical_dict(), "thinking_mode": thinking_mode,
                "stream": stream, "attempt": current_retry_attempt()}

    def complete_chat(self, api_url=None, api_key=None, remote_model_id=None, model_request=None, thinking_mode="default", timeout_seconds=None, cancellation_token=None):
        payload = self.build_chat_payload(remote_model_id=remote_model_id, model_request=model_request, thinking_mode=thinking_mode, stream=False)
        payload["timeout_seconds"] = timeout_seconds
        def invoke():
            payload["attempt"] = current_retry_attempt()
            if self.config.official:
                try:
                    return self._service().generate(self.account_id, GenerationRequest.model_validate(payload), cancellation_token=cancellation_token)
                except SerenitaError as error:
                    official_error({"detail": error.detail})
            value = official_http(self.default_api_url, "/api/serenita/generate", token=self.access_token(), payload=payload,
                timeout_seconds=timeout_seconds or self.attachment_timeout_seconds, cancellation_token=cancellation_token)
            return AssistantModelOutput(**{**value, "tool_calls": tuple(ToolCall(**item) for item in value["tool_calls"])})
        return run_model_request(invoke, cancellation_token=cancellation_token)

    def stream_chat_payload(self, *, provider_payload, timeout_seconds=None, cancellation_token=None, **_):
        payload = {**provider_payload, "stream": True, "timeout_seconds": timeout_seconds, "attempt": current_retry_attempt()}
        if self.config.official:
            yield from self._service().generate(self.account_id, GenerationRequest.model_validate(payload), cancellation_token=cancellation_token)
            return
        try:
            with httpx.Client(timeout=timeout_seconds or self.attachment_timeout_seconds, follow_redirects=False) as client:
                unregister = cancellation_token.register(client.close) if cancellation_token else lambda: None
                try:
                    if cancellation_token:
                        cancellation_token.raise_if_cancelled()
                    with client.stream("POST", self.default_api_url + "/api/serenita/generate", json=payload,
                            headers={"Authorization": f"Bearer {self.access_token()}"}) as response:
                        if response.status_code != 200:
                            response.read()
                            official_error(response.json(), response.status_code)
                        completed = False
                        for line in response.iter_lines():
                            if cancellation_token:
                                cancellation_token.raise_if_cancelled()
                            if not line.startswith("data: "):
                                continue
                            if line[6:] == "[DONE]":
                                completed = True
                                break
                            value = json.loads(line[6:])
                            if "error" in value:
                                official_error(value)
                            yield ModelStreamChunk(**{**value, "tool_call_deltas": tuple(ToolCallDelta(**item) for item in value["tool_call_deltas"])})
                        if not completed:
                            raise ProviderChatCompletionError("官方模型输出连接中断。", code="MODEL_STREAM_INCOMPLETE")
                finally:
                    unregister()
        except httpx.TransportError as error:
            if cancellation_token:
                cancellation_token.raise_if_cancelled()
            raise connection_error(error) from error

    def complete_embedding(self, *, remote_model_id, inputs, mode="independent", dimensions=None, timeout_seconds=None, cancellation_token=None, purpose="embedding", **_):
        payload = dict(model_id=remote_model_id, inputs=inputs, mode=mode, dimensions=dimensions, timeout_seconds=timeout_seconds, purpose=purpose)
        def invoke():
            payload["attempt"] = current_retry_attempt()
            if self.config.official:
                try:
                    return self._service().embed(self.account_id, EmbeddingRequest.model_validate(payload), cancellation_token=cancellation_token)
                except SerenitaError as error:
                    official_error({"detail": error.detail})
            value = official_http(self.default_api_url, "/api/serenita/embed", token=self.access_token(), payload=payload,
                timeout_seconds=timeout_seconds or self.attachment_timeout_seconds, cancellation_token=cancellation_token)
            return EmbeddingResult(**value)
        return run_model_request(invoke, cancellation_token=cancellation_token)

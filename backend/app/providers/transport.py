from backend.app.providers.types import ProviderModel
import httpx
import json
from http.client import IncompleteRead
from typing import Any, List, Optional
from urllib import error, parse, request

from backend.app.agent_runtime.model_types import (
    AssistantModelOutput,
    ModelRequest,
)
from backend.app.core.cancellation import (
    CancellationToken,
    OperationCancelledError,
)


from backend.app.providers.errors import (
    ProviderChatCompletionError,
    ProviderModelListError,
    _decode_error_body,
    connection_error,
    model_list_error,
)
from backend.app.providers.types import ProviderConnectionResult


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


class ProviderTransport:
    def request_json(self, *, url, api_key, payload=None, cancellation_token=None, timeout_seconds=None):
        headers = {**self.policy.authorization_headers(api_key), "Content-Type": "application/json", "Accept": "application/json"}
        content = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
        method = "POST" if payload is not None else "GET"
        timeout = self._request_timeout(timeout_seconds, self.policy.timeout_seconds)
        _, body, _ = self._request_bytes(
            method=method, url=url, headers=headers, content=content,
            timeout_seconds=timeout, cancellation_token=cancellation_token,
        )
        try:
            result = json.loads(body)
        except (ValueError, UnicodeError) as exc:
            raise ProviderChatCompletionError("接口返回的 JSON 无效", code="INVALID_MODEL_RESPONSE") from exc
        self.errors.raise_payload_error(result)
        if not isinstance(result, dict) or result.get("error") or result.get("code"):
            raise ProviderChatCompletionError("接口未返回有效结果", code="INVALID_MODEL_RESPONSE")
        return result

    @staticmethod
    def _request_timeout(timeout_seconds, default):
        if timeout_seconds is None:
            return default
        return None if float(timeout_seconds) <= 0 else max(0.001, float(timeout_seconds))

    def _request_bytes(
        self, *, method, url, headers, timeout_seconds,
        cancellation_token=None, content=None,
    ):
        """Perform exactly one request and preserve sanitized HTTP diagnostics."""
        try:
            if cancellation_token is not None:
                status, body, response_headers = self._request_bytes_cancellable(
                    method=method, url=url, headers=headers, content=content,
                    timeout_seconds=timeout_seconds, cancellation_token=cancellation_token,
                )
            else:
                with self._urlopen(
                    request.Request(url, data=content, headers=headers, method=method),
                    timeout=timeout_seconds,
                ) as response:
                    status = response.status if hasattr(response, "status") else response.getcode()
                    body = response.read()
                    response_headers = getattr(response, "headers", None)
        except error.HTTPError as exc:
            try:
                failure = self.errors.completion_error(
                    exc.code, _decode_error_body(exc.read(16 * 1024)), exc.headers
                )
            finally:
                exc.close()
            raise failure from exc
        except (OSError, IncompleteRead, httpx.TransportError) as exc:
            raise connection_error(exc) from exc
        if not 200 <= status < 300:
            raise self.errors.completion_error(status, _decode_error_body(body), response_headers)
        return status, body, response_headers

    def __init__(
        self,
        policy,
        errors,
        responses,
        *,
        urlopen=request.urlopen,
        stream_client_factory=None,
    ):
        self.policy = policy
        self.errors = errors
        self.responses = responses
        self._urlopen = urlopen
        self._stream_client_factory = stream_client_factory

    def test_connection(self, api_url: str, api_key: str, cancellation_token=None) -> ProviderConnectionResult:
        normalized_api_url = (api_url or self.policy.default_api_url).rstrip("/")
        if not normalized_api_url:
            return self.policy.failure("缺少 API 地址")
        if not api_key.strip() and self.policy.requires_api_key:
            return self.policy.failure("缺少 API key")
        self.request_json(
            url=normalized_api_url + self.policy.connection_test_path,
            api_key=api_key,
            timeout_seconds=self.policy.timeout_seconds,
            cancellation_token=cancellation_token,
        )
        return ProviderConnectionResult(
            provider_id=self.policy.provider_id, reachable=True,
            message="API Key 验证成功。" if api_key.strip() else "连接测试成功。",
        )

    def list_models(
        self,
        api_url: str,
        api_key: str,
        cancellation_token: CancellationToken | None = None,
    ) -> List[ProviderModel]:
        normalized_api_url = (api_url or self.policy.default_api_url).rstrip("/")
        if not normalized_api_url:
            raise ProviderModelListError("缺少 API 地址")
        if not api_key.strip() and self.policy.requires_api_key:
            raise ProviderModelListError("缺少 API key")
        try:
            _, body, _ = self._request_bytes(
                method="GET", url=f"{normalized_api_url}/models",
                headers={"Accept": "application/json", **self.policy.authorization_headers(api_key)},
                timeout_seconds=self.policy.timeout_seconds,
                cancellation_token=cancellation_token,
            )
        except ProviderChatCompletionError as exc:
            raise model_list_error(exc) from exc
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderModelListError("模型服务返回的模型列表不是有效 JSON") from exc
        try:
            self.errors.raise_payload_error(payload)
        except ProviderChatCompletionError as exc:
            raise model_list_error(exc) from exc
        return self.policy.parse_model_payload(payload)

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
        normalized_api_url = (api_url or self.policy.default_api_url).rstrip("/")
        if not normalized_api_url:
            raise ProviderChatCompletionError("缺少 API 地址")
        if not api_key.strip() and self.policy.requires_api_key:
            raise ProviderChatCompletionError("缺少 API key")
        if not remote_model_id.strip():
            raise ProviderChatCompletionError("缺少模型 ID")

        payload = self.policy.build_chat_payload(
            remote_model_id=remote_model_id,
            model_request=model_request,
            thinking_mode=thinking_mode,
            stream=False,
        )
        request_timeout_seconds = self._request_timeout(
            timeout_seconds, self._chat_completion_timeout_seconds(payload["messages"])
        )
        _, body, _ = self._request_bytes(
            method="POST", url=f"{normalized_api_url}/chat/completions",
            headers={
                "Accept": "application/json", **self.policy.authorization_headers(api_key),
                "Content-Type": "application/json",
            },
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout_seconds=request_timeout_seconds, cancellation_token=cancellation_token,
        )

        try:
            completion_payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderChatCompletionError(
                "模型服务返回的对话结果不是有效 JSON"
            ) from exc

        return self.responses.completion(completion_payload)

    def stream_chat_payload(
        self,
        *,
        api_url: str,
        api_key: str,
        provider_payload: dict[str, Any],
        timeout_seconds: float | None = None,
        cancellation_token: CancellationToken | None = None,
    ):
        """Stream the exact prepared payload without rebuilding it."""

        normalized_api_url = (api_url or self.policy.default_api_url).rstrip("/")
        if not normalized_api_url:
            raise ProviderChatCompletionError("缺少 API 地址")
        if not api_key.strip() and self.policy.requires_api_key:
            raise ProviderChatCompletionError("缺少 API key")
        payload_model_id = str(provider_payload.get("model") or "")
        if not payload_model_id.strip():
            raise ProviderChatCompletionError("缺少模型 ID")

        serialized_messages = provider_payload.get("messages")
        if not isinstance(serialized_messages, list):
            raise ProviderChatCompletionError("模型请求缺少消息列表")
        request_timeout_seconds: float | None = self._chat_completion_timeout_seconds(
            serialized_messages
        )
        if timeout_seconds is not None:
            request_timeout_seconds = (
                None
                if float(timeout_seconds) <= 0
                else max(0.001, float(timeout_seconds))
            )

        if cancellation_token is not None:
            yield from self._stream_chat_payload_cancellable(
                url=f"{normalized_api_url}/chat/completions",
                api_key=api_key,
                provider_payload=provider_payload,
                timeout_seconds=request_timeout_seconds,
                cancellation_token=cancellation_token,
            )
            return

        completion_request = request.Request(
            f"{normalized_api_url}/chat/completions",
            data=json.dumps(provider_payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Accept": "text/event-stream",
                **self.policy.authorization_headers(api_key),
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with self._urlopen(
                completion_request, timeout=request_timeout_seconds
            ) as response:
                status = (
                    response.status
                    if hasattr(response, "status")
                    else response.getcode()
                )
                if not 200 <= status < 300:
                    raise self.errors.completion_error(
                        status, _decode_error_body(response.read()), getattr(response, "headers", None)
                    )
                yield from self.responses.stream(response)
        except error.HTTPError as exc:
            try:
                failure = self.errors.completion_error(
                    exc.code, _decode_error_body(exc.read(16 * 1024)), exc.headers
                )
            finally:
                exc.close()
            raise failure from exc
        except (OSError, IncompleteRead, httpx.TransportError) as exc:
            raise connection_error(exc) from exc

    def _request_bytes_cancellable(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        timeout_seconds: float | None,
        cancellation_token: CancellationToken,
        content: bytes | None = None,
    ) -> tuple[int, bytes, Any]:
        """Send a closeable request so cancellation interrupts blocking I/O."""

        cancellation_token.raise_if_cancelled()
        client = self._new_stream_client(url, timeout_seconds)
        unregister_client = cancellation_token.register(client.close)
        try:
            cancellation_token.raise_if_cancelled()
            with client.stream(
                method,
                url,
                content=content,
                headers=headers,
            ) as response:
                unregister_response = cancellation_token.register(response.close)
                try:
                    cancellation_token.raise_if_cancelled()
                    body = response.read()
                    cancellation_token.raise_if_cancelled()
                    return int(response.status_code), body, response.headers
                finally:
                    unregister_response()
        except OperationCancelledError:
            raise
        except (OSError, IncompleteRead, httpx.TransportError) as exc:
            if cancellation_token.is_cancelled:
                raise OperationCancelledError("操作已取消。") from exc
            raise connection_error(exc) from exc
        except Exception as exc:
            if cancellation_token.is_cancelled:
                raise OperationCancelledError("操作已取消。") from exc
            raise
        finally:
            unregister_client()
            client.close()

    def _stream_chat_payload_cancellable(
        self,
        *,
        url: str,
        api_key: str,
        provider_payload: dict[str, Any],
        timeout_seconds: float | None,
        cancellation_token: CancellationToken,
    ):
        """Stream through a closeable client so cancellation interrupts TTFB too."""

        cancellation_token.raise_if_cancelled()
        client = self._new_stream_client(url, timeout_seconds)
        unregister_client = cancellation_token.register(client.close)
        try:
            cancellation_token.raise_if_cancelled()
            with client.stream(
                "POST",
                url,
                content=json.dumps(
                    provider_payload,
                    ensure_ascii=False,
                ).encode("utf-8"),
                headers={
                    "Accept": "text/event-stream",
                    **self.policy.authorization_headers(api_key),
                    "Content-Type": "application/json",
                },
            ) as response:
                unregister_response = cancellation_token.register(response.close)
                try:
                    cancellation_token.raise_if_cancelled()
                    status = int(response.status_code)
                    if not 200 <= status < 300:
                        body = response.read()
                        cancellation_token.raise_if_cancelled()
                        raise self.errors.completion_error(
                            status, _decode_error_body(body), response.headers
                        )
                    yield from self.responses.stream(
                        response.iter_lines(), cancellation_token
                    )
                finally:
                    unregister_response()
        except OperationCancelledError:
            raise
        except (OSError, IncompleteRead, httpx.TransportError) as exc:
            if cancellation_token.is_cancelled:
                raise OperationCancelledError("操作已取消。") from exc
            raise connection_error(exc) from exc
        except Exception as exc:
            if cancellation_token.is_cancelled:
                raise OperationCancelledError("操作已取消。") from exc
            raise
        finally:
            unregister_client()
            client.close()

    def _new_stream_client(
        self,
        url: str,
        timeout_seconds: float | None,
    ):
        if self._stream_client_factory is not None:
            return self._stream_client_factory(timeout=timeout_seconds)
        parsed_url = parse.urlsplit(url)
        proxy_url = None
        if not request.proxy_bypass(parsed_url.hostname or ""):
            # Match urllib's scheme-specific behavior. In particular, do not
            # let an unrelated ALL_PROXY SOCKS value override HTTPS_PROXY and
            # introduce an optional socksio dependency into ordinary requests.
            proxy_url = request.getproxies().get(parsed_url.scheme)
        return httpx.Client(
            timeout=timeout_seconds,
            proxy=proxy_url,
            trust_env=False,
        )

    def _chat_completion_timeout_seconds(self, messages: list[dict[str, Any]]) -> int:
        if _messages_include_native_attachment(messages):
            return max(
                self.policy.timeout_seconds, self.policy.attachment_timeout_seconds
            )
        return self.policy.timeout_seconds

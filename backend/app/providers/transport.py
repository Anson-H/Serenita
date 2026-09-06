from backend.app.providers.errors import _http_error_code
from backend.app.providers.types import ProviderModel
import httpx
import json
import socket
import time
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

    def test_connection(self, api_url: str, api_key: str) -> ProviderConnectionResult:
        normalized_api_url = (api_url or self.policy.default_api_url).rstrip("/")
        if not normalized_api_url:
            return self.policy.failure("缺少 API 地址")
        if not api_key.strip():
            return self.policy.failure("缺少 API key")

        connection_request = request.Request(
            f"{normalized_api_url}/models",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="GET",
        )

        try:
            with self._urlopen(
                connection_request, timeout=self.policy.timeout_seconds
            ) as response:
                status = (
                    response.status
                    if hasattr(response, "status")
                    else response.getcode()
                )
        except error.HTTPError as exc:
            if exc.code in (401, 403):
                return self.policy.failure(
                    "模型服务认证失败", code="PROVIDER_AUTH_FAILED"
                )
            return self.policy.failure(
                f"模型服务连接失败，HTTP {exc.code}", code=_http_error_code(exc.code)
            )
        except (TimeoutError, socket.timeout):
            return self.policy.failure("连接超时", code="MODEL_TIMEOUT")
        except error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                return self.policy.failure("连接超时", code="MODEL_TIMEOUT")
            return self.policy.failure("模型服务连接失败")

        if 200 <= status < 300:
            return ProviderConnectionResult(
                provider_id=self.policy.provider_id,
                reachable=True,
                message="连接测试成功",
            )
        if status in (401, 403):
            return self.policy.failure("模型服务认证失败", code="PROVIDER_AUTH_FAILED")
        return self.policy.failure(
            f"模型服务连接失败，HTTP {status}", code=_http_error_code(status)
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
        if not api_key.strip():
            raise ProviderModelListError("缺少 API key")

        url = f"{normalized_api_url}/models"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        if cancellation_token is not None:
            try:
                status, body = self._request_bytes_cancellable(
                    method="GET",
                    url=url,
                    headers=headers,
                    timeout_seconds=self.policy.timeout_seconds,
                    cancellation_token=cancellation_token,
                )
            except OperationCancelledError:
                raise
            except TimeoutError as exc:
                raise ProviderModelListError("连接超时", code="MODEL_TIMEOUT") from exc
            except OSError as exc:
                raise ProviderModelListError("模型服务连接失败") from exc
        else:
            model_request = request.Request(
                url,
                headers=headers,
                method="GET",
            )

            try:
                with self._urlopen(
                    model_request, timeout=self.policy.timeout_seconds
                ) as response:
                    status = (
                        response.status
                        if hasattr(response, "status")
                        else response.getcode()
                    )
                    body = response.read()
            except error.HTTPError as exc:
                if exc.code in (401, 403):
                    raise ProviderModelListError(
                        "模型服务认证失败", code="PROVIDER_AUTH_FAILED"
                    ) from exc
                raise ProviderModelListError(
                    f"模型服务连接失败，HTTP {exc.code}",
                    code=_http_error_code(exc.code),
                ) from exc
            except (TimeoutError, socket.timeout) as exc:
                raise ProviderModelListError("连接超时", code="MODEL_TIMEOUT") from exc
            except error.URLError as exc:
                if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                    raise ProviderModelListError(
                        "连接超时", code="MODEL_TIMEOUT"
                    ) from exc
                raise ProviderModelListError("模型服务连接失败") from exc

        if not 200 <= status < 300:
            if status in (401, 403):
                raise ProviderModelListError(
                    "模型服务认证失败", code="PROVIDER_AUTH_FAILED"
                )
            raise ProviderModelListError(
                f"模型服务连接失败，HTTP {status}", code=_http_error_code(status)
            )

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderModelListError("模型服务返回的模型列表不是有效 JSON") from exc

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
        if not api_key.strip():
            raise ProviderChatCompletionError("缺少 API key")
        if not remote_model_id.strip():
            raise ProviderChatCompletionError("缺少模型 ID")

        payload = self.policy.build_chat_payload(
            remote_model_id=remote_model_id,
            model_request=model_request,
            thinking_mode=thinking_mode,
            stream=False,
        )
        serialized_messages = payload["messages"]
        request_timeout_seconds: float | None = self._chat_completion_timeout_seconds(
            serialized_messages
        )
        explicit_timeout = timeout_seconds is not None
        no_timeout = explicit_timeout and float(timeout_seconds) <= 0
        if no_timeout:
            request_timeout_seconds = None
        elif explicit_timeout:
            request_timeout_seconds = max(0.001, float(timeout_seconds))
        deadline = (
            time.monotonic() + timeout_seconds
            if timeout_seconds is not None and timeout_seconds > 0
            else None
        )

        if cancellation_token is not None:
            try:
                status, body = self._request_bytes_cancellable(
                    method="POST",
                    url=f"{normalized_api_url}/chat/completions",
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    timeout_seconds=request_timeout_seconds,
                    cancellation_token=cancellation_token,
                )
            except OperationCancelledError:
                raise
            except TimeoutError as exc:
                raise ProviderChatCompletionError(
                    "连接超时", code="MODEL_TIMEOUT"
                ) from exc
            except OSError as exc:
                raise ProviderChatCompletionError("模型服务调用失败") from exc

            if not 200 <= status < 300:
                raise self.errors.completion_error(status, _decode_error_body(body))
            try:
                completion_payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProviderChatCompletionError(
                    "模型服务返回的对话结果不是有效 JSON"
                ) from exc
            return self.responses.completion(completion_payload)

        completion_request = request.Request(
            f"{normalized_api_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        # Explicit calls are non-idempotent and use one attempt. A non-positive
        # timeout explicitly disables the transport deadline for background work.
        attempts = 1 if explicit_timeout else 3
        for attempt in range(attempts):
            remaining = deadline - time.monotonic() if deadline is not None else None
            if remaining is not None and remaining <= 0:
                raise ProviderChatCompletionError("连接超时", code="MODEL_TIMEOUT")
            attempt_timeout = request_timeout_seconds
            if remaining is not None and request_timeout_seconds is not None:
                attempt_timeout = min(request_timeout_seconds, max(0.001, remaining))
            try:
                with self._urlopen(
                    completion_request, timeout=attempt_timeout
                ) as response:
                    status = (
                        response.status
                        if hasattr(response, "status")
                        else response.getcode()
                    )
                    body = response.read()
            except error.HTTPError as exc:
                failure = self.errors.completion_error(
                    exc.code, _decode_error_body(exc.read(16 * 1024)), exc.headers
                )
                if (
                    500 <= exc.code < 600
                    and attempt < attempts - 1
                    and not failure.is_context_overflow
                ):
                    continue
                raise failure from exc
            except (TimeoutError, socket.timeout) as exc:
                if attempt < attempts - 1:
                    continue
                raise ProviderChatCompletionError(
                    "连接超时", code="MODEL_TIMEOUT"
                ) from exc
            except error.URLError as exc:
                if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                    if attempt < attempts - 1:
                        continue
                    raise ProviderChatCompletionError(
                        "连接超时", code="MODEL_TIMEOUT"
                    ) from exc
                if attempt < attempts - 1:
                    continue
                raise ProviderChatCompletionError("模型服务调用失败") from exc

            if 200 <= status < 300:
                break
            failure = self.errors.completion_error(status, _decode_error_body(body))
            if (
                500 <= status < 600
                and attempt < attempts - 1
                and not failure.is_context_overflow
            ):
                continue
            raise failure

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
        if not api_key.strip():
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
                "Authorization": f"Bearer {api_key}",
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
                        status, _decode_error_body(response.read())
                    )
                yield from self.responses.stream(response)
        except error.HTTPError as exc:
            raise self.errors.completion_error(
                exc.code, _decode_error_body(exc.read(16 * 1024)), exc.headers
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ProviderChatCompletionError("连接超时", code="MODEL_TIMEOUT") from exc
        except error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ProviderChatCompletionError(
                    "连接超时", code="MODEL_TIMEOUT"
                ) from exc
            raise ProviderChatCompletionError("模型服务调用失败") from exc

    def _request_bytes_cancellable(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        timeout_seconds: float | None,
        cancellation_token: CancellationToken,
        content: bytes | None = None,
    ) -> tuple[int, bytes]:
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
                    return int(response.status_code), body
                finally:
                    unregister_response()
        except OperationCancelledError:
            raise
        except httpx.TimeoutException as exc:
            if cancellation_token.is_cancelled:
                raise OperationCancelledError("操作已取消。") from exc
            raise TimeoutError("连接超时") from exc
        except httpx.HTTPError as exc:
            if cancellation_token.is_cancelled:
                raise OperationCancelledError("操作已取消。") from exc
            raise OSError("模型服务调用失败") from exc
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
                    "Authorization": f"Bearer {api_key}",
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
        except httpx.TimeoutException as exc:
            if cancellation_token.is_cancelled:
                raise OperationCancelledError("操作已取消。") from exc
            raise ProviderChatCompletionError("连接超时", code="MODEL_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            if cancellation_token.is_cancelled:
                raise OperationCancelledError("操作已取消。") from exc
            raise ProviderChatCompletionError("模型服务调用失败") from exc
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

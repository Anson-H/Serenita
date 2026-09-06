import io
import json
from urllib import error
import httpx
import pytest
from backend.app.agent_runtime.model_types import ModelRequest
from backend.app.core.cancellation import CancellationToken
from backend.app.providers.aliyun_bailian import AliyunBailianProvider
from backend.app.providers.errors import ProviderChatCompletionError
from backend.app.providers.deepseek import DeepSeekProvider
from backend.app.providers.openrouter import OpenRouterProvider


PROVIDERS = (AliyunBailianProvider, DeepSeekProvider, OpenRouterProvider)
TRANSPORTS = (
    "urllib-complete", "urllib-stream",
    "urllib-status-complete", "urllib-status-stream",
    "httpx-complete", "httpx-stream",
)
CONTEXT_ERROR = {"error": {"code": "context_length_exceeded", "message": "private prompt"}}


def invoke(provider_class, transport, *, status=400, payload=None, body=None, failure=None):
    if body is None:
        body = json.dumps(payload).encode()

    class Response(io.BytesIO):
        def __init__(self):
            super().__init__(body)
            self.status = status

    def urlopen(request, timeout):
        if failure is not None:
            raise failure
        if status >= 400 and "status" not in transport:
            raise error.HTTPError(
                request.full_url, status, "upstream failure",
                {"x-request-id": "test-request"}, io.BytesIO(body),
            )
        return Response()

    def handler(request):
        if failure is not None:
            raise failure
        return httpx.Response(status, content=body, headers={"x-request-id": "test-request"})

    provider = provider_class(
        urlopen=urlopen,
        stream_client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    kwargs = dict(
        api_url="https://provider.example/v1",
        api_key="test-key",
        remote_model_id="test-model",
        model_request=ModelRequest.build(
            system="", messages=[{"role": "user", "content": "hello"}]
        ),
        timeout_seconds=1,
    )
    if transport.startswith("httpx"):
        kwargs["cancellation_token"] = CancellationToken()
    if transport.endswith("stream"):
        return list(provider.stream_chat(**kwargs))
    return provider.complete_chat(**kwargs)


def assert_overflow(exc):
    assert exc.code == "CONTEXT_WINDOW_EXCEEDED"
    assert exc.is_context_overflow is True
    assert "private prompt" not in str(exc)


def test_exception_interface_uses_explicit_code_only():
    ordinary = ProviderChatCompletionError("context_length_exceeded")
    assert ordinary.args == ("context_length_exceeded",)
    assert ordinary.code is None
    assert ordinary.is_context_overflow is False
    assert_overflow(ProviderChatCompletionError("too long", code="CONTEXT_WINDOW_EXCEEDED"))
    assert not ProviderChatCompletionError("too long", code="OTHER").is_context_overflow


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("transport", TRANSPORTS)
def test_explicit_context_code_across_providers_and_transports(provider, transport):
    with pytest.raises(ProviderChatCompletionError) as caught:
        invoke(provider, transport, payload=CONTEXT_ERROR)
    assert_overflow(caught.value)
    if transport.startswith("urllib-") and "status" not in transport:
        assert isinstance(caught.value.__cause__, error.HTTPError)


@pytest.mark.parametrize("provider,payload", [
    (AliyunBailianProvider, {"code": "InvalidParameter", "message": "Range of input length should be [1, 32768]"}),
    (AliyunBailianProvider, {"error": {"code": "InternalError.Algo.InvalidParameter", "message": "Range of input length should be [1, 32768]"}}),
    (AliyunBailianProvider, {"error": {"code": "InputTooLong"}}),
    (AliyunBailianProvider, {"error": {"code": "InvalidParameter", "message": "Total message token length exceed model limit (10000000 tokens)."}}),
    (DeepSeekProvider, {"error": {"type": "invalid_request_error", "code": None, "message": "This model's maximum context length is 65536 tokens. However, you requested 70000 tokens (68000 in the messages, 2000 in the completion)."}}),
    (OpenRouterProvider, {"error": {"code": 400, "message": "This endpoint's maximum context length is 32768 tokens. However, you requested 40000 tokens."}}),
    (OpenRouterProvider, {"error": {"code": 400, "message": "Provider returned error", "metadata": {"raw": json.dumps(CONTEXT_ERROR)}}}),
    (OpenRouterProvider, {"error": {"code": 400, "metadata": {"raw": {"error": {"type": "invalid_request_error", "message": "prompt is too long: 70000 tokens > 65536 maximum"}}}}}),
])
@pytest.mark.parametrize("transport", TRANSPORTS)
def test_provider_specific_api_errors(provider, payload, transport):
    with pytest.raises(ProviderChatCompletionError) as caught:
        invoke(provider, transport, payload=payload)
    assert_overflow(caught.value)


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("transport", TRANSPORTS)
@pytest.mark.parametrize("status", [401, 403, 408, 429, 504])
def test_other_http_statuses_do_not_become_context_errors(provider, transport, status):
    with pytest.raises(ProviderChatCompletionError) as caught:
        invoke(provider, transport, status=status, payload=CONTEXT_ERROR)
    assert caught.value.code == ("PROVIDER_AUTH_FAILED" if status in {401, 403} else "MODEL_TIMEOUT" if status in {408, 504} else "MODEL_ERROR")
    assert not caught.value.is_context_overflow


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("payload", [
    {"error": {"code": "InvalidParameter", "message": "Range of max_tokens should be [1, 8192]"}},
    {"error": {"code": "invalid_request_error", "message": "max_tokens is too large"}},
    {"error": {"code": "InvalidParameter", "message": "Invalid context parameter"}},
    {"error": {"code": "length", "message": "Output truncated at max_tokens"}},
    {"error": {"code": "authentication_error", "message": "context length exceeded"}},
    {"error": {"code": "timeout", "message": "context length exceeded"}},
    {"error": {"code": 401, "message": "context length exceeded"}},
    {"code": 401, "error": "context length exceeded"},
    {"error": {"code": "InvalidParameter", "message": "file exceeds size limit"}},
    {"error": {"code": "InvalidParameter", "message": "This model's maximum context length is 65536 tokens. Invalid max_tokens."}},
    {"error": {"metadata": {"raw": "unstructured context length exceeded"}}},
    {"error": {"code": [], "message": None}},
    {"error": None}, {"error": []}, [], None,
])
def test_unrelated_and_malformed_errors_are_not_context_overflow(provider, payload):
    with pytest.raises(ProviderChatCompletionError) as caught:
        invoke(provider, "urllib-complete", payload=payload)
    assert caught.value.code == "MODEL_ERROR"
    assert not caught.value.is_context_overflow


@pytest.mark.parametrize("transport", TRANSPORTS)
@pytest.mark.parametrize("body", [b"context length exceeded", b"{invalid JSON", b"\xff"])
def test_non_json_http_error_body_is_not_classified(transport, body):
    with pytest.raises(ProviderChatCompletionError) as caught:
        invoke(AliyunBailianProvider, transport, body=body)
    assert not caught.value.is_context_overflow


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("transport", TRANSPORTS)
def test_transport_timeout_is_not_context_overflow(provider, transport):
    failure = (
        httpx.ReadTimeout("context length exceeded")
        if transport.startswith("httpx") else TimeoutError("context length exceeded")
    )
    with pytest.raises(ProviderChatCompletionError) as caught:
        invoke(provider, transport, failure=failure)
    assert str(caught.value) == "连接超时"
    assert not caught.value.is_context_overflow


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("transport", ["urllib-stream", "httpx-stream"])
@pytest.mark.parametrize("overflow", [True, False])
def test_stream_error_after_partial_content_is_raised(provider, transport, overflow):
    payload = CONTEXT_ERROR if overflow else {"error": {"code": 401, "message": "authentication failed"}}
    body = (
        b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        + b"data: " + json.dumps(payload).encode() + b"\n\ndata: [DONE]\n\n"
    )
    with pytest.raises(ProviderChatCompletionError) as caught:
        invoke(provider, transport, status=200, body=body)
    assert caught.value.is_context_overflow is overflow


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("transport", ["urllib-complete", "httpx-complete"])
def test_json_error_with_success_http_status_is_classified(provider, transport):
    with pytest.raises(ProviderChatCompletionError) as caught:
        invoke(provider, transport, status=200, payload=CONTEXT_ERROR)
    assert_overflow(caught.value)


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("transport", TRANSPORTS)
def test_length_finish_reason_and_assistant_text_are_preserved(provider, transport):
    content = "context length exceeded"
    if transport.endswith("stream"):
        payload = {"choices": [{"delta": {"content": content}, "finish_reason": "length"}]}
        body = b"data: " + json.dumps(payload).encode() + b"\n\ndata: [DONE]\n\n"
        chunks = invoke(provider, transport, status=200, body=body)
        assert chunks[0].content_delta == content
        assert chunks[0].stop_reason == "length"
    else:
        payload = {"choices": [{"message": {"content": content}, "finish_reason": "length"}]}
        result = invoke(provider, transport, status=200, payload=payload)
        assert result.content == content
        assert result.stop_reason == "length"


def test_safe_http_diagnostics_do_not_expose_upstream_message():
    with pytest.raises(ProviderChatCompletionError) as caught:
        invoke(DeepSeekProvider, "urllib-complete", payload={"error": {"code": "bad_request", "message": "private prompt"}})
    assert "bad_request" in str(caught.value)
    assert "test-request" in str(caught.value)
    assert "private prompt" not in str(caught.value)


@pytest.mark.parametrize("overflow", [True, False])
@pytest.mark.parametrize("returned_status", [True, False])
def test_only_transient_server_errors_are_retried(overflow, returned_status):
    attempts = []
    payload = CONTEXT_ERROR if overflow else {"error": {"code": "server_error"}}
    body = json.dumps(payload).encode()

    class Response(io.BytesIO):
        status = 500

    def urlopen(request, timeout):
        attempts.append(request)
        if returned_status:
            return Response(body)
        raise error.HTTPError(request.full_url, 500, "error", {}, io.BytesIO(body))

    with pytest.raises(ProviderChatCompletionError) as caught:
        DeepSeekProvider(urlopen=urlopen).complete_chat(
            api_url="https://provider.example/v1",
            api_key="test-key",
            remote_model_id="test-model",
            model_request=ModelRequest.build(
                system="", messages=[{"role": "user", "content": "hello"}]
            ),
        )
    assert caught.value.is_context_overflow is overflow
    assert len(attempts) == (1 if overflow else 3)

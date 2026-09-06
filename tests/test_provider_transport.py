import base64
import json
import socket
import threading
import time
import unittest
from urllib import error
from backend.app.agent_runtime.model_types import AssistantModelOutput, ModelRequest, ModelStreamChunk, ToolCall, ToolSchema
from backend.app.application.model_provider_service import ModelProviderService
from backend.app.core.cancellation import CancellationToken, OperationCancelledError
from backend.app.model_capabilities import ModelCapabilityProfile, profiles_from_profile
from backend.app.providers.aliyun_bailian import AliyunBailianProvider
from backend.app.providers.base import ModelProvider
from backend.app.providers.capability_probe import _CAPABILITY_PROBE_ASSET_ROOT
from backend.app.providers.errors import ProviderChatCompletionError
from backend.app.providers.types import ProviderModel
from backend.app.providers.deepseek import DeepSeekProvider
from backend.app.providers.openrouter import OpenRouterProvider


def chat_request(messages):
    return ModelRequest.build(system="", messages=messages)


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return b'{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}'


class FakeReasoningResponse(FakeResponse):
    def read(self):
        return b'{"choices":[{"message":{"reasoning_content":"check context","content":"ok"},"finish_reason":"stop"}]}'


class FakeStreamingResponse(FakeResponse):
    def __iter__(self):
        return iter(
            [
                b'data: {"choices":[{"delta":{"reasoning_content":"think "},"finish_reason":null}]}\n\n',
                b'data: {"choices":[{"delta":{"reasoning_content":"first"},"finish_reason":null}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"hel"},"finish_reason":null}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":"stop"}]}\n\n',
                b"data: [DONE]\n\n",
            ]
        )


class BlockingStreamClient:
    def __init__(self, *, timeout=None):
        self.timeout = timeout
        self.entered = threading.Event()
        self.closed = threading.Event()

    def stream(self, *_args, **_kwargs):
        client = self

        class Context:
            def __enter__(self):
                client.entered.set()
                if not client.closed.wait(timeout=5):
                    raise TimeoutError("test stream was not cancelled")
                raise RuntimeError("stream client closed during response wait")

            def __exit__(self, _exc_type, _exc, _traceback):
                return False

        return Context()

    def close(self):
        self.closed.set()


class ProviderTransportTests(unittest.TestCase):
    def test_cancellation_closes_stream_while_waiting_for_response_headers(self):
        clients = []

        def client_factory(**kwargs):
            client = BlockingStreamClient(**kwargs)
            clients.append(client)
            return client

        provider = ModelProvider(stream_client_factory=client_factory)
        cancellation_token = CancellationToken()
        errors = []

        def consume():
            try:
                list(
                    provider.stream_chat(
                        api_url="https://provider.example/v1",
                        api_key="secret",
                        remote_model_id="remote-model",
                        model_request=chat_request(
                            [{"role": "user", "content": "hello"}]
                        ),
                        cancellation_token=cancellation_token,
                    )
                )
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=consume)
        thread.start()
        deadline = time.monotonic() + 1
        while not clients and time.monotonic() < deadline:
            time.sleep(0.001)
        self.assertTrue(clients)
        self.assertTrue(clients[0].entered.wait(timeout=1))

        cancellation_token.cancel()
        thread.join(timeout=1)

        self.assertFalse(thread.is_alive())
        self.assertTrue(clients[0].closed.is_set())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], OperationCancelledError)

    def test_cancellation_closes_non_stream_probe_request(self):
        clients = []

        def client_factory(**kwargs):
            client = BlockingStreamClient(**kwargs)
            clients.append(client)
            return client

        provider = ModelProvider(stream_client_factory=client_factory)
        cancellation_token = CancellationToken()
        errors = []

        def complete():
            try:
                provider.complete_chat(
                    api_url="https://provider.example/v1",
                    api_key="secret",
                    remote_model_id="remote-model",
                    model_request=chat_request(
                        [{"role": "user", "content": "hello"}]
                    ),
                    timeout_seconds=300,
                    cancellation_token=cancellation_token,
                )
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=complete)
        thread.start()
        deadline = time.monotonic() + 1
        while not clients and time.monotonic() < deadline:
            time.sleep(0.001)
        self.assertTrue(clients)
        self.assertTrue(clients[0].entered.wait(timeout=1))

        cancellation_token.cancel()
        thread.join(timeout=1)

        self.assertFalse(thread.is_alive())
        self.assertTrue(clients[0].closed.is_set())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], OperationCancelledError)

    def test_capability_probe_samples_are_real_project_assets(self):
        expected_signatures = {
            "image.png": b"\x89PNG\r\n\x1a\n",
            "document.pdf": b"%PDF-1.4",
            "audio.wav": b"RIFF",
            "video.mp4": b"\x00\x00\x00\x1cftyp",
        }

        for filename, signature in expected_signatures.items():
            sample = (_CAPABILITY_PROBE_ASSET_ROOT / filename).read_bytes()
            self.assertTrue(sample.startswith(signature), filename)

    def test_deepseek_capability_probes_disable_thinking_without_changing_chat_modes(self):
        provider = DeepSeekProvider()
        probe_request = ModelRequest.build(
            system="",
            messages=[{"role": "user", "content": "仅回复 OK"}],
            model_config={"max_tokens": 8},
        )

        probe_payload = provider.build_chat_payload(
            remote_model_id="deepseek-v4-flash",
            model_request=probe_request,
            thinking_mode="off",
            stream=False,
        )
        chat_payload = provider.build_chat_payload(
            remote_model_id="deepseek-v4-flash",
            model_request=chat_request([{"role": "user", "content": "hello"}]),
            thinking_mode="high",
            stream=True,
        )
        max_chat_payload = provider.build_chat_payload(
            remote_model_id="deepseek-v4-flash",
            model_request=chat_request([{"role": "user", "content": "hello"}]),
            thinking_mode="max",
            stream=True,
        )

        self.assertEqual(probe_payload["thinking"], {"type": "disabled"})
        self.assertEqual(chat_payload["thinking"], {"type": "enabled"})
        self.assertEqual(chat_payload["reasoning_effort"], "high")
        self.assertEqual(max_chat_payload["reasoning_effort"], "max")

    def test_deepseek_vision_model_serializes_and_probes_image_input(self):
        class ProbeDeepSeekProvider(DeepSeekProvider):
            def __init__(self):
                super().__init__()
                self.requests = []

            def complete_chat(
                self,
                api_url,
                api_key,
                remote_model_id,
                model_request,
                thinking_mode="default",
                timeout_seconds=None,
             cancellation_token=None):
                self.requests.append((thinking_mode, model_request))
                if model_request.tools:
                    return AssistantModelOutput(
                        tool_calls=(
                            ToolCall(
                                id="probe-call",
                                name="capability_probe",
                                arguments={},
                            ),
                        )
                    )
                content = model_request.messages[0].get("content")
                if isinstance(content, list) and content[1].get("type") != "image":
                    raise ProviderChatCompletionError(
                        "upstream does not support this input", capability_rejected=True
                    )
                return AssistantModelOutput(content="ok")

        provider = ProbeDeepSeekProvider()
        remote_model_id = "deepseek-v4-flash-vision-exp"
        profile = provider.normalize_capabilities({}, remote_model_id)
        result = provider.probe_capabilities(
            api_url="https://api.deepseek.com",
            api_key="secret",
            remote_model_id=remote_model_id,
            current_profiles=profiles_from_profile(profile),
            thinking_modes=profile.thinking_modes,
        )

        self.assertEqual(result.checks["aggregate"]["image_input"], "supported")
        self.assertEqual(result.checks["aggregate"]["pdf_input"], "unsupported")
        self.assertEqual(result.checks["aggregate"]["audio_input"], "unsupported")
        self.assertEqual(result.checks["aggregate"]["video_input"], "unsupported")
        self.assertEqual(
            result.profiles.non_thinking.file_mime_types,
            ["image/gif", "image/jpeg", "image/png", "image/webp"],
        )
        self.assertEqual(
            result.profiles.thinking.file_mime_types,
            ["image/gif", "image/jpeg", "image/png", "image/webp"],
        )
        self.assertEqual(len(provider.requests), 19)
        self.assertEqual(
            result.checks["thinking_modes"],
            {
                "off": "supported",
                "minimal": "supported",
                "low": "supported",
                "medium": "supported",
                "high": "supported",
                "xhigh": "supported",
                "max": "supported",
            },
        )

        image_request = next(
            model_request
            for _, model_request in provider.requests
            if isinstance(model_request.messages[0].get("content"), list)
            and model_request.messages[0]["content"][1].get("type") == "image"
        )
        image_payload = provider.build_chat_payload(
            remote_model_id=remote_model_id,
            model_request=image_request,
            thinking_mode="off",
            stream=False,
        )
        image_part = image_payload["messages"][0]["content"][1]
        self.assertEqual(image_part["type"], "image_url")
        self.assertTrue(
            image_part["image_url"]["url"].startswith("data:image/png;base64,")
        )

    def test_deepseek_connection_test_verifies_a_minimal_chat_request(self):
        class ConnectionDeepSeekProvider(DeepSeekProvider):
            def __init__(self):
                super().__init__()
                self.requests = []

            def list_models(self, api_url, api_key, cancellation_token=None):
                return [
                    ProviderModel(
                        remote_model_id="deepseek-v4-flash",
                        model_name="DeepSeek V4 Flash",
                    )
                ]

            def complete_chat(
                self,
                api_url,
                api_key,
                remote_model_id,
                model_request,
                thinking_mode="default",
                timeout_seconds=None,
             cancellation_token=None):
                self.requests.append(
                    (remote_model_id, model_request, thinking_mode, timeout_seconds)
                )
                return AssistantModelOutput(content="OK")

        provider = ConnectionDeepSeekProvider()

        result = provider.test_connection("https://api.deepseek.com", "sk-test")

        self.assertTrue(result.reachable)
        self.assertEqual(len(provider.requests), 1)
        remote_model_id, model_request, thinking_mode, timeout_seconds = provider.requests[0]
        self.assertEqual(remote_model_id, "deepseek-v4-flash")
        self.assertEqual(thinking_mode, "off")
        self.assertNotIn("thinking", model_request.model_config)
        self.assertEqual(timeout_seconds, provider.timeout_seconds)

    def test_capability_probe_uses_real_request_shapes_and_preserves_unprobed_values(self):
        class ScriptedProbeProvider(ModelProvider):
            def __init__(self):
                super().__init__()
                self.requests = []

            def native_attachment_mime_types(self):
                return {
                    "image/png",
                    "image/jpeg",
                    "application/pdf",
                    "audio/wav",
                    "audio/mpeg",
                    "video/mp4",
                }

            def complete_chat(
                self,
                api_url,
                api_key,
                remote_model_id,
                model_request,
                thinking_mode="default",
                timeout_seconds=None,
             cancellation_token=None):
                self.requests.append((thinking_mode, model_request))
                if model_request.tools:
                    return AssistantModelOutput(
                        tool_calls=(
                            ToolCall(id="probe-call", name="capability_probe", arguments={}),
                        )
                    )
                return AssistantModelOutput(content="ok")

        provider = ScriptedProbeProvider()
        result = provider.probe_capabilities(
            api_url="https://provider.example/v1",
            api_key="secret",
            remote_model_id="remote-model",
            current_profiles=profiles_from_profile(ModelCapabilityProfile(
                file_mime_types=["video/mp4"],
                thinking_modes=["default", "high"],
                context_window_tokens=131072,
                max_output_tokens=8192,
            )),
            thinking_modes=["default", "high"],
        )

        expected_checks = {
                "text": "supported",
                "tool_calling": "supported",
                "image_input": "supported",
                "pdf_input": "supported",
                "audio_input": "supported",
                "video_input": "supported",
        }
        self.assertEqual(result.checks["aggregate"], expected_checks)
        self.assertEqual(result.checks["non_thinking"], expected_checks)
        self.assertEqual(result.checks["thinking"], expected_checks)
        expected_mime_types = [
            "image/jpeg",
            "image/png",
            "application/pdf",
            "audio/mpeg",
            "audio/wav",
            "video/mp4",
        ]
        self.assertEqual(result.profiles.non_thinking.file_mime_types, expected_mime_types)
        self.assertEqual(result.profiles.thinking.file_mime_types, expected_mime_types)
        self.assertEqual(len(provider.requests), 19)
        self.assertEqual(
            [mode for mode, _ in provider.requests].count("off"),
            7,
        )
        self.assertEqual(
            [mode for mode, _ in provider.requests].count("high"),
            7,
        )

        def media_parts(part_type):
            return next(
                model_request.messages[0]["content"]
                for mode, model_request in provider.requests
                if mode == "off"
                and isinstance(model_request.messages[0].get("content"), list)
                and model_request.messages[0]["content"][1].get("type")
                == part_type
            )

        image_parts = media_parts("image")
        self.assertEqual(image_parts[1]["mime_type"], "image/png")
        self.assertGreater(len(image_parts[1]["data_base64"]), 40)
        pdf_parts = media_parts("file")
        self.assertEqual(pdf_parts[1]["type"], "file")
        self.assertEqual(pdf_parts[1]["mime_type"], "application/pdf")
        self.assertEqual(pdf_parts[1]["name"], "capability-probe.pdf")
        pdf_bytes = base64.b64decode(pdf_parts[1]["data_base64"])
        self.assertTrue(pdf_bytes.startswith(b"%PDF-1.4"))
        self.assertTrue(pdf_bytes.rstrip().endswith(b"%%EOF"))
        audio_parts = media_parts("audio")
        self.assertEqual(audio_parts[1]["mime_type"], "audio/wav")
        self.assertEqual(base64.b64decode(audio_parts[1]["data_base64"])[:4], b"RIFF")
        video_parts = media_parts("video")
        self.assertEqual(video_parts[1]["mime_type"], "video/mp4")
        video_bytes = base64.b64decode(video_parts[1]["data_base64"])
        self.assertEqual(video_bytes[4:8], b"ftyp")
        movie_header = video_bytes.index(b"mvhd")
        timescale = int.from_bytes(video_bytes[movie_header + 16 : movie_header + 20])
        duration = int.from_bytes(video_bytes[movie_header + 20 : movie_header + 24])
        self.assertGreaterEqual(duration / timescale, 2)

    def test_empty_metadata_probes_every_capability_without_adapter_declarations(self):
        class EmptyMetadataProvider(ModelProvider):
            def __init__(self):
                super().__init__()
                self.requests = []
                self.thinking_mode_thread_ids = set()
                self.capability_thread_ids = set()
                self.thread_lock = threading.Lock()
                self.thinking_mode_barrier = threading.Barrier(7)
                self.capability_barrier = threading.Barrier(12)
                self.thinking_modes_finished = threading.Event()
                self.finished_thinking_mode_count = 0

            def complete_chat(
                self,
                api_url,
                api_key,
                remote_model_id,
                model_request,
                thinking_mode="default",
                timeout_seconds=None,
             cancellation_token=None):
                self.requests.append((thinking_mode, model_request))
                if model_request.transport_mode == "thinking_mode_probe":
                    with self.thread_lock:
                        self.thinking_mode_thread_ids.add(threading.get_ident())
                    self.thinking_mode_barrier.wait(timeout=5)
                    with self.thread_lock:
                        self.finished_thinking_mode_count += 1
                        if self.finished_thinking_mode_count == 7:
                            self.thinking_modes_finished.set()
                else:
                    self.assert_capabilities_start_after_thinking_modes()
                    with self.thread_lock:
                        self.capability_thread_ids.add(threading.get_ident())
                    self.capability_barrier.wait(timeout=5)
                if model_request.tools:
                    return AssistantModelOutput(
                        tool_calls=(
                            ToolCall(
                                id="probe-call",
                                name="capability_probe",
                                arguments={},
                            ),
                        )
                    )
                return AssistantModelOutput(content="ok")

            def assert_capabilities_start_after_thinking_modes(self):
                if not self.thinking_modes_finished.is_set():
                    raise AssertionError(
                        "capability probes started before every thinking mode completed"
                    )

        provider = EmptyMetadataProvider()
        result = provider.probe_capabilities(
            api_url="https://provider.example/v1",
            api_key="secret",
            remote_model_id="metadata-empty-model",
            current_profiles=profiles_from_profile(ModelCapabilityProfile()),
            thinking_modes=["default"],
            capability_declarations={},
        )

        self.assertEqual(
            set(result.checks["aggregate"].values()),
            {"supported"},
        )
        self.assertEqual(len(provider.requests), 19)
        self.assertEqual(len(provider.thinking_mode_thread_ids), 7)
        self.assertEqual(len(provider.capability_thread_ids), 12)
        self.assertEqual(
            [mode for mode, _ in provider.requests].count("off"),
            7,
        )
        self.assertEqual(
            [mode for mode, _ in provider.requests].count("high"),
            7,
        )
        self.assertEqual(result.profiles.default_state, "unknown")
        media_requests = [
            model_request
            for _, model_request in provider.requests
            if isinstance(model_request.messages[0].get("content"), list)
        ]
        self.assertEqual(len(media_requests), 8)
        for media_request in media_requests:
            self.assertEqual(media_request.transport_mode, "capability_probe")
            provider.build_chat_payload(
                remote_model_id="metadata-empty-model",
                model_request=media_request,
                thinking_mode="off",
                stream=False,
            )
        self.assertEqual(
            result.profiles.non_thinking.file_mime_types,
            ["image/png", "application/pdf", "audio/wav", "video/mp4"],
        )

    def test_complete_metadata_is_used_without_live_capability_requests(self):
        class DeclaredProvider(ModelProvider):
            def __init__(self):
                super().__init__()
                self.probed_modes = []

            def complete_chat(self, *args, **kwargs):
                model_request = args[3]
                if model_request.transport_mode != "thinking_mode_probe":
                    raise AssertionError("declared input/output capabilities must not be probed")
                mode = kwargs["thinking_mode"]
                self.probed_modes.append(mode)
                if mode not in {"off", "high"}:
                    raise ProviderChatCompletionError("unsupported parameter")
                return AssistantModelOutput(content="ok")

        profile = ModelCapabilityProfile(
            file_mime_types=["image/png", "application/pdf"],
            thinking_modes=["default", "off", "high"],
            supports_tool_calling=True,
            default_thinking_state="thinking",
        )
        provider = DeclaredProvider()
        result = provider.probe_capabilities(
            api_url="https://provider.example/v1",
            api_key="secret",
            remote_model_id="fully-declared-model",
            current_profiles=profiles_from_profile(profile),
            thinking_modes=profile.thinking_modes,
            capability_declarations={
                "text": True,
                "tool_calling": True,
                "image_input": True,
                "pdf_input": True,
                "audio_input": False,
                "video_input": False,
                "thinking": True,
            },
        )

        self.assertEqual(
            result.checks["aggregate"],
            {
                "text": "supported",
                "tool_calling": "supported",
                "image_input": "supported",
                "pdf_input": "supported",
                "audio_input": "unsupported",
                "video_input": "unsupported",
            },
        )
        self.assertEqual(
            result.profiles.thinking.file_mime_types,
            ["image/png", "application/pdf"],
        )
        self.assertEqual(
            set(provider.probed_modes),
            {"off", "minimal", "low", "medium", "high", "xhigh", "max"},
        )

    def test_provider_adapters_encode_fast_and_keep_max_without_downgrading(self):
        model_request = chat_request([{"role": "user", "content": "hello"}])
        aliyun = AliyunBailianProvider()
        openrouter = OpenRouterProvider()

        aliyun_fast = aliyun.build_chat_payload(
            remote_model_id="qwen3.8-max",
            model_request=model_request,
            thinking_mode="off",
            stream=False,
        )
        aliyun_max = aliyun.build_chat_payload(
            remote_model_id="qwen3.8-max",
            model_request=model_request,
            thinking_mode="max",
            stream=False,
        )
        aliyun_minimal = aliyun.build_chat_payload(
            remote_model_id="qwen3.8-max",
            model_request=model_request,
            thinking_mode="minimal",
            stream=False,
        )
        openrouter_fast = openrouter.build_chat_payload(
            remote_model_id="vendor/reasoning-model",
            model_request=model_request,
            thinking_mode="off",
            stream=False,
        )
        openrouter_max = openrouter.build_chat_payload(
            remote_model_id="vendor/reasoning-model",
            model_request=model_request,
            thinking_mode="max",
            stream=False,
        )
        openrouter_minimal = openrouter.build_chat_payload(
            remote_model_id="vendor/reasoning-model",
            model_request=model_request,
            thinking_mode="minimal",
            stream=False,
        )

        self.assertIs(aliyun_fast["enable_thinking"], False)
        self.assertIs(aliyun_max["enable_thinking"], True)
        self.assertEqual(aliyun_max["reasoning_effort"], "max")
        self.assertEqual(aliyun_minimal["reasoning_effort"], "minimal")
        self.assertEqual(openrouter_fast["reasoning"], {"effort": "none"})
        self.assertEqual(openrouter_max["reasoning"], {"effort": "max"})
        self.assertEqual(openrouter_minimal["reasoning"], {"effort": "minimal"})

    def test_explicit_thinking_only_metadata_skips_non_thinking_probes(self):
        class ThinkingOnlyProvider(AliyunBailianProvider):
            def complete_chat(self, *args, **kwargs):
                if (
                    args[3].transport_mode == "thinking_mode_probe"
                    and kwargs["thinking_mode"] == "off"
                ):
                    raise ProviderChatCompletionError("unsupported parameter")
                return AssistantModelOutput(content="ok")

        provider = ThinkingOnlyProvider()
        profile = ModelCapabilityProfile(
            thinking_modes=["default", "high"],
            default_thinking_state="thinking",
        )
        result = provider.probe_capabilities(
            api_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="secret",
            remote_model_id="qwen3-vl-32b-thinking",
            current_profiles=profiles_from_profile(profile),
            thinking_modes=profile.thinking_modes,
            capability_declarations={"thinking": True},
        )

        self.assertEqual(
            set(result.checks["non_thinking"].values()),
            {"not_applicable"},
        )
        self.assertEqual(result.profiles.non_thinking.availability, "unavailable")

    def test_aliyun_probe_preserves_existing_capabilities_when_requests_are_inconclusive(self):
        class RejectingAliyunProvider(AliyunBailianProvider):
            def __init__(self):
                super().__init__()
                self.requests = []

            def complete_chat(
                self,
                api_url,
                api_key,
                remote_model_id,
                model_request,
                thinking_mode="default",
                timeout_seconds=None,
             cancellation_token=None):
                self.requests.append((thinking_mode, model_request))
                if model_request.tools:
                    raise ProviderChatCompletionError(
                        "模型服务调用失败，HTTP 400（上游代码 InvalidParameter）"
                    )
                content = model_request.messages[0].get("content")
                if isinstance(content, list):
                    part_type = content[1].get("type")
                    if part_type in {"file", "audio", "video"}:
                        raise ProviderChatCompletionError(
                            "模型服务调用失败，HTTP 400（上游代码 InvalidParameter）"
                        )
                return AssistantModelOutput(content="ok")

        provider = RejectingAliyunProvider()
        result = provider.probe_capabilities(
            api_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="secret",
            remote_model_id="qwen3.8-max",
            current_profiles=profiles_from_profile(
                ModelCapabilityProfile(
                    file_mime_types=[
                        "image/png",
                        "video/mp4",
                    ],
                    thinking_modes=["default", "off", "high"],
                    supports_tool_calling=True,
                    default_thinking_state="thinking",
                )
            ),
            thinking_modes=["default", "off", "high"],
        )

        self.assertEqual(result.checks["aggregate"]["tool_calling"], "unverified")
        self.assertEqual(result.checks["aggregate"]["video_input"], "unverified")
        self.assertEqual(result.checks["aggregate"]["audio_input"], "unverified")
        self.assertEqual(result.checks["aggregate"]["pdf_input"], "unverified")
        for profile in (result.profiles.non_thinking, result.profiles.thinking):
            self.assertTrue(profile.supports_tool_calling)
            self.assertIn("image/png", profile.file_mime_types)
            self.assertIn("video/mp4", profile.file_mime_types)
            self.assertNotIn("audio/wav", profile.file_mime_types)
        self.assertEqual(
            [mode for mode, _ in provider.requests].count("off"),
            7,
        )
        self.assertEqual(
            [mode for mode, _ in provider.requests].count("high"),
            7,
        )
        thinking_tool_request = next(
            model_request
            for mode, model_request in provider.requests
            if mode == "high" and model_request.tools
        )
        self.assertEqual(thinking_tool_request.tool_choice, "auto")

    def test_prepared_stream_payload_is_built_once_and_sent_by_identity(self):
        class CountingProvider(ModelProvider):
            provider_id = "counting"
            default_api_url = "https://provider.example/v1"

            def __init__(self):
                super().__init__()
                self.build_count = 0
                self.sent_payload = None

            def build_chat_payload(self, **kwargs):
                self.build_count += 1
                return super().build_chat_payload(**kwargs)

            def stream_chat_payload(self, **kwargs):
                self.sent_payload = kwargs["provider_payload"]
                yield ModelStreamChunk(content_delta="ok")

        class Catalog(ModelProviderService):
            def __init__(self, provider):
                super().__init__()
                self.provider = provider

            def _provider(self, _provider_id):
                return self.provider

            def _provider_row(self, _account, _provider_id):
                return {"is_configured": 1, "api_url": self.provider.default_api_url}

            def _api_key_from_row(self, _account, _row):
                return "secret"

        provider = CountingProvider()
        catalog = Catalog(provider)
        model = {
            "provider_id": "counting",
            "remote_model_id": "remote-model",
            "supports_tool_calling": True,
        }
        prepared = catalog.prepare_stream_chat_for_account(
            account_id="alice",
            model=model,
            model_request=ModelRequest.build(
                system="system",
                messages=[{"role": "user", "content": "hello"}],
                tools=[
                    ToolSchema(
                        name="lookup",
                        parameters={"type": "object", "properties": {}},
                    )
                ],
            ),
            thinking_mode="default",
        )

        chunks = list(
            catalog.stream_prepared_chat_for_account(
                prepared_request=prepared,
            )
        )

        self.assertEqual(provider.build_count, 1)
        self.assertIs(provider.sent_payload, prepared.provider_payload)
        self.assertEqual(chunks[0].content_delta, "ok")
        self.assertLess(
            list(prepared.provider_payload).index("tools"),
            list(prepared.provider_payload).index("messages"),
        )

    def test_saved_output_limit_is_sent_to_provider(self):
        model = {
            "provider_id": "test",
            "remote_model_id": "test-model",
            "supports_tool_calling": True,
            "max_output_tokens": 4096,
        }
        logical_request = ModelRequest.build(
            system="",
            messages=[{"role": "user", "content": "hello"}],
        )

        transport_request = ModelProviderService.prepare_transport_request(
            model,
            logical_request,
            "default",
        )
        payload = ModelProvider().build_chat_payload(
            remote_model_id="test-model",
            model_request=transport_request,
            thinking_mode="default",
            stream=True,
        )

        self.assertEqual(transport_request.model_config["max_output_tokens"], 4096)
        self.assertEqual(payload["max_tokens"], 4096)

    def test_base_provider_rejects_file_attachment_parts(self):
        provider = ModelProvider(urlopen=lambda request, timeout: FakeStreamingResponse())

        with self.assertRaisesRegex(ProviderChatCompletionError, "不支持该附件类型"):
            list(
                provider.stream_chat(
                    api_url="https://provider.example/v1",
                    api_key="secret",
                    remote_model_id="remote-model",
                    model_request=chat_request([
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "请分析附件"},
                                {
                                    "type": "file",
                                    "mime_type": "application/pdf",
                                    "name": "report.pdf",
                                    "data_base64": "JVBERi0xLjQ=",
                                },
                            ],
                        }
                    ]),
                )
            )

    def test_openrouter_serializes_image_and_pdf_parts_without_forcing_pdf_engine(self):
        seen = {}

        def streaming_urlopen(request, timeout):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeStreamingResponse()

        provider = OpenRouterProvider(urlopen=streaming_urlopen)

        list(
            provider.stream_chat(
                api_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="remote-model",
                model_request=chat_request([
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请分析附件"},
                            {"type": "image", "mime_type": "image/png", "data_base64": "iVBORw0KGgo="},
                            {
                                "type": "file",
                                "mime_type": "application/pdf",
                                "name": "report.pdf",
                                "data_base64": "JVBERi0xLjQ=",
                            },
                        ],
                    }
                ]),
            )
        )

        self.assertEqual(
            seen["body"]["messages"][0]["content"],
            [
                {"type": "text", "text": "请分析附件"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="}},
                {
                    "type": "file",
                    "file": {
                        "filename": "report.pdf",
                        "file_data": "data:application/pdf;base64,JVBERi0xLjQ=",
                    },
                },
            ],
        )
        self.assertNotIn("plugins", seen["body"])

    def test_openrouter_streams_attachment_requests_with_five_minute_timeout(self):
        seen = {}

        def streaming_urlopen(request, timeout):
            seen["timeout"] = timeout
            return FakeStreamingResponse()

        provider = OpenRouterProvider(urlopen=streaming_urlopen)

        list(
            provider.stream_chat(
                api_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="remote-model",
                model_request=chat_request([
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请分析附件"},
                            {
                                "type": "file",
                                "mime_type": "application/pdf",
                                "name": "report.pdf",
                                "data_base64": "JVBERi0xLjQ=",
                            },
                        ],
                    }
                ]),
            )
        )

        self.assertEqual(seen["timeout"], 300)

    def test_openrouter_serializes_audio_and_video_parts_natively(self):
        seen = {}

        def streaming_urlopen(request, timeout):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeStreamingResponse()

        provider = OpenRouterProvider(urlopen=streaming_urlopen)

        list(
            provider.stream_chat(
                api_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="google/gemini-3.5-flash",
                model_request=chat_request([
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请分析音视频"},
                            {
                                "type": "audio",
                                "mime_type": "audio/mpeg",
                                "name": "voice.mp3",
                                "data_base64": "SUQzBAAAAAAA",
                            },
                            {
                                "type": "video",
                                "mime_type": "video/mp4",
                                "name": "clip.mp4",
                                "data_base64": "AAAAIGZ0eXBpc29t",
                            },
                        ],
                    }
                ]),
            )
        )

        self.assertEqual(
            seen["body"]["messages"][0]["content"],
            [
                {"type": "text", "text": "请分析音视频"},
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": "SUQzBAAAAAAA",
                        "format": "mp3",
                    },
                },
                {
                    "type": "video_url",
                    "video_url": {"url": "data:video/mp4;base64,AAAAIGZ0eXBpc29t"},
                },
            ],
        )
        self.assertNotIn("plugins", seen["body"])

    def test_aliyun_serializes_only_image_parts(self):
        seen = {}

        def streaming_urlopen(request, timeout):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeStreamingResponse()

        provider = AliyunBailianProvider(urlopen=streaming_urlopen)

        list(
            provider.stream_chat(
                api_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="remote-model",
                model_request=chat_request([
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请描述图片"},
                            {"type": "image", "mime_type": "image/jpeg", "data_base64": "/9j/4AAQSkZJRg=="},
                        ],
                    }
                ]),
            )
        )

        self.assertEqual(
            seen["body"]["messages"][0]["content"],
            [
                {"type": "text", "text": "请描述图片"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQSkZJRg=="}},
            ],
        )
        self.assertNotIn("plugins", seen["body"])

    def test_aliyun_serializes_audio_and_video_parts_natively(self):
        seen = {}

        def streaming_urlopen(request, timeout):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeStreamingResponse()

        provider = AliyunBailianProvider(urlopen=streaming_urlopen)

        list(
            provider.stream_chat(
                api_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="qwen3.5-omni-plus",
                model_request=chat_request([
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请分析音视频"},
                            {
                                "type": "audio",
                                "mime_type": "audio/mpeg",
                                "data_base64": "SUQzBAAAAAAA",
                            },
                            {
                                "type": "video",
                                "mime_type": "video/x-msvideo",
                                "data_base64": "UklGRg==",
                            },
                        ],
                    }
                ]),
            )
        )

        self.assertEqual(
            seen["body"]["messages"][0]["content"],
            [
                {"type": "text", "text": "请分析音视频"},
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": "SUQzBAAAAAAA",
                        "format": "mp3",
                    },
                },
                {
                    "type": "video_url",
                    "video_url": {"url": "data:video/x-msvideo;base64,UklGRg=="},
                },
            ],
        )
        self.assertNotIn("plugins", seen["body"])

    def test_complete_chat_retries_transient_url_errors_before_success(self):
        attempts = []

        def flaky_urlopen(request, timeout):
            attempts.append(request.full_url)
            if len(attempts) < 3:
                raise error.URLError("connection reset")
            return FakeResponse()

        provider = ModelProvider(urlopen=flaky_urlopen)

        result = provider.complete_chat(
            api_url="https://provider.example/v1",
            api_key="secret",
            remote_model_id="remote-model",
            model_request=chat_request([{"role": "user", "content": "hello"}]),
        )

        self.assertEqual(result.content, "ok")
        self.assertEqual(len(attempts), 3)

    def test_complete_chat_timeout_budget_is_global_across_retries(self):
        attempts = []

        def timeout_urlopen(request, timeout):
            attempts.append(timeout)
            time.sleep(timeout)
            raise socket.timeout()

        provider = AliyunBailianProvider(urlopen=timeout_urlopen)
        started = time.monotonic()
        with self.assertRaises(ProviderChatCompletionError):
            provider.complete_chat(
                api_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="qwen3-vl-plus",
                model_request=chat_request([
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "mime_type": "image/jpeg",
                                "data_base64": "AA==",
                            }
                        ],
                    }
                ]),
                timeout_seconds=0.03,
            )

        self.assertEqual(len(attempts), 1)
        self.assertLessEqual(attempts[0], 0.03)
        self.assertLess(time.monotonic() - started, 0.15)

    def test_explicit_long_timeout_uses_one_nonduplicating_attempt(self):
        attempts = []

        def timeout_urlopen(request, timeout):
            attempts.append(timeout)
            raise socket.timeout()

        provider = AliyunBailianProvider(urlopen=timeout_urlopen)
        with self.assertRaisesRegex(ProviderChatCompletionError, "连接超时"):
            provider.complete_chat(
                api_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="qwen-plus",
                model_request=chat_request([{"role": "user", "content": "analyze"}]),
                timeout_seconds=90,
            )

        self.assertEqual(len(attempts), 1)
        self.assertGreater(attempts[0], 89)
        self.assertLessEqual(attempts[0], 90)

    def test_non_positive_timeout_disables_transport_deadline_without_retries(self):
        attempts = []

        def successful_urlopen(request, timeout):
            attempts.append(timeout)
            return FakeResponse()

        provider = AliyunBailianProvider(urlopen=successful_urlopen)
        result = provider.complete_chat(
            api_url="https://provider.example/v1",
            api_key="secret",
            remote_model_id="qwen3.7-plus",
            model_request=chat_request([{"role": "user", "content": "parse report"}]),
            timeout_seconds=0,
        )

        self.assertEqual(result.content, "ok")
        self.assertEqual(attempts, [None])

    def test_bare_completion_403_is_not_mislabeled_as_authentication(self):
        def forbidden_urlopen(request, timeout):
            raise error.HTTPError(
                request.full_url,
                403,
                "Forbidden",
                {},
                __import__("io").BytesIO(b"Forbidden"),
            )

        provider = AliyunBailianProvider(urlopen=forbidden_urlopen)
        with self.assertRaisesRegex(
            ProviderChatCompletionError,
            "模型服务网关拒绝请求，HTTP 403",
        ):
            provider.complete_chat(
                api_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="qwen-plus",
                model_request=chat_request([{"role": "user", "content": "analyze"}]),
            )

    def test_complete_chat_preserves_explicit_reasoning_content(self):
        provider = ModelProvider(urlopen=lambda request, timeout: FakeReasoningResponse())

        result = provider.complete_chat(
            api_url="https://provider.example/v1",
            api_key="secret",
            remote_model_id="remote-model",
            model_request=chat_request([{"role": "user", "content": "hello"}]),
        )

        self.assertEqual(result.content, "ok")
        self.assertEqual(result.reasoning, "check context")

    def test_stream_chat_yields_reasoning_and_content_deltas_from_sse(self):
        seen = {}

        def streaming_urlopen(request, timeout):
            seen["body"] = request.data.decode("utf-8")
            seen["accept"] = request.get_header("Accept")
            seen["timeout"] = timeout
            return FakeStreamingResponse()

        provider = ModelProvider(urlopen=streaming_urlopen)

        chunks = list(
            provider.stream_chat(
                api_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="remote-model",
                model_request=chat_request([{"role": "user", "content": "hello"}]),
                timeout_seconds=90,
            )
        )

        self.assertIn('"stream": true', seen["body"])
        self.assertEqual(seen["accept"], "text/event-stream")
        self.assertEqual(seen["timeout"], 90)
        self.assertEqual([chunk.reasoning_delta for chunk in chunks], ["think ", "first", "", ""])
        self.assertEqual([chunk.content_delta for chunk in chunks], ["", "", "hel", "lo"])
        self.assertEqual(chunks[-1].stop_reason, "stop")

    def test_stream_chat_non_positive_timeout_disables_transport_deadline(self):
        seen = []

        def streaming_urlopen(request, timeout):
            seen.append(timeout)
            return FakeStreamingResponse()

        provider = ModelProvider(urlopen=streaming_urlopen)
        list(
            provider.stream_chat(
                api_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="remote-model",
                model_request=chat_request([{"role": "user", "content": "parse report"}]),
                timeout_seconds=0,
            )
        )

        self.assertEqual(seen, [None])

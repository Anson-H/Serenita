import json
import unittest
from urllib import error

from backend.app.providers.aliyun_bailian import AliyunBailianProvider
from backend.app.providers.base import ModelProvider, ProviderChatCompletionError
from backend.app.providers.openrouter import OpenRouterProvider


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


class ProviderTransportTests(unittest.TestCase):
    def test_base_provider_rejects_file_attachment_parts(self):
        provider = ModelProvider(urlopen=lambda request, timeout: FakeStreamingResponse())

        with self.assertRaisesRegex(ProviderChatCompletionError, "不支持该附件类型"):
            list(
                provider.stream_chat(
                    base_url="https://provider.example/v1",
                    api_key="secret",
                    remote_model_id="remote-model",
                    messages=[
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
                    ],
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
                base_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="remote-model",
                messages=[
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
                ],
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
                base_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="remote-model",
                messages=[
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
                ],
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
                base_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="google/gemini-3.5-flash",
                messages=[
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
                ],
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
                base_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="remote-model",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请描述图片"},
                            {"type": "image", "mime_type": "image/jpeg", "data_base64": "/9j/4AAQSkZJRg=="},
                        ],
                    }
                ],
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
                base_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="qwen3.5-omni-plus",
                messages=[
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
                ],
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
            base_url="https://provider.example/v1",
            api_key="secret",
            remote_model_id="remote-model",
            messages=[{"role": "user", "content": "hello"}],
        )

        self.assertEqual(result.content, "ok")
        self.assertEqual(len(attempts), 3)

    def test_complete_chat_preserves_explicit_reasoning_content(self):
        provider = ModelProvider(urlopen=lambda request, timeout: FakeReasoningResponse())

        result = provider.complete_chat(
            base_url="https://provider.example/v1",
            api_key="secret",
            remote_model_id="remote-model",
            messages=[{"role": "user", "content": "hello"}],
        )

        self.assertEqual(result.content, "ok")
        self.assertEqual(result.thinking_content, "check context")

    def test_stream_chat_yields_reasoning_and_content_deltas_from_sse(self):
        seen = {}

        def streaming_urlopen(request, timeout):
            seen["body"] = request.data.decode("utf-8")
            seen["accept"] = request.get_header("Accept")
            return FakeStreamingResponse()

        provider = ModelProvider(urlopen=streaming_urlopen)

        chunks = list(
            provider.stream_chat(
                base_url="https://provider.example/v1",
                api_key="secret",
                remote_model_id="remote-model",
                messages=[{"role": "user", "content": "hello"}],
            )
        )

        self.assertIn('"stream": true', seen["body"])
        self.assertEqual(seen["accept"], "text/event-stream")
        self.assertEqual([chunk.thinking_delta for chunk in chunks], ["think ", "first", "", ""])
        self.assertEqual([chunk.content_delta for chunk in chunks], ["", "", "hel", "lo"])
        self.assertEqual(chunks[-1].stop_reason, "stop")


if __name__ == "__main__":
    unittest.main()

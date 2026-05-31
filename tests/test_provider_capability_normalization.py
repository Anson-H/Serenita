import json
import unittest


class ProviderCapabilityNormalizationTests(unittest.TestCase):
    def test_openrouter_models_are_normalized_from_architecture_and_supported_parameters(self):
        from backend.app.providers.openrouter import OpenRouterProvider

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "data": [
                            {
                                "id": "openai/gpt-4.1-mini",
                                "name": "GPT-4.1 Mini",
                                "architecture": {
                                    "input_modalities": ["text", "image", "file"],
                                    "output_modalities": ["text"],
                                },
                                "supported_parameters": [
                                    "tools",
                                    "response_format",
                                    "structured_outputs",
                                ],
                                "context_length": 1048576,
                                "top_provider": {"max_completion_tokens": 32768},
                            }
                        ]
                    }
                ).encode("utf-8")

        provider = OpenRouterProvider(urlopen=lambda request, timeout: Response())

        models = provider.list_models("https://openrouter.ai/api/v1", "sk-test")

        self.assertEqual(len(models), 1)
        model = models[0]
        self.assertEqual(model.remote_model_id, "openai/gpt-4.1-mini")
        self.assertTrue(model.supports_text)
        self.assertIn("image/png", model.file_mime_types)
        self.assertIn("application/pdf", model.file_mime_types)
        self.assertNotIn(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            model.file_mime_types,
        )
        self.assertNotIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            model.file_mime_types,
        )
        self.assertNotIn("application/msword", model.file_mime_types)
        self.assertNotIn("application/vnd.ms-excel", model.file_mime_types)
        self.assertTrue(model.supports_tool_calling)
        self.assertTrue(model.supports_json_output)
        self.assertEqual(model.context_window_tokens, 1048576)
        self.assertEqual(model.max_output_tokens, 32768)

    def test_openrouter_file_modality_only_advertises_pdf_documents(self):
        from backend.app.providers.openrouter import OpenRouterProvider

        provider = OpenRouterProvider()

        profile = provider.normalize_capabilities(
            {
                "architecture": {
                    "input_modalities": ["text", "file"],
                    "output_modalities": ["text"],
                }
            },
            "provider/native-file-model",
        )

        self.assertEqual(profile.file_mime_types, ["application/pdf"])

    def test_openrouter_gemini_3_multimodal_inputs_are_normalized_to_attachment_mime_types(self):
        from backend.app.providers.openrouter import OpenRouterProvider

        provider = OpenRouterProvider()

        profile = provider.normalize_capabilities(
            {
                "architecture": {
                    "input_modalities": ["text", "image", "file", "audio", "video"],
                    "output_modalities": ["text"],
                }
            },
            "google/gemini-3.5-flash",
        )

        self.assertIn("image/png", profile.file_mime_types)
        self.assertIn("application/pdf", profile.file_mime_types)
        self.assertIn("audio/mpeg", profile.file_mime_types)
        self.assertIn("video/mp4", profile.file_mime_types)

    def test_openrouter_gemini_3_image_preview_only_advertises_image_attachments(self):
        from backend.app.providers.openrouter import OpenRouterProvider

        provider = OpenRouterProvider()

        profile = provider.normalize_capabilities(
            {
                "architecture": {
                    "input_modalities": ["image", "text"],
                    "output_modalities": ["image", "text"],
                }
            },
            "google/gemini-3-pro-image-preview",
        )

        self.assertIn("image/png", profile.file_mime_types)
        self.assertNotIn("application/pdf", profile.file_mime_types)
        self.assertNotIn("audio/mpeg", profile.file_mime_types)
        self.assertNotIn("video/mp4", profile.file_mime_types)

    def test_deepseek_models_are_normalized_from_model_ids(self):
        from backend.app.providers.deepseek import DeepSeekProvider

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "object": "list",
                        "data": [
                            {
                                "id": "deepseek-v4-pro",
                                "object": "model",
                                "owned_by": "deepseek",
                            }
                        ],
                    }
                ).encode("utf-8")

        provider = DeepSeekProvider(urlopen=lambda request, timeout: Response())

        model = provider.list_models("https://api.deepseek.com", "sk-test")[0]

        self.assertTrue(model.supports_text)
        self.assertEqual(model.file_mime_types, [])
        self.assertEqual(model.thinking_modes, ["default", "high", "xhigh"])
        self.assertTrue(model.supports_tool_calling)
        self.assertTrue(model.supports_json_output)
        self.assertEqual(model.context_window_tokens, 1_000_000)

    def test_aliyun_bailian_models_are_normalized_from_model_ids(self):
        from backend.app.providers.aliyun_bailian import AliyunBailianProvider

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "object": "list",
                        "data": [
                            {
                                "id": "qwen3-vl-32b-thinking",
                                "object": "model",
                                "owned_by": "aliyun",
                            }
                        ],
                    }
                ).encode("utf-8")

        provider = AliyunBailianProvider(urlopen=lambda request, timeout: Response())

        model = provider.list_models(
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "sk-test",
        )[0]

        self.assertTrue(model.supports_text)
        self.assertIn("image/png", model.file_mime_types)
        self.assertIn("video/mp4", model.file_mime_types)
        self.assertEqual(model.thinking_modes, ["default", "high"])
        self.assertTrue(model.supports_tool_calling)
        self.assertTrue(model.supports_json_output)

    def test_aliyun_bailian_qwen_3_5_and_newer_attachment_mime_types_match_model_family(self):
        from backend.app.providers.aliyun_bailian import AliyunBailianProvider

        provider = AliyunBailianProvider()

        for model_id in ("qwen3.5-plus", "qwen3.6-plus", "qwen3-vl-plus"):
            with self.subTest(model_id=model_id):
                profile = provider.normalize_capabilities({}, model_id)

                self.assertIn("image/bmp", profile.file_mime_types)
                self.assertIn("image/png", profile.file_mime_types)
                self.assertIn("video/mp4", profile.file_mime_types)
                self.assertIn("video/x-msvideo", profile.file_mime_types)
                self.assertNotIn("audio/mpeg", profile.file_mime_types)

        for model_id in ("qwen3.5-omni-plus", "qwen3-omni-flash"):
            with self.subTest(model_id=model_id):
                profile = provider.normalize_capabilities({}, model_id)

                self.assertIn("image/png", profile.file_mime_types)
                self.assertIn("audio/mpeg", profile.file_mime_types)
                self.assertIn("audio/amr", profile.file_mime_types)
                self.assertIn("video/mp4", profile.file_mime_types)

        for model_id in ("qwen3.7-max", "qwen3.7-max-2026-05-20", "qwen3-max"):
            with self.subTest(model_id=model_id):
                profile = provider.normalize_capabilities({}, model_id)

                self.assertEqual(profile.file_mime_types, [])


if __name__ == "__main__":
    unittest.main()

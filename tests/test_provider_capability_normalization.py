import json
import unittest


class ProviderCapabilityNormalizationTests(unittest.TestCase):
    def test_capability_profiles_aggregate_with_boolean_or_and_mime_union(self):
        from backend.app.domain.model_capabilities import (
            ModelCapabilityProfiles,
            ModelModeCapabilityProfile,
            aggregate_capability_profile,
        )

        aggregate = aggregate_capability_profile(
            ModelCapabilityProfiles(
                default_state="thinking",
                non_thinking=ModelModeCapabilityProfile(
                    availability="available",
                    supports_text=True,
                    file_mime_types=["image/png"],
                    supports_tool_calling=True,
                ),
                thinking=ModelModeCapabilityProfile(
                    availability="unverified",
                    supports_text=True,
                    file_mime_types=["audio/wav", "image/png"],
                ),
            ),
            thinking_modes=["default", "off", "max"],
            context_window_tokens=1_000_000,
            max_output_tokens=131_072,
        )

        self.assertTrue(aggregate.supports_tool_calling)
        self.assertEqual(aggregate.file_mime_types, ["image/png", "audio/wav"])
        self.assertEqual(aggregate.thinking_modes[-1], "max")

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
        self.assertEqual(model.context_window_tokens, 1048576)
        self.assertEqual(model.max_output_tokens, 32768)
        self.assertEqual(
            model.capability_declarations,
            {
                "text": True,
                "tool_calling": True,
                "image_input": True,
                "pdf_input": True,
                "audio_input": False,
                "video_input": False,
                "thinking": False,
            },
        )

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

    def test_openrouter_preserves_minimal_reasoning_effort_from_metadata(self):
        from backend.app.providers.openrouter import OpenRouterProvider

        profile = OpenRouterProvider().normalize_capabilities(
            {
                "reasoning": {
                    "supported_efforts": ["minimal", "low", "high"],
                    "default_enabled": True,
                }
            },
            "provider/reasoning-model",
        )

        self.assertEqual(
            profile.thinking_modes,
            ["default", "off", "minimal", "low", "high"],
        )

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

    def test_provider_model_ids_do_not_infer_capabilities(self):
        from backend.app.domain.model_capabilities import DEFAULT_CAPABILITY_PROFILE
        from backend.app.providers.aliyun_bailian import AliyunBailianProvider
        from backend.app.providers.deepseek import DeepSeekProvider

        cases = (
            (DeepSeekProvider(), "deepseek-v4-flash-vision-exp"),
            (DeepSeekProvider(), "deepseek-reasoner"),
            (AliyunBailianProvider(), "qwen3.8-max"),
            (AliyunBailianProvider(), "qwen3.5-omni-plus"),
        )
        for provider, remote_model_id in cases:
            with self.subTest(
                provider=provider.provider_id,
                remote_model_id=remote_model_id,
            ):
                self.assertEqual(
                    provider.normalize_capabilities({}, remote_model_id),
                    DEFAULT_CAPABILITY_PROFILE,
                )
                self.assertEqual(
                    provider.capability_declarations({}, remote_model_id),
                    {},
                )

    def test_provider_native_formats_are_transport_metadata_not_model_inference(self):
        from backend.app.providers.aliyun_bailian import AliyunBailianProvider
        from backend.app.providers.deepseek import DeepSeekProvider

        self.assertEqual(
            DeepSeekProvider().native_attachment_mime_types(),
            {"image/jpeg", "image/png", "image/gif", "image/webp"},
        )
        aliyun_types = AliyunBailianProvider().native_attachment_mime_types()
        self.assertIn("image/bmp", aliyun_types)
        self.assertIn("image/tiff", aliyun_types)
        self.assertIn("audio/mpeg", aliyun_types)
        self.assertIn("video/mp4", aliyun_types)


def test_invalid_stored_model_profiles_raise_a_schema_error():
    import pytest
    from backend.app.storage.model_codec import capability_profiles_from_row
    from backend.app.storage.sqlite import UnsupportedSchemaError
    for value in (None, '', '{invalid'):
        with pytest.raises(UnsupportedSchemaError):
            capability_profiles_from_row({'capability_profiles': value})

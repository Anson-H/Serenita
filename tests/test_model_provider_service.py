import os
import tempfile
import unittest

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None


@unittest.skipIf(TestClient is None, "FastAPI is installed in the uv environment")
class ModelProviderServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["SERENITA_DATA_ROOT"] = self.tempdir.name

        from backend.app.api.auth import reset_auth_state_for_tests
        from backend.app.main import create_app

        reset_auth_state_for_tests()
        self.client = TestClient(create_app())
        sign_up_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "user_name": "DemoUser",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.headers = {
            "Authorization": f"Bearer {sign_up_response.json()['session_token']}"
        }

    def tearDown(self):
        self.tempdir.cleanup()
        os.environ.pop("SERENITA_DATA_ROOT", None)

    def test_reads_saved_default_models_by_usage_for_current_account(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "sk-test-secret",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        model_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "openrouter",
                "remote_model_id": "openai/gpt-4.1-mini",
                "model_name": "GPT-4.1 Mini",
            },
        )
        self.assertEqual(model_response.status_code, 200, model_response.text)
        title_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "openrouter",
                "remote_model_id": "anthropic/claude-sonnet-4.5",
                "model_name": "Claude Sonnet 4.5",
            },
        )
        self.assertEqual(title_response.status_code, 200, title_response.text)
        defaults_response = self.client.patch(
            "/api/model-defaults",
            headers=self.headers,
            json={
                "chat": "openrouter:openai/gpt-4.1-mini",
                "title": "openrouter:anthropic/claude-sonnet-4.5",
            },
        )
        self.assertEqual(defaults_response.status_code, 200, defaults_response.text)

        from backend.app.application.model_provider_service import ModelProviderService

        catalog = ModelProviderService()
        chat_model_id = "openrouter:openai/gpt-4.1-mini"
        title_model_id = "openrouter:anthropic/claude-sonnet-4.5"

        self.assertEqual(catalog.model_for_account("demo_patient", chat_model_id)["model_id"], chat_model_id)
        self.assertEqual(catalog.default_model_for_account("demo_patient")["model_id"], chat_model_id)
        self.assertEqual(catalog.default_model_for_account("demo_patient", "title")["model_id"], title_model_id)
        self.assertIsNone(catalog.default_model_for_account("demo_patient", "vision_parse"))
        self.assertIsNone(catalog.default_model_for_account("other_patient"))


if __name__ == "__main__":
    unittest.main()

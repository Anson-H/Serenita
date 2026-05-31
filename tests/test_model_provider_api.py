import unittest
import tempfile
import os
from urllib.parse import quote

from backend.app.storage.sqlite import connect

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None


@unittest.skipIf(TestClient is None, "FastAPI is installed in the uv environment")
class ModelProviderApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["SERENITA_DATA_ROOT"] = self.tempdir.name

        from backend.app.api.auth import reset_auth_state_for_tests
        from backend.app.api import model_providers
        from backend.app.providers.base import ModelProvider, ProviderConnectionResult, ProviderModel
        from backend.app.providers.registry import ProviderRegistry

        reset_auth_state_for_tests()
        self.model_providers_module = model_providers
        self.original_registry_factory = model_providers.create_default_provider_registry

        class FakeProvider(ModelProvider):
            provider_id = "fake"
            display_name = "Fake Provider"
            default_base_url = "https://provider.example/v1"
            default_official_url = "https://provider.example/top-up"

            def __init__(self):
                super().__init__()
                self.connection_attempt = None

            def test_connection(self, base_url, api_key):
                self.connection_attempt = {
                    "base_url": base_url,
                    "api_key": api_key,
                }
                return ProviderConnectionResult(
                    provider_id=self.provider_id,
                    reachable=True,
                    message="连接测试成功",
                )

            def list_models(self, base_url, api_key):
                self.model_list_attempt = {
                    "base_url": base_url,
                    "api_key": api_key,
                }
                return [
                    ProviderModel(
                        remote_model_id="remote-live-model",
                        model_name="Remote Live Model",
                        supports_text=True,
                        file_mime_types=[],
                        thinking_modes=["default"],
                    ),
                    ProviderModel(
                        remote_model_id="remote-second-model",
                        model_name="Remote Second Model",
                        supports_text=True,
                        file_mime_types=["image/png"],
                        thinking_modes=["default", "high"],
                        supports_tool_calling=True,
                    ),
                    ProviderModel(
                        remote_model_id="remote-gemini-3",
                        model_name="Remote Gemini 3",
                        supports_text=True,
                        file_mime_types=["image/png", "application/pdf", "audio/mpeg", "video/mp4"],
                        thinking_modes=["default", "low", "medium", "high"],
                        supports_tool_calling=True,
                        supports_json_output=True,
                        context_window_tokens=1048576,
                        max_output_tokens=65536,
                    ),
                ]

        self.fake_provider = FakeProvider()
        registry = ProviderRegistry()
        registry.register(self.fake_provider)
        model_providers.create_default_provider_registry = lambda: registry

        from backend.app.main import create_app

        self.client = TestClient(create_app())
        sign_up_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "user_name": "陈女士",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.headers = {
            "Authorization": f"Bearer {sign_up_response.json()['session_token']}"
        }

    def tearDown(self):
        self.model_providers_module.create_default_provider_registry = self.original_registry_factory
        self.tempdir.cleanup()
        os.environ.pop("SERENITA_DATA_ROOT", None)

    def test_list_model_providers_returns_default_base_urls(self):
        response = self.client.get("/api/model-providers", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "providers": [
                    {
                        "provider_id": "fake",
                        "provider_name": "Fake Provider",
                        "default_base_url": "https://provider.example/v1",
                        "default_official_url": "https://provider.example/top-up",
                        "base_url": "https://provider.example/v1",
                        "official_url": "https://provider.example/top-up",
                        "api_key": "",
                        "configured": False,
                        "default": False,
                    }
                ]
            },
        )

    def test_test_model_provider_uses_request_body_without_persisting_key(self):
        response = self.client.post(
            "/api/model-providers/fake/test",
            headers=self.headers,
            json={"api_key": "secret-key"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "provider_id": "fake",
                "reachable": True,
                "message": "连接测试成功",
            },
        )
        self.assertEqual(
            self.fake_provider.connection_attempt,
            {
                "base_url": "https://provider.example/v1",
                "api_key": "secret-key",
            },
        )

    def test_model_provider_api_key_is_returned_editable_and_stored_plain(self):
        create_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://provider.example/v1",
                "official_url": "https://provider.example/top-up",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(create_response.status_code, 200, create_response.text)
        self.assertEqual(create_response.json()["api_key"], "secret-key")

        update_response = self.client.patch(
            "/api/model-providers/fake",
            headers=self.headers,
            json={
                "base_url": "https://proxy.example/v1",
                "official_url": "https://provider.example/billing",
                "api_key": "replacement-key",
                "default": True,
            },
        )
        self.assertEqual(update_response.status_code, 200, update_response.text)
        self.assertTrue(update_response.json()["configured"])
        self.assertEqual(update_response.json()["base_url"], "https://proxy.example/v1")
        self.assertEqual(update_response.json()["official_url"], "https://provider.example/billing")
        self.assertEqual(update_response.json()["api_key"], "replacement-key")

        list_response = self.client.get("/api/model-providers", headers=self.headers)
        provider = list_response.json()["providers"][0]
        self.assertEqual(provider["api_key"], "replacement-key")
        self.assertEqual(provider["official_url"], "https://provider.example/billing")

        config_db = os.path.join(self.tempdir.name, "demo_patient", "config", "config.db")
        with connect(config_db) as connection:
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(model_providers)").fetchall()
            }
            row = connection.execute(
                "SELECT api_key, official_url FROM model_providers WHERE provider_id = ?",
                ("fake",),
            ).fetchone()
        self.assertIn("api_key", columns)
        self.assertIn("official_url", columns)
        self.assertNotIn("account_md5", columns)
        self.assertNotIn("key_md5", columns)
        self.assertNotIn("key_info_md5", columns)
        self.assertNotIn("key_info_data", columns)
        self.assertEqual(row["api_key"], "replacement-key")
        self.assertEqual(row["official_url"], "https://provider.example/billing")

        test_response = self.client.post(
            "/api/model-providers/fake/test",
            headers=self.headers,
            json={"base_url": "https://proxy.example/v1"},
        )
        self.assertEqual(test_response.status_code, 200, test_response.text)
        self.assertEqual(
            self.fake_provider.connection_attempt,
            {
                "base_url": "https://proxy.example/v1",
                "api_key": "replacement-key",
            },
        )

    def test_test_model_provider_maps_provider_failures_to_stable_error_codes(self):
        from backend.app.providers.base import ModelProvider, ProviderConnectionResult
        from backend.app.providers.registry import ProviderRegistry

        class AuthFailedProvider(ModelProvider):
            provider_id = "auth_failed"
            display_name = "Auth Failed"
            default_base_url = "https://provider.example/v1"

            def test_connection(self, base_url, api_key):
                return ProviderConnectionResult(
                    provider_id=self.provider_id,
                    reachable=False,
                    message="模型服务认证失败",
                )

        class TimeoutProvider(ModelProvider):
            provider_id = "timeout"
            display_name = "Timeout"
            default_base_url = "https://provider.example/v1"

            def test_connection(self, base_url, api_key):
                return ProviderConnectionResult(
                    provider_id=self.provider_id,
                    reachable=False,
                    message="连接超时",
                )

        registry = ProviderRegistry()
        registry.register(AuthFailedProvider())
        registry.register(TimeoutProvider())
        self.model_providers_module.create_default_provider_registry = lambda: registry

        auth_response = self.client.post(
            "/api/model-providers/auth_failed/test",
            headers=self.headers,
            json={"api_key": "bad-key"},
        )
        self.assertEqual(auth_response.status_code, 502)
        self.assertEqual(auth_response.json()["detail"]["code"], "PROVIDER_AUTH_FAILED")

        timeout_response = self.client.post(
            "/api/model-providers/timeout/test",
            headers=self.headers,
            json={"api_key": "slow-key"},
        )
        self.assertEqual(timeout_response.status_code, 504)
        self.assertEqual(timeout_response.json()["detail"]["code"], "MODEL_TIMEOUT")

    def test_fetch_provider_models_calls_remote_provider_with_saved_base_url_and_key(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)

        response = self.client.get("/api/model-providers/fake/models", headers=self.headers)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            self.fake_provider.model_list_attempt,
            {
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(
            response.json()["models"],
            [
                {
                    "remote_model_id": "remote-live-model",
                    "model_name": "Remote Live Model",
                    "supports_text": True,
                    "file_mime_types": [],
                    "thinking_modes": ["default"],
                    "supports_tool_calling": False,
                    "supports_json_output": False,
                    "context_window_tokens": None,
                    "max_output_tokens": None,
                },
                {
                    "remote_model_id": "remote-second-model",
                    "model_name": "Remote Second Model",
                    "supports_text": True,
                    "file_mime_types": ["image/png"],
                    "thinking_modes": ["default", "high"],
                    "supports_tool_calling": True,
                    "supports_json_output": False,
                    "context_window_tokens": None,
                    "max_output_tokens": None,
                },
                {
                    "remote_model_id": "remote-gemini-3",
                    "model_name": "Remote Gemini 3",
                    "supports_text": True,
                    "file_mime_types": ["image/png", "application/pdf", "audio/mpeg", "video/mp4"],
                    "thinking_modes": ["default", "low", "medium", "high"],
                    "supports_tool_calling": True,
                    "supports_json_output": True,
                    "context_window_tokens": 1048576,
                    "max_output_tokens": 65536,
                },
            ],
        )

    def test_model_provider_autosave_accepts_urls_before_api_key(self):
        response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://draft.example/v1",
                "official_url": "https://draft.example/top-up",
                "api_key": "",
                "default": False,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["configured"])
        self.assertEqual(response.json()["base_url"], "https://draft.example/v1")
        self.assertEqual(response.json()["official_url"], "https://draft.example/top-up")
        self.assertEqual(response.json()["api_key"], "")

        update_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://draft.example/v2",
                "official_url": "https://draft.example/billing",
                "api_key": "secret-key",
                "default": True,
            },
        )

        self.assertEqual(update_response.status_code, 200, update_response.text)
        self.assertTrue(update_response.json()["configured"])
        self.assertEqual(update_response.json()["base_url"], "https://draft.example/v2")
        self.assertEqual(update_response.json()["official_url"], "https://draft.example/billing")
        self.assertEqual(update_response.json()["api_key"], "secret-key")

    def test_add_model_accepts_remote_model_returned_by_live_catalog_payload(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)

        response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "model_name": "Remote Live Model",
                "supports_text": True,
                "file_mime_types": [],
                "thinking_modes": ["default"],
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["model_id"], "fake:remote-live-model")
        self.assertEqual(response.json()["model_name"], "Remote Live Model")
        self.assertTrue(response.json()["supports_text"])
        self.assertNotIn("supports_vision", response.json())
        self.assertEqual(response.json()["file_mime_types"], [])
        self.assertEqual(response.json()["thinking_modes"], ["default"])

        config_db = os.path.join(self.tempdir.name, "demo_patient", "config", "config.db")
        with connect(config_db) as connection:
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(models)").fetchall()
            }
            row = connection.execute(
                """
                SELECT supports_text, file_mime_types, thinking_modes
                FROM models WHERE model_id = ?
                """,
                ("fake:remote-live-model",),
            ).fetchone()
        self.assertNotIn("capabilities_json", columns)
        self.assertNotIn("supports_vision", columns)
        self.assertTrue(bool(row["supports_text"]))
        self.assertEqual(row["file_mime_types"], "")
        self.assertEqual(row["thinking_modes"], "default")

    def test_model_default_settings_are_stored_by_usage(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        chat_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "model_name": "Remote Live Model",
                "thinking_modes": ["default"],
            },
        )
        self.assertEqual(chat_response.status_code, 200, chat_response.text)
        title_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-second-model",
                "model_name": "Remote Second Model",
                "thinking_modes": ["default", "high"],
            },
        )
        self.assertEqual(title_response.status_code, 200, title_response.text)

        update_response = self.client.patch(
            "/api/model-defaults",
            headers=self.headers,
            json={
                "chat": "fake:remote-live-model",
                "title": "fake:remote-second-model",
                "vision_parse": None,
                "compact": None,
            },
        )
        self.assertEqual(update_response.status_code, 200, update_response.text)
        defaults = update_response.json()["defaults"]
        self.assertEqual(defaults["chat"]["model_id"], "fake:remote-live-model")
        self.assertEqual(defaults["title"]["model_id"], "fake:remote-second-model")
        self.assertIsNone(defaults["vision_parse"])
        self.assertNotIn("ocr", defaults)
        self.assertIsNone(defaults["compact"])

        get_response = self.client.get("/api/model-defaults", headers=self.headers)
        self.assertEqual(get_response.status_code, 200, get_response.text)
        self.assertEqual(get_response.json(), update_response.json())

        config_db = os.path.join(self.tempdir.name, "demo_patient", "config", "config.db")
        with connect(config_db) as connection:
            rows = connection.execute(
                "SELECT setting_key, model_id FROM model_default_settings ORDER BY setting_key"
            ).fetchall()
            model_columns = [
                row["name"]
                for row in connection.execute("PRAGMA table_info(models)").fetchall()
            ]
        self.assertNotIn("default_model", model_columns)
        self.assertEqual(
            [(row["setting_key"], row["model_id"]) for row in rows],
            [
                ("chat", "fake:remote-live-model"),
                ("compact", None),
                ("title", "fake:remote-second-model"),
                ("vision_parse", None),
            ],
        )
        legacy_response = self.client.patch(
            "/api/models/default",
            headers=self.headers,
            json={"model_id": "fake:remote-live-model"},
        )
        self.assertIn(legacy_response.status_code, {404, 405})

    def test_model_default_settings_repairs_legacy_foreign_key_before_update(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        model_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "model_name": "Remote Live Model",
                "thinking_modes": ["default"],
            },
        )
        self.assertEqual(model_response.status_code, 200, model_response.text)

        config_db = os.path.join(self.tempdir.name, "demo_patient", "config", "config.db")
        with connect(config_db) as connection:
            connection.execute("DROP TABLE model_default_settings")
            connection.execute(
                """
                CREATE TABLE model_default_settings (
                    setting_key TEXT PRIMARY KEY,
                    model_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (setting_key IN ('chat', 'title', 'ocr', 'compact')),
                    FOREIGN KEY (model_id) REFERENCES models_before_rebuild(model_id) ON DELETE SET NULL
                )
                """
            )

        update_response = self.client.patch(
            "/api/model-defaults",
            headers=self.headers,
            json={"chat": model_response.json()["model_id"]},
        )

        self.assertEqual(update_response.status_code, 200, update_response.text)
        self.assertEqual(update_response.json()["defaults"]["chat"]["model_id"], "fake:remote-live-model")
        with connect(config_db) as connection:
            default_foreign_keys = connection.execute(
                "PRAGMA foreign_key_list(model_default_settings)"
            ).fetchall()
        self.assertEqual(default_foreign_keys[0]["table"], "models")

    def test_model_default_settings_migrates_legacy_ocr_usage_to_vision_parse(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        model_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "model_name": "Remote Live Model",
                "thinking_modes": ["default"],
            },
        )
        self.assertEqual(model_response.status_code, 200, model_response.text)

        config_db = os.path.join(self.tempdir.name, "demo_patient", "config", "config.db")
        with connect(config_db) as connection:
            connection.execute("DROP TABLE model_default_settings")
            connection.execute(
                """
                CREATE TABLE model_default_settings (
                    setting_key TEXT PRIMARY KEY,
                    model_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (setting_key IN ('chat', 'title', 'ocr', 'compact')),
                    FOREIGN KEY (model_id) REFERENCES models(model_id) ON DELETE SET NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO model_default_settings (
                    setting_key, model_id, created_at, updated_at
                )
                VALUES ('ocr', ?, '2026-05-22T00:00:00+00:00', '2026-05-22T00:00:00+00:00')
                """,
                (model_response.json()["model_id"],),
            )

        defaults_response = self.client.get("/api/model-defaults", headers=self.headers)

        self.assertEqual(defaults_response.status_code, 200, defaults_response.text)
        defaults = defaults_response.json()["defaults"]
        self.assertNotIn("ocr", defaults)
        self.assertEqual(defaults["vision_parse"]["model_id"], "fake:remote-live-model")
        with connect(config_db) as connection:
            rows = connection.execute(
                "SELECT setting_key, model_id FROM model_default_settings ORDER BY setting_key"
            ).fetchall()
        self.assertEqual(
            [(row["setting_key"], row["model_id"]) for row in rows],
            [("vision_parse", "fake:remote-live-model")],
        )

    def test_model_default_settings_reject_models_from_other_accounts(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        other_signup = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "other_patient",
                "user_name": "Other",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        other_headers = {"Authorization": f"Bearer {other_signup.json()['session_token']}"}
        other_provider_response = self.client.post(
            "/api/model-providers",
            headers=other_headers,
            json={
                "provider_id": "fake",
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(other_provider_response.status_code, 200, other_provider_response.text)
        other_model_response = self.client.post(
            "/api/models",
            headers=other_headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "model_name": "Remote Live Model",
            },
        )
        self.assertEqual(other_model_response.status_code, 200, other_model_response.text)

        response = self.client.patch(
            "/api/model-defaults",
            headers=self.headers,
            json={"chat": other_model_response.json()["model_id"]},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "MODEL_NOT_FOUND")

    def test_add_model_rejects_inline_default_flag(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)

        response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "model_name": "Remote Live Model",
                "default": True,
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("default", response.text)

    def test_add_model_persists_gemini_3_multimodal_attachment_mime_types(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)

        response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-gemini-3",
                "model_name": "Remote Gemini 3",
                "supports_text": True,
                "file_mime_types": ["image/png", "application/pdf", "audio/mpeg", "video/mp4"],
                "thinking_modes": ["default", "low", "medium", "high"],
                "supports_tool_calling": True,
                "supports_json_output": True,
                "context_window_tokens": 1048576,
                "max_output_tokens": 65536,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["file_mime_types"],
            ["image/png", "application/pdf", "audio/mpeg", "video/mp4"],
        )

        config_db = os.path.join(self.tempdir.name, "demo_patient", "config", "config.db")
        with connect(config_db) as connection:
            row = connection.execute(
                "SELECT file_mime_types FROM models WHERE model_id = ?",
                ("fake:remote-gemini-3",),
            ).fetchone()
        self.assertEqual(row["file_mime_types"], "image/png\napplication/pdf\naudio/mpeg\nvideo/mp4")

    def test_add_builtin_rich_model_advertises_only_native_attachment_mime_types(self):
        from backend.app.providers.base import ModelProvider, ProviderConnectionResult
        from backend.app.providers.registry import ProviderRegistry

        class OpenRouterProvider(ModelProvider):
            provider_id = "openrouter"
            display_name = "OpenRouter"
            default_base_url = "https://openrouter.ai/api/v1"

            def test_connection(self, base_url, api_key):
                return ProviderConnectionResult(
                    provider_id=self.provider_id,
                    reachable=True,
                    message="连接测试成功",
                )

            def list_models(self, base_url, api_key):
                return []

        registry = ProviderRegistry()
        registry.register(OpenRouterProvider())
        self.model_providers_module.create_default_provider_registry = lambda: registry

        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "openrouter",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)

        response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "openrouter",
                "remote_model_id": "openai/gpt-4.1-mini",
                "model_name": "GPT-4.1 Mini",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("application/pdf", response.json()["file_mime_types"])
        self.assertNotIn(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            response.json()["file_mime_types"],
        )
        self.assertNotIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            response.json()["file_mime_types"],
        )
        self.assertNotIn("application/msword", response.json()["file_mime_types"])
        self.assertNotIn("application/vnd.ms-excel", response.json()["file_mime_types"])

    def test_add_model_rejects_legacy_capabilities_json_payload(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)

        response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "model_name": "Remote Live Model",
                "capabilities": {
                    "text": True,
                    "vision": False,
                    "file_input": False,
                    "file_mime_types": [],
                    "thinking_modes": ["default"],
                },
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("capabilities", response.text)

    def test_models_do_not_accept_return_or_store_supports_file_input(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)

        rejected_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "model_name": "Remote Live Model",
                "supports_file_input": True,
                "file_mime_types": ["image/png"],
            },
        )
        self.assertEqual(rejected_response.status_code, 422)
        self.assertIn("supports_file_input", rejected_response.text)

        response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "model_name": "Remote Live Model",
                "file_mime_types": ["image/png"],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("supports_file_input", response.json())

        list_response = self.client.get("/api/models", headers=self.headers)
        self.assertNotIn("supports_file_input", list_response.json()["models"][0])

        config_db = os.path.join(self.tempdir.name, "demo_patient", "config", "config.db")
        with connect(config_db) as connection:
            columns = [
                row[1]
                for row in connection.execute("PRAGMA table_info(models)").fetchall()
            ]
        self.assertNotIn("supports_file_input", columns)
        self.assertEqual(
            columns,
            [
                "model_id",
                "provider_id",
                "remote_model_id",
                "model_name",
                "created_at",
                "updated_at",
                "thinking_modes",
                "supports_text",
                "file_mime_types",
                "supports_tool_calling",
                "supports_json_output",
                "context_window_tokens",
                "max_output_tokens",
            ],
        )

    def test_models_do_not_accept_return_or_store_supports_vision(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)

        rejected_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "model_name": "Remote Live Model",
                "supports_vision": True,
                "file_mime_types": ["image/png"],
            },
        )
        self.assertEqual(rejected_response.status_code, 422)
        self.assertIn("supports_vision", rejected_response.text)

        response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "model_name": "Remote Live Model",
                "file_mime_types": ["image/png"],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("supports_vision", response.json())

        list_response = self.client.get("/api/models", headers=self.headers)
        self.assertNotIn("supports_vision", list_response.json()["models"][0])

        config_db = os.path.join(self.tempdir.name, "demo_patient", "config", "config.db")
        with connect(config_db) as connection:
            columns = [
                row[1]
                for row in connection.execute("PRAGMA table_info(models)").fetchall()
            ]
        self.assertNotIn("supports_vision", columns)

    def test_legacy_capabilities_json_is_migrated_to_split_columns(self):
        config_db = os.path.join(self.tempdir.name, "demo_patient", "config", "config.db")
        os.makedirs(os.path.dirname(config_db), exist_ok=True)
        with connect(config_db) as connection:
            connection.execute(
                """
                CREATE TABLE model_providers (
                    provider_id TEXT PRIMARY KEY,
                    provider_name TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    api_key TEXT,
                    configured INTEGER NOT NULL DEFAULT 0,
                    default_provider INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO model_providers (
                    provider_id, provider_name, base_url, api_key, configured,
                    default_provider, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "fake",
                    "Fake Provider",
                    "https://provider.example/v1",
                    "secret-key",
                    1,
                    1,
                    "2026-05-22T00:00:00+00:00",
                    "2026-05-22T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                CREATE TABLE models (
                    model_id TEXT PRIMARY KEY,
                    provider_id TEXT NOT NULL,
                    remote_model_id TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO models (
                    model_id, provider_id, remote_model_id, model_name,
                    capabilities_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "fake:legacy-model",
                    "fake",
                    "legacy-model",
                    "Legacy Model",
                    (
                        '{"text": true, "vision": true, "file_input": true, '
                        '"file_mime_types": ["image/png"], '
                        '"thinking_modes": ["default", "high"], '
                        '"supports_tool_calling": true}'
                    ),
                    "2026-05-22T00:00:00+00:00",
                    "2026-05-22T00:00:00+00:00",
                ),
            )

        response = self.client.get("/api/models", headers=self.headers)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["models"][0]["file_mime_types"], ["image/png"])
        self.assertEqual(response.json()["models"][0]["thinking_modes"], ["default", "high"])
        self.assertNotIn("supports_vision", response.json()["models"][0])
        self.assertTrue(response.json()["models"][0]["supports_tool_calling"])

        with connect(config_db) as connection:
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(models)").fetchall()
            }
        self.assertNotIn("capabilities_json", columns)
        self.assertNotIn("supports_vision", columns)
        self.assertIn("supports_text", columns)

    def test_delete_model_removes_added_model_and_clears_default_references(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        first_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "model_name": "Remote Live Model",
            },
        )
        second_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "second-live-model",
                "model_name": "Second Live Model",
            },
        )
        self.assertEqual(first_response.status_code, 200, first_response.text)
        self.assertEqual(second_response.status_code, 200, second_response.text)
        default_response = self.client.patch(
            "/api/model-defaults",
            headers=self.headers,
            json={"chat": first_response.json()["model_id"]},
        )
        self.assertEqual(default_response.status_code, 200, default_response.text)

        delete_response = self.client.delete(
            "/api/models/fake:remote-live-model",
            headers=self.headers,
        )

        self.assertEqual(delete_response.status_code, 200, delete_response.text)
        self.assertEqual(delete_response.json(), {"model_id": "fake:remote-live-model", "deleted": True})
        list_response = self.client.get("/api/models", headers=self.headers)
        self.assertEqual(
            list_response.json()["models"],
            [
                {
                    "model_id": "fake:second-live-model",
                    "provider_id": "fake",
                    "remote_model_id": "second-live-model",
                    "model_name": "Second Live Model",
                    "supports_text": True,
                    "file_mime_types": [],
                    "thinking_modes": ["default"],
                    "supports_tool_calling": False,
                    "supports_json_output": False,
                    "context_window_tokens": None,
                    "max_output_tokens": None,
                }
            ],
        )
        defaults_response = self.client.get("/api/model-defaults", headers=self.headers)
        self.assertEqual(defaults_response.status_code, 200, defaults_response.text)
        self.assertIsNone(defaults_response.json()["defaults"]["chat"])

    def test_delete_model_accepts_openrouter_model_ids_with_slashes(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "base_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        add_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "openai/gpt-4.1-mini",
                "model_name": "GPT-4.1 Mini",
            },
        )
        self.assertEqual(add_response.status_code, 200, add_response.text)

        model_id = add_response.json()["model_id"]
        delete_response = self.client.delete(
            f"/api/models/{quote(model_id, safe='')}",
            headers=self.headers,
        )

        self.assertEqual(delete_response.status_code, 200, delete_response.text)
        self.assertEqual(delete_response.json(), {"model_id": model_id, "deleted": True})
        self.assertEqual(
            self.client.get("/api/models", headers=self.headers).json(),
            {"models": []},
        )


if __name__ == "__main__":
    unittest.main()

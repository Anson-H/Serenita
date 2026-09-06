import unittest
import tempfile
import os
import threading
from urllib.parse import quote
from backend.app.storage.sqlite import connect
from backend.app.storage.paths import app_paths
from tests.api_client import TestClient


def _capability_profiles(
    *,
    file_mime_types=(),
    supports_text=True,
    supports_tool_calling=False,
):
    profile = {
        "availability": "available",
        "supports_text": supports_text,
        "file_mime_types": list(file_mime_types),
        "supports_tool_calling": supports_tool_calling,
    }
    return {
        "default_state": "unknown",
        "non_thinking": dict(profile),
        "thinking": dict(profile),
    }


class ModelProviderApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["DATA_ROOT"] = self.tempdir.name

        from backend.app.application import model_settings_service as model_providers
        from backend.app.model_capabilities import (
            ModelCapabilityProfiles,
            ModelModeCapabilityProfile,
        )
        from backend.app.providers.base import ModelProvider
        from backend.app.providers.errors import ProviderModelListError
        from backend.app.providers.types import ModelCapabilityProbeResult, ProviderConnectionResult, ProviderModel
        from backend.app.providers.registry import ProviderRegistry

        self.model_providers_module = model_providers
        self.original_registry_factory = model_providers.create_default_provider_registry

        class FakeProvider(ModelProvider):
            provider_id = "fake"
            provider_name = "Fake Provider"
            default_api_url = "https://provider.example/v1"
            default_official_url = "https://provider.example/top-up"

            def __init__(self):
                super().__init__()
                self.connection_attempt = None
                self.probe_attempt = None
                self.model_list_failure = None
                self.operation_order = []
                self.block_probe = False
                self.probe_started = threading.Event()
                self.probe_cancelled = threading.Event()

            def native_attachment_mime_types(self):
                return {"image/png", "application/pdf", "audio/mpeg", "video/mp4"}

            def test_connection(self, api_url, api_key):
                self.connection_attempt = {
                    "api_url": api_url,
                    "api_key": api_key,
                }
                return ProviderConnectionResult(
                    provider_id=self.provider_id,
                    reachable=True,
                    message="连接测试成功",
                )

            def list_models(self, api_url, api_key, cancellation_token=None):
                self.operation_order.append("metadata")
                if self.model_list_failure:
                    raise ProviderModelListError(self.model_list_failure)
                self.model_list_attempt = {
                    "api_url": api_url,
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
                        context_window_tokens=1048576,
                        max_output_tokens=65536,
                    ),
                ]

            def probe_capabilities(
                self,
                *,
                api_url,
                api_key,
                remote_model_id,
                current_profiles,
                thinking_modes,
                capability_declarations=None,
                cancellation_token=None,
            ):
                self.operation_order.append("probe")
                self.probe_attempt = {
                    "api_url": api_url,
                    "api_key": api_key,
                    "remote_model_id": remote_model_id,
                    "current_profiles": current_profiles,
                    "thinking_modes": thinking_modes,
                    "capability_declarations": dict(
                        capability_declarations or {}
                    ),
                }
                if self.block_probe:
                    self.probe_started.set()
                    if cancellation_token is None:
                        raise AssertionError("能力识别缺少取消令牌")
                    cancellation_token.register(self.probe_cancelled.set)
                    if not self.probe_cancelled.wait(timeout=3):
                        raise AssertionError("删除模型没有停止能力识别")
                    cancellation_token.raise_if_cancelled()
                probed = ModelModeCapabilityProfile(
                    availability="available",
                    supports_text=True,
                    file_mime_types=["image/png", "application/pdf"],
                    supports_tool_calling=True,
                )
                not_applicable = {
                    "text": "not_applicable",
                    "tool_calling": "not_applicable",
                    "image_input": "not_applicable",
                    "pdf_input": "not_applicable",
                    "audio_input": "not_applicable",
                    "video_input": "not_applicable",
                }
                supported = {
                    "text": "supported",
                    "tool_calling": "supported",
                    "image_input": "supported",
                    "pdf_input": "supported",
                    "audio_input": "unsupported",
                    "video_input": "unsupported",
                }
                thinking_mode_checks = {
                    "off": "supported",
                    "minimal": "unsupported",
                    "low": "unsupported",
                    "medium": "unsupported",
                    "high": "supported",
                    "xhigh": "unsupported",
                    "max": "unsupported",
                }
                thinking_profile = (
                    current_profiles.thinking
                    if current_profiles.thinking.availability == "unavailable"
                    else probed
                )
                return ModelCapabilityProbeResult(
                    profiles=ModelCapabilityProfiles(
                        default_state=current_profiles.default_state,
                        non_thinking=probed,
                        thinking=thinking_profile,
                    ),
                    checks={
                        "thinking_modes": thinking_mode_checks,
                        "aggregate": supported,
                        "non_thinking": supported,
                        "thinking": (
                            not_applicable
                            if thinking_profile.availability == "unavailable"
                            else supported
                        ),
                    },
                    errors={
                        "thinking_modes": {},
                        "non_thinking": {},
                        "thinking": {},
                    },
                )

        self.fake_provider = FakeProvider()
        registry = ProviderRegistry()
        registry.register(self.fake_provider)
        model_providers.create_default_provider_registry = lambda: registry

        from backend.app.main import create_app

        self.client = TestClient(create_app())
        sign_up = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "demo_patient",
                "account_name": "陈女士",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        self.account_id = sign_up.json()["account_id"]
        self.headers = {
            "X-Serenita-Account-ID": self.account_id,
            "Cookie": "serenita_auth_session_token="
            + self.client.cookies.get("serenita_auth_session_token")
        }

    def test_connection_uses_saved_provider_address(self):
        saved = self.client.post("/api/model-providers", headers=self.headers,
            json={"provider_id": "fake", "api_url": "https://custom.example/v1", "api_key": "test-key"})
        self.assertEqual(saved.status_code, 200)
        result = self.client.post("/api/model-providers/fake/test", headers=self.headers, json={})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.fake_provider.connection_attempt["api_url"], "https://custom.example/v1")

    def tearDown(self):
        self.model_providers_module.create_default_provider_registry = self.original_registry_factory
        self.tempdir.cleanup()
        os.environ.pop("DATA_ROOT", None)

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
                        "default_api_url": "https://provider.example/v1",
                        "default_official_url": "https://provider.example/top-up",
                        "native_attachment_mime_types": [
                            "application/pdf",
                            "audio/mpeg",
                            "image/png",
                            "video/mp4",
                        ],
                        "api_url": "https://provider.example/v1",
                        "official_url": "https://provider.example/top-up",
                        "has_api_key": False,
                        "is_configured": False,
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
                "api_url": "https://provider.example/v1",
                "api_key": "secret-key",
            },
        )

    def test_model_provider_api_key_is_redacted_by_default_and_explicitly_revealed(self):
        from backend.app.storage.crypto import unseal_secret

        create_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "api_url": "https://provider.example/v1",
                "official_url": "https://provider.example/top-up",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(create_response.status_code, 200, create_response.text)
        self.assertTrue(create_response.json()["has_api_key"])
        self.assertNotIn("api_key", create_response.json())
        self.assertNotIn("secret-key", create_response.text)

        update_response = self.client.patch(
            "/api/model-providers/fake",
            headers=self.headers,
            json={
                "api_url": "https://proxy.example/v1",
                "official_url": "https://provider.example/billing",
                "api_key": "replacement-key",
            },
        )
        self.assertEqual(update_response.status_code, 200, update_response.text)
        self.assertTrue(update_response.json()["is_configured"])
        self.assertEqual(update_response.json()["api_url"], "https://proxy.example/v1")
        self.assertEqual(update_response.json()["official_url"], "https://provider.example/billing")
        self.assertTrue(update_response.json()["has_api_key"])
        self.assertNotIn("api_key", update_response.json())
        self.assertNotIn("replacement-key", update_response.text)

        list_response = self.client.get("/api/model-providers", headers=self.headers)
        provider = list_response.json()["providers"][0]
        self.assertTrue(provider["has_api_key"])
        self.assertNotIn("api_key", provider)
        self.assertNotIn("replacement-key", list_response.text)
        self.assertEqual(provider["official_url"], "https://provider.example/billing")

        reveal_response = self.client.post(
            "/api/model-providers/fake/credential/reveal",
            headers=self.headers,
        )
        self.assertEqual(reveal_response.status_code, 200, reveal_response.text)
        self.assertEqual(
            reveal_response.json(),
            {"provider_id": "fake", "api_key": "replacement-key"},
        )
        self.assertIn("no-store", reveal_response.headers["cache-control"])
        self.assertEqual(reveal_response.headers["pragma"], "no-cache")

        config_db = app_paths().config_db(self.account_id)
        with connect(config_db) as connection:
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(model_providers)").fetchall()
            }
            row = connection.execute(
                "SELECT encrypted_api_key, official_url FROM model_providers WHERE provider_id = ?",
                ("fake",),
            ).fetchone()
        self.assertNotIn("api_key", columns)
        self.assertIn("official_url", columns)
        self.assertNotIn("account_md5", columns)
        self.assertNotIn("key_md5", columns)
        self.assertNotIn("key_info_md5", columns)
        self.assertIn("encrypted_api_key", columns)
        self.assertNotEqual(row["encrypted_api_key"], b"replacement-key")
        self.assertEqual(
            unseal_secret(self.account_id, "fake", row["encrypted_api_key"]),
            "replacement-key",
        )
        self.assertEqual(row["official_url"], "https://provider.example/billing")

        test_response = self.client.post(
            "/api/model-providers/fake/test",
            headers=self.headers,
            json={"api_url": "https://proxy.example/v1"},
        )
        self.assertEqual(test_response.status_code, 200, test_response.text)
        self.assertEqual(
            self.fake_provider.connection_attempt,
            {
                "api_url": "https://proxy.example/v1",
                "api_key": "replacement-key",
            },
        )

    def test_blank_or_omitted_provider_key_preserves_existing_secret(self):
        initial_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={"provider_id": "fake", "api_key": "original-key"},
        )
        self.assertEqual(initial_response.status_code, 200, initial_response.text)

        blank_response = self.client.patch(
            "/api/model-providers/fake",
            headers=self.headers,
            json={"api_url": "https://blank.example/v1", "api_key": "   "},
        )
        self.assertEqual(blank_response.status_code, 200, blank_response.text)
        self.assertTrue(blank_response.json()["has_api_key"])

        omitted_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={"provider_id": "fake", "official_url": "https://billing.example"},
        )
        self.assertEqual(omitted_response.status_code, 200, omitted_response.text)
        self.assertTrue(omitted_response.json()["has_api_key"])

        test_response = self.client.post(
            "/api/model-providers/fake/test",
            headers=self.headers,
            json={"api_url": "https://blank.example/v1", "api_key": ""},
        )
        self.assertEqual(test_response.status_code, 200, test_response.text)
        self.assertEqual(self.fake_provider.connection_attempt["api_key"], "original-key")

    def test_tampered_provider_secret_returns_safe_error(self):
        response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={"provider_id": "fake", "api_key": "private-value"},
        )
        self.assertEqual(response.status_code, 200, response.text)

        config_db = app_paths().config_db(self.account_id)
        with connect(config_db) as connection:
            row = connection.execute(
                "SELECT encrypted_api_key FROM model_providers WHERE provider_id = ?",
                ("fake",),
            ).fetchone()
            tampered = bytearray(row["encrypted_api_key"])
            tampered[-3] = ord("A") if tampered[-3] != ord("A") else ord("B")
            connection.execute(
                "UPDATE model_providers SET encrypted_api_key = ? WHERE provider_id = ?",
                (bytes(tampered), "fake"),
            )

        failed = self.client.post(
            "/api/model-providers/fake/test",
            headers=self.headers,
            json={},
        )
        self.assertEqual(failed.status_code, 422, failed.text)
        self.assertEqual(
            failed.json()["detail"]["code"],
            "PROVIDER_SECRET_UNAVAILABLE",
        )
        self.assertNotIn("private-value", failed.text)
        self.assertNotIn(row["encrypted_api_key"].decode("ascii"), failed.text)

    def test_test_model_provider_maps_provider_failures_to_stable_error_codes(self):
        from backend.app.providers.base import ModelProvider
        from backend.app.providers.types import ProviderConnectionResult
        from backend.app.providers.registry import ProviderRegistry

        class AuthFailedProvider(ModelProvider):
            provider_id = "auth_failed"
            provider_name = "Auth Failed"
            default_api_url = "https://provider.example/v1"

            def test_connection(self, api_url, api_key):
                return ProviderConnectionResult(
                    provider_id=self.provider_id,
                    reachable=False,
                    message="模型服务认证失败",
                    code="PROVIDER_AUTH_FAILED",
                )

        class TimeoutProvider(ModelProvider):
            provider_id = "timeout"
            provider_name = "Timeout"
            default_api_url = "https://provider.example/v1"

            def test_connection(self, api_url, api_key):
                return ProviderConnectionResult(
                    provider_id=self.provider_id,
                    reachable=False,
                    message="连接超时",
                    code="MODEL_TIMEOUT",
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
                "api_url": "https://proxy.example/v1",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)

        response = self.client.get("/api/model-providers/fake/models", headers=self.headers)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            self.fake_provider.model_list_attempt,
            {
                "api_url": "https://proxy.example/v1",
                "api_key": "secret-key",
            },
        )
        models = response.json()["models"]
        self.assertEqual(
            [model["remote_model_id"] for model in models],
            ["remote-live-model", "remote-second-model", "remote-gemini-3"],
        )
        self.assertEqual(models[1]["file_mime_types"], ["image/png"])
        self.assertTrue(models[1]["capability_profiles"]["thinking"]["supports_tool_calling"])
        self.assertEqual(models[2]["context_window_tokens"], 1048576)
        self.assertEqual(models[2]["max_output_tokens"], 65536)

    def test_aliyun_id_only_metadata_does_not_infer_capabilities(self):
        import json

        from backend.app.providers.aliyun_bailian import AliyunBailianProvider
        from backend.app.providers.registry import ProviderRegistry

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
                                "id": "qwen3.7-plus",
                                "owned_by": "aliyun",
                                "created": 1788000000,
                            }
                        ],
                    }
                ).encode("utf-8")

        provider = AliyunBailianProvider(urlopen=lambda request, timeout: Response())
        registry = ProviderRegistry()
        registry.register(provider)
        self.model_providers_module.create_default_provider_registry = lambda: registry

        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "aliyun_bailian",
                "api_key": "test-only-key",
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)

        remote_response = self.client.get(
            "/api/model-providers/aliyun_bailian/models",
            headers=self.headers,
        )
        self.assertEqual(remote_response.status_code, 200, remote_response.text)
        dynamic_model = remote_response.json()["models"][0]
        self.assertEqual(dynamic_model["created_at"], 1788000000)

        add_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "aliyun_bailian",
                "remote_model_id": "qwen3.7-plus",
            },
        )
        self.assertEqual(add_response.status_code, 200, add_response.text)
        added_model = add_response.json()

        for model in (dynamic_model, added_model):
            with self.subTest(model=model):
                self.assertTrue(model["supports_text"])
                self.assertEqual(model["file_mime_types"], [])
                self.assertEqual(model["thinking_modes"], ["default"])
                self.assertFalse(model["supports_tool_calling"])
                self.assertNotIn("supports_json_output", model)
                self.assertIsNone(model["max_output_tokens"])
        self.assertIsNone(dynamic_model["context_window_tokens"])
        self.assertEqual(added_model["context_window_tokens"], 131072)

    def test_model_provider_autosave_accepts_urls_before_api_key(self):
        response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "api_url": "https://draft.example/v1",
                "official_url": "https://draft.example/top-up",
                "api_key": "",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["is_configured"])
        self.assertEqual(response.json()["api_url"], "https://draft.example/v1")
        self.assertEqual(response.json()["official_url"], "https://draft.example/top-up")
        self.assertFalse(response.json()["has_api_key"])
        self.assertNotIn("api_key", response.json())

        update_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "api_url": "https://draft.example/v2",
                "official_url": "https://draft.example/billing",
                "api_key": "secret-key",
            },
        )

        self.assertEqual(update_response.status_code, 200, update_response.text)
        self.assertTrue(update_response.json()["is_configured"])
        self.assertEqual(update_response.json()["api_url"], "https://draft.example/v2")
        self.assertEqual(update_response.json()["official_url"], "https://draft.example/billing")
        self.assertTrue(update_response.json()["has_api_key"])
        self.assertNotIn("api_key", update_response.json())

    def test_add_model_accepts_remote_model_returned_by_live_catalog_payload(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "api_url": "https://proxy.example/v1",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)

        response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "thinking_modes": ["default", "off", "high", "max"],
                "capability_profiles": _capability_profiles(),
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["model_id"], "fake:remote-live-model")
        self.assertEqual(response.json()["model_name"], "remote-live-model")
        self.assertTrue(response.json()["supports_text"])
        self.assertNotIn("supports_vision", response.json())
        self.assertEqual(response.json()["file_mime_types"], [])
        self.assertEqual(
            response.json()["thinking_modes"],
            ["default", "off", "high", "max"],
        )
        self.assertEqual(response.json()["context_window_tokens"], 131072)
        self.assertIsNone(response.json()["max_output_tokens"])

        config_db = app_paths().config_db(self.account_id)
        with connect(config_db) as connection:
            table_info = connection.execute("PRAGMA table_info(models)").fetchall()
            columns = {row["name"] for row in table_info}
            row = connection.execute(
                """
                SELECT capability_profiles, thinking_modes,
                       context_window_tokens, max_output_tokens
                FROM models WHERE model_id = ?
                """,
                ("fake:remote-live-model",),
            ).fetchone()
        self.assertNotIn("capabilities_json", columns)
        self.assertNotIn("supports_vision", columns)
        self.assertNotIn("supports_text", columns)
        self.assertIn('"supports_text":true', row["capability_profiles"])
        self.assertEqual(row["thinking_modes"], "default\noff\nhigh\nmax")
        self.assertEqual(row["context_window_tokens"], 131072)
        self.assertIsNone(row["max_output_tokens"])
        context_column = next(
            item for item in table_info if item["name"] == "context_window_tokens"
        )
        self.assertEqual(context_column["notnull"], 1)
        self.assertEqual(context_column["dflt_value"], "131072")

    def test_capability_probe_updates_the_existing_model_row_only(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "api_url": "https://proxy.example/v1",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        add_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "thinking_modes": ["default", "off", "high", "max"],
                "context_window_tokens": 8192,
            },
        )
        self.assertEqual(add_response.status_code, 200, add_response.text)

        config_db = app_paths().config_db(self.account_id)
        with connect(config_db) as connection:
            rows_before = connection.execute("SELECT COUNT(*) AS count FROM models").fetchone()["count"]

        self.fake_provider.operation_order = []
        response = self.client.post(
            "/api/models/capability-probe/fake%3Aremote-live-model",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["model"]["model_id"], "fake:remote-live-model")
        self.assertEqual(response.json()["model"]["model_name"], "remote-live-model")
        self.assertEqual(response.json()["metadata"]["status"], "refreshed")
        self.assertEqual(
            response.json()["model"]["file_mime_types"],
            ["image/png", "application/pdf"],
        )
        self.assertTrue(response.json()["model"]["supports_tool_calling"])
        self.assertEqual(
            response.json()["model"]["thinking_modes"],
            ["default", "off", "high"],
        )
        self.assertNotIn("supports_json_output", response.json()["model"])
        self.assertEqual(response.json()["model"]["context_window_tokens"], 8192)
        expected_checks = {
                "text": "supported",
                "tool_calling": "supported",
                "image_input": "supported",
                "pdf_input": "supported",
                "audio_input": "unsupported",
                "video_input": "unsupported",
        }
        self.assertEqual(response.json()["checks"]["aggregate"], expected_checks)
        self.assertEqual(response.json()["checks"]["non_thinking"], expected_checks)
        self.assertEqual(response.json()["checks"]["thinking"], expected_checks)
        self.assertEqual(
            self.fake_provider.probe_attempt,
            {
                "api_url": "https://proxy.example/v1",
                "api_key": "secret-key",
                "remote_model_id": "remote-live-model",
                "current_profiles": self.fake_provider.probe_attempt["current_profiles"],
                "thinking_modes": ["default", "off", "high", "max"],
                "capability_declarations": {},
            },
        )
        self.assertEqual(
            self.fake_provider.probe_attempt["current_profiles"].default_state,
            "non_thinking",
        )
        self.assertEqual(
            self.fake_provider.probe_attempt["current_profiles"].thinking.availability,
            "available",
        )
        self.assertEqual(self.fake_provider.operation_order, ["metadata", "probe"])
        with connect(config_db) as connection:
            rows_after = connection.execute("SELECT COUNT(*) AS count FROM models").fetchone()["count"]
        self.assertEqual(rows_after, rows_before)

    def test_capability_probe_continues_when_metadata_refresh_is_unavailable(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "api_url": "https://proxy.example/v1",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        add_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
                "thinking_modes": ["default", "off", "high", "max"],
            },
        )
        self.assertEqual(add_response.status_code, 200, add_response.text)

        self.fake_provider.model_list_failure = "元数据服务暂不可用"
        self.fake_provider.operation_order = []
        response = self.client.post(
            "/api/models/capability-probe/fake%3Aremote-live-model",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["metadata"]["status"], "unavailable")
        self.assertIn("元数据服务暂不可用", response.json()["metadata"]["message"])
        self.assertEqual(self.fake_provider.operation_order, ["metadata", "probe"])
        self.assertEqual(
            self.fake_provider.probe_attempt["thinking_modes"],
            ["default", "off", "high", "max"],
        )
        self.assertEqual(
            set(response.json()["checks"]["thinking"].values()),
            {"supported", "unsupported"},
        )

    def test_deleting_model_cancels_inflight_capability_probe(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "api_url": "https://proxy.example/v1",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        add_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
            },
        )
        self.assertEqual(add_response.status_code, 200, add_response.text)

        self.fake_provider.block_probe = True
        probe_result = {}

        def run_probe():
            probe_result["response"] = self.client.post(
                "/api/models/capability-probe/fake%3Aremote-live-model",
                headers=self.headers,
            )

        probe_thread = threading.Thread(target=run_probe)
        probe_thread.start()
        self.assertTrue(self.fake_provider.probe_started.wait(timeout=1))

        delete_response = self.client.delete(
            "/api/models/fake%3Aremote-live-model",
            headers=self.headers,
        )
        probe_thread.join(timeout=2)

        self.assertEqual(delete_response.status_code, 200, delete_response.text)
        self.assertFalse(probe_thread.is_alive())
        self.assertTrue(self.fake_provider.probe_cancelled.is_set())
        self.assertEqual(probe_result["response"].status_code, 409)
        self.assertEqual(
            probe_result["response"].json()["detail"]["code"],
            "MODEL_CAPABILITY_PROBE_CANCELLED",
        )
        models_response = self.client.get("/api/models", headers=self.headers)
        self.assertEqual(models_response.json()["models"], [])

    def test_model_patch_visually_editable_columns_without_changing_identity(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={"provider_id": "fake", "api_key": "secret-key"},
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        add_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
            },
        )
        self.assertEqual(add_response.status_code, 200, add_response.text)

        response = self.client.patch(
            "/api/models/fake%3Aremote-live-model",
            headers=self.headers,
            json={
                "model_name": "Edited Model",
                "thinking_modes": ["default", "off", "high", "max"],
                "capability_profiles": {
                    "default_state": "non_thinking",
                    "non_thinking": {
                        "availability": "available",
                        "supports_text": True,
                        "file_mime_types": ["image/png", "application/pdf", "image/png"],
                        "supports_tool_calling": True,
                    },
                    "thinking": {
                        "availability": "available",
                        "supports_text": True,
                        "file_mime_types": ["image/png"],
                        "supports_tool_calling": False,
                    },
                },
                "context_window_tokens": 131072,
                "max_output_tokens": None,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["model_id"], "fake:remote-live-model")
        self.assertEqual(response.json()["provider_id"], "fake")
        self.assertEqual(response.json()["remote_model_id"], "remote-live-model")
        self.assertEqual(response.json()["model_name"], "Edited Model")
        self.assertEqual(response.json()["file_mime_types"], ["image/png", "application/pdf"])
        self.assertEqual(
            response.json()["thinking_modes"],
            ["default", "off", "high", "max"],
        )
        self.assertFalse(
            response.json()["capability_profiles"]["thinking"]["supports_tool_calling"]
        )
        self.assertNotIn("supports_json_output", response.json())
        self.assertNotIn(
            "supports_json_output",
            response.json()["capability_profiles"]["non_thinking"],
        )
        self.assertEqual(response.json()["context_window_tokens"], 131072)
        self.assertIsNone(response.json()["max_output_tokens"])

        custom_context = self.client.patch(
            "/api/models/fake%3Aremote-live-model",
            headers=self.headers,
            json={"context_window_tokens": 8192},
        )
        self.assertEqual(custom_context.status_code, 200, custom_context.text)
        self.assertEqual(custom_context.json()["context_window_tokens"], 8192)
        restored_default = self.client.patch(
            "/api/models/fake%3Aremote-live-model",
            headers=self.headers,
            json={"context_window_tokens": None},
        )
        self.assertEqual(restored_default.status_code, 200, restored_default.text)
        self.assertEqual(restored_default.json()["context_window_tokens"], 131072)
        self.assertIsNone(restored_default.json()["max_output_tokens"])

        immutable_response = self.client.patch(
            "/api/models/fake%3Aremote-live-model",
            headers=self.headers,
            json={"provider_id": "another"},
        )
        self.assertEqual(immutable_response.status_code, 422, immutable_response.text)

        minimal_mode_response = self.client.patch(
            "/api/models/fake%3Aremote-live-model",
            headers=self.headers,
            json={"thinking_modes": ["default", "minimal", "high"]},
        )
        self.assertEqual(minimal_mode_response.status_code, 200, minimal_mode_response.text)
        self.assertEqual(
            minimal_mode_response.json()["thinking_modes"],
            ["default", "minimal", "high"],
        )

        invalid_mode_response = self.client.patch(
            "/api/models/fake%3Aremote-live-model",
            headers=self.headers,
            json={"thinking_modes": ["default", "unsupported-mode", "high"]},
        )
        self.assertEqual(invalid_mode_response.status_code, 422, invalid_mode_response.text)
        self.assertEqual(
            invalid_mode_response.json()["detail"]["code"],
            "INVALID_THINKING_MODES",
        )

        config_db = app_paths().config_db(self.account_id)
        with connect(config_db) as connection:
            rows = connection.execute(
                "SELECT model_id, provider_id, remote_model_id, capability_profiles FROM models"
            ).fetchall()
        self.assertEqual(
            [(row["model_id"], row["provider_id"], row["remote_model_id"]) for row in rows],
            [("fake:remote-live-model", "fake", "remote-live-model")],
        )
        self.assertNotIn("supports_json_output", rows[0]["capability_profiles"])

    def test_model_access_settings_are_stored_in_one_row(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "api_url": "https://proxy.example/v1",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        chat_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
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
                "thinking_modes": ["default", "high"],
            },
        )
        self.assertEqual(title_response.status_code, 200, title_response.text)

        update_response = self.client.patch(
            "/api/model-access-settings",
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

        get_response = self.client.get("/api/model-access-settings", headers=self.headers)
        self.assertEqual(get_response.status_code, 200, get_response.text)
        self.assertEqual(get_response.json(), update_response.json())

        config_db = app_paths().config_db(self.account_id)
        with connect(config_db) as connection:
            row = connection.execute(
                """
                SELECT singleton_id, chat_model_id, title_model_id,
                       vision_parse_model_id, compact_model_id
                FROM model_access_settings
                """
            ).fetchone()
            model_columns = [
                row["name"]
                for row in connection.execute("PRAGMA table_info(models)").fetchall()
            ]
        self.assertNotIn("default_model", model_columns)
        self.assertEqual(
            tuple(row),
            (
                1,
                "fake:remote-live-model",
                "fake:remote-second-model",
                None,
                None,
            ),
        )

        from backend.app.application.model_provider_service import ModelProviderService
        catalog = ModelProviderService()
        self.assertEqual(catalog.model_for_account(self.account_id, "fake:remote-live-model")["model_id"], "fake:remote-live-model")
        self.assertEqual(catalog.default_model_for_account(self.account_id)["model_id"], "fake:remote-live-model")
        self.assertEqual(catalog.default_model_for_account(self.account_id, "title")["model_id"], "fake:remote-second-model")
        self.assertIsNone(catalog.default_model_for_account(self.account_id, "vision_parse"))


    def test_model_access_settings_reject_models_from_other_accounts(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "api_url": "https://proxy.example/v1",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "other_patient",
                "account_name": "Other",
                "password": "secret",
                "confirm_password": "secret",
            },
        )
        other_headers = {
            "Cookie": "serenita_auth_session_token="
            + self.client.cookies.get("serenita_auth_session_token")
        }
        other_provider_response = self.client.post(
            "/api/model-providers",
            headers=other_headers,
            json={
                "provider_id": "fake",
                "api_url": "https://proxy.example/v1",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(other_provider_response.status_code, 200, other_provider_response.text)
        other_model_response = self.client.post(
            "/api/models",
            headers=other_headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
            },
        )
        self.assertEqual(other_model_response.status_code, 200, other_model_response.text)

        response = self.client.patch(
            "/api/model-access-settings",
            headers=self.headers,
            json={"chat": other_model_response.json()["model_id"]},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "MODEL_NOT_FOUND")

    def test_add_model_rejects_derived_and_default_fields(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "api_url": "https://proxy.example/v1",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)

        for field_name, value in (
            ("model_name", "Remote Live Model"),
            ("default", True),
        ):
            with self.subTest(field_name=field_name):
                response = self.client.post(
                    "/api/models",
                    headers=self.headers,
                    json={
                        "provider_id": "fake",
                        "remote_model_id": "remote-live-model",
                        field_name: value,
                    },
                )

                self.assertEqual(response.status_code, 422)
                self.assertIn(field_name, response.text)

    def test_add_model_persists_gemini_3_multimodal_attachment_mime_types(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "api_url": "https://proxy.example/v1",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)

        response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-gemini-3",
                "thinking_modes": ["default", "low", "medium", "high"],
                "capability_profiles": _capability_profiles(
                    file_mime_types=[
                        "image/png",
                        "application/pdf",
                        "audio/mpeg",
                        "video/mp4",
                    ],
                    supports_tool_calling=True,
                ),
                "context_window_tokens": 1048576,
                "max_output_tokens": 65536,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["file_mime_types"],
            ["image/png", "application/pdf", "audio/mpeg", "video/mp4"],
        )

        config_db = app_paths().config_db(self.account_id)
        with connect(config_db) as connection:
            row = connection.execute(
                "SELECT capability_profiles FROM models WHERE model_id = ?",
                ("fake:remote-gemini-3",),
            ).fetchone()
        self.assertIn('"audio/mpeg"', row["capability_profiles"])
        self.assertIn('"video/mp4"', row["capability_profiles"])
        self.assertNotIn("supports_json_output", row["capability_profiles"])

    def test_add_model_without_metadata_does_not_infer_capabilities_from_id(self):
        from backend.app.providers.types import ProviderConnectionResult
        from backend.app.providers.openrouter import OpenRouterProvider
        from backend.app.providers.registry import ProviderRegistry

        class StubOpenRouterProvider(OpenRouterProvider):
            def test_connection(self, api_url, api_key):
                return ProviderConnectionResult(
                    provider_id=self.provider_id,
                    reachable=True,
                    message="连接测试成功",
                )

            def list_models(self, api_url, api_key, cancellation_token=None):
                return []

        registry = ProviderRegistry()
        registry.register(StubOpenRouterProvider())
        self.model_providers_module.create_default_provider_registry = lambda: registry

        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "openrouter",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)

        response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "openrouter",
                "remote_model_id": "openai/gpt-4.1-mini",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["file_mime_types"], [])
        self.assertEqual(response.json()["thinking_modes"], ["default"])
        self.assertFalse(response.json()["supports_tool_calling"])


    def test_delete_model_removes_added_model_and_clears_default_references(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "api_url": "https://proxy.example/v1",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        first_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "remote-live-model",
            },
        )
        second_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "second-live-model",
            },
        )
        self.assertEqual(first_response.status_code, 200, first_response.text)
        self.assertEqual(second_response.status_code, 200, second_response.text)
        default_response = self.client.patch(
            "/api/model-access-settings",
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
        remaining_models = list_response.json()["models"]
        self.assertEqual(len(remaining_models), 1)
        self.assertEqual(remaining_models[0]["model_id"], "fake:second-live-model")
        self.assertEqual(
            remaining_models[0]["capability_profiles"]["default_state"],
            "non_thinking",
        )
        defaults_response = self.client.get("/api/model-access-settings", headers=self.headers)
        self.assertEqual(defaults_response.status_code, 200, defaults_response.text)
        self.assertIsNone(defaults_response.json()["defaults"]["chat"])

    def test_delete_model_accepts_openrouter_model_ids_with_slashes(self):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "api_url": "https://proxy.example/v1",
                "api_key": "secret-key",
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        add_response = self.client.post(
            "/api/models",
            headers=self.headers,
            json={
                "provider_id": "fake",
                "remote_model_id": "openai/gpt-4.1-mini",
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

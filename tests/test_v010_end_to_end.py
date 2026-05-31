import json
import os
import tempfile
import time
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None


def _test_chunks(text, chunk_size):
    for index in range(0, len(text or ""), chunk_size):
        yield text[index : index + chunk_size]


@unittest.skipIf(TestClient is None, "FastAPI is installed in the uv environment")
class V010EndToEndApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["SERENITA_DATA_ROOT"] = self.tempdir.name

        from backend.app.api.auth import reset_auth_state_for_tests
        from backend.app.main import create_app

        reset_auth_state_for_tests()
        self.client = TestClient(create_app())
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()
        os.environ.pop("SERENITA_DATA_ROOT", None)

    def sign_up(self, account="demo_patient", user_name="陈女士", password="secret"):
        response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": account,
                "user_name": user_name,
                "password": password,
                "confirm_password": password,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        token = response.json()["session_token"]
        return response.json(), {"Authorization": f"Bearer {token}"}

    def add_default_model(self, headers):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=headers,
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
            headers=headers,
            json={
                "provider_id": "openrouter",
                "remote_model_id": "openai/gpt-4.1-mini",
                "model_name": "GPT-4.1 Mini",
            },
        )
        self.assertEqual(model_response.status_code, 200, model_response.text)
        model = model_response.json()
        default_response = self.client.patch(
            "/api/model-defaults",
            headers=headers,
            json={"chat": model["model_id"]},
        )
        self.assertEqual(default_response.status_code, 200, default_response.text)
        return model

    def add_deepseek_model(self, headers):
        provider_response = self.client.post(
            "/api/model-providers",
            headers=headers,
            json={
                "provider_id": "deepseek",
                "base_url": "https://api.deepseek.com",
                "api_key": "sk-deepseek-test",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        model_response = self.client.post(
            "/api/models",
            headers=headers,
            json={
                "provider_id": "deepseek",
                "remote_model_id": "deepseek-chat",
                "model_name": "DeepSeek Chat",
            },
        )
        self.assertEqual(model_response.status_code, 200, model_response.text)
        model = model_response.json()
        default_response = self.client.patch(
            "/api/model-defaults",
            headers=headers,
            json={"chat": model["model_id"]},
        )
        self.assertEqual(default_response.status_code, 200, default_response.text)
        return model

    def install_fake_openrouter_registry(
        self,
        thinking_content="",
        thinking_chunk_delay_seconds=0.0,
        response_content=None,
        title_response_content=None,
    ):
        from backend.app.api import model_providers
        from backend.app.application import model_provider_service
        from backend.app.providers.base import ChatCompletionChunk, ModelProvider, ProviderModel
        from backend.app.providers.registry import ProviderRegistry

        class ProviderCalls(list):
            pass

        calls = ProviderCalls()
        calls.title_calls = []

        def provider_text(content):
            if isinstance(content, list):
                return "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            return content

        class TestOpenRouterProvider(ModelProvider):
            provider_id = "openrouter"
            display_name = "OpenRouter"
            default_base_url = "https://openrouter.ai/api/v1"
            default_official_url = "https://openrouter.ai/settings/credits"

            def list_models(self, base_url, api_key):
                return [
                    ProviderModel(
                        remote_model_id="openai/gpt-4.1-mini",
                        model_name="GPT-4.1 Mini",
                        supports_text=True,
                        file_mime_types=["application/pdf"],
                        thinking_modes=["default", "fast"],
                    )
                ]

            def native_attachment_mime_types(self):
                return {
                    "application/pdf",
                    "image/png",
                    "image/jpeg",
                    "image/heic",
                    "image/webp",
                    "audio/mpeg",
                    "video/mp4",
                }

            def complete_chat(self, base_url, api_key, remote_model_id, messages, thinking_mode):
                explicit_thinking = thinking_content
                is_title_request = any(
                    "会话标题" in provider_text(message.get("content", ""))
                    or "只输出标题" in provider_text(message.get("content", ""))
                    for message in messages
                )
                last_user_text = provider_text(messages[-1]["content"])
                call = {
                    "base_url": base_url,
                    "api_key": api_key,
                    "remote_model_id": remote_model_id,
                    "messages": messages,
                    "thinking_mode": thinking_mode,
                }
                if is_title_request:
                    calls.title_calls.append(call)
                else:
                    calls.append(call)

                class Result:
                    content = (
                        title_response_content
                        if is_title_request and title_response_content is not None
                        else "头晕注意事项"
                        if is_title_request and "头晕" in last_user_text
                        else "健康咨询摘要"
                        if is_title_request
                        else response_content or f"模型真实回复 {len(calls)}：核心结论：{last_user_text}"
                    )
                    thinking_content = explicit_thinking
                    usage = {"input_tokens": 7, "output_tokens": 11}
                    stop_reason = "end_turn"

                return Result()

            def stream_chat(self, base_url, api_key, remote_model_id, messages, thinking_mode):
                result = self.complete_chat(base_url, api_key, remote_model_id, messages, thinking_mode)
                for delta in _test_chunks(result.thinking_content, 12):
                    yield ChatCompletionChunk(thinking_delta=delta)
                    if thinking_chunk_delay_seconds:
                        time.sleep(thinking_chunk_delay_seconds)
                for delta in _test_chunks(result.content, 12):
                    yield ChatCompletionChunk(content_delta=delta)
                yield ChatCompletionChunk(stop_reason=result.stop_reason, usage=result.usage)

        registry = ProviderRegistry()
        registry.register(TestOpenRouterProvider())
        original_api_registry_factory = model_providers.create_default_provider_registry
        original_service_registry_factory = getattr(
            model_provider_service,
            "create_default_provider_registry",
            None,
        )
        model_providers.create_default_provider_registry = lambda: registry
        model_provider_service.create_default_provider_registry = lambda: registry

        def restore():
            model_providers.create_default_provider_registry = original_api_registry_factory
            if original_service_registry_factory is None:
                delattr(model_provider_service, "create_default_provider_registry")
            else:
                model_provider_service.create_default_provider_registry = original_service_registry_factory

        return calls, restore

    def install_fake_chat_and_vision_registry(self):
        from backend.app.api import model_providers
        from backend.app.application import model_provider_service
        from backend.app.providers.base import ChatCompletionChunk, ModelProvider
        from backend.app.providers.registry import ProviderRegistry

        class ProviderCalls:
            def __init__(self):
                self.chat_calls = []
                self.vision_calls = []
                self.order = []

        calls = ProviderCalls()

        def provider_text(content):
            if isinstance(content, list):
                return "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            return content

        class TestDeepSeekProvider(ModelProvider):
            provider_id = "deepseek"
            display_name = "深度求索"
            default_base_url = "https://api.deepseek.com"
            default_official_url = "https://platform.deepseek.com/top_up"

            def complete_chat(self, base_url, api_key, remote_model_id, messages, thinking_mode):
                is_title_request = any(
                    "会话标题" in provider_text(message.get("content", ""))
                    or "只输出标题" in provider_text(message.get("content", ""))
                    for message in messages
                )
                if is_title_request:
                    class TitleResult:
                        content = "附件解读"
                        thinking_content = ""
                        usage = {}
                        stop_reason = "end_turn"

                    return TitleResult()

                calls.order.append("chat")
                calls.chat_calls.append(
                    {
                        "remote_model_id": remote_model_id,
                        "messages": messages,
                        "thinking_mode": thinking_mode,
                    }
                )
                all_text = "\n".join(provider_text(message.get("content", "")) for message in messages)

                class Result:
                    content = f"DeepSeek 最终回答：{all_text}"
                    thinking_content = ""
                    usage = {"input_tokens": 9, "output_tokens": 13}
                    stop_reason = "end_turn"

                return Result()

            def stream_chat(self, base_url, api_key, remote_model_id, messages, thinking_mode):
                result = self.complete_chat(base_url, api_key, remote_model_id, messages, thinking_mode)
                for delta in _test_chunks(result.content, 12):
                    yield ChatCompletionChunk(content_delta=delta)
                yield ChatCompletionChunk(stop_reason=result.stop_reason, usage=result.usage)

        class TestOpenRouterProvider(ModelProvider):
            provider_id = "openrouter"
            display_name = "OpenRouter"
            default_base_url = "https://openrouter.ai/api/v1"
            default_official_url = "https://openrouter.ai/settings/credits"

            def native_attachment_mime_types(self):
                return {
                    "image/png",
                    "image/jpeg",
                    "image/heic",
                    "image/webp",
                    "application/pdf",
                }

            def complete_chat(self, base_url, api_key, remote_model_id, messages, thinking_mode):
                is_title_request = any(
                    "会话标题" in provider_text(message.get("content", ""))
                    or "只输出标题" in provider_text(message.get("content", ""))
                    for message in messages
                )
                if is_title_request:
                    class TitleResult:
                        content = "附件解读"
                        thinking_content = ""
                        usage = {}
                        stop_reason = "end_turn"

                    return TitleResult()

                if remote_model_id == "anthropic/claude-sonnet-4.5":
                    calls.order.append("vision_parse")
                    calls.vision_calls.append(
                        {
                            "remote_model_id": remote_model_id,
                            "messages": messages,
                            "thinking_mode": thinking_mode,
                        }
                    )

                    class VisionResult:
                        content = "视觉解析结果：乙肝表面抗原阳性，ALT 轻度升高。"
                        thinking_content = ""
                        usage = {"input_tokens": 17, "output_tokens": 19}
                        stop_reason = "end_turn"

                    return VisionResult()

                calls.order.append("chat")
                calls.chat_calls.append(
                    {
                        "remote_model_id": remote_model_id,
                        "messages": messages,
                        "thinking_mode": thinking_mode,
                    }
                )

                class ChatResult:
                    content = "OpenRouter 直接视觉回答：已阅读图片。"
                    thinking_content = ""
                    usage = {"input_tokens": 11, "output_tokens": 13}
                    stop_reason = "end_turn"

                return ChatResult()

            def stream_chat(self, base_url, api_key, remote_model_id, messages, thinking_mode):
                result = self.complete_chat(base_url, api_key, remote_model_id, messages, thinking_mode)
                for delta in _test_chunks(result.content, 12):
                    yield ChatCompletionChunk(content_delta=delta)
                yield ChatCompletionChunk(stop_reason=result.stop_reason, usage=result.usage)

        registry = ProviderRegistry()
        registry.register(TestDeepSeekProvider())
        registry.register(TestOpenRouterProvider())
        original_api_registry_factory = model_providers.create_default_provider_registry
        original_service_registry_factory = getattr(
            model_provider_service,
            "create_default_provider_registry",
            None,
        )
        model_providers.create_default_provider_registry = lambda: registry
        model_provider_service.create_default_provider_registry = lambda: registry

        def restore():
            model_providers.create_default_provider_registry = original_api_registry_factory
            if original_service_registry_factory is None:
                delattr(model_provider_service, "create_default_provider_registry")
            else:
                model_provider_service.create_default_provider_registry = original_service_registry_factory

        return calls, restore

    def test_auth_is_durable_and_account_settings_update_current_session(self):
        invalid_response = self.client.post(
            "/api/auth/sign_up",
            json={
                "account": "../bad",
                "user_name": "Bad",
                "password": "x",
                "confirm_password": "x",
            },
        )
        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(invalid_response.json()["detail"]["code"], "INVALID_REQUEST")
        self.assertFalse((self.root / "../bad").exists())

        body, headers = self.sign_up(" Demo_Patient ", "陈女士")

        self.assertEqual(body["account"], "demo_patient")
        self.assertTrue((self.root / "all_users" / "auth" / "auth_info.db").exists())
        self.assertTrue((self.root / "all_users" / "auth" / "demo_patient" / "session.json").exists())
        self.assertFalse((self.root / "all_users" / "login" / "key_info.db").exists())
        self.assertTrue((self.root / "demo_patient" / "config").exists())
        self.assertTrue((self.root / "demo_patient" / "conversations" / "db_storage").exists())
        self.assertTrue((self.root / "demo_patient" / "favorites" / "db_storage").exists())

        session_response = self.client.get("/api/auth/session", headers=headers)
        self.assertEqual(session_response.json()["account"], "demo_patient")

        update_response = self.client.patch(
            "/api/auth/account",
            headers=headers,
            json={"user_name": "李女士"},
        )
        self.assertEqual(update_response.status_code, 200, update_response.text)
        self.assertEqual(update_response.json()["user_name"], "李女士")
        self.assertEqual(
            self.client.get("/api/auth/session", headers=headers).json()["user_name"],
            "李女士",
        )

        second_sign_in = self.client.post(
            "/api/auth/sign_in",
            json={"account": "DEMO_PATIENT", "password": "secret"},
        )
        self.assertEqual(second_sign_in.status_code, 200, second_sign_in.text)
        second_headers = {"Authorization": f"Bearer {second_sign_in.json()['session_token']}"}

        password_response = self.client.patch(
            "/api/auth/password",
            headers=headers,
            json={
                "current_password": "secret",
                "new_password": "new-secret",
                "confirm_password": "new-secret",
            },
        )
        self.assertEqual(password_response.status_code, 200, password_response.text)
        self.assertEqual(
            self.client.get("/api/auth/session", headers=headers).json()["authenticated"],
            True,
        )
        self.assertEqual(
            self.client.get("/api/auth/session", headers=second_headers).json()["authenticated"],
            False,
        )
        old_sign_in = self.client.post(
            "/api/auth/sign_in",
            json={"account": "demo_patient", "password": "secret"},
        )
        self.assertEqual(old_sign_in.status_code, 401)
        self.assertEqual(old_sign_in.json()["detail"]["code"], "SIGN_IN_FAILED")
        new_sign_in = self.client.post(
            "/api/auth/sign_in",
            json={"account": "demo_patient", "password": "new-secret"},
        )
        self.assertEqual(new_sign_in.status_code, 200, new_sign_in.text)

    def test_model_configuration_is_saved_per_account_with_editable_plain_api_key(self):
        from backend.app.api import model_providers
        from backend.app.providers.base import ModelProvider, ProviderModel
        from backend.app.providers.registry import ProviderRegistry

        original_registry_factory = model_providers.create_default_provider_registry

        class TestOpenRouterProvider(ModelProvider):
            provider_id = "openrouter"
            display_name = "OpenRouter"
            default_base_url = "https://openrouter.ai/api/v1"
            default_official_url = "https://openrouter.ai/settings/credits"

            def list_models(self, base_url, api_key):
                return [
                    ProviderModel(
                        remote_model_id="openai/gpt-4.1-mini",
                        model_name="GPT-4.1 Mini",
                        supports_text=True,
                        file_mime_types=["application/pdf"],
                        thinking_modes=["default", "fast"],
                    )
                ]

        registry = ProviderRegistry()
        registry.register(TestOpenRouterProvider())
        model_providers.create_default_provider_registry = lambda: registry

        unauth_response = self.client.get("/api/model-providers")
        try:
            self.assertEqual(unauth_response.status_code, 401)

            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            _, other_headers = self.sign_up("other_patient", "王先生")

            save_response = self.client.post(
                "/api/model-providers",
                headers=demo_headers,
                json={
                    "provider_id": "openrouter",
                    "base_url": "https://custom.example/v1",
                    "api_key": "sk-visible-only-in-request",
                    "default": True,
                },
            )
            self.assertEqual(save_response.status_code, 200, save_response.text)
            saved = save_response.json()
            self.assertEqual(saved["provider_id"], "openrouter")
            self.assertEqual(saved["base_url"], "https://custom.example/v1")
            self.assertTrue(saved["configured"])
            self.assertEqual(saved["api_key"], "sk-visible-only-in-request")

            demo_providers = self.client.get("/api/model-providers", headers=demo_headers).json()[
                "providers"
            ]
            other_providers = self.client.get("/api/model-providers", headers=other_headers).json()[
                "providers"
            ]
            self.assertTrue(next(item for item in demo_providers if item["provider_id"] == "openrouter")["configured"])
            self.assertEqual(
                next(item for item in demo_providers if item["provider_id"] == "openrouter")["api_key"],
                "sk-visible-only-in-request",
            )
            self.assertFalse(next(item for item in other_providers if item["provider_id"] == "openrouter")["configured"])
            self.assertEqual(next(item for item in other_providers if item["provider_id"] == "openrouter")["api_key"], "")

            models_response = self.client.get(
                "/api/model-providers/openrouter/models",
                headers=demo_headers,
            )
            self.assertEqual(models_response.status_code, 200, models_response.text)
            remote_model = models_response.json()["models"][0]
            self.assertIn("thinking_modes", remote_model)

            add_model_response = self.client.post(
                "/api/models",
                headers=demo_headers,
                json={
                    "provider_id": "openrouter",
                    "remote_model_id": remote_model["remote_model_id"],
                    "model_name": remote_model["model_name"],
                },
            )
            self.assertEqual(add_model_response.status_code, 200, add_model_response.text)
            defaults_response = self.client.get("/api/model-defaults", headers=demo_headers)
            self.assertEqual(defaults_response.status_code, 200, defaults_response.text)
            self.assertIsNone(defaults_response.json()["defaults"]["chat"])
            set_default_response = self.client.patch(
                "/api/model-defaults",
                headers=demo_headers,
                json={"chat": add_model_response.json()["model_id"]},
            )
            self.assertEqual(set_default_response.status_code, 200, set_default_response.text)

            self.assertEqual(
                len(self.client.get("/api/models", headers=demo_headers).json()["models"]),
                1,
            )
            self.assertEqual(
                self.client.get("/api/models", headers=other_headers).json(),
                {"models": []},
            )
        finally:
            model_providers.create_default_provider_registry = original_registry_factory

    def test_home_conversation_calls_configured_provider_with_saved_api_key(self):
        calls, restore_registry = self.install_fake_openrouter_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            provider_response = self.client.post(
                "/api/model-providers",
                headers=demo_headers,
                json={
                    "provider_id": "openrouter",
                    "base_url": "https://custom-openrouter.example/api/v1",
                    "api_key": "sk-real-call-test",
                    "default": True,
                },
            )
            self.assertEqual(provider_response.status_code, 200, provider_response.text)
            model_response = self.client.post(
                "/api/models",
                headers=demo_headers,
                json={
                    "provider_id": "openrouter",
                    "remote_model_id": "openai/gpt-4.1-mini",
                    "model_name": "GPT-4.1 Mini",
                },
            )
            self.assertEqual(model_response.status_code, 200, model_response.text)
            default_response = self.client.patch(
                "/api/model-defaults",
                headers=demo_headers,
                json={"chat": model_response.json()["model_id"]},
            )
            self.assertEqual(default_response.status_code, 200, default_response.text)

            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": None,
                    "parent_message_id": None,
                    "raw_text": "我最近头晕需要注意什么？",
                    "model_id": model_response.json()["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            message_body = message_response.json()

            self.assertEqual(message_body["message_status"], "streaming")
            self.assertEqual(message_body["content"], "")
            self.assertEqual(len(calls), 0)

            stream_response = self.client.get(
                f"/api/conversations/streams/{message_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(stream_response.status_code, 200, stream_response.text)
            self.assertIn("模型真实回复 1", stream_response.text)
            self.assertIn("核心结", stream_response.text)
            self.assertIn("论：我最近头晕需要注意什", stream_response.text)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["base_url"], "https://custom-openrouter.example/api/v1")
            self.assertEqual(calls[0]["api_key"], "sk-real-call-test")
            self.assertEqual(calls[0]["remote_model_id"], "openai/gpt-4.1-mini")
            self.assertEqual(calls[0]["thinking_mode"], "default")
            self.assertEqual(calls[0]["messages"][0]["role"], "system")
            self.assertIn("核心结论", calls[0]["messages"][0]["content"])
            self.assertIn("下一步建议", calls[0]["messages"][0]["content"])
            self.assertEqual(
                calls[0]["messages"][-1],
                {"role": "user", "content": "我最近头晕需要注意什么？"},
            )
            self.assertNotIn("下一步建议：记录症状开始时间", stream_response.text)

            detail_response = self.client.get(
                f"/api/conversations/{message_body['session_id']}",
                headers=demo_headers,
            )
            self.assertEqual(detail_response.status_code, 200, detail_response.text)
            self.assertEqual(detail_response.json()["title"], "头晕注意事项")
            session_list_response = self.client.get("/api/conversations", headers=demo_headers)
            self.assertEqual(session_list_response.status_code, 200, session_list_response.text)
            self.assertEqual(session_list_response.json()["sessions"][0]["title"], "头晕注意事项")
            self.assertNotEqual(
                session_list_response.json()["sessions"][0]["title"],
                "我最近头晕需要注意什么？"[:20],
            )
        finally:
            restore_registry()

    def test_draft_upload_sessions_are_hidden_from_conversation_history_until_sent(self):
        calls, restore_registry = self.install_fake_openrouter_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            model = self.add_default_model(demo_headers)

            upload_response = self.client.post(
                "/api/conversations/context-resources",
                headers=demo_headers,
                data={"session_id": "", "model_id": model["model_id"]},
                files={"file": ("report.pdf", b"%PDF-1.4 demo", "application/pdf")},
            )
            self.assertEqual(upload_response.status_code, 200, upload_response.text)
            upload_body = upload_response.json()
            session_id = upload_body["session_id"]
            resource_id = upload_body["resource"]["resource_id"]

            draft_detail = self.client.get(f"/api/conversations/{session_id}", headers=demo_headers)
            self.assertEqual(draft_detail.status_code, 200, draft_detail.text)
            self.assertEqual(draft_detail.json()["messages"], [])

            draft_list = self.client.get("/api/conversations", headers=demo_headers)
            self.assertEqual(draft_list.status_code, 200, draft_list.text)
            self.assertEqual(draft_list.json()["sessions"], [])

            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": session_id,
                    "parent_message_id": None,
                    "raw_text": "报告里的肌酐偏高严重吗？",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [{"resource_type": "file", "resource_id": resource_id}],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            self.assertEqual(len(calls), 0)

            pending_list = self.client.get("/api/conversations", headers=demo_headers)
            self.assertEqual(pending_list.status_code, 200, pending_list.text)
            self.assertEqual(
                [session["session_id"] for session in pending_list.json()["sessions"]],
                [session_id],
            )
        finally:
            restore_registry()

    def test_file_attachment_is_forwarded_as_typed_provider_content_not_metadata_only(self):
        calls, restore_registry = self.install_fake_openrouter_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            model = self.add_default_model(demo_headers)

            upload_response = self.client.post(
                "/api/conversations/context-resources",
                headers=demo_headers,
                data={"session_id": "", "model_id": model["model_id"]},
                files={"file": ("report.pdf", b"%PDF-1.4 demo", "application/pdf")},
            )
            self.assertEqual(upload_response.status_code, 200, upload_response.text)
            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": upload_response.json()["session_id"],
                    "parent_message_id": None,
                    "raw_text": "请总结附件",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [
                        {
                            "resource_type": "file",
                            "resource_id": upload_response.json()["resource"]["resource_id"],
                        }
                    ],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            stream_response = self.client.get(
                f"/api/conversations/streams/{message_response.json()['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(stream_response.status_code, 200, stream_response.text)

            user_message = calls[0]["messages"][-1]
            self.assertEqual(user_message["role"], "user")
            self.assertIsInstance(user_message["content"], list)
            self.assertEqual(user_message["content"][0], {"type": "text", "text": "请总结附件"})
            self.assertEqual(user_message["content"][1]["type"], "file")
            self.assertEqual(user_message["content"][1]["mime_type"], "application/pdf")
            self.assertEqual(user_message["content"][1]["name"], "report.pdf")
            self.assertEqual(user_message["content"][1]["data_base64"], "JVBERi0xLjQgZGVtbw==")
            self.assertNotIn("用户附加上下文：\n- 文件：", str(calls[0]["messages"]))
        finally:
            restore_registry()

    def test_file_attachment_can_be_sent_without_text(self):
        calls, restore_registry = self.install_fake_openrouter_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            model = self.add_default_model(demo_headers)

            upload_response = self.client.post(
                "/api/conversations/context-resources",
                headers=demo_headers,
                data={"session_id": "", "model_id": model["model_id"]},
                files={"file": ("report.pdf", b"%PDF-1.4 demo", "application/pdf")},
            )
            self.assertEqual(upload_response.status_code, 200, upload_response.text)
            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": upload_response.json()["session_id"],
                    "parent_message_id": None,
                    "raw_text": "   ",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [
                        {
                            "resource_type": "file",
                            "resource_id": upload_response.json()["resource"]["resource_id"],
                        }
                    ],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            stream_response = self.client.get(
                f"/api/conversations/streams/{message_response.json()['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(stream_response.status_code, 200, stream_response.text)

            user_message = calls[0]["messages"][-1]
            self.assertEqual(user_message["role"], "user")
            self.assertEqual(
                user_message["content"][0],
                {"type": "text", "text": "请阅读并总结附件内容。"},
            )
            self.assertEqual(user_message["content"][1]["type"], "file")
            self.assertEqual(user_message["content"][1]["name"], "report.pdf")
            self.assertFalse(
                any(part == {"type": "text", "text": ""} for part in user_message["content"])
            )
            detail = self.client.get(
                f"/api/conversations/{message_response.json()['session_id']}",
                headers=demo_headers,
            ).json()
            self.assertEqual(detail["messages"][0]["content"], "")
            self.assertEqual(detail["messages"][0]["context_resources"][0]["name"], "report.pdf")
        finally:
            restore_registry()

    def test_image_attachment_is_forwarded_as_typed_provider_content(self):
        calls, restore_registry = self.install_fake_openrouter_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            model = self.add_default_model(demo_headers)

            upload_response = self.client.post(
                "/api/conversations/context-resources",
                headers=demo_headers,
                data={"session_id": "", "model_id": model["model_id"]},
                files={"file": ("scan.png", b"\x89PNG\r\n", "image/png")},
            )
            self.assertEqual(upload_response.status_code, 200, upload_response.text)
            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": upload_response.json()["session_id"],
                    "parent_message_id": None,
                    "raw_text": "看图说明",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [
                        {
                            "resource_type": "file",
                            "resource_id": upload_response.json()["resource"]["resource_id"],
                        }
                    ],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            self.client.get(
                f"/api/conversations/streams/{message_response.json()['stream_id']}",
                headers=demo_headers,
            )

            image_part = calls[0]["messages"][-1]["content"][1]
            self.assertEqual(image_part["type"], "image")
            self.assertEqual(image_part["mime_type"], "image/png")
            self.assertEqual(image_part["name"], "scan.png")
            self.assertEqual(image_part["data_base64"], "iVBORw0K")
        finally:
            restore_registry()

    def test_audio_and_video_attachments_are_forwarded_as_typed_provider_content(self):
        calls, restore_registry = self.install_fake_openrouter_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            provider_response = self.client.post(
                "/api/model-providers",
                headers=demo_headers,
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
                headers=demo_headers,
                json={
                    "provider_id": "openrouter",
                    "remote_model_id": "google/gemini-3.5-flash",
                    "model_name": "Gemini 3.5 Flash",
                    "supports_text": True,
                    "file_mime_types": ["audio/mpeg", "video/mp4"],
                    "thinking_modes": ["default"],
                },
            )
            self.assertEqual(model_response.status_code, 200, model_response.text)
            model = model_response.json()
            default_response = self.client.patch(
                "/api/model-defaults",
                headers=demo_headers,
                json={"chat": model["model_id"]},
            )
            self.assertEqual(default_response.status_code, 200, default_response.text)

            upload_audio_response = self.client.post(
                "/api/conversations/context-resources",
                headers=demo_headers,
                data={"session_id": "", "model_id": model["model_id"]},
                files={"file": ("voice.mp3", b"ID3 demo", "audio/mpeg")},
            )
            self.assertEqual(upload_audio_response.status_code, 200, upload_audio_response.text)
            session_id = upload_audio_response.json()["session_id"]
            upload_video_response = self.client.post(
                "/api/conversations/context-resources",
                headers=demo_headers,
                data={"session_id": session_id, "model_id": model["model_id"]},
                files={"file": ("clip.mp4", b"\x00\x00\x00 ftypisom", "video/mp4")},
            )
            self.assertEqual(upload_video_response.status_code, 200, upload_video_response.text)
            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": session_id,
                    "parent_message_id": None,
                    "raw_text": "请分析音视频",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [
                        {
                            "resource_type": "file",
                            "resource_id": upload_audio_response.json()["resource"]["resource_id"],
                        },
                        {
                            "resource_type": "file",
                            "resource_id": upload_video_response.json()["resource"]["resource_id"],
                        },
                    ],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            stream_response = self.client.get(
                f"/api/conversations/streams/{message_response.json()['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(stream_response.status_code, 200, stream_response.text)

            content = calls[0]["messages"][-1]["content"]
            self.assertEqual(content[1]["type"], "audio")
            self.assertEqual(content[1]["mime_type"], "audio/mpeg")
            self.assertEqual(content[1]["name"], "voice.mp3")
            self.assertEqual(content[1]["data_base64"], "SUQzIGRlbW8=")
            self.assertEqual(content[2]["type"], "video")
            self.assertEqual(content[2]["mime_type"], "video/mp4")
            self.assertEqual(content[2]["name"], "clip.mp4")
            self.assertEqual(content[2]["data_base64"], "AAAAIGZ0eXBpc29t")
        finally:
            restore_registry()

    def test_completed_conversation_title_uses_question_and_answer(self):
        calls, restore_registry = self.install_fake_openrouter_registry(
            response_content=(
                "核心结论：根据你的描述，更像压力性头痛，需要结合诱因和持续时间观察。"
                "下一步建议：记录诱因并尽快复诊。"
            ),
            title_response_content="压力性头痛复诊建议",
        )
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            model = self.add_default_model(demo_headers)

            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": None,
                    "parent_message_id": None,
                    "raw_text": "可以帮我分析一下吗？",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            message_body = message_response.json()
            pending_detail = self.client.get(
                f"/api/conversations/{message_body['session_id']}",
                headers=demo_headers,
            )
            self.assertEqual(pending_detail.status_code, 200, pending_detail.text)
            self.assertEqual(pending_detail.json()["title"], "新对话")

            stream_response = self.client.get(
                f"/api/conversations/streams/{message_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(stream_response.status_code, 200, stream_response.text)
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(calls.title_calls), 1)
            self.assertIn("可以帮我分析一下吗？", calls.title_calls[0]["messages"][-1]["content"])
            self.assertIn("压力性头痛", calls.title_calls[0]["messages"][-1]["content"])

            detail_response = self.client.get(
                f"/api/conversations/{message_body['session_id']}",
                headers=demo_headers,
            )
            self.assertEqual(detail_response.status_code, 200, detail_response.text)
            self.assertEqual(detail_response.json()["title"], "压力性头痛复诊建议")
            session_list_response = self.client.get("/api/conversations", headers=demo_headers)
            self.assertEqual(session_list_response.status_code, 200, session_list_response.text)
            self.assertEqual(session_list_response.json()["sessions"][0]["title"], "压力性头痛复诊建议")
        finally:
            restore_registry()

    def test_completed_conversation_title_uses_title_default_model(self):
        calls, restore_registry = self.install_fake_openrouter_registry(
            response_content=(
                "核心结论：根据你的描述，更像压力性头痛，需要结合诱因和持续时间观察。"
                "下一步建议：记录诱因并尽快复诊。"
            ),
            title_response_content="压力性头痛复诊建议",
        )
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            chat_model = self.add_default_model(demo_headers)
            title_model_response = self.client.post(
                "/api/models",
                headers=demo_headers,
                json={
                    "provider_id": "openrouter",
                    "remote_model_id": "anthropic/claude-sonnet-4.5",
                    "model_name": "Claude Sonnet 4.5",
                },
            )
            self.assertEqual(title_model_response.status_code, 200, title_model_response.text)
            defaults_response = self.client.patch(
                "/api/model-defaults",
                headers=demo_headers,
                json={
                    "chat": chat_model["model_id"],
                    "title": title_model_response.json()["model_id"],
                },
            )
            self.assertEqual(defaults_response.status_code, 200, defaults_response.text)

            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": None,
                    "parent_message_id": None,
                    "raw_text": "可以帮我分析一下吗？",
                    "model_id": None,
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            self.assertEqual(message_response.json()["model_id"], chat_model["model_id"])
            stream_response = self.client.get(
                f"/api/conversations/streams/{message_response.json()['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(stream_response.status_code, 200, stream_response.text)
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(calls.title_calls), 1)
            self.assertEqual(calls[0]["remote_model_id"], "openai/gpt-4.1-mini")
            self.assertEqual(calls.title_calls[0]["remote_model_id"], "anthropic/claude-sonnet-4.5")
        finally:
            restore_registry()

    def test_home_conversation_rejects_non_chat_default_model(self):
        calls, restore_registry = self.install_fake_openrouter_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            chat_model = self.add_default_model(demo_headers)
            title_model_response = self.client.post(
                "/api/models",
                headers=demo_headers,
                json={
                    "provider_id": "openrouter",
                    "remote_model_id": "anthropic/claude-sonnet-4.5",
                    "model_name": "Claude Sonnet 4.5",
                },
            )
            self.assertEqual(title_model_response.status_code, 200, title_model_response.text)
            defaults_response = self.client.patch(
                "/api/model-defaults",
                headers=demo_headers,
                json={
                    "chat": chat_model["model_id"],
                    "title": title_model_response.json()["model_id"],
                },
            )
            self.assertEqual(defaults_response.status_code, 200, defaults_response.text)

            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": None,
                    "parent_message_id": None,
                    "raw_text": "可以帮我分析一下吗？",
                    "model_id": title_model_response.json()["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(message_response.status_code, 400)
            self.assertEqual(message_response.json()["detail"]["code"], "INVALID_REQUEST")
            self.assertEqual(len(calls), 0)
        finally:
            restore_registry()

    def test_legacy_first_message_titles_are_backfilled_to_compact_titles(self):
        calls, restore_registry = self.install_fake_openrouter_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            model = self.add_default_model(demo_headers)

            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": None,
                    "parent_message_id": None,
                    "raw_text": "请问我最近头晕需要注意什么？",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            message_body = message_response.json()
            stream_response = self.client.get(
                f"/api/conversations/streams/{message_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(stream_response.status_code, 200, stream_response.text)
            self.assertEqual(len(calls), 1)

            from backend.app.storage.paths import app_paths
            from backend.app.storage.sqlite import connect

            legacy_title = "请问我最近头晕需要注意什么？"[:20]
            with connect(app_paths().conversations_db("demo_patient")) as connection:
                connection.execute(
                    """
                    UPDATE conversation_sessions
                    SET title = ?
                    WHERE session_id = ?
                    """,
                    (legacy_title, message_body["session_id"]),
                )

            session_list_response = self.client.get("/api/conversations", headers=demo_headers)
            self.assertEqual(session_list_response.status_code, 200, session_list_response.text)
            self.assertEqual(session_list_response.json()["sessions"][0]["title"], "头晕注意事项")
            detail_response = self.client.get(
                f"/api/conversations/{message_body['session_id']}",
                headers=demo_headers,
            )
            self.assertEqual(detail_response.status_code, 200, detail_response.text)
            self.assertEqual(detail_response.json()["title"], "头晕注意事项")
        finally:
            restore_registry()

    def test_provider_thinking_process_is_saved_and_streamed(self):
        thinking_content = "先核对用户问题和上下文。再确认风险信号。最后组织下一步建议。"
        calls, restore_registry = self.install_fake_openrouter_registry(
            thinking_content=thinking_content,
            thinking_chunk_delay_seconds=0.02,
        )
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            model = self.add_default_model(demo_headers)

            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": None,
                    "parent_message_id": None,
                    "raw_text": "我最近头晕需要注意什么？",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            message_body = message_response.json()
            self.assertIsNotNone(message_body["thinking_message_id"])

            detail = self.client.get(
                f"/api/conversations/{message_body['session_id']}",
                headers=demo_headers,
            ).json()
            self.assertEqual([message["role"] for message in detail["messages"]], ["user"])
            self.assertEqual(detail["pending_turns"][0]["stream_id"], message_body["stream_id"])

            stream_response = self.client.get(
                f"/api/conversations/streams/{message_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(stream_response.status_code, 200, stream_response.text)
            self.assertIn("event: thinking_delta", stream_response.text)
            self.assertIn("先核对用户问题和上下文。", stream_response.text)
            self.assertGreaterEqual(stream_response.text.count("event: thinking_delta"), 2)
            self.assertGreaterEqual(stream_response.text.count("event: content_delta"), 2)
            self.assertIn(message_body["thinking_message_id"], stream_response.text)
            self.assertIn(message_body["assistant_message_id"], stream_response.text)

            completed_detail = self.client.get(
                f"/api/conversations/{message_body['session_id']}",
                headers=demo_headers,
            ).json()
            self.assertEqual(
                [message["role"] for message in completed_detail["messages"]],
                ["user", "thinking", "assistant"],
            )
            self.assertEqual(completed_detail["messages"][1]["content"], thinking_content)
            self.assertGreaterEqual(completed_detail["messages"][1]["duration_ms"], 20)
            self.assertNotEqual(completed_detail["messages"][1]["duration_ms"], 1)
            turn = self.client.get(
                f"/api/conversations/{message_body['session_id']}/turns/{message_body['turn_id']}",
                headers=demo_headers,
            ).json()
            self.assertEqual(turn["status"], "completed")
        finally:
            restore_registry()

    def test_stream_completion_event_is_not_blocked_by_title_generation(self):
        source = (Path(__file__).resolve().parents[1] / "backend" / "app" / "application" / "conversation_service.py").read_text(
            encoding="utf-8"
        )
        live_stream_source = source.split("def _stream_live_turn", 1)[1].split(
            "def _append_completed_turn_messages",
            1,
        )[0]
        append_source = source.split("def _append_completed_turn_messages", 1)[1].split(
            "def _finish_completed_turn_session_index",
            1,
        )[0]

        self.assertIn("completed_turn = self._append_completed_turn_messages(", live_stream_source)
        self.assertIn("yield self._completed_stream_event(", live_stream_source)
        self.assertIn("self._finish_completed_turn_session_index(", live_stream_source)
        self.assertLess(
            live_stream_source.index("yield self._completed_stream_event("),
            live_stream_source.index("self._finish_completed_turn_session_index("),
        )
        self.assertNotIn("_generate_completed_turn_title", append_source)

    def test_regenerate_resumes_existing_pending_turn_for_same_user_message(self):
        calls, restore_registry = self.install_fake_openrouter_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            model = self.add_default_model(demo_headers)

            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": None,
                    "parent_message_id": None,
                    "raw_text": "我最近头晕需要注意什么？",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            message_body = message_response.json()
            stream_response = self.client.get(
                f"/api/conversations/streams/{message_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(stream_response.status_code, 200, stream_response.text)

            first_regenerate_response = self.client.post(
                f"/api/conversations/{message_body['session_id']}/messages/{message_body['assistant_message_id']}/regenerate",
                headers=demo_headers,
                json={"thinking_mode": "default"},
            )
            self.assertEqual(first_regenerate_response.status_code, 200, first_regenerate_response.text)
            first_regenerate_body = first_regenerate_response.json()

            resumed_regenerate_response = self.client.post(
                f"/api/conversations/{message_body['session_id']}/messages/{message_body['assistant_message_id']}/regenerate",
                headers=demo_headers,
                json={"thinking_mode": "default"},
            )
            self.assertEqual(resumed_regenerate_response.status_code, 200, resumed_regenerate_response.text)
            resumed_regenerate_body = resumed_regenerate_response.json()
            self.assertEqual(resumed_regenerate_body["turn_id"], first_regenerate_body["turn_id"])
            self.assertEqual(resumed_regenerate_body["stream_id"], first_regenerate_body["stream_id"])

            regenerate_stream_response = self.client.get(
                f"/api/conversations/streams/{resumed_regenerate_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(regenerate_stream_response.status_code, 200, regenerate_stream_response.text)
            turn = self.client.get(
                f"/api/conversations/{message_body['session_id']}/turns/{resumed_regenerate_body['turn_id']}",
                headers=demo_headers,
            ).json()
            self.assertEqual(turn["status"], "completed")
            self.assertEqual(len(calls), 2)
        finally:
            restore_registry()

    def test_cancel_generation_preserves_partial_assistant_message(self):
        calls, restore_registry = self.install_fake_openrouter_registry(
            thinking_content="先确认症状持续时间，再判断风险信号。"
        )
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            model = self.add_default_model(demo_headers)

            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": None,
                    "parent_message_id": None,
                    "raw_text": "我最近头晕需要注意什么？",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            message_body = message_response.json()

            cancel_response = self.client.post(
                f"/api/conversations/{message_body['session_id']}/turns/{message_body['turn_id']}/cancel",
                headers=demo_headers,
                json={
                    "preserve_partial": True,
                    "partial_content": "核心结论：先坐下休息，观察是否伴随胸痛。",
                    "partial_thinking": "先确认风险信号。",
                },
            )
            self.assertEqual(cancel_response.status_code, 200, cancel_response.text)
            self.assertEqual(cancel_response.json()["status"], "cancelled")
            self.assertTrue(cancel_response.json()["preserve_partial"])

            detail = self.client.get(
                f"/api/conversations/{message_body['session_id']}",
                headers=demo_headers,
            ).json()
            self.assertEqual(detail["pending_turns"], [])
            self.assertEqual([message["role"] for message in detail["messages"]], ["user", "thinking", "assistant"])
            self.assertEqual(detail["messages"][1]["content"], "先确认风险信号。")
            self.assertEqual(detail["messages"][2]["status"], "cancelled")
            self.assertEqual(detail["messages"][2]["stop_reason"], "cancelled")
            self.assertEqual(detail["messages"][2]["content"], "核心结论：先坐下休息，观察是否伴随胸痛。")

            cancelled_stream_response = self.client.get(
                f"/api/conversations/streams/{message_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(cancelled_stream_response.status_code, 200, cancelled_stream_response.text)
            self.assertIn("event: cancelled", cancelled_stream_response.text)
            self.assertNotIn("event: completed", cancelled_stream_response.text)

            follow_up_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": message_body["session_id"],
                    "parent_message_id": detail["messages"][-1]["message_id"],
                    "raw_text": "那我应该记录哪些症状？",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(follow_up_response.status_code, 200, follow_up_response.text)
            self.assertEqual(len(calls), 0)
        finally:
            restore_registry()

    def test_cancel_for_regenerate_discards_partial_and_can_regenerate_from_user_message(self):
        calls, restore_registry = self.install_fake_openrouter_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            model = self.add_default_model(demo_headers)

            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": None,
                    "parent_message_id": None,
                    "raw_text": "我最近头晕需要注意什么？",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            message_body = message_response.json()

            cancel_response = self.client.post(
                f"/api/conversations/{message_body['session_id']}/turns/{message_body['turn_id']}/cancel",
                headers=demo_headers,
                json={
                    "preserve_partial": False,
                    "partial_content": "这段半截回答不应该入库",
                },
            )
            self.assertEqual(cancel_response.status_code, 200, cancel_response.text)
            self.assertEqual(cancel_response.json()["status"], "cancelled")
            self.assertFalse(cancel_response.json()["preserve_partial"])

            detail = self.client.get(
                f"/api/conversations/{message_body['session_id']}",
                headers=demo_headers,
            ).json()
            self.assertEqual(detail["pending_turns"], [])
            self.assertEqual([message["role"] for message in detail["messages"]], ["user"])
            self.assertNotIn("这段半截回答不应该入库", str(detail))

            regenerate_response = self.client.post(
                f"/api/conversations/{message_body['session_id']}/messages/{message_body['user_message_id']}/regenerate",
                headers=demo_headers,
                json={"thinking_mode": "default"},
            )
            self.assertEqual(regenerate_response.status_code, 200, regenerate_response.text)
            regenerate_body = regenerate_response.json()
            self.assertNotEqual(regenerate_body["turn_id"], message_body["turn_id"])

            regenerate_stream_response = self.client.get(
                f"/api/conversations/streams/{regenerate_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(regenerate_stream_response.status_code, 200, regenerate_stream_response.text)
            self.assertIn("event: completed", regenerate_stream_response.text)
            self.assertEqual(len(calls), 1)
        finally:
            restore_registry()

    def test_branch_switch_extends_selected_branch_to_its_saved_answer(self):
        calls, restore_registry = self.install_fake_openrouter_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            model = self.add_default_model(demo_headers)

            first_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": None,
                    "parent_message_id": None,
                    "raw_text": "我最近头晕需要注意什么？",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(first_response.status_code, 200, first_response.text)
            first_body = first_response.json()
            first_stream = self.client.get(
                f"/api/conversations/streams/{first_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(first_stream.status_code, 200, first_stream.text)

            existing_branch_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": first_body["session_id"],
                    "parent_message_id": first_body["assistant_message_id"],
                    "raw_text": "那我今晚应该怎么观察？",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(existing_branch_response.status_code, 200, existing_branch_response.text)
            existing_branch_body = existing_branch_response.json()
            existing_branch_stream = self.client.get(
                f"/api/conversations/streams/{existing_branch_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(existing_branch_stream.status_code, 200, existing_branch_stream.text)

            new_branch_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": first_body["session_id"],
                    "parent_message_id": first_body["assistant_message_id"],
                    "raw_text": "我明天复查前要准备什么？",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(new_branch_response.status_code, 200, new_branch_response.text)
            new_branch_body = new_branch_response.json()
            new_branch_stream = self.client.get(
                f"/api/conversations/streams/{new_branch_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(new_branch_stream.status_code, 200, new_branch_stream.text)

            switch_to_existing = self.client.patch(
                f"/api/conversations/{first_body['session_id']}/active-path",
                headers=demo_headers,
                json={
                    "active_path_message_ids": [
                        first_body["user_message_id"],
                        first_body["assistant_message_id"],
                        existing_branch_body["user_message_id"],
                    ]
                },
            )
            self.assertEqual(switch_to_existing.status_code, 200, switch_to_existing.text)
            existing_detail = self.client.get(
                f"/api/conversations/{first_body['session_id']}",
                headers=demo_headers,
            ).json()
            self.assertEqual(existing_detail["messages"][-1]["message_id"], existing_branch_body["assistant_message_id"])
            self.assertIn(existing_branch_body["assistant_message_id"], existing_detail["active_path_message_ids"])

            switch_to_new = self.client.patch(
                f"/api/conversations/{first_body['session_id']}/active-path",
                headers=demo_headers,
                json={
                    "active_path_message_ids": [
                        first_body["user_message_id"],
                        first_body["assistant_message_id"],
                        new_branch_body["user_message_id"],
                    ]
                },
            )
            self.assertEqual(switch_to_new.status_code, 200, switch_to_new.text)
            new_detail = self.client.get(
                f"/api/conversations/{first_body['session_id']}",
                headers=demo_headers,
            ).json()
            self.assertEqual(new_detail["messages"][-1]["message_id"], new_branch_body["assistant_message_id"])
            self.assertIn(new_branch_body["assistant_message_id"], new_detail["active_path_message_ids"])
            self.assertEqual(len(calls), 3)
        finally:
            restore_registry()

    def test_upload_rejects_attachments_for_selected_model_without_native_support(self):
        _, demo_headers = self.sign_up("demo_patient", "陈女士")
        deepseek_model = self.add_deepseek_model(demo_headers)

        upload_response = self.client.post(
            "/api/conversations/context-resources",
            headers=demo_headers,
            data={"session_id": "", "model_id": deepseek_model["model_id"]},
            files={"file": ("report.pdf", b"%PDF-1.4 demo", "application/pdf")},
        )

        self.assertEqual(upload_response.status_code, 422)
        self.assertEqual(upload_response.json()["detail"]["code"], "MODEL_FILE_UNSUPPORTED")

    def test_chat_model_without_vision_uses_vision_parse_model_directly_for_image_attachment(self):
        calls, restore_registry = self.install_fake_chat_and_vision_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            deepseek_model = self.add_deepseek_model(demo_headers)
            provider_response = self.client.post(
                "/api/model-providers",
                headers=demo_headers,
                json={
                    "provider_id": "openrouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key": "sk-openrouter-test",
                    "default": False,
                },
            )
            self.assertEqual(provider_response.status_code, 200, provider_response.text)
            vision_model_response = self.client.post(
                "/api/models",
                headers=demo_headers,
                json={
                    "provider_id": "openrouter",
                    "remote_model_id": "anthropic/claude-sonnet-4.5",
                    "model_name": "Claude Sonnet 4.5",
                },
            )
            self.assertEqual(vision_model_response.status_code, 200, vision_model_response.text)
            defaults_response = self.client.patch(
                "/api/model-defaults",
                headers=demo_headers,
                json={
                    "chat": deepseek_model["model_id"],
                    "vision_parse": vision_model_response.json()["model_id"],
                },
            )
            self.assertEqual(defaults_response.status_code, 200, defaults_response.text)

            upload_response = self.client.post(
                "/api/conversations/context-resources",
                headers=demo_headers,
                data={"session_id": "", "model_id": deepseek_model["model_id"]},
                files={"file": ("scan.png", b"\x89PNG\r\n", "image/png")},
            )
            self.assertEqual(upload_response.status_code, 200, upload_response.text)

            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": upload_response.json()["session_id"],
                    "parent_message_id": None,
                    "raw_text": "请结合附件解释",
                    "model_id": deepseek_model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [
                        {
                            "resource_type": "file",
                            "resource_id": upload_response.json()["resource"]["resource_id"],
                        }
                    ],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            stream_response = self.client.get(
                f"/api/conversations/streams/{message_response.json()['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(stream_response.status_code, 200, stream_response.text)

            self.assertEqual(calls.order, ["vision_parse"])
            self.assertEqual(calls.chat_calls, [])
            vision_user_content = calls.vision_calls[0]["messages"][-1]["content"]
            self.assertIsInstance(vision_user_content, list)
            self.assertEqual(vision_user_content[1]["type"], "image")
            self.assertEqual(vision_user_content[1]["mime_type"], "image/png")
            vision_messages = json.dumps(calls.vision_calls[0]["messages"], ensure_ascii=False)
            self.assertIn("请结合附件解释", vision_messages)
            self.assertNotIn("视觉解析模型提取的附件内容", vision_messages)
            self.assertIn("视觉解析结果", stream_response.text)
            self.assertNotIn("DeepSeek", stream_response.text)
        finally:
            restore_registry()

    def test_vision_parse_model_is_not_called_when_chat_model_supports_image_attachment(self):
        calls, restore_registry = self.install_fake_chat_and_vision_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            provider_response = self.client.post(
                "/api/model-providers",
                headers=demo_headers,
                json={
                    "provider_id": "openrouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key": "sk-openrouter-test",
                    "default": True,
                },
            )
            self.assertEqual(provider_response.status_code, 200, provider_response.text)
            chat_model_response = self.client.post(
                "/api/models",
                headers=demo_headers,
                json={
                    "provider_id": "openrouter",
                    "remote_model_id": "openai/gpt-4.1-mini",
                    "model_name": "GPT-4.1 Mini",
                },
            )
            self.assertEqual(chat_model_response.status_code, 200, chat_model_response.text)
            vision_model_response = self.client.post(
                "/api/models",
                headers=demo_headers,
                json={
                    "provider_id": "openrouter",
                    "remote_model_id": "anthropic/claude-sonnet-4.5",
                    "model_name": "Claude Sonnet 4.5",
                },
            )
            self.assertEqual(vision_model_response.status_code, 200, vision_model_response.text)
            defaults_response = self.client.patch(
                "/api/model-defaults",
                headers=demo_headers,
                json={
                    "chat": chat_model_response.json()["model_id"],
                    "vision_parse": vision_model_response.json()["model_id"],
                },
            )
            self.assertEqual(defaults_response.status_code, 200, defaults_response.text)

            upload_response = self.client.post(
                "/api/conversations/context-resources",
                headers=demo_headers,
                data={"session_id": "", "model_id": chat_model_response.json()["model_id"]},
                files={"file": ("scan.png", b"\x89PNG\r\n", "image/png")},
            )
            self.assertEqual(upload_response.status_code, 200, upload_response.text)
            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": upload_response.json()["session_id"],
                    "parent_message_id": None,
                    "raw_text": "请看图",
                    "model_id": chat_model_response.json()["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [
                        {
                            "resource_type": "file",
                            "resource_id": upload_response.json()["resource"]["resource_id"],
                        }
                    ],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            stream_response = self.client.get(
                f"/api/conversations/streams/{message_response.json()['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(stream_response.status_code, 200, stream_response.text)

            self.assertEqual(calls.order, ["chat"])
            self.assertEqual(calls.vision_calls, [])
            direct_user_content = calls.chat_calls[0]["messages"][-1]["content"]
            self.assertIsInstance(direct_user_content, list)
            self.assertEqual(direct_user_content[1]["type"], "image")
            self.assertEqual(direct_user_content[1]["data_base64"], "iVBORw0K")
        finally:
            restore_registry()

    def test_send_rejects_attachment_after_switching_to_unsupported_model(self):
        _, demo_headers = self.sign_up("demo_patient", "陈女士")
        model = self.add_default_model(demo_headers)
        deepseek_model = self.add_deepseek_model(demo_headers)
        default_response = self.client.patch(
            "/api/model-defaults",
            headers=demo_headers,
            json={"chat": model["model_id"]},
        )
        self.assertEqual(default_response.status_code, 200, default_response.text)

        upload_response = self.client.post(
            "/api/conversations/context-resources",
            headers=demo_headers,
            data={"session_id": "", "model_id": model["model_id"]},
            files={"file": ("report.pdf", b"%PDF-1.4 demo", "application/pdf")},
        )
        self.assertEqual(upload_response.status_code, 200, upload_response.text)

        message_response = self.client.post(
            "/api/conversations/messages",
            headers=demo_headers,
            json={
                "session_id": upload_response.json()["session_id"],
                "parent_message_id": None,
                "raw_text": "请看这个文件",
                "model_id": deepseek_model["model_id"],
                "thinking_mode": "default",
                "context_resources": [
                    {
                        "resource_type": "file",
                        "resource_id": upload_response.json()["resource"]["resource_id"],
                    }
                ],
            },
        )

        self.assertEqual(message_response.status_code, 400)
        self.assertEqual(message_response.json()["detail"]["code"], "INVALID_REQUEST")

    def test_upload_rejects_stale_model_metadata_when_provider_cannot_forward_attachment(self):
        _, demo_headers = self.sign_up("demo_patient", "陈女士")
        provider_response = self.client.post(
            "/api/model-providers",
            headers=demo_headers,
            json={
                "provider_id": "deepseek",
                "base_url": "https://api.deepseek.com",
                "api_key": "sk-deepseek-test",
                "default": True,
            },
        )
        self.assertEqual(provider_response.status_code, 200, provider_response.text)
        stale_model = self.client.post(
            "/api/models",
            headers=demo_headers,
            json={
                "provider_id": "deepseek",
                "remote_model_id": "deepseek-chat",
                "model_name": "DeepSeek Chat",
                "file_mime_types": ["application/pdf"],
            },
        ).json()
        default_response = self.client.patch(
            "/api/model-defaults",
            headers=demo_headers,
            json={"chat": stale_model["model_id"]},
        )
        self.assertEqual(default_response.status_code, 200, default_response.text)

        upload_response = self.client.post(
            "/api/conversations/context-resources",
            headers=demo_headers,
            data={"session_id": "", "model_id": stale_model["model_id"]},
            files={"file": ("report.pdf", b"%PDF-1.4 demo", "application/pdf")},
        )

        self.assertEqual(upload_response.status_code, 422)
        self.assertEqual(upload_response.json()["detail"]["code"], "MODEL_ATTACHMENT_UNSUPPORTED")

    def test_conversation_context_branching_favorites_and_isolation(self):
        calls, restore_registry = self.install_fake_openrouter_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            _, other_headers = self.sign_up("other_patient", "王先生")

            no_model_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": None,
                    "parent_message_id": None,
                    "raw_text": "我最近头晕需要注意什么？",
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(no_model_response.status_code, 422)
            self.assertEqual(no_model_response.json()["detail"]["code"], "MODEL_NOT_CONFIGURED")

            model = self.add_default_model(demo_headers)

            unsupported_file = self.client.post(
                "/api/conversations/context-resources",
                headers=demo_headers,
                data={"session_id": ""},
                files={"file": ("note.txt", b"plain text", "text/plain")},
            )
            self.assertEqual(unsupported_file.status_code, 415)
            self.assertEqual(unsupported_file.json()["detail"]["code"], "UNSUPPORTED_FILE_TYPE")

            upload_response = self.client.post(
                "/api/conversations/context-resources",
                headers=demo_headers,
                data={"session_id": "", "model_id": model["model_id"]},
                files={"file": ("report.pdf", b"%PDF-1.4 demo", "application/pdf")},
            )
            self.assertEqual(upload_response.status_code, 200, upload_response.text)
            upload_body = upload_response.json()
            session_id = upload_body["session_id"]
            resource_id = upload_body["resource"]["resource_id"]
            self.assertEqual(upload_body["resource"]["usage_status"], "pending")

            draft_detail = self.client.get(f"/api/conversations/{session_id}", headers=demo_headers)
            self.assertEqual(draft_detail.status_code, 200, draft_detail.text)
            self.assertEqual(draft_detail.json()["messages"], [])

            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": session_id,
                    "parent_message_id": None,
                    "raw_text": "报告里的肌酐偏高严重吗？",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [{"resource_type": "file", "resource_id": resource_id}],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            message_body = message_response.json()
            self.assertEqual(message_body["message_status"], "streaming")
            self.assertEqual(message_body["content"], "")

            turn_response = self.client.get(
                f"/api/conversations/{session_id}/turns/{message_body['turn_id']}",
                headers=demo_headers,
            )
            self.assertEqual(turn_response.status_code, 200, turn_response.text)
            self.assertEqual(turn_response.json()["status"], "streaming")

            stream_response = self.client.get(
                f"/api/conversations/streams/{message_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(stream_response.status_code, 200, stream_response.text)
            self.assertIn("模型真实回复", stream_response.text)
            self.assertIn("核心结", stream_response.text)
            self.assertIn("论：报告里的肌酐偏高严重", stream_response.text)

            detail = self.client.get(f"/api/conversations/{session_id}", headers=demo_headers).json()
            self.assertEqual(len(detail["messages"]), 2)
            first_assistant_id = message_body["assistant_message_id"]
            first_active_path = detail["active_path_message_ids"]
            self.assertEqual(detail["messages"][0]["context_resources"][0]["resource_id"], resource_id)

            favorite_response = self.client.post(
                "/api/favorites",
                headers=demo_headers,
                json={
                    "source_type": "message",
                    "source_session_id": session_id,
                    "source_id": first_assistant_id,
                    "tags": ["肾功能"],
                },
            )
            self.assertEqual(favorite_response.status_code, 200, favorite_response.text)
            favorite_id = favorite_response.json()["favorite_id"]
            self.assertIn("核心结论", favorite_response.json()["content_snapshot"])

            regenerate_response = self.client.post(
                f"/api/conversations/{session_id}/messages/{first_assistant_id}/regenerate",
                headers=demo_headers,
                json={"thinking_mode": "default"},
            )
            self.assertEqual(regenerate_response.status_code, 200, regenerate_response.text)
            regenerate_body = regenerate_response.json()
            second_assistant_id = regenerate_body["assistant_message_id"]
            self.assertNotEqual(first_assistant_id, second_assistant_id)
            regenerate_stream_response = self.client.get(
                f"/api/conversations/streams/{regenerate_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(regenerate_stream_response.status_code, 200, regenerate_stream_response.text)

            switch_response = self.client.patch(
                f"/api/conversations/{session_id}/active-path",
                headers=demo_headers,
                json={"active_path_message_ids": first_active_path},
            )
            self.assertEqual(switch_response.status_code, 200, switch_response.text)
            switched_detail = self.client.get(f"/api/conversations/{session_id}", headers=demo_headers).json()
            self.assertEqual(switched_detail["active_path_message_ids"], first_active_path)
            self.assertEqual(switched_detail["messages"][-1]["message_id"], first_assistant_id)

            branch_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": session_id,
                    "parent_message_id": first_assistant_id,
                    "raw_text": "那我复查前应该准备什么？",
                    "thinking_mode": "default",
                    "context_resources": [
                        {
                            "resource_type": "message_quote",
                            "resource_id": first_assistant_id,
                            "quote_text": "核心结论",
                        }
                    ],
                },
            )
            self.assertEqual(branch_response.status_code, 200, branch_response.text)
            branch_body = branch_response.json()
            branch_stream_response = self.client.get(
                f"/api/conversations/streams/{branch_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(branch_stream_response.status_code, 200, branch_stream_response.text)

            favorites_list = self.client.get("/api/favorites", headers=demo_headers).json()
            self.assertEqual(len(favorites_list["favorites"]), 1)
            self.assertEqual(
                self.client.get("/api/favorites", headers=other_headers).json()["favorites"],
                [],
            )

            favorite_detail = self.client.get(
                f"/api/favorites/{favorite_id}",
                headers=demo_headers,
            ).json()
            self.assertTrue(favorite_detail["source_available"])

            tag_response = self.client.patch(
                f"/api/favorites/{favorite_id}",
                headers=demo_headers,
                json={"tags": ["复查建议"]},
            )
            self.assertEqual(tag_response.status_code, 200, tag_response.text)
            self.assertEqual(tag_response.json()["tags"], ["复查建议"])

            other_session_response = self.client.get(
                f"/api/conversations/{session_id}",
                headers=other_headers,
            )
            self.assertEqual(other_session_response.status_code, 404)
            other_favorite_response = self.client.get(
                f"/api/favorites/{favorite_id}",
                headers=other_headers,
            )
            self.assertEqual(other_favorite_response.status_code, 404)

            delete_session_response = self.client.delete(
                f"/api/conversations/{session_id}",
                headers=demo_headers,
            )
            self.assertEqual(delete_session_response.status_code, 200, delete_session_response.text)
            deleted_source_detail = self.client.get(
                f"/api/favorites/{favorite_id}",
                headers=demo_headers,
            ).json()
            self.assertFalse(deleted_source_detail["source_available"])
            self.assertIn("核心结论", deleted_source_detail["content_snapshot"])

            batch_delete = self.client.post(
                "/api/favorites/batch-delete",
                headers=demo_headers,
                json={"favorite_ids": [favorite_id]},
            )
            self.assertEqual(batch_delete.status_code, 200, batch_delete.text)
            self.assertEqual(batch_delete.json()["deleted_ids"], [favorite_id])
            self.assertEqual(
                self.client.get("/api/favorites", headers=demo_headers).json()["favorites"],
                [],
            )
            self.assertGreaterEqual(len(calls), 3)
        finally:
            restore_registry()

    def test_stream_replay_and_context_rejections_are_account_scoped(self):
        calls, restore_registry = self.install_fake_openrouter_registry()
        try:
            _, demo_headers = self.sign_up("demo_patient", "陈女士")
            _, other_headers = self.sign_up("other_patient", "王先生")
            model = self.add_default_model(demo_headers)

            message_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": None,
                    "parent_message_id": None,
                    "raw_text": "我最近头晕需要注意什么？",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [],
                },
            )
            self.assertEqual(message_response.status_code, 200, message_response.text)
            message_body = message_response.json()

            stream_response = self.client.get(
                f"/api/conversations/streams/{message_body['stream_id']}",
                headers=demo_headers,
            )
            self.assertEqual(stream_response.status_code, 200, stream_response.text)
            self.assertEqual(stream_response.headers["cache-control"], "no-cache")
            self.assertEqual(stream_response.headers["x-accel-buffering"], "no")
            stream_text = stream_response.text
            self.assertIn("event: content_delta", stream_text)
            self.assertIn("核心结", stream_text)
            self.assertIn("论：我最近头晕需要注意什", stream_text)
            self.assertIn("event: completed", stream_text)
            self.assertIn(message_body["assistant_message_id"], stream_text)

            other_stream_response = self.client.get(
                f"/api/conversations/streams/{message_body['stream_id']}",
                headers=other_headers,
            )
            self.assertEqual(other_stream_response.status_code, 404)
            self.assertEqual(other_stream_response.json()["detail"]["code"], "NOT_FOUND")

            bad_quote_response = self.client.post(
                "/api/conversations/messages",
                headers=demo_headers,
                json={
                    "session_id": message_body["session_id"],
                    "parent_message_id": message_body["assistant_message_id"],
                    "raw_text": "引用这句继续分析",
                    "model_id": model["model_id"],
                    "thinking_mode": "default",
                    "context_resources": [
                        {
                            "resource_type": "message_quote",
                            "resource_id": message_body["assistant_message_id"],
                            "quote_text": "这段文本不在回答里",
                        }
                    ],
                },
            )
            self.assertEqual(bad_quote_response.status_code, 400)
            self.assertEqual(bad_quote_response.json()["detail"]["code"], "INVALID_REQUEST")
            self.assertEqual(len(calls), 1)
        finally:
            restore_registry()

    def test_file_context_rejects_expired_resources_and_model_file_mismatch(self):
        _, demo_headers = self.sign_up("demo_patient", "陈女士")
        model = self.add_default_model(demo_headers)
        deepseek_model = self.add_deepseek_model(demo_headers)
        default_response = self.client.patch(
            "/api/model-defaults",
            headers=demo_headers,
            json={"chat": model["model_id"]},
        )
        self.assertEqual(default_response.status_code, 200, default_response.text)

        upload_response = self.client.post(
            "/api/conversations/context-resources",
            headers=demo_headers,
            data={"session_id": "", "model_id": model["model_id"]},
            files={"file": ("report.pdf", b"%PDF-1.4 demo", "application/pdf")},
        )
        self.assertEqual(upload_response.status_code, 200, upload_response.text)
        upload_body = upload_response.json()

        unsupported_response = self.client.post(
            "/api/conversations/messages",
            headers=demo_headers,
            json={
                "session_id": upload_body["session_id"],
                "parent_message_id": None,
                "raw_text": "请看这个文件",
                "model_id": deepseek_model["model_id"],
                "thinking_mode": "default",
                "context_resources": [
                    {
                        "resource_type": "file",
                        "resource_id": upload_body["resource"]["resource_id"],
                    }
                ],
            },
        )
        self.assertEqual(unsupported_response.status_code, 400)
        self.assertEqual(unsupported_response.json()["detail"]["code"], "INVALID_REQUEST")
        self.assertEqual(
            self.client.get(
                f"/api/conversations/{upload_body['session_id']}",
                headers=demo_headers,
            ).json()["messages"],
            [],
        )

        from backend.app.storage.paths import app_paths
        from backend.app.storage.sqlite import connect

        with connect(app_paths().conversations_db("demo_patient")) as connection:
            connection.execute(
                """
                UPDATE conversation_resources
                SET expires_at = '2000-01-01T00:00:00+00:00'
                WHERE resource_id = ?
                """,
                (upload_body["resource"]["resource_id"],),
            )

        expired_response = self.client.post(
            "/api/conversations/messages",
            headers=demo_headers,
            json={
                "session_id": upload_body["session_id"],
                "parent_message_id": None,
                "raw_text": "请看这个过期文件",
                "model_id": model["model_id"],
                "thinking_mode": "default",
                "context_resources": [
                    {
                        "resource_type": "file",
                        "resource_id": upload_body["resource"]["resource_id"],
                    }
                ],
            },
        )
        self.assertEqual(expired_response.status_code, 400)
        self.assertEqual(expired_response.json()["detail"]["code"], "INVALID_REQUEST")

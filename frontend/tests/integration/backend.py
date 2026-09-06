"""An isolated real application; only external provider responses are substituted."""

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def main():
    with TemporaryDirectory(prefix="serenita-integration-") as root:
        os.environ["DATA_ROOT"] = str(Path(root).resolve())
        from backend.app.agent_runtime.model_types import (
            AssistantModelOutput,
            ModelStreamChunk,
        )
        from backend.app.application.auth_service import AuthService
        from backend.app.application.member_service import MemberService
        from backend.app.application import (
            model_provider_service,
            model_settings_service,
        )
        from backend.app.providers.base import ModelProvider
        from backend.app.providers.types import ProviderConnectionResult, ProviderModel, ModelCapabilityProbeResult
        from backend.app.providers.registry import ProviderRegistry
        from backend.app.schemas.model_provider import (
            ModelProviderSaveRequest,
            AddModelRequest,
            ModelDefaultsPatchRequest,
        )
        from backend.app.plugins.web import service as web_service
        from backend.app.main import create_app
        import uvicorn

        class IntegrationProvider(ModelProvider):
            provider_id = "integration"
            provider_name = "联调模型服务"
            default_api_url = "https://integration.invalid/v1"

            def native_attachment_mime_types(self):
                return {"image/jpeg", "image/png"}

            def test_connection(self, **kwargs):
                return ProviderConnectionResult(self.provider_id, True, "联调服务可用")

            def list_models(self, **kwargs):
                return [
                    ProviderModel(
                        "chat",
                        "联调模型",
                        file_mime_types=["image/jpeg", "image/png"],
                        supports_tool_calling=True,
                        context_window_tokens=32000,
                    )
                ]

            def complete_chat(self, **kwargs):
                return AssistantModelOutput(content="联调聊天", stop_reason="stop")

            def stream_chat_payload(self, *, cancellation_token=None, **kwargs):
                for part in ["联调回答", "：已收到消息。"]:
                    if cancellation_token:
                        cancellation_token.raise_if_cancelled()
                    yield ModelStreamChunk(content_delta=part)
                    time.sleep(0.04)
                yield ModelStreamChunk(
                    stop_reason="stop",
                    usage={
                        "prompt_tokens": 100,
                        "completion_tokens": 12,
                        "total_tokens": 112,
                    },
                )

            def probe_capabilities(self, **kwargs):
                return ModelCapabilityProbeResult(
                    kwargs["current_profiles"],
                    {
                        "thinking_modes": {"default": "supported"},
                        "non_thinking": {
                            "text": "supported",
                            "tool_calling": "supported",
                        },
                        "thinking": {
                            "text": "not_applicable",
                            "tool_calling": "not_applicable",
                        },
                    },
                )

        registry = ProviderRegistry()
        registry.register(IntegrationProvider())
        model_provider_service.create_default_provider_registry = lambda: registry
        model_settings_service.create_default_provider_registry = lambda: registry

        class IntegrationWeb:
            def test(self, api_key):
                return None

        web_service._default_adapter_factory = lambda *_: IntegrationWeb()

        user, _ = AuthService().sign_up(
            account="integration",
            account_name="联调账号",
            password="test-password",
            confirm_password="test-password",
        )
        MemberService().create_member(
            user.account_id,
            {
                "member_name": "联调成员",
                "sex": None,
                "birth_date": None,
                "blood_type": None,
            },
            set_as_default=True,
        )
        settings = model_settings_service.ModelSettingsService(
            provider_registry=registry
        )
        settings.create_model_provider(
            user.account_id,
            ModelProviderSaveRequest(
                provider_id="integration", api_key="integration-test-key"
            ),
        )
        profile = {
            "availability": "available",
            "supports_text": True,
            "supports_tool_calling": True,
            "file_mime_types": ["image/jpeg", "image/png"],
        }
        settings.add_model(
            user.account_id,
            AddModelRequest(
                provider_id="integration",
                remote_model_id="chat",
                thinking_modes=["default"],
                context_window_tokens=32000,
                capability_profiles={
                    "default_state": "non_thinking",
                    "non_thinking": profile,
                    "thinking": {**profile, "availability": "unavailable"},
                },
            ),
        )
        settings.update_model_defaults(
            user.account_id,
            ModelDefaultsPatchRequest(
                chat="integration:chat",
                title="integration:chat",
                compact="integration:chat",
                vision_parse="integration:chat",
            ),
        )
        uvicorn.run(create_app(), host="127.0.0.1", port=8186, log_level="warning")


if __name__ == "__main__":
    main()

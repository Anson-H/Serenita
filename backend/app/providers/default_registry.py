from backend.app.providers.aliyun_bailian import AliyunBailianProvider
from backend.app.providers.deepseek import DeepSeekProvider
from backend.app.providers.openrouter import OpenRouterProvider
from backend.app.providers.registry import ProviderRegistry
from backend.app.providers.zhipu import ZhipuProvider


def create_default_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(OpenRouterProvider())
    registry.register(DeepSeekProvider())
    registry.register(AliyunBailianProvider())
    registry.register(ZhipuProvider())
    return registry

from typing import Dict

from backend.app.providers.base import ModelProvider


class ProviderNotFoundError(KeyError):
    pass


class ProviderRegistry:
    def __init__(self):
        self._providers: Dict[str, ModelProvider] = {}

    def register(self, provider: ModelProvider) -> None:
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> ModelProvider:
        try:
            return self._providers[provider_id]
        except KeyError:
            raise ProviderNotFoundError(provider_id)

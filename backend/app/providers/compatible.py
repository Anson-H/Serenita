"""Account-owned OpenAI-compatible model connections."""
from backend.app.providers.base import ModelProvider


class CompatibleProvider(ModelProvider):
    provider_kind = "custom"
    requires_api_key = False

    def __init__(self, provider_id, provider_name="", api_url="", **kwargs):
        super().__init__(**kwargs)
        self.provider_id = provider_id
        self.provider_name = provider_name
        self.default_api_url = api_url

    def native_attachment_mime_types(self):
        from backend.app.domain.model_capabilities import (
            IMAGE_FILE_MIME_TYPES, AUDIO_FILE_MIME_TYPES, NATIVE_DOCUMENT_FILE_MIME_TYPES,
        )
        return set(IMAGE_FILE_MIME_TYPES + AUDIO_FILE_MIME_TYPES + NATIVE_DOCUMENT_FILE_MIME_TYPES)

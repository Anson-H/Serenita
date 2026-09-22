"""Configured native attachment support shared by conversation and task input."""


class ModelAttachmentCapabilities:
    def __init__(self, model_catalog):
        self.model_catalog = model_catalog

    def model_can_forward_attachment(self, model, mime_type):
        return mime_type in model.get('file_mime_types', []) and self.model_catalog.provider_supports_native_attachment(model, mime_type)

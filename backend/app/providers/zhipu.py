"""智谱开放平台的生成与向量接口。"""
from backend.app.providers.base import ModelProvider


class ZhipuProvider(ModelProvider):
    provider_id = "zhipu"
    provider_name = "智谱开放平台"
    default_api_url = "https://open.bigmodel.cn/api/paas/v4"
    default_official_url = "https://bigmodel.cn"
    connection_test_path = "/files?limit=1"

    def native_attachment_mime_types(self):
        from backend.app.domain.model_capabilities import IMAGE_FILE_MIME_TYPES, VIDEO_FILE_MIME_TYPES
        return set(IMAGE_FILE_MIME_TYPES + VIDEO_FILE_MIME_TYPES)

    def thinking_mode_payload(self, remote_model_id, thinking_mode):
        if thinking_mode == "default":
            return {}
        return {"thinking": {"type": "disabled" if thinking_mode == "off" else "enabled"}}

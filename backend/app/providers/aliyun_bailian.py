import re
from typing import Any

from backend.app.providers.base import ModelProvider
from backend.app.providers.errors import _can_classify_context_error


ALIYUN_IMAGE_FILE_MIME_TYPES = (
    "image/bmp",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
    "image/heic",
)

ALIYUN_AUDIO_FILE_MIME_TYPES = (
    "audio/amr",
    "audio/wav",
    "audio/x-wav",
    "audio/3gpp",
    "audio/3gpp2",
    "audio/aac",
    "audio/mpeg",
    "audio/mp3",
)

ALIYUN_VIDEO_FILE_MIME_TYPES = (
    "video/mp4",
    "video/x-msvideo",
    "video/x-matroska",
    "video/mov",
    "video/quicktime",
    "video/x-flv",
    "video/x-ms-wmv",
)


class AliyunBailianProvider(ModelProvider):
    provider_id = "aliyun_bailian"
    provider_name = "阿里云百炼"
    default_api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    default_official_url = "https://bailian.console.aliyun.com/?tab=model#/api-key"

    def model_type_from_metadata(self, item):
        capabilities = item.get("capabilities", [])
        if isinstance(capabilities, list):
            if set(capabilities) & {"TR", "ME"}:
                return "embedding"
            if "TG" in capabilities:
                return "generation"
        return super().model_type_from_metadata(item)

    def _native_embedding_root(self, api_url):
        from urllib.parse import urlsplit
        parsed = urlsplit(api_url)
        official = {"dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com", "dashscope-us.aliyuncs.com"}
        if parsed.scheme == "https" and parsed.netloc in official and parsed.path.rstrip("/") in {"/compatible-mode/v1", "/api/v1"}:
            return f"https://{parsed.netloc}/api/v1"
        return None

    def embedding_protocols(self, api_url):
        return ["compatible", "aliyun_multimodal"]

    def embedding_modalities(self, protocol):
        return {"text", "image", "video"} if protocol == "aliyun_multimodal" else {"text"}

    def embedding_dimensions(self, remote_model_id):
        # Official parameter domains; every candidate is still verified by request.
        return {
            "qwen3-vl-embedding": [2560, 2048, 1536, 1024, 768, 512, 256],
            "qwen2.5-vl-embedding": [2048, 1024, 768, 512],
            "tongyi-embedding-vision-plus-2026-03-06": [64, 128, 256, 512, 1024, 1152],
            "tongyi-embedding-vision-flash-2026-03-06": [64, 128, 256, 512, 768],
            "text-embedding-v3": [1024, 768, 512, 256, 128, 64],
            "text-embedding-v4": [2048, 1536, 1024, 768, 512, 256, 128, 64],
        }.get(remote_model_id, [])

    def build_embedding_request(self, api_url, model, inputs, mode, dimensions, protocol):
        if protocol != "aliyun_multimodal":
            return super().build_embedding_request(api_url, model, inputs, mode, dimensions, protocol)
        from backend.app.providers.errors import ProviderChatCompletionError
        root = self._native_embedding_root(api_url)
        if not root:
            raise ProviderChatCompletionError("自定义地址的原生多模态向量协议未确认。", code="EMBEDDING_PROTOCOL_UNCONFIRMED")
        if any(item["modality"] not in self.embedding_modalities(protocol) for item in inputs):
            raise ProviderChatCompletionError("原生接口不支持此输入模态。", code="EMBEDDING_INPUT_UNSUPPORTED", capability_rejected=True)
        contents = [{item["modality"]: item["value"]} for item in inputs]
        parameters = {}
        if dimensions is not None:
            parameters["dimension"] = dimensions
        if mode == "fusion":
            if model.startswith("tongyi-embedding-vision-") and model.endswith("-2026-03-06"):
                if len({item["modality"] for item in inputs}) != len(inputs):
                    raise ProviderChatCompletionError("该融合结构每种模态只能出现一次。", capability_rejected=True)
                contents = [{key: value for item in contents for key, value in item.items()}]
            elif model != "qwen2.5-vl-embedding":
                parameters["enable_fusion"] = True
        return root + "/services/embeddings/multimodal-embedding/multimodal-embedding", {"model": model, "input": {"contents": contents}, "parameters": parameters}

    def is_context_overflow(self, details: dict[str, Any]) -> bool:
        if not _can_classify_context_error(details):
            return False
        if super().is_context_overflow(details):
            return True
        code = details.get("code")
        if isinstance(code, str) and code in {
            "InputTooLong",
            "InvalidParameter.InputTooLong",
        }:
            return True
        message = details.get("message")
        # DashScope documents this specific input-range error as input overflow.
        # The similarly worded max_tokens range error is an output parameter error.
        return isinstance(message, str) and bool(
            re.search(
                r"\bRange of input length should be \[1,\s*\d+\]",
                message,
                re.IGNORECASE,
            )
        )

    def native_attachment_mime_types(self) -> set[str]:
        return {
            *ALIYUN_IMAGE_FILE_MIME_TYPES,
            *ALIYUN_AUDIO_FILE_MIME_TYPES,
            *ALIYUN_VIDEO_FILE_MIME_TYPES,
        }

    def thinking_mode_payload(
        self,
        remote_model_id: str,
        thinking_mode: str,
    ) -> dict[str, object]:
        if thinking_mode == "off":
            return {"enable_thinking": False}
        if thinking_mode == "default":
            return {}
        return {
            "enable_thinking": True,
            "reasoning_effort": thinking_mode,
        }

    def capability_probe_tool_choice(self, state: str) -> Any:
        if state == "thinking":
            return "auto"
        return super().capability_probe_tool_choice(state)

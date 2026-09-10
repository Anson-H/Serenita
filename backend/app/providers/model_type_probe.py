"""Actual interface detection precedes provider metadata and detailed probes."""

from backend.app.agent_runtime.model_types import ModelRequest
from backend.app.domain.model_capabilities import EmbeddingCapabilities
from backend.app.providers.errors import ProviderChatCompletionError, ProviderModelListError
from backend.app.providers.capability_probe import (
    _CAPABILITY_PROBE_PNG_BASE64, _CAPABILITY_PROBE_PDF_BASE64,
    _CAPABILITY_PROBE_WAV_BASE64, _CAPABILITY_PROBE_MP4_BASE64,
)

SAMPLES = {
    "text": {"modality": "text", "value": "向量检测"},
    "image": {"modality": "image", "value": "data:image/png;base64," + _CAPABILITY_PROBE_PNG_BASE64},
    "audio": {"modality": "audio", "value": "data:audio/wav;base64," + _CAPABILITY_PROBE_WAV_BASE64},
    "video": {"modality": "video", "value": "data:video/mp4;base64," + _CAPABILITY_PROBE_MP4_BASE64},
    "document": {"modality": "document", "value": "data:application/pdf;base64," + _CAPABILITY_PROBE_PDF_BASE64},
}
MIMES = {"image": "image/png", "audio": "audio/wav", "video": "video/mp4", "document": "application/pdf"}


def sample(modality, protocol):
    if modality == "video" and protocol == "aliyun_multimodal":
        return {"modality": "video", "value": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20250107/lbcemt/new+video.mp4"}
    return dict(SAMPLES[modality])


def attempt(checks, errors, key, action):
    try:
        result = action()
        checks[key] = "supported"
        return result
    except (ProviderChatCompletionError, ProviderModelListError) as exc:
        checks[key] = "unsupported" if getattr(exc, "capability_rejected", False) else "unverified"
        labels = {401: "认证失败", 403: "权限不足", 404: "接口或模型不存在", 429: "请求限流"}
        label = labels.get(getattr(exc, "upstream_status", None), exc.code or "MODEL_ERROR")
        errors[key] = f"{label}：{exc}"
        return None


def detect_model_type(provider, *, api_url, api_key, remote_model_id, cancellation_token):
    args = dict(api_url=api_url, api_key=api_key, remote_model_id=remote_model_id, cancellation_token=cancellation_token)
    checks, errors, successes = {}, {}, []
    def generation():
        output = provider.complete_chat(**args, model_request=ModelRequest.build(system="", messages=[{"role": "user", "content": "OK"}], model_config={"max_tokens": 32}))
        if not (output.content or output.reasoning or output.tool_calls):
            raise ProviderChatCompletionError("生成接口返回空结果。", code="INVALID_MODEL_RESPONSE")
        return output
    attempt(checks, errors, "generation", generation)
    # Every applicable protocol/modality is tried; a failed text probe cannot hide a vision-only embedding.
    for protocol in provider.embedding_protocols(api_url):
        for modality in sorted(provider.embedding_modalities(protocol)):
            cancellation_token.raise_if_cancelled()
            result = attempt(checks, errors, f"{protocol}_{modality}", lambda: provider.complete_embedding(**args, inputs=[sample(modality, protocol)], protocol=protocol))
            # Fusion-only native models need a fused request even for a single input.
            if result is None and protocol == "aliyun_multimodal":
                result = attempt(checks, errors, f"{protocol}_{modality}_fusion", lambda: provider.complete_embedding(**args, inputs=[sample(modality, protocol)], mode="fusion", protocol=protocol))
            if result is not None:
                successes.append((protocol, modality, result))
    generation_ok = checks["generation"] == "supported"
    conflict = generation_ok and bool(successes)
    kind = "unknown" if conflict else "generation" if generation_ok else "embedding" if successes else "unknown"
    metadata = {"status": "not_found", "message": "接口实测完成。"}
    listed = None
    try:
        listed = next((m for m in provider.list_models(api_url=api_url, api_key=api_key, cancellation_token=cancellation_token) if m.remote_model_id == remote_model_id), None)
        if listed:
            if kind == "unknown" and not conflict:
                kind = listed.model_type
            metadata = {"status": "refreshed", "message": "已完成接口实测并读取提供方模型信息。"}
        elif kind == "unknown":
            metadata["message"] = "接口和目录均未确认类型，请手工选择。"
    except ProviderModelListError as exc:
        metadata = {"status": "unavailable", "message": str(exc)}
    if conflict:
        metadata["message"] = "生成与向量接口均成功，请选择本条配置的模型类型。"
    return kind, checks, errors, successes, metadata, listed, conflict


def probe_embeddings(provider, *, api_url, api_key, remote_model_id, cancellation_token, successes, dimensions=None, declared_dimensions=()):
    capabilities = EmbeddingCapabilities()
    output_dimensions = None
    checks, errors = {}, {}
    protocol = successes[0][0] if successes else provider.embedding_protocols(api_url)[0]
    # Prefer native multimodal when it actually succeeded.
    if any(p == "aliyun_multimodal" for p, _, _ in successes):
        protocol = "aliyun_multimodal"
    args = dict(api_url=api_url, api_key=api_key, remote_model_id=remote_model_id, cancellation_token=cancellation_token, protocol=protocol)
    verified = []
    for modality in SAMPLES:
        if modality not in provider.embedding_modalities(protocol):
            checks[modality] = "not_applicable"
            continue
        cancellation_token.raise_if_cancelled()
        result = next((result for p, m, result in successes if p == protocol and m == modality), None)
        if result is None:
            result = attempt(checks, errors, modality, lambda: provider.complete_embedding(**args, inputs=[sample(modality, protocol)]))
        else:
            checks[modality] = "supported"
        if result:
            capabilities.protocol = protocol
            verified.append(sample(modality, protocol))
            if output_dimensions is not None and output_dimensions != result.dimensions:
                checks[modality] = "unverified"
                errors[modality] = "不同输入模态的默认维度不一致。"
                verified.pop()
                continue
            output_dimensions = result.dimensions
            if modality == "text":
                capabilities.supports_text = True
            if modality in MIMES:
                capabilities.file_mime_types.append(MIMES[modality])
    if verified:
        independent = attempt(checks, errors, "independent", lambda: provider.complete_embedding(**args, inputs=[verified[0]]))
        capabilities.independent = checks["independent"]
        attempt(checks, errors, "batch", lambda: provider.complete_embedding(**args, inputs=[verified[0], {**verified[0], "value": "另一个输入"} if verified[0]["modality"] == "text" else dict(verified[0])]))
        if len(verified) >= 2:
            attempt(checks, errors, "fusion", lambda: provider.complete_embedding(**args, inputs=verified[:2], mode="fusion"))
        else:
            checks["fusion"] = "not_applicable"
        capabilities.fusion = checks["fusion"]
        for dimension in sorted(set(declared_dimensions) | set(provider.embedding_dimensions(remote_model_id)) | ({dimensions} if dimensions else set())):
            cancellation_token.raise_if_cancelled()
            key = f"dimension_{dimension}"
            attempt(checks, errors, key, lambda: provider.complete_embedding(**args, inputs=[verified[0]], mode="independent" if independent else "fusion", dimensions=dimension))
            capabilities.dimensions[str(dimension)] = checks[key]
    else:
        checks.update(independent="unverified", fusion="unverified", batch="unverified")
        if dimensions:
            checks[f"dimension_{dimensions}"] = "unverified"
            capabilities.dimensions[str(dimensions)] = "unverified"
    return capabilities.model_dump(), output_dimensions, checks, errors

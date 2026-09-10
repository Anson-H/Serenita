"""Provider embedding requests and strict input/result correspondence."""

import math
from dataclasses import dataclass
from typing import Any
from backend.app.providers.errors import ProviderChatCompletionError


def invalid(message):
    return ProviderChatCompletionError(message, code="INVALID_EMBEDDING_RESPONSE")


@dataclass(frozen=True)
class EmbeddingResult:
    model: str
    vectors: list[list[float]]
    dimensions: int
    mode: str
    usage: dict[str, Any]


def validate_vectors(payload, *, count, dimensions=None, model, mode, native=False, inputs=None):
    container = payload.get("output") if native else payload
    rows = container.get("embeddings" if native else "data") if isinstance(container, dict) else None
    if not isinstance(rows, list) or len(rows) != count:
        raise invalid(f"向量返回数量不正确，预期 {count} 条。")
    mapped = {}
    size = None
    for row in rows:
        if not isinstance(row, dict):
            raise invalid("向量条目格式无效。")
        index, vector = row.get("index"), row.get("embedding")
        if type(index) is not int or index not in range(count) or index in mapped:
            raise invalid("向量索引缺失、重复或越界。")
        if not isinstance(vector, list) or not vector:
            raise invalid("向量不能为空。")
        try:
            finite = all(type(value) in (int, float) and math.isfinite(value) for value in vector)
        except OverflowError:
            finite = False
        if not finite:
            raise invalid("向量包含无效数值。")
        if size is not None and size != len(vector):
            raise invalid("同一请求的向量维度不一致。")
        size = len(vector)
        if dimensions is not None and size != dimensions:
            raise invalid(f"维度参数未生效：请求 {dimensions}，实际 {size}。")
        if native and mode == "fusion" and count == 1 and row.get("type") not in {"fusion", "fused"}:
            raise invalid("返回结果没有确认融合向量。")
        if native and mode == "independent" and inputs and row.get("type") not in {inputs[index]["modality"], "vl"}:
            raise invalid("向量类型与输入不对应。")
        mapped[index] = vector
    return EmbeddingResult(payload.get("model") or model, [mapped[i] for i in range(count)], size, mode, payload.get("usage", {}))


def compatible_payload(model, inputs, mode, dimensions):
    if mode != "independent" or any(item["modality"] != "text" for item in inputs):
        raise ProviderChatCompletionError("该接口未声明此输入结构或融合方式。", code="EMBEDDING_PROTOCOL_UNCONFIRMED")
    payload = {"model": model, "input": [item["value"] for item in inputs], "encoding_format": "float"}
    if dimensions is not None:
        payload["dimensions"] = dimensions
    return payload


def complete_embedding(provider, *, api_url, api_key, remote_model_id, inputs, mode="independent", dimensions=None, protocol="compatible", cancellation_token=None, timeout_seconds=None):
    if not inputs or mode not in {"independent", "fusion"}:
        raise ValueError("向量输入不能为空，生成方式必须有效。")
    if dimensions is not None and (type(dimensions) is not int or dimensions <= 0):
        raise ValueError("向量维度必须为正整数。")
    url, payload = provider.build_embedding_request(api_url, remote_model_id, inputs, mode, dimensions, protocol)
    response = provider.transport.request_json(url=url, api_key=api_key, payload=payload, cancellation_token=cancellation_token, timeout_seconds=timeout_seconds)
    return validate_vectors(response, count=1 if mode == "fusion" else len(inputs), dimensions=dimensions, model=remote_model_id, mode=mode, native=protocol == "aliyun_multimodal", inputs=inputs)

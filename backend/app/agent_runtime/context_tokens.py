"""Shared tokenizer estimates and native-media accounting, without payload edits."""
import base64
import binascii
import hashlib
from io import BytesIO
import json
import math

from PIL import Image, UnidentifiedImageError
from backend.app.core.token_counting import text_token_counter


IMAGE_TOKEN_CEILING = 17000
IMAGE_BUDGET_SOURCE = "https://help.aliyun.com/zh/model-studio/vision-model/"
VERIFIED_IMAGE_MODELS = frozenset({"qwen3.8-flash", "qwen3.8-max", "qwen3.8-max-0902", "qwen3.7-plus", "qwen3.7-flash"})
IMAGE_DIMENSION_SOURCES = (
    "https://help.aliyun.com/zh/model-studio/vision",
    "https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions",
)
_IMAGE_CONTROLS = frozenset({"min_pixels", "max_pixels", "vl_high_resolution_images", "resized_height", "resized_width"})
_MEDIA_BYTES_PER_TOKEN = {"image": 128, "audio": 32, "video": 16, "file": 8}


def _has_image_controls(value):
    if not isinstance(value, dict):
        return False
    return bool(_IMAGE_CONTROLS.intersection(value)) or any(
        _has_image_controls(value.get(key)) for key in ("model_config", "extra_body", "image_url"))


def _image_bound(part, model, payload):
    fallback = {"method": "provider_ceiling", "tokens": IMAGE_TOKEN_CEILING}
    if model["remote_model_id"] != "qwen3.8-flash" or any(_has_image_controls(value) for value in (part, model, payload)):
        return {**fallback, "reason": "dimension_protocol_unconfirmed"}
    encoded = part["data_base64"]
    if len(encoded) > 20 * 1024 * 1024:
        return {**fallback, "reason": "encoded_image_exceeds_documented_limit"}
    try:
        data = base64.b64decode(encoded, validate=True)
        with Image.open(BytesIO(data)) as original:
            width, height = original.size
            if original.format != {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[part["mime_type"]]:
                return {**fallback, "reason": "image_format_mismatch"}
            if getattr(original, "n_frames", 1) != 1:
                return {**fallback, "reason": "multiple_frames"}
            # The API's current minimum is 65536 pixels; the older resize
            # example says 4096. Requiring both sides >=256 covers both and
            # avoids extrapolating any small-image upscaling behavior.
            if min(width, height) < 256 or max(width, height) > 200 * min(width, height) or width * height > 16777216:
                return {**fallback, "reason": "dimensions_outside_confirmed_range"}
            original.verify()
        with Image.open(BytesIO(data)) as original:
            original.load()
    except (ValueError, OSError, SyntaxError, binascii.Error, UnidentifiedImageError, Image.DecompressionBombError):
        return {**fallback, "reason": "image_bytes_unverified"}
    # Each side rounds upward to a full 32-pixel cell. This bounds both the
    # documented nearest-cell rounding and any max-pixel downscale, without
    # assuming that the provider actually downsamples the original image.
    bound = ((width + 31) // 32) * ((height + 31) // 32) + 2
    if bound >= IMAGE_TOKEN_CEILING:
        return {**fallback, "reason": "dimension_bound_not_smaller"}
    return {"method": "verified_dimensions", "tokens": bound,
        "width": width, "height": height, "patch_size": 32, "minimum_pixels": 65536,
        "sha256": hashlib.sha256(data).hexdigest(), "source_urls": list(IMAGE_DIMENSION_SOURCES)}


def _media_projection(payload, model):
    if not isinstance(payload, dict):
        return payload, [], 0
    messages = payload.get("messages")
    if not isinstance(messages, (list, tuple)):
        return payload, [], 0
    verified = (isinstance(model, dict) and model.get("provider_id") == "aliyun_bailian"
                and model.get("remote_model_id") in VERIFIED_IMAGE_MODELS)
    normalized, images, attachments = [], [], 0
    for message in messages:
        if not isinstance(message, dict) or not isinstance(message.get("content"), (list, tuple)):
            normalized.append(message)
            continue
        parts = []
        for part in message["content"]:
            if (isinstance(part, dict) and part.get("type") in _MEDIA_BYTES_PER_TOKEN
                    and isinstance(part.get("data_base64"), str) and part["data_base64"]):
                # Only native message parts are media. Lookalike tool data is text.
                kind = part["type"]
                parts.append({key: value for key, value in part.items() if key != "data_base64"})
                if verified and kind == "image" and part.get("mime_type") in {"image/jpeg", "image/png", "image/webp"}:
                    images.append(_image_bound(part, model, payload))
                else:
                    decoded_bytes = math.ceil(len(part["data_base64"].strip()) * 3 / 4)
                    estimate = max(512, math.ceil(decoded_bytes / _MEDIA_BYTES_PER_TOKEN[kind]))
                    if kind == "image":
                        images.append({"method": "encoded_size_estimate", "tokens": estimate})
                    else:
                        attachments += estimate
            else:
                parts.append(part)
        normalized.append({**message, "content": parts})
    return {**payload, "messages": normalized}, images, attachments


def input_budget_provenance(payload, *, model=None):
    normalized, images, attachments = _media_projection(payload, model)
    if isinstance(normalized, dict):
        # Generation controls and internal audit fields are not model input text.
        normalized = {key: value for key, value in normalized.items()
                      if key in {"system", "messages", "tools", "tool_choice"}
                      and (value or key == "messages")}
        if payload.get("supports_json_schema_output") is True and payload.get("output_schema") is not None:
            normalized["output_schema"] = payload["output_schema"]
    counter = text_token_counter(model)
    text_tokens = counter.count(json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), default=str))
    count = len(images)
    image_tokens = sum(item["tokens"] for item in images)
    return {"method": "tokenizer", "tokenizer": {"name": counter.name, "match": counter.match},
        "text_tokens": text_tokens, "image_count": count,
        "image_tokens": image_tokens, "images": images, "attachment_tokens": attachments,
        "estimated_tokens": text_tokens + image_tokens + attachments,
        "provider_id": model.get("provider_id") if isinstance(model, dict) else None,
        "remote_model_id": model.get("remote_model_id") if isinstance(model, dict) else None,
        "source_url": IMAGE_BUDGET_SOURCE if any(item["method"] != "encoded_size_estimate" for item in images) else None}



def estimate_input_tokens(payload, *, model=None):
    return input_budget_provenance(payload, model=model)["estimated_tokens"]

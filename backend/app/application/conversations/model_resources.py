"""解析工具关联的原件，在工具结果进入模型上下文前准备完整内容。"""

from pathlib import Path
import base64
import time
from typing import Any
from backend.app.core.errors import raise_error
from backend.app.providers.errors import ProviderChatCompletionError
from backend.app.plugins.registry import resolve_plugin_model_resource_refs


class ConversationModelResources:
    def __init__(self, *, account_id, inputs, model_catalog, runtime_context):
        self.account_id = account_id
        self.inputs = inputs
        self.model_catalog = model_catalog
        self.runtime_context = runtime_context

    def prepare(
        self,
        refs: list[dict[str, Any]],
        current_model: dict[str, Any],
        *,
        resolved_resources: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        token = self.runtime_context.cancellation_token
        if token is not None:
            token.raise_if_cancelled()
        resources = (
            resolved_resources
            if resolved_resources is not None
            else resolve_plugin_model_resource_refs(
                runtime_context=self.runtime_context,
                resource_refs=refs,
            )
        )
        resolved = [
            (
                resource,
                (
                    Path(str(resource["path"]))
                    if str(resource.get("path") or "")
                    else None
                ),
                str(resource.get("original_filename") or ""),
                str(resource.get("mime_type") or ""),
            )
            for resource in resources
        ]

        def can_read(model: dict[str, Any], mime_type: str) -> bool:
            if mime_type == "text/plain":
                return True
            return self.inputs.model_can_forward_attachment(model, mime_type) or (
                mime_type == "application/pdf"
                and self.inputs.model_can_forward_attachment(model, "image/jpeg")
            )

        candidates = [current_model]
        fallback = self.model_catalog.default_model_for_account(
            self.account_id, "vision_parse"
        )
        if fallback and fallback.get("model_id") != current_model.get("model_id"):
            candidates.append(fallback)
        selected = next(
            (
                model
                for model in candidates
                if all(
                    can_read(model, mime_type)
                    for _ref, _path, _name, mime_type in resolved
                )
            ),
            None,
        )
        if selected is None:
            raise_error(
                "invalid_structure",
                "MODEL_FILE_UNSUPPORTED",
                "当前聊天模型和视觉后备模型都不能读取工具返回的原件资源。",
            )

        parts: list[dict[str, Any]] = []
        for ref, path, name, mime_type in resolved:
            if token is not None:
                token.raise_if_cancelled()
            safe_ref = {
                key: value
                for key, value in ref.items()
                if key not in {"path", "text", "content_bytes"}
            }
            identifiers = {"model_resource_ref": safe_ref}
            if mime_type == "text/plain":
                source_text = ref.get("text")
                if isinstance(ref.get("content_bytes"), bytes):
                    source_text = ref["content_bytes"].decode("utf-8")
                if not isinstance(source_text, str):
                    if path is None:
                        raise ProviderChatCompletionError(
                            "模型文本资源缺少可读取内容。"
                        )
                    try:
                        source_text = path.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError) as exc:
                        raise ProviderChatCompletionError(
                            "工具返回的文本原件无法读取。"
                        ) from exc
                parts.append(
                    {
                        "type": "text",
                        "text": source_text,
                        "name": name,
                        **identifiers,
                    }
                )
                continue
            if (
                mime_type == "application/pdf"
                and not self.inputs.model_can_forward_attachment(
                    selected, mime_type
                )
            ):
                if path is None and not isinstance(ref.get("content_bytes"), bytes):
                    raise ProviderChatCompletionError(
                        "模型 PDF 资源缺少可读取原件。"
                    )
                from backend.app.application.conversations.attachment_rendering import (
                    model_file_parts,
                )

                rendered = model_file_parts(
                    path or Path(name or "source.pdf"),
                    mime_type,
                    deadline=time.monotonic() + 60,
                    content_bytes=ref.get("content_bytes"),
                )
                parts.extend({**dict(page), **identifiers} for page in rendered)
                continue
            content = ref.get("content_bytes")
            if path is None and not isinstance(content, bytes):
                raise ProviderChatCompletionError("模型资源缺少可读取原件。")
            try:
                if not isinstance(content, bytes):
                    content = path.read_bytes()
            except OSError as exc:
                raise ProviderChatCompletionError(
                    "工具返回的原件无法读取。"
                ) from exc
            part_type = next((kind for kind in ("image", "audio", "video") if mime_type.startswith(kind + "/")), "file")
            parts.append(
                {
                    "type": part_type,
                    "mime_type": mime_type,
                    "name": name,
                    "data_base64": base64.b64encode(content).decode("ascii"),
                    **identifiers,
                }
            )
        if token is not None:
            token.raise_if_cancelled()
        return selected, parts

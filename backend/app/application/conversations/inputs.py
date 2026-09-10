"""校验会话输入和附件，管理附件内容读取，并准备模型可读取的内容。"""

import base64
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Optional

from backend.app.agent_runtime.model_types import ModelRequest
from backend.app.core.attachment_content import AttachmentContent
from backend.app.core.errors import SerenitaError, raise_error
from backend.app.core.member_errors import member_error
from backend.app.core.time import parse_local_datetime, local_now
from backend.app.core.markdown_text import markdown_selection_text
from backend.app.providers.errors import ProviderChatCompletionError
from backend.app.application.conversations.access import session_member_access

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES_PER_TURN = 20
MAX_TOTAL_FILE_BYTES = 100 * 1024 * 1024
ALLOWED_MIME_TYPES = {
    "image/bmp": ".bmp",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "image/heic": ".heic",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "audio/amr": ".amr",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/3gpp": ".3gp",
    "audio/3gpp2": ".3gpp",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/aiff": ".aiff",
    "audio/x-aiff": ".aiff",
    "audio/aac": ".aac",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/x-m4a": ".m4a",
    "video/mp4": ".mp4",
    "video/mpeg": ".mpeg",
    "video/x-msvideo": ".avi",
    "video/x-matroska": ".mkv",
    "video/mov": ".mov",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "video/x-flv": ".flv",
    "video/x-ms-wmv": ".wmv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/msword": ".doc",
    "application/vnd.ms-excel": ".xls",
}
MODEL_RENDERABLE_ATTACHMENT_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/heic", "application/pdf"}
)


def _annotation_source_values(record: dict[str, Any]) -> list[Any] | None:
    kind = record.get("kind")
    if kind in {"user", "assistant"}:
        return [record.get("content")]
    if kind == "model" and record.get("channel") == "content":
        return [record.get("value")]
    return None


def _annotation_text_belongs_to_record(
    annotation_text: str,
    record: dict[str, Any],
) -> bool:
    values = _annotation_source_values(record)
    if values is None:
        return False
    normalized_annotation = re.sub(r"\s+", " ", annotation_text).strip()
    if not normalized_annotation:
        return False
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = [
                json.dumps(value, ensure_ascii=False, indent=2, default=str),
                json.dumps(
                    value, ensure_ascii=False, separators=(",", ":"), default=str
                ),
            ]
        for candidate in candidates:
            if annotation_text in candidate:
                return True
            if normalized_annotation in re.sub(r"\s+", " ", candidate).strip():
                return True
            # Browser selections omit Markdown syntax. Derive the visible text
            # from the trusted record, never from client-supplied source text.
            rendered_text = markdown_selection_text(candidate)
            if normalized_annotation in re.sub(r"\s+", " ", rendered_text).strip():
                return True
    return False


class ConversationInputs:
    def __init__(self, repository, members, model_catalog, services, events):
        self.repository = repository
        self.members = members
        self.model_catalog = model_catalog
        self.services = services
        self.events = events

    def upload_context_resource(
        self,
        account_id: str,
        session_id: Optional[str],
        model_id: Optional[str],
        upload: dict[str, Any],
        *,
        member_id: str | None,
    ) -> dict[str, Any]:
        self.maintain_attachments(account_id)
        self.repository.init_db(account_id)
        content = upload["content"]
        if len(content) > MAX_FILE_BYTES:
            raise_error("resource_limit", "FILE_TOO_LARGE", "单文件大小不能超过 20MB。")
        mime_type = upload["mime_type"]
        if mime_type not in ALLOWED_MIME_TYPES:
            raise_error("unsupported", "UNSUPPORTED_FILE_TYPE", "文件类型不支持。")
        model = self.validate_model(account_id, model_id, "default")
        self.validate_attachment_supported_for_conversation(
            account_id, model, mime_type
        )

        actual_session_id = self.repository.ensure_session(
            account_id, session_id.strip() if session_id else None, member_id=member_id
        )
        session_member_access(
            self.repository, self.members, account_id, actual_session_id
        )
        extension = ALLOWED_MIME_TYPES[mime_type]
        try:
            resource = self.repository.create_uploaded_resource(
                account_id=account_id,
                session_id=actual_session_id,
                original_filename=upload["original_filename"],
                fallback_extension=extension,
                mime_type=mime_type,
                content=content,
            )
        except Exception:
            # Drain any exact-path job created by a normal write failure.
            # A ready-transition failure intentionally leaves a recoverable
            # writing record and therefore creates no cleanup job.
            self.drain_attachment_cleanup(account_id)
            raise

        return {
            "session_id": actual_session_id,
            "member_id": member_id,
            "resource": {"member_id": member_id, **resource},
        }

    def trusted_attachment_resource(
        self,
        account_id: str,
        session_id: str,
        resource_id: str,
    ) -> dict[str, Any] | None:
        row = self.repository.resource_row(account_id, session_id, resource_id)
        if (
            row is None
            or row["storage_status"] != "ready"
            or row["lifecycle_status"] in {"expired", "deleted"}
        ):
            return None
        path = self.repository.attachment_cleanup_path(
            account_id, str(row["relative_path"])
        )
        if path is None or not path.is_file():
            return None
        return {
            "resource_id": resource_id,
            "path": str(path.resolve()),
            "original_filename": str(row["original_filename"]),
            "mime_type": str(row["mime_type"]),
            "sha256": str(row["sha256"]),
        }

    def read_attachment_content(
        self, account_id: str, session_id: str, resource_id: str
    ) -> AttachmentContent:
        """Read one authorized conversation attachment and verify its content."""

        resource = self.trusted_attachment_resource(account_id, session_id, resource_id)
        if resource is None:
            raise PermissionError("附件不可用或不属于当前会话。")
        try:
            content = Path(resource["path"]).read_bytes()
        except FileNotFoundError as exc:
            raise PermissionError("附件已经不可用。") from exc
        if hashlib.sha256(content).hexdigest() != resource["sha256"]:
            raise ValueError("附件完整性校验失败。")
        return AttachmentContent(
            resource_id=resource_id,
            original_filename=resource["original_filename"],
            mime_type=resource["mime_type"],
            content_bytes=content,
        )

    def context_resource_download(
        self,
        account_id: str,
        session_id: str,
        resource_id: str,
    ) -> tuple[Path, str, str]:
        """Resolve one account_id-scoped conversation attachment for user preview."""

        self.maintain_attachments(account_id)
        row = self.repository.resource_row(account_id, session_id, resource_id)
        if (
            row is None
            or row["storage_status"] != "ready"
            or row["lifecycle_status"] in {"expired", "deleted"}
        ):
            raise_error("missing", "RESOURCE_NOT_FOUND", "附件不存在或已过期。")
        resource = self.trusted_attachment_resource(
            account_id,
            session_id,
            resource_id,
        )
        if resource is None:
            raise_error("missing", "RESOURCE_NOT_FOUND", "附件不存在或已过期。")
        return (
            Path(str(resource["path"])),
            str(resource["original_filename"]),
            str(resource["mime_type"]),
        )

    def visible_attachments_for_messages(
        self,
        account_id: str,
        session_id: str,
        messages_by_id: dict[str, dict[str, Any]],
        visible_message_ids: set[str],
    ) -> dict[str, dict[str, Any]]:
        """Trusted metadata for every branch-visible file, including past turns."""

        visible_attachments: dict[str, dict[str, Any]] = {}
        for message_id in sorted(visible_message_ids):
            visible_message = messages_by_id.get(message_id)
            if not isinstance(visible_message, dict):
                continue
            if visible_message.get("role") != "user":
                continue
            for resource in visible_message.get("context_resources", []):
                if not isinstance(resource, dict):
                    continue
                if resource.get("resource_type") != "file":
                    continue
                resource_id = str(resource.get("resource_id") or "")
                if not resource_id or resource_id in visible_attachments:
                    continue
                trusted_resource = self.trusted_attachment_resource(
                    account_id, session_id, resource_id
                )
                if trusted_resource is None:
                    continue
                visible_attachments[resource_id] = trusted_resource
        return visible_attachments

    def validate_model(
        self, account_id: str, model_id: Optional[str], thinking_mode: str
    ):
        chat_model = self.model_catalog.default_model_for_account(account_id, "chat")
        if not chat_model:
            raise_error(
                "invalid_structure",
                "MODEL_NOT_CONFIGURED",
                "请先在账号设置中配置模型并添加默认聊天模型。",
            )
        if model_id:
            model = self.model_catalog.model_for_account(account_id, model_id)
            if not model:
                raise_error("missing", "MODEL_NOT_FOUND", "模型不存在或未添加。")
            if model["model_id"] != chat_model["model_id"]:
                raise_error(
                    "invalid_input", "INVALID_REQUEST", "首页只能使用默认聊天模型。"
                )
        else:
            model = chat_model
        if not model:
            raise_error(
                "invalid_structure",
                "MODEL_NOT_CONFIGURED",
                "请先在账号设置中配置模型并添加默认模型。",
            )
        if thinking_mode not in model.get("thinking_modes", []):
            raise_error(
                "invalid_input", "INVALID_REQUEST", "当前模型不支持所选推理强度。"
            )
        return model

    def attachment_capabilities(self, account_id: str, model_id: str | None = None):
        model = (
            self.model_catalog.model_for_account(account_id, model_id)
            if model_id
            else self.model_catalog.default_model_for_account(account_id, "chat")
        )
        if model_id and not model:
            raise_error("missing", "MODEL_NOT_FOUND", "模型不存在或未添加。")
        if not model:
            return {"model_id": None, "file_mime_types": []}
        vision = self.model_catalog.default_model_for_account(
            account_id, "vision_parse"
        )
        candidates = (
            set(model.get("file_mime_types", []))
            | set((vision or {}).get("file_mime_types", []))
            | MODEL_RENDERABLE_ATTACHMENT_MIME_TYPES
        )
        accepted = []
        for mime_type in sorted(candidates & ALLOWED_MIME_TYPES.keys()):
            try:
                self.validate_attachment_supported_for_conversation(
                    account_id, model, mime_type
                )
            except SerenitaError as exc:
                if exc.detail.get("code") not in {
                    "MODEL_ATTACHMENT_UNSUPPORTED",
                    "MODEL_FILE_UNSUPPORTED",
                }:
                    raise
            else:
                accepted.append(mime_type)
        return {"model_id": model["model_id"], "file_mime_types": accepted}

    def validate_attachment_supported_for_conversation(
        self,
        account_id: str,
        model: dict[str, Any],
        mime_type: str,
    ) -> None:
        if self.model_can_forward_attachment(model, mime_type):
            return
        if self.can_render_attachment_for_model(account_id, model, mime_type):
            return
        vision_model = self.vision_parse_model_for_attachment(account_id, mime_type)
        if vision_model:
            return
        if mime_type in model.get("file_mime_types", []):
            raise_error(
                "invalid_structure",
                "MODEL_ATTACHMENT_UNSUPPORTED",
                "当前模型服务不能原生上传该附件类型。",
            )
        raise_error(
            "invalid_structure",
            "MODEL_FILE_UNSUPPORTED",
            "当前聊天模型不支持该文件格式，且未配置可用的视觉解析模型。",
        )

    def model_can_forward_attachment(
        self, model: dict[str, Any], mime_type: str
    ) -> bool:
        return mime_type in model.get(
            "file_mime_types", []
        ) and self.model_catalog.provider_supports_native_attachment(model, mime_type)

    def vision_parse_model_for_attachment(
        self, account_id: str, mime_type: str
    ) -> Optional[dict[str, Any]]:
        model = self.model_catalog.default_model_for_account(account_id, "vision_parse")
        if not model or mime_type not in model.get("file_mime_types", []):
            return None
        if not self.model_catalog.provider_supports_native_attachment(model, mime_type):
            raise_error(
                "invalid_structure",
                "MODEL_ATTACHMENT_UNSUPPORTED",
                "视觉解析模型服务不能原生上传该附件类型。",
            )
        return model

    def can_render_attachment_for_model(
        self,
        account_id: str,
        chat_model: dict[str, Any],
        mime_type: str,
    ) -> bool:
        if mime_type not in MODEL_RENDERABLE_ATTACHMENT_MIME_TYPES:
            return False
        if self.model_can_forward_attachment(chat_model, mime_type):
            return True
        vision_model = self.model_catalog.default_model_for_account(
            account_id, "vision_parse"
        )
        required_mime = "image/jpeg" if mime_type == "application/pdf" else mime_type
        return bool(
            vision_model
            and self.model_can_forward_attachment(vision_model, required_mime)
        )

    def validate_context_resources(
        self,
        account_id: str,
        session_id: str,
        references: list[dict[str, Any]],
        model: dict[str, Any],
    ) -> list[dict[str, Any]]:
        normalized = []
        seen_plugin_resources: set[tuple[str, str]] = set()
        file_count = sum(
            1
            for reference in references
            if self.ref_value(reference, "resource_type") == "file"
        )
        if file_count > MAX_FILES_PER_TURN:
            raise_error("resource_limit", "TOO_MANY_FILES", "单次最多发送 20 个文件。")
        total_file_bytes = 0
        records_by_id = {
            str(record.get("record_id") or ""): record
            for record in self.events.view(account_id, session_id).records
            if record.get("record_id")
        }
        member_access = session_member_access(
            self.repository, self.members, account_id, session_id
        )
        member_id = member_access.member_id if member_access is not None else None
        for reference in references:
            if self.ref_value(reference, "member_id") not in {None, "", member_id}:
                member_error("MEMBER_MISMATCH", "不能引用其他成员的资源。", "conflict")
            resource_type = self.ref_value(reference, "resource_type")
            resource_id = self.ref_value(reference, "resource_id")
            if resource_type == "file":
                row = self.repository.resource_row(account_id, session_id, resource_id)
                if not row:
                    raise_error("missing", "NOT_FOUND", "上下文资源不存在。")
                if row["storage_status"] != "ready":
                    raise_error(
                        "conflict", "RESOURCE_NOT_READY", "上下文资源尚未完成写入。"
                    )
                if row["lifecycle_status"] in {"expired", "deleted"}:
                    raise_error(
                        "invalid_input", "INVALID_REQUEST", "上下文资源已过期。"
                    )
                if (
                    row["expires_at"]
                    and parse_local_datetime(row["expires_at"]) <= local_now()
                ):
                    self.repository.expire_resource(
                        account_id, session_id, row["resource_id"]
                    )
                    self.drain_attachment_cleanup(account_id)
                    raise_error(
                        "invalid_input", "INVALID_REQUEST", "上下文资源已过期。"
                    )
                self.validate_attachment_supported_for_conversation(
                    account_id, model, row["mime_type"]
                )
                if int(row["size_bytes"]) > MAX_FILE_BYTES:
                    raise_error(
                        "resource_limit", "FILE_TOO_LARGE", "单文件大小不能超过 20MB。"
                    )
                total_file_bytes += int(row["size_bytes"])
                if total_file_bytes > MAX_TOTAL_FILE_BYTES:
                    raise_error(
                        "resource_limit",
                        "FILES_TOO_LARGE",
                        "单次发送文件总大小不能超过 100MB。",
                    )
                normalized.append(
                    {
                        "resource_type": "file",
                        "resource_id": row["resource_id"],
                        "original_filename": row["original_filename"],
                        "mime_type": row["mime_type"],
                        "size_bytes": row["size_bytes"],
                    }
                )
            elif resource_type == "record_annotation":
                source_record_id = self.ref_value(reference, "source_record_id")
                source_record = records_by_id.get(source_record_id)
                if not source_record:
                    raise_error("missing", "NOT_FOUND", "注释来源记录不存在。")
                if _annotation_source_values(source_record) is None:
                    raise_error(
                        "invalid_input",
                        "INVALID_REQUEST",
                        "只有用户输入和助手回答可以添加为注释。",
                    )
                annotation_text = self.ref_value(reference, "annotation_text") or ""
                if not _annotation_text_belongs_to_record(
                    annotation_text, source_record
                ):
                    raise_error(
                        "invalid_input", "INVALID_REQUEST", "注释文本不属于来源记录。"
                    )
                normalized.append(
                    {
                        "resource_type": "record_annotation",
                        "resource_id": resource_id or self.repository.new_id(),
                        "source_record_id": source_record_id,
                        "annotation_text": annotation_text,
                    }
                )
            else:
                resource_key = (str(resource_type), str(resource_id))
                if resource_key in seen_plugin_resources:
                    continue
                try:
                    from backend.app.plugins import (
                        PluginRuntimeContext,
                        resolve_plugin_resource_refs,
                    )

                    resolved = resolve_plugin_resource_refs(
                        runtime_context=PluginRuntimeContext(
                            service_factory=lambda plugin_id: (
                                self.services.plugin_service(
                                    account_id, member_id, plugin_id
                                )
                            ),
                            account_id=account_id,
                            member_id=member_id,
                            event_recorder=lambda _event: None,
                        ),
                        resource_refs=[
                            {
                                "resource_type": resource_type,
                                "resource_id": resource_id,
                                "member_id": reference.get("member_id"),
                            }
                        ],
                    )
                    if not resolved:
                        raise LookupError(resource_id)
                    plugin_resource = resolved[0]
                except Exception as exc:
                    if isinstance(exc, SerenitaError):
                        raise
                    raise_error(
                        "missing", "RESOURCE_NOT_FOUND", "插件资源不存在或无权访问。"
                    )
                normalized.append(dict(plugin_resource))
                seen_plugin_resources.add(resource_key)
        # A model may inspect a PDF through images rendered by the backend even
        # when the provider cannot accept PDF as a native chat attachment.
        direct_response_resources = [
            resource
            for resource in normalized
            if not (
                resource.get("resource_type") == "file"
                and resource.get("mime_type") == "application/pdf"
                and self.can_render_attachment_for_model(
                    account_id, model, "application/pdf"
                )
            )
        ]
        self.response_model_for_context_resources(
            account_id, session_id, direct_response_resources, model
        )
        return normalized

    def maintain_attachments(self, account_id: str) -> None:
        """Recover writes, expire drafts, and drain account-scoped cleanup work."""
        self.repository.recover_writing_resources(account_id, limit=100)
        self.repository.expire_due_resources(account_id, limit=100)
        self.drain_attachment_cleanup(account_id)

    def drain_attachment_cleanup(self, account_id: str, *, limit: int = 32) -> None:
        for job in self.repository.attachment_cleanup_jobs(account_id, limit=limit):
            cleanup_id = job["cleanup_id"]
            path = self.repository.attachment_cleanup_path(
                account_id, job["relative_path"]
            )
            if path is None:
                # Invalid persisted paths are discarded without touching disk.
                self.repository.complete_attachment_cleanup(account_id, cleanup_id)
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                self.repository.record_attachment_cleanup_attempt(
                    account_id, cleanup_id
                )
                continue
            self.repository.complete_attachment_cleanup(account_id, cleanup_id)
            self.repository.remove_empty_attachment_dirs(account_id, path.parent)

    @staticmethod
    def model_request_from_messages(
        messages: list[dict[str, Any]],
        *,
        purpose: str,
        parent_tool_call_id: str | None = None,
    ) -> ModelRequest:
        system_parts = [
            str(message.get("content") or "")
            for message in messages
            if message.get("role") == "system"
        ]
        return ModelRequest.build(
            system="\n\n".join(item for item in system_parts if item),
            messages=[
                dict(message) for message in messages if message.get("role") != "system"
            ],
            tools=(),
            tool_choice=None,
            model_config={
                "purpose": purpose,
                **(
                    {"parent_tool_call_id": parent_tool_call_id}
                    if parent_tool_call_id
                    else {}
                ),
            },
        )

    def response_model_for_context_resources(
        self,
        account_id: str,
        session_id: str,
        context_resources: list[dict[str, Any]],
        chat_model: dict[str, Any],
    ) -> dict[str, Any]:
        file_mime_types = self.context_file_mime_types(
            account_id, session_id, context_resources
        )
        if not file_mime_types:
            return chat_model
        if all(
            self.model_can_forward_attachment(chat_model, mime_type)
            for mime_type in file_mime_types
        ):
            return chat_model
        vision_model = self.model_catalog.default_model_for_account(
            account_id, "vision_parse"
        )
        if vision_model and all(
            self.model_can_forward_attachment(vision_model, mime_type)
            for mime_type in file_mime_types
        ):
            return vision_model
        raise_error(
            "invalid_structure",
            "MODEL_FILE_UNSUPPORTED",
            "当前聊天模型不支持本轮附件，且未配置可直接回答这些附件的视觉解析模型。",
        )

    def model_and_attachment_parts(
        self,
        account_id: str,
        session_id: str,
        context_resources: list[dict[str, Any]],
        chat_model: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        file_rows: list[tuple[dict[str, Any], Any]] = []
        for resource in context_resources:
            if resource.get("resource_type") != "file":
                continue
            row = self.repository.resource_row(
                account_id, session_id, str(resource.get("resource_id") or "")
            )
            if row is None:
                continue
            file_rows.append((resource, row))
        if not file_rows:
            return chat_model, []

        candidate_models = [chat_model]
        vision_model = self.model_catalog.default_model_for_account(
            account_id, "vision_parse"
        )
        if vision_model and vision_model.get("model_id") != chat_model.get("model_id"):
            candidate_models.append(vision_model)
        selected_model = next(
            (
                model
                for model in candidate_models
                if all(
                    self.model_can_forward_attachment(model, str(row["mime_type"]))
                    or (
                        str(row["mime_type"]) == "application/pdf"
                        and self.model_can_forward_attachment(model, "image/jpeg")
                    )
                    for _resource, row in file_rows
                )
            ),
            None,
        )
        if selected_model is None:
            raise_error(
                "invalid_structure",
                "MODEL_FILE_UNSUPPORTED",
                "当前聊天模型和视觉解析模型都不能读取本聊天中的附件。",
            )

        parts: list[dict[str, Any]] = []
        for resource, row in file_rows:
            resource_id = str(resource.get("resource_id") or "")
            mime_type = str(row["mime_type"])
            if mime_type == "application/pdf" and not self.model_can_forward_attachment(
                selected_model, mime_type
            ):
                path = self.repository.timeline_abs_path(
                    account_id, str(row["relative_path"])
                )
                from backend.app.application.conversations.attachment_rendering import (
                    model_file_parts,
                )

                rendered = model_file_parts(
                    path,
                    mime_type,
                    deadline=time.monotonic() + 60,
                )
                for page in rendered:
                    parts.append(
                        {
                            **dict(page),
                            "source_resource_id": resource_id,
                        }
                    )
                continue
            part = self.attachment_part(account_id, session_id, resource)
            part["source_resource_id"] = resource_id
            parts.append(part)
        return selected_model, parts

    def context_file_mime_types(
        self,
        account_id: str,
        session_id: str,
        context_resources: list[dict[str, Any]],
    ) -> list[str]:
        mime_types = []
        for resource in context_resources:
            if resource.get("resource_type") != "file":
                continue
            row = self.repository.resource_row(
                account_id, session_id, resource["resource_id"]
            )
            if row:
                mime_types.append(row["mime_type"])
        return mime_types

    def default_thinking_mode(self, model: dict[str, Any]) -> str:
        thinking_modes = model.get("thinking_modes", [])
        if "default" in thinking_modes:
            return "default"
        return thinking_modes[0] if thinking_modes else "default"

    def thinking_mode_for_model(
        self, model: dict[str, Any], requested_mode: str
    ) -> str:
        thinking_modes = model.get("thinking_modes", [])
        if requested_mode == "off":
            profiles = model.get("capability_profiles")
            non_thinking = (
                profiles.get("non_thinking") if isinstance(profiles, dict) else None
            )
            if (
                isinstance(non_thinking, dict)
                and non_thinking.get("availability") != "unavailable"
            ):
                return "off"
        if requested_mode in thinking_modes:
            return requested_mode
        return self.default_thinking_mode(model)

    def effective_thinking_mode_for_turn(
        self,
        model: dict[str, Any],
        requested_mode: str,
        *,
        has_tools: bool,
        attachment_parts: list[dict[str, Any]],
    ) -> tuple[str, list[str]]:
        profiles = model.get("capability_profiles")
        if not isinstance(profiles, dict):
            return requested_mode, []

        requested_state = self.thinking_state_for_mode(
            requested_mode,
            profiles,
        )
        alternate_state = (
            "thinking" if requested_state == "non_thinking" else "non_thinking"
        )
        required_mime_types = {
            str(part.get("mime_type") or "")
            for part in attachment_parts
            if isinstance(part, dict) and str(part.get("mime_type") or "")
        }
        reasons = self.unsupported_mode_requirements(
            profiles.get(requested_state),
            has_tools=has_tools,
            required_mime_types=required_mime_types,
        )
        if not reasons:
            return requested_mode, []
        if self.unsupported_mode_requirements(
            profiles.get(alternate_state),
            has_tools=has_tools,
            required_mime_types=required_mime_types,
        ):
            return requested_mode, []
        if alternate_state == "non_thinking":
            return "off", reasons
        thinking_modes = [
            str(mode)
            for mode in model.get("thinking_modes", [])
            if str(mode) not in {"", "off"}
        ]
        if profiles.get("default_state") == "thinking" and "default" in thinking_modes:
            return "default", reasons
        explicit_mode = next(
            (mode for mode in thinking_modes if mode != "default"),
            None,
        )
        return (explicit_mode, reasons) if explicit_mode else (requested_mode, [])

    @staticmethod
    def thinking_state_for_mode(mode: str, profiles: dict[str, Any]) -> str:
        if mode == "off":
            return "non_thinking"
        if mode == "default":
            state = str(profiles.get("default_state") or "unknown")
            return state if state in {"thinking", "non_thinking"} else "non_thinking"
        return "thinking"

    @staticmethod
    def unsupported_mode_requirements(
        profile: Any,
        *,
        has_tools: bool,
        required_mime_types: set[str],
    ) -> list[str]:
        if (
            not isinstance(profile, dict)
            or profile.get("availability") == "unavailable"
        ):
            return ["text"]
        reasons: list[str] = []
        if not bool(profile.get("supports_text")):
            reasons.append("text")
        if has_tools and not bool(profile.get("supports_tool_calling")):
            reasons.append("tool_calling")
        supported_types = {
            str(mime_type)
            for mime_type in profile.get("file_mime_types", [])
            if isinstance(mime_type, str)
        }
        for mime_type in sorted(required_mime_types - supported_types):
            if mime_type.startswith("image/"):
                reason = "image_input"
            elif mime_type.startswith("audio/"):
                reason = "audio_input"
            elif mime_type.startswith("video/"):
                reason = "video_input"
            else:
                reason = "file_input"
            if reason not in reasons:
                reasons.append(reason)
        return reasons

    def attachment_part(
        self, account_id: str, session_id: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        row = self.repository.resource_row(
            account_id, session_id, resource["resource_id"]
        )
        if not row:
            raise ProviderChatCompletionError("上下文资源不存在。")
        path = self.repository.timeline_abs_path(account_id, row["relative_path"])
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ProviderChatCompletionError("读取附件失败。") from exc
        mime_type = str(row["mime_type"])
        if mime_type.startswith("image/"):
            part_type = "image"
        elif mime_type.startswith("audio/"):
            part_type = "audio"
        elif mime_type.startswith("video/"):
            part_type = "video"
        else:
            part_type = "file"
        return {
            "type": part_type,
            "mime_type": mime_type,
            "name": str(row["original_filename"]),
            "data_base64": base64.b64encode(content).decode("ascii"),
        }

    def ref_value(self, reference: Any, key: str):
        if isinstance(reference, dict):
            return reference.get(key)
        return getattr(reference, key)

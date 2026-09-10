from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from backend.app.core.errors import raise_error
from backend.app.application.report_file_validation import validate_report_signature
from backend.app.application.report_file_cleanup import drain_report_file_cleanup
from backend.app.core.time import local_now


MAX_FILE_BYTES = 20 * 1024 * 1024


ALLOWED_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".heic": "image/heic",
    ".pdf": "application/pdf",
}


ALLOWED_MIME_TYPES = set(ALLOWED_EXTENSIONS.values()) | {"image/jpg", "image/heif"}


MIME_TYPE_ALIASES = {"image/jpg": "image/jpeg", "image/heif": "image/heic"}


class ReportSourceStore:
    """Files and source metadata, called inside the member authorization boundary."""

    def __init__(self, repository):
        self.repository = repository
        self.paths = repository.paths
        self.account_id = repository.account_id

    def validate_parsed_source_reference(
        self,
        member_id: str,
        reference: Any,
        *,
        source_text: str,
        session_id: str,
        source_message_id: str,
        visible_attachments: dict[str, dict[str, Any]],
        authorized_report_sources: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        if not isinstance(reference, dict):
            raise ValueError("医疗报告来源引用必须是对象。")
        source_type = str(reference.get("source_type") or "")
        if source_type == "conversation_text":
            raw_text = str(source_text or "")
            message_id = str(source_message_id or "").strip()
            if not raw_text.strip() or not message_id:
                raise ValueError("当前用户消息没有可绑定的医疗报告文本。")
            digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            return (
                {
                    "source_type": source_type,
                    "session_id": str(session_id or ""),
                    "message_id": message_id,
                    "source_text": raw_text,
                    "mime_type": "text/plain",
                    "sha256": digest,
                },
                (source_type, str(session_id or ""), message_id, digest),
            )
        if source_type == "conversation_attachment":
            resource_id = str(reference.get("resource_id") or "")
            trusted = visible_attachments.get(resource_id)
            if not resource_id or not isinstance(trusted, dict):
                raise PermissionError("附件来源不属于当前分支可见消息的附件资源。")
            source_path = Path(str(trusted.get("path") or ""))
            if not source_path.is_file():
                raise FileNotFoundError("医疗报告附件已经不可用。")
            content = source_path.read_bytes()
            digest = str(trusted.get("sha256") or "")
            if not digest or hashlib.sha256(content).hexdigest() != digest:
                raise ValueError("医疗报告附件完整性校验失败。")
            return (
                {
                    "source_type": source_type,
                    "resource_id": resource_id,
                    "path": str(source_path),
                    "original_filename": str(
                        trusted.get("original_filename") or source_path.name
                    ),
                    "mime_type": str(trusted.get("mime_type") or ""),
                    "sha256": digest,
                },
                (source_type, resource_id),
            )
        if source_type == "report_source":
            read_call_id = str(reference.get("read_call_id") or "")
            report_id = str(reference.get("report_id") or "")
            resource_id = str(reference.get("resource_id") or "")
            key = "\0".join((read_call_id, report_id, resource_id))
            observed = authorized_report_sources.get(key)
            if not all((read_call_id, report_id, resource_id)) or not isinstance(
                observed, dict
            ):
                raise PermissionError(
                    '原件来源必须引用当前可见分支中 read_report_information(fields=["sources"]) 观测。'
                )
            stored = self.repository.source_for_report(
                member_id, report_id, resource_id
            )
            if stored is None:
                raise PermissionError("引用的医疗报告原件不属于当前账号或目标医疗报告。")
            source_path = self.source_path(member_id, stored)
            digest = str(stored.get("sha256") or "")
            if not source_path.is_file():
                raise FileNotFoundError("医疗报告原件已经不可用。")
            if (
                not digest
                or hashlib.sha256(source_path.read_bytes()).hexdigest() != digest
            ):
                raise ValueError("医疗报告原件完整性校验失败。")
            return (
                {
                    "source_type": source_type,
                    "read_call_id": read_call_id,
                    "report_id": report_id,
                    "resource_id": resource_id,
                    "mime_type": str(stored.get("mime_type") or ""),
                    "sha256": str(stored.get("sha256") or ""),
                },
                (source_type, report_id, resource_id),
            )
        raise ValueError("医疗报告来源类型无效。")

    def ensure_parsed_sources(
        self,
        member_id: str,
        parsed_sources: list[dict[str, Any]],
        *,
        session_id: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if not parsed_sources:
            raise ValueError("每份解析医疗报告必须绑定至少一个来源。")
        sources: list[dict[str, Any]] = []
        created_resource_ids: list[str] = []
        seen_resource_ids: set[str] = set()
        try:
            for parsed_source in parsed_sources:
                source, created = self.ensure_parsed_source(
                    member_id, parsed_source, session_id=session_id
                )
                resource_id = str(source["resource_id"])
                if resource_id in seen_resource_ids:
                    continue
                seen_resource_ids.add(resource_id)
                sources.append(source)
                if created:
                    created_resource_ids.append(resource_id)
        except Exception:
            self.cleanup_new_unlinked_sources(member_id, created_resource_ids)
            raise
        return sources, created_resource_ids

    def cleanup_new_unlinked_sources(
        self, member_id: str, resource_ids: list[str]
    ) -> None:
        for resource_id in resource_ids:
            self.repository.delete_source_if_unlinked(member_id, resource_id)
        if resource_ids:
            self.drain_file_cleanup(member_id)

    def ensure_parsed_source(
        self,
        member_id: str,
        parsed_source: dict[str, Any],
        *,
        session_id: str,
    ) -> tuple[dict[str, Any], bool]:
        source_type = str(parsed_source.get("source_type") or "")
        expected_sha = str(parsed_source.get("sha256") or "")
        if source_type == "conversation_attachment":
            conversation_resource_id = str(parsed_source.get("resource_id") or "")
            source_path = Path(str(parsed_source.get("path") or ""))
            if not conversation_resource_id or not source_path.is_file():
                raise_error(
                    "missing", "REPORT_SOURCE_NOT_FOUND", "原始医疗报告附件已经不可用。"
                )
            content = source_path.read_bytes()
            if not expected_sha or hashlib.sha256(content).hexdigest() != expected_sha:
                raise_error(
                    "conflict", "REPORT_SOURCE_CHANGED", "医疗报告附件完整性校验失败。"
                )
            resource_seed = "\0".join((member_id, session_id, conversation_resource_id))
            report_resource_id = (
                "RESOURCE-"
                + hashlib.sha256(resource_seed.encode("utf-8")).hexdigest()[:32].upper()
            )
            existing = self.repository.source_file(member_id, report_resource_id)
            if existing is not None:
                if str(existing.get("sha256") or "") != expected_sha:
                    raise_error(
                        "conflict",
                        "REPORT_SOURCE_CHANGED",
                        "已登记来源与解析附件不一致。",
                    )
                return existing, False
            normalized = self.normalize_upload(
                {
                    "original_filename": str(
                        parsed_source.get("original_filename") or source_path.name
                    ),
                    "mime_type": str(parsed_source.get("mime_type") or ""),
                    "content": content,
                }
            )
            return self._persist_upload(
                member_id, normalized, resource_id=report_resource_id
            )
        if source_type == "report_source":
            report_id = str(parsed_source.get("report_id") or "")
            resource_id = str(parsed_source.get("resource_id") or "")
            existing = self.repository.source_for_report(
                member_id, report_id, resource_id
            )
            if existing is None:
                raise PermissionError("医疗报告原件来源已经不可用或不属于当前账号。")
            if expected_sha and str(existing.get("sha256") or "") != expected_sha:
                raise_error(
                    "conflict", "REPORT_SOURCE_CHANGED", "医疗报告原件完整性校验失败。"
                )
            return existing, False
        if source_type != "conversation_text":
            raise ValueError("医疗报告来源类型无效。")
        if str(parsed_source.get("session_id") or "") != str(session_id or ""):
            raise PermissionError("医疗报告文本来源不属于当前会话。")
        source_text = str(parsed_source.get("source_text") or "")
        content = source_text.encode("utf-8")
        if (
            not source_text.strip()
            or hashlib.sha256(content).hexdigest() != expected_sha
        ):
            raise_error(
                "conflict", "REPORT_TEXT_SOURCE_CHANGED", "医疗报告文本来源完整性校验失败。"
            )
        message_id = str(parsed_source.get("message_id") or "")
        source_seed = "\0".join((member_id, session_id, message_id, expected_sha))
        report_resource_id = (
            "TEXT-"
            + hashlib.sha256(source_seed.encode("utf-8")).hexdigest()[:24].upper()
        )
        existing = self.repository.source_file(member_id, report_resource_id)
        if existing is not None:
            if str(existing.get("sha256") or "") != expected_sha:
                raise_error(
                    "conflict", "REPORT_TEXT_SOURCE_CHANGED", "已登记文本来源不一致。"
                )
            return existing, False
        return self.repository.persist_source_file(
            member_id, resource_id=report_resource_id, extension="txt",
            mime_type="text/plain", content=content, source_kind="unknown",
        )

    def source_path(self, member_id: str, source: dict[str, Any]) -> Path:
        account_root = self.paths.account_root(self.account_id).resolve()
        attachments_root = self.paths.report_attachments_dir(self.account_id).resolve()
        resolved_path = (account_root / source["relative_path"]).resolve()
        if not resolved_path.is_relative_to(attachments_root):
            raise ValueError("不安全的医疗报告源文件路径")
        return resolved_path

    def drain_file_cleanup(self, member_id: str, *, limit: int = 8) -> None:
        # Include committed jobs for deleted members belonging to this owner.
        drain_report_file_cleanup(self.repository, limit=limit)

    def normalize_upload(self, upload: dict[str, Any]) -> dict[str, Any]:
        filename = (
            str(upload.get("original_filename") or "")
            .replace("\\", "/")
            .rsplit("/", 1)[-1]
        )
        extension = Path(filename).suffix.lower()
        content = upload.get("content")
        if not filename or extension not in ALLOWED_EXTENSIONS:
            raise_error(
                "unsupported",
                "FILE_FORMAT_UNSUPPORTED",
                "仅支持 JPG、PNG、HEIC 和 PDF 医疗报告文件。",
            )
        if not isinstance(content, (bytes, bytearray)):
            raise_error("invalid_input", "INVALID_REQUEST", "上传文件内容无效。")
        if len(content) > MAX_FILE_BYTES:
            raise_error(
                "resource_limit", "FILE_TOO_LARGE", "单个医疗报告文件不能超过 20MB。"
            )
        if not content:
            raise_error("invalid_input", "INVALID_REQUEST", "不能上传空文件。")
        declared = str(upload.get("mime_type") or "").lower().split(";", 1)[0]
        expected = ALLOWED_EXTENSIONS[extension]
        if (
            declared
            and declared not in ALLOWED_MIME_TYPES
            and declared != "application/octet-stream"
        ):
            raise_error(
                "unsupported", "FILE_FORMAT_UNSUPPORTED", "文件 MIME 类型不受支持。"
            )
        try:
            validate_report_signature(bytes(content), expected)
        except ValueError as exc:
            raise_error("unsupported", "FILE_FORMAT_UNSUPPORTED", str(exc))
        normalized_mime = expected
        return {
            "original_filename": filename,
            "extension": extension,
            "mime_type": normalized_mime,
            "content": bytes(content),
        }

    def persist_normalized_upload(
        self,
        member_id: str,
        upload: dict[str, Any],
        *,
        resource_id: str,
    ) -> dict[str, Any]:
        source, _created = self._persist_upload(member_id, upload, resource_id=resource_id)
        return source

    def _persist_upload(self, member_id, upload, *, resource_id):
        return self.repository.persist_source_file(
            member_id, resource_id=resource_id, extension=upload["extension"].lstrip("."),
            mime_type=upload["mime_type"], content=upload["content"],
            source_kind="pdf" if upload["mime_type"] == "application/pdf" else "unknown",
        )

    def new_id(self, prefix: str) -> str:
        return (
            f"{prefix}-{local_now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:12].upper()}"
        )

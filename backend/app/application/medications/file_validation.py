"""Validate medication originals before persistence."""

from backend.app.core.errors import raise_error
from backend.app.application.reports.file_validation import validate_report_signature

from backend.app.domain.medication_files import FILE_TYPES
from backend.app.core.business_operation import validate_operation_id


def validate_medication_file(mime, content, purpose, operation_id):
    if mime == "image/heif":
        mime = "image/heic"
    if mime not in FILE_TYPES or not content or len(content) > 20 * 1024 * 1024:
        raise_error(
            "invalid_input",
            "MEDICATION_FILE_INVALID",
            "支持 JPEG、PNG、HEIC、PDF、纯文本，每份文件须非空且不超过 20 MB。",
        )
    if purpose not in ("package", "label", "leaflet"):
        raise_error("invalid_input", "MEDICATION_FILE_INVALID", "文件用途无效。")
    try:
        validate_operation_id(operation_id)
        if mime == "text/plain":
            content.decode("utf-8")
        else:
            validate_report_signature(content, mime)
    except ValueError as exc:
        raise_error("invalid_input", "MEDICATION_FILE_INVALID", str(exc))
    return mime

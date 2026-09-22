from typing import Any
from pathlib import Path
from copy import deepcopy
from backend.app.schemas.report import REPORT_TYPED_FIELDS


def model_report_evidence(detail: dict[str, Any]) -> dict[str, Any]:
    """Return only the evidence fields the Agent needs to read a report.

    Nested typed payloads are projected again at this boundary so the
    model does not see storage foreign keys that repeat their parent
    report object.
    """

    typed_fields = REPORT_TYPED_FIELDS
    projected = {
        key: detail.get(key)
        for key in (
            "report_id",
            "report_type",
            "report_name",
            "report_time",
            "institution_name",
        )
    }
    projected["lab_test_results"] = [
        {
            key: item.get(key)
            for key in (
                "item_id",
                "item_name_zh",
                "result_text",
                "reference_text",
                "flag_text",
            )
        }
        for item in detail.get("lab_test_results") or []
        if isinstance(item, dict)
    ]
    for field, keys in typed_fields.items():
        payload = detail.get(field)
        if isinstance(payload, dict):
            projected[field] = {key: payload.get(key) for key in keys}
        else:
            projected[field] = None
    return projected


def safe_detail(detail: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(detail)
    for source in result.get("sources", []):
        source["filename"] = Path(source.pop("relative_path")).name
        is_conversation_text = is_conversation_text_source(source)
        source["source_type"] = (
            "conversation_text" if is_conversation_text else "uploaded_file"
        )
    for item in result.get("lab_test_results", []):
        item.pop("member_id", None)
    for typed_key in (
        "examination_report",
        "pathology_report",
        "surgery_report",
        "outpatient_report",
        "emergency_report",
        "other_report",
    ):
        if isinstance(result.get(typed_key), dict):
            result[typed_key].pop("member_id", None)
    return result


def is_conversation_text_source(source: dict[str, Any]) -> bool:
    """Distinguish message provenance from an uploaded report original."""

    return str(source.get("resource_id") or "").startswith("TEXT-")

from datetime import date
from typing import Any
from backend.app.schemas.report import ParsedReport
from backend.app.storage.report_database import REPORT_DATABASE_SCHEMA
from backend.app.core.time import local_iso


def normalize_analysis_content(raw: str | bytes) -> str:
    """Normalize report-analysis text without enforcing a writing format."""
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("解读结果不是有效 UTF-8 文本。") from exc
    if not isinstance(raw, str):
        raise ValueError("解读结果必须是文本。")
    content = raw.strip()
    if not content:
        raise ValueError("解读结果不能为空。")
    return content


def normalize_lab_category(category_name: str) -> str:
    """Normalize category text without deciding its language or medical meaning."""
    normalized = category_name.strip()
    if not normalized:
        raise ValueError("分类名称不能为空白。")
    if len(normalized) > 64:
        raise ValueError("分类名称不能超过 64 个字符。")
    return normalized


def validate_final_parsed_report(
    raw_report: Any,
) -> dict[str, Any]:
    parsed_model = ParsedReport.model_validate(raw_report)
    parsed = parsed_model.model_dump(mode="json")
    parsed["report_time"] = normalize_report_time(parsed["report_time"])
    if parsed["report_type"] == "手术报告":
        for field in ("started_at", "ended_at"):
            value = parsed["surgery_report"].get(field)
            if value:
                parsed["surgery_report"][field] = normalize_report_time(value)
    if parsed["report_type"] == "检验报告":
        item_ids = [
            str(item.get("item_id") or "") for item in parsed["lab_test_results"]
        ]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("同一份检验报告不能重复包含同一个 item_id。")
        categories = {
            normalize_lab_category(item["category_name"])
            for item in parsed["lab_test_results"]
        }
        if len(categories) != 1:
            raise ValueError("每份检验报告必须且只能包含一个医学功能分类。")
        category = next(iter(categories))
        if str(parsed.get("report_name") or "").strip() != category:
            raise ValueError("检验报告 report_name 必须与唯一 category_name 完全一致。")
    REPORT_DATABASE_SCHEMA.table_by_name['reports'].validate_values(parsed, partial=True)
    for name in ('examination_report', 'pathology_report', 'surgery_report', 'outpatient_report', 'emergency_report', 'other_report'):
        if parsed.get(name) is not None:
            REPORT_DATABASE_SCHEMA.table_by_name[name].validate_values(parsed[name], partial=True)
    for item in parsed.get('lab_test_results', []):
        REPORT_DATABASE_SCHEMA.table_by_name['lab_test_report'].validate_values(item, partial=True)
    return parsed


def normalize_report_time(value: str) -> str:
    normalized = value.strip()
    try:
        if len(normalized) == 10:
            date.fromisoformat(normalized)
        return local_iso(normalized)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("时间必须是有效的本地 ISO 日期或日期时间")

import json
import re
import uuid
from typing import Any, Optional

from backend.app.core.time import local_now_iso


REPORT_PREFIXES = {
    "检验报告": "LAB",
    "检查报告": "EXAM",
    "病理报告": "PATH",
    "手术报告": "SURG",
    "门诊病历": "OUTPATIENT",
    "急诊病历": "EMERGENCY",
    "其它医疗报告": "OTHER",
}


def _now_iso() -> str:
    return local_now_iso()


def _row_dict(row) -> Optional[dict[str, Any]]:
    return dict(row) if row is not None else None


def _json_loads(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _lab_name_key(value: Any) -> str:
    return re.sub(r"[\s\-_（）()]+", "", str(value or "")).casefold()


def _new_lab_item_id() -> str:
    return str(uuid.uuid4())


def _lab_value_key(value: Any) -> str:
    """Normalize presentation-only spacing and dash variants for comparisons."""

    normalized = str(value or "").translate(
        str.maketrans({"–": "-", "—": "-", "−": "-", "﹣": "-"})
    )
    return re.sub(r"\s+", "", normalized).casefold()

"""Health diary references and their current availability."""

from backend.app.application.medical_log_service import MedicalLogService
from backend.app.core.errors import SerenitaError


def log_reference(item):
    return {
        "resource_type": "medical_log", "resource_id": item["medical_log_id"],
        "member_id": item["member_id"], "name": item["title"],
        "recorded_on": item["recorded_on"],
        "created_at": item["created_at"], "updated_at": item["updated_at"],
    }


def resolve_resource_state(*, runtime_context, reference):
    if reference.get("resource_type") != "medical_log":
        return None
    state = {key: reference[key] for key in ("resource_type", "resource_id", "member_id")}
    try:
        service = runtime_context.service("medical_log", MedicalLogService)
        item = service.read(runtime_context.account_id, reference["member_id"],
                            medical_log_ids=[reference["resource_id"]])["medical_logs"][0]
        return {**state, "availability": "available", "current_created_at": item["created_at"],
                "current_updated_at": item["updated_at"]}
    except SerenitaError as exc:
        if exc.kind not in ("forbidden", "missing"):
            raise
        return {**state, "availability": "forbidden" if exc.kind == "forbidden" else "deleted"}

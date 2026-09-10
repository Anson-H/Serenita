"""Body record references and their current availability."""

from backend.app.application.body_metric_service import BodyMetricService
from backend.app.core.errors import SerenitaError
from backend.app.domain.body_metric_statistics import category
from backend.app.schemas.body_metric import CATALOG


def body_reference(item):
    name = CATALOG[item["metric"]]["label"] if item["kind"] == "measurement" else {
        "meal": "饮食记录", "sleep": "睡眠记录", "workout": "运动记录",
    }[item["kind"]]
    return {"resource_type": "body_record", "resource_id": item["record_id"],
            "member_id": item["member_id"], "name": name, "category": category(item),
            "created_at": item["created_at"], "updated_at": item["updated_at"]}


def resolve_resource_state(*, runtime_context, reference):
    if reference.get("resource_type") != "body_record":
        return None
    state = {key: reference[key] for key in ("resource_type", "resource_id", "member_id")}
    try:
        service = runtime_context.service("body_metric", BodyMetricService)
        item = service.read(runtime_context.account_id, reference["member_id"], reference["resource_id"])
        return {**state, "availability": "available", "current_created_at": item["created_at"],
                "current_updated_at": item["updated_at"]}
    except SerenitaError as exc:
        if exc.kind not in ("forbidden", "missing"):
            raise
        return {**state, "availability": "forbidden" if exc.kind == "forbidden" else "deleted"}

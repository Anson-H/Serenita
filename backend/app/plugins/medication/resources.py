"""Resolve medication resources and their current availability."""

from backend.app.application.medication_service import MedicationService
from backend.app.plugins.medication.constants import NAMES, PLUGIN_ID


def resolve_model_resource(*, runtime_context, reference):
    if reference.get('resource_type') != 'medication_source' or not runtime_context.member_id:
        return None
    service = runtime_context.service(PLUGIN_ID, MedicationService)
    metadata, content = service.source(runtime_context.account_id, runtime_context.member_id,
        reference['medication_id'], reference['resource_id'])
    return {**reference, 'original_filename': metadata['original_filename'],
        'mime_type': metadata['mime_type'], 'content_bytes': content}


def resolve_resource_state(*, runtime_context, reference):
    from backend.app.core.errors import SerenitaError

    kind = {NAMES[k]: k for k in ("medication", "plan", "batch")}.get(
        reference.get("resource_type")
    )
    if not kind:
        return None
    state = {k: reference[k] for k in ("resource_type", "resource_id", "member_id")}
    try:
        service = runtime_context.service(PLUGIN_ID, MedicationService)
        item = service.read(
            runtime_context.account_id,
            reference["member_id"],
            kind,
            reference["resource_id"],
        )
        return {
            **state,
            "availability": "available",
            "current_created_at": item["created_at"],
            "current_updated_at": item["updated_at"],
        }
    except SerenitaError as exc:
        if exc.kind not in ("forbidden", "missing"):
            raise
        return {
            **state,
            "availability": "forbidden" if exc.kind == "forbidden" else "deleted",
        }

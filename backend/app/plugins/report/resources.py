from __future__ import annotations

from backend.app.core.errors import SerenitaError

from backend.app.application.report_service import ReportService
from backend.app.application.member_service import MemberService
from backend.app.plugins.runtime_context import PluginRuntimeContext


PLUGIN_ID = "report"


def resolve_resource(
    *, runtime_context: PluginRuntimeContext, reference: dict
) -> dict | None:
    if not runtime_context.member_id:
        return None
    if reference.get("resource_type") != "report":
        return None
    resource_id = str(reference.get("resource_id") or "").strip()
    if not resource_id:
        return None
    service = runtime_context.service(
        PLUGIN_ID,
        lambda: ReportService.for_member(
            runtime_context.account_id, runtime_context.member_id
        ),
    )
    if not service.report_exists(runtime_context.member_id, resource_id):
        return None
    return service.validate_report_context(runtime_context.member_id, resource_id)


def resolve_resource_state(
    *, runtime_context: PluginRuntimeContext, reference: dict
) -> dict | None:
    if reference.get("resource_type") != "report":
        return None
    resource_id = str(reference.get("resource_id") or "").strip()
    if not resource_id:
        return None
    member_id = reference.get("member_id")
    state = {
        "resource_type": "report",
        "resource_id": resource_id,
        "member_id": member_id,
        "availability": "deleted",
    }
    if not member_id:
        return state
    try:
        service = runtime_context.service(
            f"report:{member_id}",
            lambda: ReportService.for_member(runtime_context.account_id, member_id),
        )
        return service.report_resource_state(member_id, resource_id)
    except SerenitaError as exc:
        if exc.kind == "forbidden":
            exists = runtime_context.service("members", MemberService).member_exists(
                member_id
            )
            return {**state, "availability": "forbidden" if exists else "deleted"}
        if exc.kind == "missing":
            return state
        raise


def resolve_model_resource(
    *, runtime_context: PluginRuntimeContext, reference: dict
) -> dict | None:
    if not runtime_context.member_id:
        return None
    if reference.get("resource_type") != "report_source":
        return None
    report_id = str(reference.get("report_id") or "")
    resource_id = str(reference.get("resource_id") or "")
    if not report_id or not resource_id:
        return None
    service = runtime_context.service(
        PLUGIN_ID,
        lambda: ReportService.for_member(
            runtime_context.account_id, runtime_context.member_id
        ),
    )
    path, original_filename, mime_type = service.source_download(
        runtime_context.member_id, report_id, resource_id
    )
    return {
        **reference,
        "path": str(path.resolve()),
        "original_filename": original_filename,
        "mime_type": mime_type,
    }


def resolve_input_model_resource(
    *, runtime_context: PluginRuntimeContext, reference: dict
) -> dict | None:
    if not runtime_context.member_id:
        return None
    if reference.get("resource_type") != "report":
        return None
    report_id = str(reference.get("resource_id") or "").strip()
    if not report_id:
        return None
    service = runtime_context.service(
        PLUGIN_ID,
        lambda: ReportService.for_member(
            runtime_context.account_id, runtime_context.member_id
        ),
    )
    return service.conversation_input_resource(runtime_context.member_id, report_id)

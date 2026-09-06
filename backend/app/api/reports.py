from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse, Response

from backend.app.api.report_projection import report_response
from backend.app.api.dependencies import get_report_service, require_current_user
from backend.app.application.auth_service import CurrentUser
from backend.app.application.report_service import MAX_REPORT_BATCH_BYTES, MAX_REPORT_FILES, ReportService
from backend.app.application.report_source_store import MAX_FILE_BYTES
from backend.app.core.errors import raise_error
from backend.app.schemas.report import (
    AddLabReportItemRequest,
    CreateReportRequest,
    UpdateReportFieldRequest,
)


router = APIRouter(tags=["reports"])


@router.post("/api/members/{member_id}/reports", status_code=201)
def create_report(
    member_id: str,
    request: CreateReportRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ReportService = Depends(get_report_service),
):
    return report_response(service.create_manual_report(
        member_id,
        report=request.model_dump(mode="json"),
    ), member_id)


@router.get("/api/members/{member_id}/reports")
def list_reports(
    member_id: str,
    report_type: Optional[str] = Query(default=None),
    user: CurrentUser = Depends(require_current_user),
    service: ReportService = Depends(get_report_service),
):
    return service.list_reports(
        member_id,
        report_type=report_type,
    )


@router.get("/api/members/{member_id}/reports/{report_id}/source-files/{resource_id}")
def download_source_file(
    member_id: str,
    report_id: str,
    resource_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ReportService = Depends(get_report_service),
):
    path, filename, mime_type = service.source_download(
        member_id, report_id, resource_id
    )
    return FileResponse(path=path, filename=filename, media_type=mime_type)


@router.get("/api/members/{member_id}/reports/{report_id}/source-files/{resource_id}/thumbnail")
def preview_source_file(
    member_id: str,
    report_id: str,
    resource_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ReportService = Depends(get_report_service),
):
    content, mime_type = service.source_thumbnail(
        member_id, report_id, resource_id
    )
    return Response(content=content, media_type=mime_type)


@router.post(
    "/api/members/{member_id}/reports/{report_id}/source-files",
    status_code=201,
)
async def add_report_source_files(
    member_id: str,
    report_id: str,
    files: list[UploadFile] = File(...),
    user: CurrentUser = Depends(require_current_user),
    service: ReportService = Depends(get_report_service),
):
    if not files:
        raise_error('invalid_input', "INVALID_REQUEST", "请至少选择一份报告原件。")
    if len(files) > MAX_REPORT_FILES:
        raise_error(
            'invalid_input',
            "TOO_MANY_FILES",
            f"每次最多补充 {MAX_REPORT_FILES} 份报告原件。",
        )

    uploads = []
    total_bytes = 0
    for file in files:
        content = await file.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            raise_error('resource_limit', "FILE_TOO_LARGE", "单个报告文件不能超过 20MB。")
        total_bytes += len(content)
        if total_bytes > MAX_REPORT_BATCH_BYTES:
            raise_error(
                'resource_limit',
                "FILE_BATCH_TOO_LARGE",
                "单次补充的报告文件总大小不能超过 100MB。",
            )
        uploads.append(
            {
                "original_filename": file.filename or "upload",
                "mime_type": file.content_type or "application/octet-stream",
                "content": content,
            }
        )

    return report_response(service.add_report_sources(
        member_id,
        report_id,
        uploads=uploads,
    ), member_id)


@router.get("/api/members/{member_id}/reports/{report_id}")
def get_report(
    member_id: str,
    report_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ReportService = Depends(get_report_service),
):
    return report_response(service.get_report(member_id, report_id), member_id)


@router.get("/api/members/{member_id}/reports/{report_id}/conversation-input-preview")
def preview_report_conversation_input(
    member_id: str,
    report_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ReportService = Depends(get_report_service),
):
    return service.conversation_input_resource(member_id, report_id)


@router.patch("/api/members/{member_id}/reports/{report_id}/fields")
def update_report_field(
    member_id: str,
    report_id: str,
    request: UpdateReportFieldRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ReportService = Depends(get_report_service),
):
    return report_response(service.update_report_field(
        member_id,
        report_id,
        field=request.field,
        value=request.value,
        item_id=request.item_id,
    ), member_id)


@router.post("/api/members/{member_id}/reports/{report_id}/lab-items", status_code=201)
def add_lab_report_item(
    member_id: str,
    report_id: str,
    request: AddLabReportItemRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ReportService = Depends(get_report_service),
):
    return report_response(service.add_lab_report_item(
        member_id,
        report_id,
        item_id=request.item_id,
        result_text=request.result_text,
        reference_text=request.reference_text,
        flag_text=request.flag_text,
    ), member_id)


@router.delete("/api/members/{member_id}/reports/{report_id}/lab-items/{item_id}")
def delete_lab_report_item(
    member_id: str,
    report_id: str,
    item_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ReportService = Depends(get_report_service),
):
    return report_response(service.delete_lab_report_items(
        member_id,
        report_id,
        item_ids=[item_id],
    ), member_id)


@router.delete("/api/members/{member_id}/reports/{report_id}")
def delete_report(
    member_id: str,
    report_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ReportService = Depends(get_report_service),
):
    return service.delete_report(
        member_id,
        report_id,
    )

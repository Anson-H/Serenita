from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    Header,
    Request,
    UploadFile,
)
from fastapi.responses import Response
from backend.app.api.dependencies import require_current_user
from backend.app.application.body_metric_import import CSV_FIELDS, MAX_UPLOAD
import csv, io, json
from starlette.concurrency import run_in_threadpool

router = APIRouter(
    prefix="/api/members/{member_id}/body-metrics", tags=["body-metrics"]
)


def service(request: Request):
    return request.app.state.services.body_metrics


@router.get("/catalog")
def catalog(member_id: str, user=Depends(require_current_user), svc=Depends(service)):
    return svc.catalog(user.account_id, member_id)


@router.get("/records")
def records(
    member_id: str,
    after: str | None = None,
    before: str | None = None,
    category: str | None = None,
    source: str | None = None,
    timezone: str = "Asia/Shanghai",
    offset: int = 0,
    limit: int = 100,
    user=Depends(require_current_user),
    svc=Depends(service),
):
    return svc.query(
        user.account_id,
        member_id,
        after,
        before,
        category,
        source,
        timezone,
        offset,
        limit,
    )


@router.get("/statistics")
def statistics(
    member_id: str,
    after: str | None = None,
    before: str | None = None,
    category: str | None = None,
    source: str | None = None,
    timezone: str = "Asia/Shanghai",
    user=Depends(require_current_user),
    svc=Depends(service),
):
    return svc.statistics(
        user.account_id, member_id, after, before, category, source, timezone
    )


@router.get("/statistics/series/{series_id}")
def series_data(
    member_id: str,
    series_id: str,
    view: str = "buckets",
    cursor: str | None = None,
    limit: int = 100,
    after: str | None = None,
    before: str | None = None,
    category: str | None = None,
    source: str | None = None,
    timezone: str = "Asia/Shanghai",
    user=Depends(require_current_user),
    svc=Depends(service),
):
    return svc.series_data(
        user.account_id,
        member_id,
        series_id,
        view=view,
        cursor=cursor,
        limit=limit,
        after=after,
        before=before,
        category=category,
        source=source,
        timezone=timezone,
    )


@router.post("/records", status_code=201)
def create(
    member_id: str,
    payload: dict = Body(...),
    request_id: str | None = Header(default=None, alias="Idempotency-Key"),
    user=Depends(require_current_user),
    svc=Depends(service),
):
    return svc.create(user.account_id, member_id, payload, request_id)


@router.get("/records/{record_id}")
def read(
    member_id: str,
    record_id: str,
    user=Depends(require_current_user),
    svc=Depends(service),
):
    return svc.read(user.account_id, member_id, record_id)


@router.patch("/records/{record_id}")
def update(
    member_id: str,
    record_id: str,
    payload: dict = Body(...),
    user=Depends(require_current_user),
    svc=Depends(service),
):
    return svc.update(user.account_id, member_id, record_id, payload)


@router.delete("/records/{record_id}")
def delete(
    member_id: str,
    record_id: str,
    user=Depends(require_current_user),
    svc=Depends(service),
):
    return svc.delete(user.account_id, member_id, record_id)


@router.post("/records/{record_id}/files")
async def upload(
    member_id: str,
    record_id: str,
    file: UploadFile = File(...),
    user=Depends(require_current_user),
    svc=Depends(service),
):
    content = await file.read(10 * 1024 * 1024 + 1)
    return await run_in_threadpool(
        svc.attach,
        user.account_id,
        member_id,
        record_id,
        file.filename or "图片",
        file.content_type,
        content,
    )


@router.get("/records/{record_id}/files/{file_id}")
def read_file(
    member_id: str,
    record_id: str,
    file_id: str,
    user=Depends(require_current_user),
    svc=Depends(service),
):
    item = svc.file(user.account_id, member_id, record_id, file_id)
    return Response(
        item["image_bytes"],
        media_type=item["mime_type"],
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )


@router.delete("/records/{record_id}/files/{file_id}")
def detach(
    member_id: str,
    record_id: str,
    file_id: str,
    user=Depends(require_current_user),
    svc=Depends(service),
):
    return svc.detach(user.account_id, member_id, record_id, file_id)


@router.post("/imports/preview")
async def preview(
    member_id: str,
    file: UploadFile = File(...),
    request_id: str = Header(alias="Idempotency-Key"),
    timezone: str = "Asia/Shanghai",
    user=Depends(require_current_user),
    svc=Depends(service),
):
    content = await file.read(MAX_UPLOAD + 1)
    return await run_in_threadpool(
        svc.preview,
        user.account_id,
        member_id,
        file.filename or "",
        content,
        request_id,
        timezone,
    )


@router.get("/imports")
def imports(member_id: str, cursor: str | None = None, limit: int = 24,
            user=Depends(require_current_user), svc=Depends(service)):
    return svc.imports(user.account_id, member_id, cursor=cursor, limit=limit)


@router.get("/imports/{import_id}")
def import_status(
    member_id: str,
    import_id: str,
    user=Depends(require_current_user),
    svc=Depends(service),
):
    return svc.imports(user.account_id, member_id, import_id)


@router.post("/imports/{import_id}/commit")
def commit(
    member_id: str,
    import_id: str,
    background: BackgroundTasks,
    payload: dict = Body(default={}),
    user=Depends(require_current_user),
    svc=Depends(service),
):
    result, started = svc.start_import(user.account_id, member_id, import_id, payload)
    if started:
        background.add_task(svc.run_import, user.account_id, member_id, import_id)
    return result


@router.delete("/imports/{import_id}")
def delete_import(
    member_id: str,
    import_id: str,
    user=Depends(require_current_user),
    svc=Depends(service),
):
    return svc.delete_import(user.account_id, member_id, import_id)


@router.get("/template")
def template(
    member_id: str,
    format: str = "json",
    user=Depends(require_current_user),
    svc=Depends(service),
):
    svc.catalog(user.account_id, member_id)
    from backend.app.application.body_metric_demo import template_records

    records = template_records()
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            record = dict(record)
            data = dict(record["data"])
            children = []
            for key, typ in (("foods", "food"), ("stages", "stage")):
                for child in data.pop(key, []):
                    children.append((typ, child))
            writer.writerow(
                {
                    **record,
                    "row_type": "record",
                    "data": json.dumps(data, ensure_ascii=False),
                }
            )
            for typ, child in children:
                child = dict(child)
                key = child.pop(typ + "_id")
                writer.writerow(
                    {
                        "row_type": typ,
                        "external_id": key,
                        "parent_id": record["external_id"],
                        "data": json.dumps(child, ensure_ascii=False),
                    }
                )
        return Response(
            "\ufeff" + buffer.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="serenita-body-metrics.csv"'
            },
        )
    return Response(
        json.dumps(
            {"format": "serenita-body-metrics", "records": records},
            ensure_ascii=False,
            indent=2,
        ),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="serenita-body-metrics.json"'
        },
    )

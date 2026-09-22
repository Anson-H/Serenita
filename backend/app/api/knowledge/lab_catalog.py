from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from backend.app.api.dependencies import require_current_user
from backend.app.api.medications import medication_service
from backend.app.application.accounts.auth_service import CurrentUser
from backend.app.application.lab_catalog_service import LabCatalogService
from backend.app.core.errors import raise_error
from backend.app.domain.report_errors import LabDictionaryMergeResultConflictError, LabDictionaryNameConflictError, LabDictionaryPrimaryCategoryError, LabDictionaryRevisionConflictError
from backend.app.schemas.lab_dictionary import (
    CreateLabCategoryRequest,
    CreateLabItemRequest,
    DeleteLabDictionaryCategoryRequest,
    DeleteLabDictionaryEntryRequest,
    MergeLabDictionaryItemsRequest,
    UpdateLabCategoryRequest,
    UpdateLabItemRequest,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def get_lab_catalog_service(request: Request) -> LabCatalogService:
    return request.app.state.services.lab_catalog


def _dictionary_response(call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return call()
    except LabDictionaryRevisionConflictError as exc:
        raise_error('conflict', exc.code, str(exc))
    except LabDictionaryNameConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except LabDictionaryMergeResultConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except LabDictionaryPrimaryCategoryError as exc:
        raise_error('conflict', exc.code, str(exc))
    except LookupError as exc:
        raise_error('missing', "LAB_DICTIONARY_ENTRY_NOT_FOUND", str(exc))
    except ValueError as exc:
        raise_error('invalid_input', "INVALID_LAB_DICTIONARY", str(exc))


@router.get("/lab-dictionary")
def get_lab_dictionary(
    user: CurrentUser = Depends(require_current_user),
    service: LabCatalogService = Depends(get_lab_catalog_service),
):
    return service.lab_dictionary(user.account_id)


@router.post("/lab-dictionary/items")
def create_lab_item(
    payload: CreateLabItemRequest,
    user: CurrentUser = Depends(require_current_user),
    service: LabCatalogService = Depends(get_lab_catalog_service),
):
    return _dictionary_response(
        lambda: service.create_lab_item(user.account_id, **payload.model_dump())
    )


@router.patch("/lab-dictionary/items/{item_id}")
def update_lab_item(
    item_id: str,
    payload: UpdateLabItemRequest,
    user: CurrentUser = Depends(require_current_user),
    service: LabCatalogService = Depends(get_lab_catalog_service),
):
    return _dictionary_response(
        lambda: service.update_lab_item(
            user.account_id, item_id, **payload.model_dump()
        )
    )


@router.delete("/lab-dictionary/items/{item_id}")
def delete_lab_item(
    item_id: str,
    payload: DeleteLabDictionaryEntryRequest,
    user: CurrentUser = Depends(require_current_user),
    service: LabCatalogService = Depends(get_lab_catalog_service),
):
    return _dictionary_response(
        lambda: service.delete_lab_item(
            user.account_id, item_id, **payload.model_dump()
        )
    )


@router.post("/lab-dictionary/items/{source_item_id}/merge")
def merge_lab_items(
    source_item_id: str,
    payload: MergeLabDictionaryItemsRequest,
    user: CurrentUser = Depends(require_current_user),
    service: LabCatalogService = Depends(get_lab_catalog_service),
):
    return _dictionary_response(
        lambda: service.merge_lab_items(
            user.account_id, source_item_id, **payload.model_dump()
        )
    )


@router.post("/lab-dictionary/categories")
def create_lab_category(
    payload: CreateLabCategoryRequest,
    user: CurrentUser = Depends(require_current_user),
    service: LabCatalogService = Depends(get_lab_catalog_service),
):
    return _dictionary_response(
        lambda: service.create_lab_category(user.account_id, **payload.model_dump())
    )


@router.patch("/lab-dictionary/categories/{category_name}")
def update_lab_category(
    category_name: str,
    payload: UpdateLabCategoryRequest,
    user: CurrentUser = Depends(require_current_user),
    service: LabCatalogService = Depends(get_lab_catalog_service),
):
    return _dictionary_response(
        lambda: service.update_lab_category(
            user.account_id, category_name, **payload.model_dump()
        )
    )


@router.delete("/lab-dictionary/categories/{category_name}")
def delete_lab_category(
    category_name: str,
    payload: DeleteLabDictionaryCategoryRequest,
    user: CurrentUser = Depends(require_current_user),
    service: LabCatalogService = Depends(get_lab_catalog_service),
):
    return _dictionary_response(
        lambda: service.delete_lab_category(
            user.account_id, category_name, **payload.model_dump()
        )
    )


@router.get('/medication-catalog')
def catalog_information(query: str='', cursor: str|None=None, limit: int=24,
        user=Depends(require_current_user), service=Depends(medication_service)):
    return service.catalog(user.account_id, None, 'medication', query=query, cursor=cursor, limit=limit)


@router.post('/medication-catalog', status_code=201)
def create_catalog_information(payload: dict=Body(...), operation_id: str=Header(alias='X-Serenita-Operation-ID'),
        user=Depends(require_current_user), service=Depends(medication_service)):
    return service.save(user.account_id, None, 'medication', payload, operation_id=operation_id)


@router.get('/medication-catalog/{medication_id}')
def read_catalog_information(medication_id: str, user=Depends(require_current_user), service=Depends(medication_service)):
    return service.read(user.account_id, None, 'medication', medication_id)


@router.patch('/medication-catalog/{medication_id}')
def update_catalog_information(medication_id: str, payload: dict=Body(...),
        user=Depends(require_current_user), service=Depends(medication_service)):
    return service.save(user.account_id, None, 'medication', payload, object_id=medication_id)


@router.delete('/medication-catalog/{medication_id}')
def delete_catalog_information(medication_id: str, user=Depends(require_current_user), service=Depends(medication_service)):
    return service.delete(user.account_id, None, 'medication', medication_id)


@router.post('/medication-catalog/{medication_id}/source-files', status_code=201)
async def add_source_files(medication_id: str, files: list[UploadFile]=File(...),
        operation_id: str=Header(alias='X-Serenita-Operation-ID'), user=Depends(require_current_user), service=Depends(medication_service)):
    if not 1 <= len(files) <= 20:
        raise_error('invalid_input', 'MEDICATION_ARGUMENTS_INVALID', '每次须选择 1 至 20 份药品原件。')
    uploads = []
    total = 0
    for file in files:
        content = await file.read(20 * 1024 * 1024 + 1)
        total += len(content)
        if total > 100 * 1024 * 1024:
            raise_error('resource_limit', 'MEDICATION_SOURCES_TOO_LARGE', '本次药品原件总大小不能超过 100 MB。')
        uploads.append({'original_filename': file.filename or '药品原件', 'mime_type': file.content_type,
            'content': content, 'purpose': 'package' if (file.content_type or '').startswith('image/') else 'label'})
    return await run_in_threadpool(service.add_sources, user.account_id, None, medication_id, uploads, operation_id)


@router.get('/medication-catalog/{medication_id}/source-files/{resource_id}')
def read_catalog_source(medication_id: str, resource_id: str,
        user=Depends(require_current_user), service=Depends(medication_service)):
    metadata, content = service.source(user.account_id, None, medication_id, resource_id)
    return Response(content, media_type=metadata['mime_type'], headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})

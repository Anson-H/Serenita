"""Member memory HTTP reads and owner-managed formation settings."""

from fastapi import APIRouter, Depends, Query, Request

from backend.app.api.dependencies import require_current_user
from backend.app.application.accounts.auth_service import CurrentUser
from backend.app.schemas.memory.requests import MemoryReadRequest, MemorySettingsSave, MemoryProcessingRetry, MemoryProcessingResume, MemoryChangeSummaries
from backend.app.schemas.memory.graph import MemoryGraphRead
from backend.app.schemas.memory.index import IndexSearchInput
from backend.app.schemas.memory.append import MemoryQuery


router = APIRouter(prefix="/api/members/{member_id}/memory", tags=["memory"])


def service(request: Request):
    return request.app.state.services.memory


def reads(request: Request):
    return request.app.state.services.memory_reads


def commands(request: Request):
    return request.app.state.services.memory_commands


@router.get("/settings")
def settings(member_id: str, user: CurrentUser = Depends(require_current_user), memory=Depends(service)):
    return memory.settings(user.account_id, member_id)


@router.put("/settings")
def save_settings(member_id: str, payload: MemorySettingsSave, user: CurrentUser = Depends(require_current_user), memory=Depends(service)):
    return memory.save_settings(user.account_id, member_id, payload.model_dump())


@router.get("/catalog")
def catalog(
    member_id: str, query: str = "", object_types: list[str] = Query(default=["event"]),
    record_cutoff: int | None = None, view: str = "current", cursor: str | None = None,
    limit: int = 24, user: CurrentUser = Depends(require_current_user), memory=Depends(service),
):
    return memory.query(user.account_id, member_id, {
        "query": query, "object_types": object_types, "record_cutoff": record_cutoff,
        "view": view, "cursor": cursor, "limit": limit,
    })


@router.post("/query")
def read(member_id: str, payload: MemoryReadRequest, user: CurrentUser = Depends(require_current_user), memory=Depends(service)):
    return memory.query(user.account_id, member_id, payload.model_dump())


@router.post('/search')
def search(member_id: str, payload: IndexSearchInput, user: CurrentUser = Depends(require_current_user), capabilities=Depends(reads)):
    return capabilities.search.search(user.account_id, member_id, payload.model_dump())


@router.post("/reading")
def reading(member_id: str, payload: MemoryReadRequest, user: CurrentUser = Depends(require_current_user), capabilities=Depends(reads)):

    return capabilities.reading.read(user.account_id, member_id, payload.model_dump(exclude_unset=True))


@router.post('/processing/{attempt_id}/retry')
def retry_processing(member_id: str, attempt_id: str, payload: MemoryProcessingRetry, request: Request, user: CurrentUser = Depends(require_current_user)):
    return commands(request).retry(user.account_id, member_id, attempt_id, operation_id=payload.operation_id)


@router.post('/processing/{attempt_id}/resume')
def resume_processing(member_id: str, attempt_id: str, payload: MemoryProcessingResume, request: Request, user: CurrentUser = Depends(require_current_user)):
    return commands(request).resume(
        user.account_id, member_id, attempt_id, operation_id=payload.operation_id)


@router.post('/processing/query')
def processing_catalog(member_id: str, payload: MemoryQuery, user: CurrentUser = Depends(require_current_user), capabilities=Depends(reads)):
    return capabilities.processing.read(user.account_id, member_id, payload.model_dump())


@router.post('/processing/{attempt_id}/cancel')
def cancel_processing(member_id: str, attempt_id: str, request: Request, user: CurrentUser = Depends(require_current_user)):
    return commands(request).cancel(user.account_id, member_id, attempt_id)


@router.post('/graph')
def graph(member_id: str, payload: MemoryGraphRead, user: CurrentUser = Depends(require_current_user), capabilities=Depends(reads)):
    return capabilities.graph.read(user.account_id, member_id, payload.model_dump(exclude_unset=True))


@router.get('/changes')
def changes(member_id: str, cursor: str | None = None, limit: int = Query(default=30, ge=1, le=100),
            user: CurrentUser = Depends(require_current_user), capabilities=Depends(reads)):
    return capabilities.changes.catalog(user.account_id, member_id, cursor, limit)


@router.post('/changes/summaries')
def change_summaries(member_id: str, payload: MemoryChangeSummaries,
                     user: CurrentUser = Depends(require_current_user), capabilities=Depends(reads)):
    return capabilities.changes.summaries(user.account_id, member_id,
        [reference.model_dump(mode='json') for reference in payload.references])


@router.get('/changes/{source_database}/{change_id}')
def change_detail(member_id: str, source_database: str, change_id: str,
                  user: CurrentUser = Depends(require_current_user), capabilities=Depends(reads)):
    return capabilities.changes.detail(user.account_id, member_id, source_database, change_id)


@router.get('/changes/{source_database}/{change_id}/status')
def change_status(member_id: str, source_database: str, change_id: str,
                  user: CurrentUser = Depends(require_current_user), capabilities=Depends(reads)):
    return capabilities.changes.status(user.account_id, member_id, source_database, change_id)


@router.get('/changes/{source_database}/{change_id}/steps/{step_id}')
def change_step(member_id: str, source_database: str, change_id: str, step_id: str, parent_step_id: str | None = None,
                user: CurrentUser = Depends(require_current_user), capabilities=Depends(reads)):
    value = capabilities.changes.detail(user.account_id, member_id, source_database, change_id,
        step=(step_id, parent_step_id), status_only=True)
    return {key: value[key] for key in ('content_available', 'access_revision', 'processing_steps', 'model_inputs')}


@router.get('/changes/{source_database}/{change_id}/models/{entry_id}')
def change_model(member_id: str, source_database: str, change_id: str, entry_id: str,
                 user: CurrentUser = Depends(require_current_user), capabilities=Depends(reads)):
    return capabilities.changes.model(user.account_id, member_id, source_database, change_id, entry_id)


@router.get('/changes/{source_database}/{change_id}/models/{entry_id}/fragments')
def model_fragments(member_id: str, source_database: str, change_id: str, entry_id: str,
                    after_entry_sequence: int = Query(default=0, ge=0, lt=2**63),
                    limit: int = Query(default=200, ge=1, le=1000),
                    user: CurrentUser = Depends(require_current_user), capabilities=Depends(reads)):
    return capabilities.changes.fragments(user.account_id, member_id, source_database, change_id, entry_id,
        after_entry_sequence=after_entry_sequence, limit=limit)


@router.get('/changes/{source_database}/{change_id}/results')
def change_results(member_id: str, source_database: str, change_id: str,
                   user: CurrentUser = Depends(require_current_user), capabilities=Depends(reads)):
    value = capabilities.changes.detail(user.account_id, member_id, source_database, change_id, results=True, status_only=True)
    return {key: value[key] for key in ('content_available', 'extraction_results', 'relation_results')}

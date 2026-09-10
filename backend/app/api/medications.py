from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, Body, Depends, File, Header, Request, UploadFile
from fastapi.responses import Response
from backend.app.api.dependencies import require_current_user
from backend.app.core.errors import raise_error

router=APIRouter(tags=['medications'])


def medication_service(request: Request): return request.app.state.services.medications



def register(kind,path):
    base='/api/members/{member_id}/'+path
    @router.get(base, name='catalog_'+kind)
    def catalog(member_id: str, query: str='', status: str|None=None, after_date: str|None=None,
                before_date: str|None=None, undated: bool=False, cursor: str|None=None, limit: int=24,
                user=Depends(require_current_user), service=Depends(medication_service)):
        return service.catalog(user.account_id,member_id,kind,query=query,status=status,after_date=after_date,before_date=before_date,undated=undated,cursor=cursor,limit=limit)
    @router.post(base, status_code=201, name='create_'+kind)
    def create(member_id: str, payload: dict=Body(...), request_id: str=Header(alias='Idempotency-Key'),
               user=Depends(require_current_user), service=Depends(medication_service)):
        return service.save(user.account_id,member_id,kind,payload,request_id=request_id)
    @router.get(base+'/{object_id}', name='read_'+kind)
    def read(member_id: str,object_id: str,user=Depends(require_current_user),service=Depends(medication_service)):
        return service.read(user.account_id,member_id,kind,object_id)
    @router.patch(base+'/{object_id}', name='update_'+kind)
    def update(member_id: str,object_id: str,payload: dict=Body(...),user=Depends(require_current_user),service=Depends(medication_service)):
        return service.save(user.account_id,member_id,kind,payload,object_id=object_id)
    @router.delete(base+'/{object_id}', name='delete_'+kind)
    def delete(member_id: str,object_id: str,user=Depends(require_current_user),service=Depends(medication_service)):
        return service.delete(user.account_id,member_id,kind,object_id)


register('plan', 'medication-plans')


@router.get('/api/medication-catalog')
def catalog_information(query: str='', cursor: str|None=None, limit: int=24,
        user=Depends(require_current_user), service=Depends(medication_service)):
    return service.catalog(user.account_id, None, 'medication', query=query, cursor=cursor, limit=limit)


@router.post('/api/medication-catalog', status_code=201)
def create_catalog_information(payload: dict=Body(...), request_id: str=Header(alias='Idempotency-Key'),
        user=Depends(require_current_user), service=Depends(medication_service)):
    return service.save(user.account_id, None, 'medication', payload, request_id=request_id)


@router.get('/api/medication-catalog/{medication_id}')
def read_catalog_information(medication_id: str, user=Depends(require_current_user), service=Depends(medication_service)):
    return service.read(user.account_id, None, 'medication', medication_id)


@router.patch('/api/medication-catalog/{medication_id}')
def update_catalog_information(medication_id: str, payload: dict=Body(...),
        user=Depends(require_current_user), service=Depends(medication_service)):
    return service.save(user.account_id, None, 'medication', payload, object_id=medication_id)


@router.delete('/api/medication-catalog/{medication_id}')
def delete_catalog_information(medication_id: str, user=Depends(require_current_user), service=Depends(medication_service)):
    return service.delete(user.account_id, None, 'medication', medication_id)


@router.get('/api/members/{member_id}/medications')
def member_medications(member_id: str, query: str='', cursor: str|None=None, limit: int=24, inventory_only: bool=False,
        user=Depends(require_current_user), service=Depends(medication_service)):
    return service.catalog(user.account_id, member_id, 'medication', query=query, cursor=cursor, limit=limit, inventory_only=inventory_only)


@router.get('/api/members/{member_id}/medications/{medication_id}')
def member_medication(member_id: str, medication_id: str, user=Depends(require_current_user), service=Depends(medication_service)):
    return service.read(user.account_id, member_id, 'medication', medication_id)


@router.get('/api/members/{member_id}/medications/{medication_id}/batches')
def batches(member_id: str,medication_id: str,user=Depends(require_current_user),service=Depends(medication_service)):
    return {'items':service.read(user.account_id,member_id,'medication',medication_id)['batches']}


@router.post('/api/members/{member_id}/medications/{medication_id}/batches',status_code=201)
def create_batch(member_id: str,medication_id: str,payload: dict=Body(...),request_id: str=Header(alias='Idempotency-Key'),user=Depends(require_current_user),service=Depends(medication_service)):
    return service.save(user.account_id,member_id,'batch',payload,request_id=request_id,medication_id=medication_id)


@router.patch('/api/members/{member_id}/medications/{medication_id}/batches/{batch_id}')
def update_batch(member_id: str,medication_id: str,batch_id: str,payload: dict=Body(...),user=Depends(require_current_user),service=Depends(medication_service)):
    existing=service.read(user.account_id,member_id,'batch',batch_id)
    if existing['medication_id'] != medication_id: raise_error('missing','MEDICATION_NOT_FOUND','批次不属于该药品。')
    return service.save(user.account_id,member_id,'batch',payload,object_id=batch_id)


@router.delete('/api/members/{member_id}/medications/{medication_id}/batches/{batch_id}')
def delete_batch(member_id: str,medication_id: str,batch_id: str,user=Depends(require_current_user),service=Depends(medication_service)):
    existing=service.read(user.account_id,member_id,'batch',batch_id)
    if existing['medication_id'] != medication_id: raise_error('missing','MEDICATION_NOT_FOUND','批次不属于该药品。')
    return service.delete(user.account_id,member_id,'batch',batch_id)


@router.post('/api/medication-catalog/{medication_id}/source-files', status_code=201)
async def add_source_files(medication_id: str, files: list[UploadFile]=File(...),
        request_id: str=Header(alias='Idempotency-Key'), user=Depends(require_current_user), service=Depends(medication_service)):
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
    return await run_in_threadpool(service.add_sources, user.account_id, None, medication_id, uploads, request_id)


@router.get('/api/members/{member_id}/medications/{medication_id}/source-files/{resource_id}')
def read_source(member_id: str, medication_id: str, resource_id: str,
        user=Depends(require_current_user), service=Depends(medication_service)):
    metadata, content = service.source(user.account_id, member_id, medication_id, resource_id)
    return Response(content, media_type=metadata['mime_type'], headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})


@router.get('/api/medication-catalog/{medication_id}/source-files/{resource_id}')
def read_catalog_source(medication_id: str, resource_id: str,
        user=Depends(require_current_user), service=Depends(medication_service)):
    metadata, content = service.source(user.account_id, None, medication_id, resource_id)
    return Response(content, media_type=metadata['mime_type'], headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})

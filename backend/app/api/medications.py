from fastapi import APIRouter, Body, Depends, Header, Request
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
    def create(member_id: str, payload: dict=Body(...), operation_id: str=Header(alias='X-Serenita-Operation-ID'),
               user=Depends(require_current_user), service=Depends(medication_service)):
        return service.save(user.account_id,member_id,kind,payload,operation_id=operation_id)
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
def create_batch(member_id: str,medication_id: str,payload: dict=Body(...),operation_id: str=Header(alias='X-Serenita-Operation-ID'),user=Depends(require_current_user),service=Depends(medication_service)):
    return service.save(user.account_id,member_id,'batch',payload,operation_id=operation_id,medication_id=medication_id)


@router.patch('/api/members/{member_id}/medications/{medication_id}/batches/{batch_id}')
def update_batch(member_id: str,medication_id: str,batch_id: str,payload: dict=Body(...),user=Depends(require_current_user),service=Depends(medication_service)):
    return service.save(user.account_id,member_id,'batch',payload,object_id=batch_id,medication_id=medication_id)


@router.delete('/api/members/{member_id}/medications/{medication_id}/batches/{batch_id}')
def delete_batch(member_id: str,medication_id: str,batch_id: str,user=Depends(require_current_user),service=Depends(medication_service)):
    return service.delete(user.account_id,member_id,'batch',batch_id,medication_id=medication_id)


@router.get('/api/members/{member_id}/medications/{medication_id}/source-files/{resource_id}')
def read_source(member_id: str, medication_id: str, resource_id: str,
        user=Depends(require_current_user), service=Depends(medication_service)):
    metadata, content = service.source(user.account_id, member_id, medication_id, resource_id)
    return Response(content, media_type=metadata['mime_type'], headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})

from fastapi import APIRouter, Depends, Request
from backend.app.api.dependencies import require_current_user
from backend.app.application.auth_service import CurrentUser
from backend.app.schemas.medical_log import MedicalLogCreate, MedicalLogUpdate

router = APIRouter(prefix="/api/members/{member_id}/medical-logs", tags=["medical_logs"])


def service(request: Request):
    return request.app.state.services.medical_logs


@router.get("")
def catalog(member_id: str, after_date: str | None = None, before_date: str | None = None,
            query: str = "", cursor: str | None = None, limit: int = 24,
            user: CurrentUser = Depends(require_current_user), logs=Depends(service)):
    return logs.catalog(user.account_id, member_id, after_date=after_date, before_date=before_date,
                        query=query, cursor=cursor, limit=limit)


@router.post("", status_code=201)
def create(member_id: str, payload: MedicalLogCreate,
           user: CurrentUser = Depends(require_current_user), logs=Depends(service)):
    return logs.create(user.account_id, member_id, payload.model_dump(exclude_unset=True))


@router.get("/{medical_log_id}")
def read(member_id: str, medical_log_id: str,
         user: CurrentUser = Depends(require_current_user), logs=Depends(service)):
    result = logs.read(user.account_id, member_id, medical_log_ids=[medical_log_id])
    return {"member_id": member_id, "medical_log": result["medical_logs"][0]}


@router.patch("/{medical_log_id}")
def update(member_id: str, medical_log_id: str, payload: MedicalLogUpdate,
           user: CurrentUser = Depends(require_current_user), logs=Depends(service)):
    return logs.update(user.account_id, member_id, medical_log_id, payload.model_dump(exclude_unset=True))


@router.delete("/{medical_log_id}")
def delete(member_id: str, medical_log_id: str,
           user: CurrentUser = Depends(require_current_user), logs=Depends(service)):
    return logs.delete(user.account_id, member_id, medical_log_id)

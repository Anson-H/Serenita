from fastapi import APIRouter

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def list_reports():
    return {"reports": []}

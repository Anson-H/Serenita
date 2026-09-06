from fastapi import APIRouter, Depends
from backend.app.api.dependencies import require_current_user, get_favorite_service
from backend.app.application.auth_service import CurrentUser
from backend.app.application.favorite_service import FavoriteService
from backend.app.schemas.favorite import (
    CreateFavoriteRequest,
    PatchFavoriteRequest,
    BatchDeleteRequest,
)

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.get("")
def list_favorites(
    user: CurrentUser = Depends(require_current_user),
    service: FavoriteService = Depends(get_favorite_service),
):
    return service.list_favorites(user.account_id)


@router.post("")
def create_favorite(
    payload: CreateFavoriteRequest,
    user: CurrentUser = Depends(require_current_user),
    service: FavoriteService = Depends(get_favorite_service),
):
    return service.create_favorite(user.account_id, payload)


@router.get("/{favorite_id}")
def get_favorite(
    favorite_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: FavoriteService = Depends(get_favorite_service),
):
    return service.get_favorite(user.account_id, favorite_id)


@router.patch("/{favorite_id}")
def patch_favorite(
    favorite_id: str,
    payload: PatchFavoriteRequest,
    user: CurrentUser = Depends(require_current_user),
    service: FavoriteService = Depends(get_favorite_service),
):
    return service.patch_favorite(user.account_id, favorite_id, payload)


@router.delete("/{favorite_id}")
def delete_favorite(
    favorite_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: FavoriteService = Depends(get_favorite_service),
):
    return service.delete_favorite(user.account_id, favorite_id)


@router.post("/batch-delete")
def batch_delete_favorites(
    payload: BatchDeleteRequest,
    user: CurrentUser = Depends(require_current_user),
    service: FavoriteService = Depends(get_favorite_service),
):
    return service.batch_delete_favorites(user.account_id, payload.favorite_ids)

from fastapi import APIRouter, Depends, Response
from backend.app.api.dependencies import (
    require_current_user,
    get_model_settings_service,
)
from backend.app.application.auth_service import CurrentUser
from backend.app.application.model_settings_service import ModelSettingsService
from backend.app.schemas.model_provider import (
    ModelProviderSaveRequest,
    ModelProviderPatchRequest,
    ModelProviderTestRequest,
    AddModelRequest,
    ModelPatchRequest,
    ModelDefaultsPatchRequest,
)

router = APIRouter(prefix="/api", tags=["model-providers"])


@router.get("/model-providers")
def list_model_providers(
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return service.list_model_providers(user.account_id)


@router.post("/model-providers/{provider_id}/credential/reveal")
def reveal_model_provider_credential(
    provider_id: str,
    response: Response,
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return service.reveal_model_provider_credential(user.account_id, provider_id)


@router.post("/model-providers")
def create_model_provider(
    payload: ModelProviderSaveRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return service.create_model_provider(user.account_id, payload)


@router.patch("/model-providers/{provider_id}")
def update_model_provider(
    provider_id: str,
    payload: ModelProviderPatchRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return service.update_model_provider(user.account_id, provider_id, payload)


@router.post("/model-providers/{provider_id}/test")
def test_model_provider(
    provider_id: str,
    payload: ModelProviderTestRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return service.test_model_provider(user.account_id, provider_id, payload)


@router.get("/model-providers/{provider_id}/models")
def list_remote_models(
    provider_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return service.list_remote_models(user.account_id, provider_id)


@router.post("/models")
def add_model(
    payload: AddModelRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return service.add_model(user.account_id, payload)


@router.get("/models")
def list_models(
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return service.list_models(user.account_id)


@router.patch("/models/{model_id:path}")
def update_model(
    model_id: str,
    payload: ModelPatchRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return service.update_model(user.account_id, model_id, payload)


@router.post("/models/capability-probe/{model_id:path}")
def probe_model_capabilities(
    model_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return service.probe_model_capabilities(user.account_id, model_id)


@router.get("/model-access-settings")
def list_model_defaults(
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return service.list_model_defaults(user.account_id)


@router.patch("/model-access-settings")
def update_model_defaults(
    payload: ModelDefaultsPatchRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return service.update_model_defaults(user.account_id, payload)


@router.delete("/models/{model_id:path}")
def delete_model(
    model_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return service.delete_model(user.account_id, model_id)

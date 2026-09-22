import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from backend.app.core.cancellation import CancellationToken, OperationCancelledError
from backend.app.api.dependencies import (
    require_current_user,
    get_model_settings_service,
)
from backend.app.application.accounts.auth_service import CurrentUser
from backend.app.application.models.settings_service import ModelSettingsService
from backend.app.schemas.model_provider import (
    ModelProviderSaveRequest,
    ModelProviderPatchRequest,
    ModelProviderTestRequest,
    AddModelRequest,
    ModelPatchRequest,
    ModelDefaultsPatchRequest,
    ModelProbeRequest,
)

router = APIRouter(prefix="/api", tags=["model-providers"])


def model_catalog_context(request: Request, user: CurrentUser = Depends(require_current_user)):
    return user, request.app.state.services.model_connections.current_catalog(user.account_id)


@router.post("/model-access-settings/recommend")
def recommend_defaults(user=Depends(require_current_user), service=Depends(get_model_settings_service)):
    return service.recommend_missing_defaults(user.account_id)


async def cancellable_model_request(request, invoke):
    """Propagate browser cancellation to blocking requests and retry waits."""
    token = CancellationToken()
    worker = asyncio.create_task(asyncio.to_thread(invoke, token))
    try:
        while not worker.done():
            if await request.is_disconnected():
                token.cancel()
            await asyncio.wait({worker}, timeout=0.1)
        return await worker
    except OperationCancelledError as error:
        raise HTTPException(status_code=499, detail={
            "code": "MODEL_REQUEST_CANCELLED", "message": "模型请求已取消。",
        }) from error
    finally:
        token.cancel()
        if not worker.done():
            worker.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)


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
async def test_model_provider(
    provider_id: str,
    payload: ModelProviderTestRequest,
    request: Request,
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return await cancellable_model_request(request, lambda token:
        service.test_model_provider(user.account_id, provider_id, payload, cancellation_token=token))


@router.delete("/model-providers/{provider_id}")
def delete_model_provider(provider_id: str, user: CurrentUser = Depends(require_current_user),
                          service: ModelSettingsService = Depends(get_model_settings_service)):
    return service.delete_model_provider(user.account_id, provider_id)


@router.get("/model-providers/{provider_id}/models")
async def list_remote_models(
    provider_id: str,
    request: Request,
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return await cancellable_model_request(request, lambda token:
        service.list_remote_models(user.account_id, provider_id, cancellation_token=token))


@router.post("/models")
async def add_model(
    payload: AddModelRequest,
    request: Request,
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return await cancellable_model_request(
        request,
        lambda token: service.add_model(
            user.account_id, payload, cancellation_token=token
        ),
    )


@router.get("/models")
def list_models(
    context=Depends(model_catalog_context),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    from backend.app.application.models.connection_service import model_with_service_status
    user, catalog = context
    models = service.list_models(user.account_id)["models"]
    return {"models": [model_with_service_status(model, catalog) for model in models]}


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
    payload: ModelProbeRequest | None = None,
    user: CurrentUser = Depends(require_current_user),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    return service.probe_model_capabilities(user.account_id, model_id, payload.probe_id if payload else None)


@router.post("/models/capability-probe-cancel/{model_id:path}")
def cancel_model_capability_probe(model_id: str, payload: ModelProbeRequest | None = None, user: CurrentUser = Depends(require_current_user), service: ModelSettingsService = Depends(get_model_settings_service)):
    service.probes.cancel(user.account_id, model_id, payload.probe_id if payload else None)
    return {"model_id": model_id, "cancelled": True}


@router.get("/model-access-settings")
def list_model_defaults(
    context=Depends(model_catalog_context),
    service: ModelSettingsService = Depends(get_model_settings_service),
):
    from backend.app.application.models.connection_service import model_with_service_status
    user, catalog = context
    defaults = service.list_model_defaults(user.account_id)["defaults"]
    return {"defaults": {purpose: model_with_service_status(model, catalog) for purpose, model in defaults.items()}}


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

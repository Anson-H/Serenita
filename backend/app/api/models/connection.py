"""Client-only connection to the official Serenita model service."""
from fastapi import APIRouter, Depends, Request
from backend.app.api.dependencies import require_current_user
from backend.app.api.models.providers import cancellable_model_request
from backend.app.schemas.model_service import OnboardingRequest, DeviceRequestReference

router = APIRouter(prefix="/api", tags=["serenita-connection"])

def connections(request: Request):
    return request.app.state.services.model_connections

@router.get("/model-onboarding")
@router.get("/serenita-connection")
def connection_state(user=Depends(require_current_user), connection=Depends(connections)):
    return connection.status(user.account_id)


@router.post("/model-onboarding")
def onboarding(payload: OnboardingRequest, user=Depends(require_current_user), connection=Depends(connections)):
    return connection.choose(user.account_id, payload.choice)


@router.post("/serenita-connection/authorize")
def connect_official(user=Depends(require_current_user), connection=Depends(connections)):
    return connection.start(user.account_id)


@router.post("/serenita-connection/poll")
def poll_official(payload: DeviceRequestReference, user=Depends(require_current_user), connection=Depends(connections)):
    return connection.poll(user.account_id, payload.user_code)


@router.delete("/serenita-connection/authorization")
def cancel_official(payload: DeviceRequestReference, user=Depends(require_current_user), connection=Depends(connections)):
    return connection.cancel(user.account_id, payload.user_code)


@router.delete("/serenita-connection")
def disconnect_official(user=Depends(require_current_user), connection=Depends(connections)):
    return connection.disconnect(user.account_id)


@router.post("/serenita-connection/refresh")
async def refresh_catalog(request: Request, user=Depends(require_current_user), connection=Depends(connections)):
    return await cancellable_model_request(request, lambda token: connection.sync_catalog(user.account_id, cancellation_token=token))



from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from backend.app.api.dependencies import (
    get_account_settings_service,
    get_web_access_service,
    require_current_user,
)
from backend.app.application.accounts.settings_service import AccountSettingsService
from backend.app.application.accounts.auth_service import CurrentUser
from backend.app.core.errors import raise_error
from backend.app.plugins.web.errors import WebAccessError
from backend.app.plugins.web.service import WebAccessService
from backend.app.schemas.conversation_preferences import ConversationPreferences


router = APIRouter(prefix="/api/account-settings", tags=["account-settings"])


class WebAccessPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_enabled: bool | None = None
    active_provider_id: str | None = None


class WebCredentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str


class WebProviderSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_url: str


class WebProviderTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str | None = None


def _web_response(call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return call()
    except WebAccessError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": str(exc), "details": exc.details},
        ) from exc
    except ValueError as exc:
        raise_error('invalid_input', "INVALID_WEB_ACCESS_SETTINGS", str(exc))


@router.get(
    "/conversation-preferences",
    response_model=ConversationPreferences,
)
def get_conversation_preferences(
    user: CurrentUser = Depends(require_current_user),
    service: AccountSettingsService = Depends(get_account_settings_service),
):
    return service.conversation_preferences(user.account_id)


@router.put(
    "/conversation-preferences",
    response_model=ConversationPreferences,
)
def put_conversation_preferences(
    payload: ConversationPreferences,
    user: CurrentUser = Depends(require_current_user),
    service: AccountSettingsService = Depends(get_account_settings_service),
):
    try:
        return service.replace_conversation_preferences(
            user.account_id,
            **payload.model_dump(),
        )
    except ValueError as exc:
        raise_error('invalid_input', "INVALID_CONVERSATION_PREFERENCES", str(exc))


@router.get("/web-access")
def get_web_access(
    user: CurrentUser = Depends(require_current_user),
    service: WebAccessService = Depends(get_web_access_service),
):
    return service.settings(user.account_id)


@router.patch("/web-access")
def patch_web_access(
    payload: WebAccessPatchRequest,
    user: CurrentUser = Depends(require_current_user),
    service: WebAccessService = Depends(get_web_access_service),
):
    return _web_response(
        lambda: service.update_settings(
            user.account_id,
            is_enabled=payload.is_enabled,
            active_provider_id=payload.active_provider_id,
        )
    )


@router.put("/web-access/providers/{provider_id}/credential")
def put_web_provider_credential(
    provider_id: str,
    payload: WebCredentialRequest,
    user: CurrentUser = Depends(require_current_user),
    service: WebAccessService = Depends(get_web_access_service),
):
    return _web_response(
        lambda: service.save_credential(user.account_id, provider_id, payload.api_key)
    )


@router.patch("/web-access/providers/{provider_id}")
def patch_web_provider(
    provider_id: str,
    payload: WebProviderSettingsRequest,
    user: CurrentUser = Depends(require_current_user),
    service: WebAccessService = Depends(get_web_access_service),
):
    return _web_response(
        lambda: service.update_provider_api_url(
            user.account_id,
            provider_id,
            payload.api_url,
        )
    )


@router.post("/web-access/providers/{provider_id}/credential/reveal")
def reveal_web_provider_credential(
    provider_id: str,
    response: Response,
    user: CurrentUser = Depends(require_current_user),
    service: WebAccessService = Depends(get_web_access_service),
):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return _web_response(
        lambda: service.reveal_credential(user.account_id, provider_id)
    )


@router.delete("/web-access/providers/{provider_id}/credential")
def delete_web_provider_credential(
    provider_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: WebAccessService = Depends(get_web_access_service),
):
    return _web_response(
        lambda: service.delete_credential(user.account_id, provider_id)
    )


@router.post("/web-access/providers/{provider_id}/test")
def test_web_provider(
    provider_id: str,
    payload: WebProviderTestRequest,
    user: CurrentUser = Depends(require_current_user),
    service: WebAccessService = Depends(get_web_access_service),
):
    return _web_response(
        lambda: service.test_provider(
            user.account_id, provider_id, api_key=payload.api_key
        )
    )

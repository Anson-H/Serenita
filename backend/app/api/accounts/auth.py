from __future__ import annotations
from fastapi import Request
from backend.app.api.dependencies import require_account_context

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Response
from pydantic import BaseModel, ConfigDict

from backend.app.api.dependencies import (
    SESSION_COOKIE_NAME,
    get_auth_service,
    require_current_user,
    require_official_login,
)
from backend.app.application.accounts.auth_service import (
    SESSION_TTL,
    AuthService,
    AuthServiceError,
    CurrentUser,
    is_guest_identity,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignUpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str
    account_name: str
    password: str
    confirm_password: str


class SignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str
    password: str


class GuestSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str
    password: str


class AccountUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str
    account_name: str


class PasswordUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str
    new_password: str
    confirm_password: str


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=int(SESSION_TTL.total_seconds()),
    )


def session_response(user: CurrentUser, *, temporary: bool | None = None) -> dict[str, object]:
    response: dict[str, object] = {
        "authenticated": True,
        "account_id": user.account_id,
        "account": user.account,
        "account_name": user.account_name,
        "expires_at": user.expires_at,
    }
    if temporary is None:
        temporary = is_guest_identity(user.account, user.account_name)
    if temporary:
        response["temporary"] = True
    return response


@router.get("/session")
def get_session(
    request: Request,
    response: Response,
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    service: AuthService = Depends(get_auth_service),
):
    if not request.app.state.services.deployment.official:
        user, token = request.app.state.services.local_workspace.session(session_token)
        if token:
            set_session_cookie(response, token)
        return session_response(user, temporary=False)
    try:
        return session_response(service.current_user(session_token))
    except AuthServiceError as exc:
        if exc.kind == "unauthenticated":
            return {"authenticated": False}
        raise


@router.post("/sign_up", dependencies=[Depends(require_official_login)])
def sign_up(
    payload: SignUpRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    user, token = service.sign_up(**payload.model_dump())
    set_session_cookie(response, token)
    return session_response(user)


@router.post("/sign_in", dependencies=[Depends(require_official_login)])
def sign_in(
    payload: SignInRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    user, token = service.sign_in(**payload.model_dump())
    set_session_cookie(response, token)
    return session_response(user)


@router.post("/guest", dependencies=[Depends(require_official_login)])
def guest_session(
    payload: GuestSessionRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    user, token = service.guest_sign_in(**payload.model_dump())
    set_session_cookie(response, token)
    return session_response(user, temporary=True)


@router.post("/guest/close", dependencies=[Depends(require_official_login)])
def close_guest_session(
    response: Response,
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    service: AuthService = Depends(get_auth_service),
):
    deleted = service.close_guest_session(session_token)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"success": True, "deleted": deleted}


@router.post("/sign_out", dependencies=[Depends(require_official_login)])
def sign_out(
    request: Request,
    response: Response,
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    service: AuthService = Depends(get_auth_service),
):
    try:
        user = service.current_user(session_token)
    except AuthServiceError as exc:
        if exc.kind != "unauthenticated":
            raise
    else:
        require_account_context(request, user)
    service.sign_out(session_token)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"success": True, "message": "已退出登录"}


@router.patch("/account", dependencies=[Depends(require_official_login)])
def update_account_profile(
    payload: AccountUpdateRequest,
    user: CurrentUser = Depends(require_current_user),
    service: AuthService = Depends(get_auth_service),
):
    return session_response(
        service.update_identity(user=user, **payload.model_dump())
    )


@router.patch("/password", dependencies=[Depends(require_official_login)])
def change_password(
    payload: PasswordUpdateRequest,
    user: CurrentUser = Depends(require_current_user),
    service: AuthService = Depends(get_auth_service),
):
    service.change_password(user=user, **payload.model_dump())
    return {"success": True, "message": "密码已更新"}

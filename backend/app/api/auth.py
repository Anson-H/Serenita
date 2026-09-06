from __future__ import annotations
from fastapi import Request
from backend.app.api.dependencies import require_account_context

from datetime import timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Response
from pydantic import BaseModel, ConfigDict

from backend.app.api.dependencies import (
    SESSION_COOKIE_NAME,
    get_auth_service,
    require_current_user,
)
from backend.app.application.auth_service import (
    SESSION_TTL,
    AuthService,
    AuthServiceError,
    CurrentUser,
)
from backend.app.core.time import parse_local_datetime


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


class AccountUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str
    account_name: str


class PasswordUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str
    new_password: str
    confirm_password: str


def _set_session_cookie(response: Response, token: str, expires_at: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        expires=parse_local_datetime(expires_at).astimezone(timezone.utc),
        max_age=int(SESSION_TTL.total_seconds()),
    )


def _session_response(user: CurrentUser) -> dict[str, object]:
    return {
        "authenticated": True,
        "account_id": user.account_id,
        "account": user.account,
        "account_name": user.account_name,
        "expires_at": user.expires_at,
    }


@router.get("/session")
def get_session(
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    service: AuthService = Depends(get_auth_service),
):
    try:
        return _session_response(service.current_user(session_token))
    except AuthServiceError as exc:
        if exc.kind == "unauthenticated":
            return {"authenticated": False}
        raise


@router.post("/sign_up")
def sign_up(
    payload: SignUpRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    user, token = service.sign_up(**payload.model_dump())
    _set_session_cookie(response, token, user.expires_at)
    return _session_response(user)


@router.post("/sign_in")
def sign_in(
    payload: SignInRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    user, token = service.sign_in(**payload.model_dump())
    _set_session_cookie(response, token, user.expires_at)
    return _session_response(user)


@router.post("/sign_out")
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


@router.patch("/account")
def update_account_profile(
    payload: AccountUpdateRequest,
    user: CurrentUser = Depends(require_current_user),
    service: AuthService = Depends(get_auth_service),
):
    return _session_response(
        service.update_identity(user=user, **payload.model_dump())
    )


@router.patch("/password")
def change_password(
    payload: PasswordUpdateRequest,
    user: CurrentUser = Depends(require_current_user),
    service: AuthService = Depends(get_auth_service),
):
    service.change_password(user=user, **payload.model_dump())
    return {"success": True, "message": "密码已更新"}

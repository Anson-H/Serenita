from typing import Optional

from fastapi import Cookie, Depends, Request
from backend.app.core.errors import raise_error

from backend.app.application.account_settings_service import AccountSettingsService
from backend.app.application.auth_service import AuthService, CurrentUser
from backend.app.application.conversation_service import ConversationService
from backend.app.application.report_service import ReportService
from backend.app.plugins.web.service import WebAccessService


SESSION_COOKIE_NAME = "serenita_auth_session_token"


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.services.auth


def require_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    service: AuthService = Depends(get_auth_service),
) -> CurrentUser:
    user = service.current_user(session_token)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_account_context(request, user)
    return user


def get_account_settings_service(request: Request) -> AccountSettingsService:
    return request.app.state.services.account_settings


def get_conversation_service(request: Request) -> ConversationService:
    return request.app.state.services.conversations


def get_report_service(request: Request, member_id: str, user: CurrentUser = Depends(require_current_user)) -> ReportService:
    return request.app.state.services.report(user.account_id, member_id)


def get_web_access_service(request: Request) -> WebAccessService:
    return request.app.state.services.web


def get_favorite_service(request: Request):
    return request.app.state.services.favorites


def get_model_settings_service(request: Request):
    return request.app.state.services.model_settings


def require_account_context(request: Request, user: CurrentUser) -> None:
    expected = request.headers.get("X-Serenita-Account-ID")
    if not expected:
        raise_error('invalid_structure', "REQUEST_VALIDATION_FAILED", "请求缺少预期账号标识。")
    if expected != user.account_id:
        raise_error('conflict', "ACCOUNT_CONTEXT_CHANGED", "登录账号已改变，请刷新后重新操作。")

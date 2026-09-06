from __future__ import annotations
from backend.app.core.errors import SerenitaError

import secrets
import shutil
import uuid
from dataclasses import dataclass
from datetime import timedelta

from backend.app.core.security import hash_secret, verify_secret
from backend.app.core.time import local_now, local_now_iso, parse_local_datetime
from backend.app.repositories.auth_repository import (
    AccountConflictError,
    AccountNotFoundError,
    AuthRepository,
)
from backend.app.storage.crypto import sha256_text
from backend.app.storage.paths import app_paths


SESSION_TTL = timedelta(days=183)


class AuthServiceError(SerenitaError):
    pass


@dataclass(frozen=True)
class CurrentUser:
    account_id: str
    account: str
    account_name: str
    session_token_hash: str
    expires_at: str


def normalize_account(account: str) -> str:
    normalized = str(account).strip().lower()
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_-"
    if (
        not normalized
        or len(normalized) > 20
        or any(character not in allowed for character in normalized)
    ):
        raise AuthServiceError(
            'invalid_input',
            "INVALID_REQUEST",
            "用户标识只能包含字母、数字、下划线和短横线，长度不超过 20。",
        )
    if normalized == "all_users":
        raise AuthServiceError('invalid_input', "INVALID_REQUEST", "该用户标识不可使用。")
    return normalized


def normalize_account_name(account_name: str) -> str:
    normalized = str(account_name).strip()
    if not normalized:
        raise AuthServiceError('invalid_input', "INVALID_REQUEST", "账号名称不能为空。")
    if len(normalized) > 50:
        raise AuthServiceError(
            'invalid_input', "INVALID_REQUEST", "账号名称长度不能超过 50 个字符。"
        )
    return normalized


def _new_session_values() -> tuple[str, str, str, str]:
    token = secrets.token_urlsafe(32)
    timestamp = local_now_iso()
    expires_at = (local_now() + SESSION_TTL).isoformat()
    return token, sha256_text(token), timestamp, expires_at


def _current_user(row, session_token_hash: str) -> CurrentUser:
    return CurrentUser(
        account_id=str(row["account_id"]),
        account=str(row["account"]),
        account_name=str(row["account_name"]),
        session_token_hash=session_token_hash,
        expires_at=str(row["expires_at"]),
    )


class AuthService:
    def __init__(self, repository: AuthRepository | None = None, *, paths=None):
        self.paths = paths or (repository.paths if repository is not None else app_paths())
        self.repository = repository or AuthRepository(paths=self.paths)

    def _require_account_tree(self, account_id: str) -> None:
        try:
            self.paths.require_account_tree(account_id)
        except FileNotFoundError as exc:
            raise AuthServiceError(
                'conflict', "ACCOUNT_STORAGE_UNAVAILABLE", "账号数据目录不存在。"
            ) from exc

    def sign_up(
        self,
        *,
        account: str,
        account_name: str,
        password: str,
        confirm_password: str,
    ) -> tuple[CurrentUser, str]:
        account = normalize_account(account)
        account_name = normalize_account_name(account_name)
        if not password:
            raise AuthServiceError('invalid_input', "INVALID_REQUEST", "密码不能为空。")
        if password != confirm_password:
            raise AuthServiceError(
                'invalid_input', "INVALID_REQUEST", "两次输入的密码不一致。"
            )

        account_id = str(uuid.uuid4())
        token, token_hash, timestamp, expires_at = _new_session_values()
        try:
            account_root = self.paths.create_account_tree(account_id)
        except FileExistsError as exc:
            raise AuthServiceError(
                'conflict', "ACCOUNT_STORAGE_EXISTS", "账号数据目录已存在，无法创建账号。"
            ) from exc
        try:
            self.repository.create_account_with_session(
                account_id=account_id,
                account=account,
                password_hash=hash_secret(password),
                account_name=account_name,
                session_token_hash=token_hash,
                expires_at=expires_at,
                timestamp=timestamp,
            )
        except Exception as exc:
            shutil.rmtree(account_root, ignore_errors=True)
            if isinstance(exc, AccountConflictError):
                raise AuthServiceError(
                    'conflict', "ACCOUNT_EXISTS", "账号已存在。"
                ) from exc
            raise

        return CurrentUser(
            account_id=account_id,
            account=account,
            account_name=account_name,
            session_token_hash=token_hash,
            expires_at=expires_at,
        ), token

    def sign_in(self, *, account: str, password: str) -> tuple[CurrentUser, str]:
        account = normalize_account(account)
        if not password:
            raise AuthServiceError('invalid_input', "INVALID_REQUEST", "密码不能为空。")
        row = self.repository.account_by_login(account)
        if row is None or not verify_secret(password, str(row["password_hash"])):
            raise AuthServiceError('unauthenticated', "SIGN_IN_FAILED", "账号或密码不正确。")
        account_id = str(row["account_id"])
        self._require_account_tree(account_id)
        token, token_hash, timestamp, expires_at = _new_session_values()
        self.repository.create_session(
            session_token_hash=token_hash,
            account_id=account_id,
            expires_at=expires_at,
            timestamp=timestamp,
        )
        return CurrentUser(
            account_id=account_id,
            account=str(row["account"]),
            account_name=str(row["account_name"]),
            session_token_hash=token_hash,
            expires_at=expires_at,
        ), token

    def current_user(self, token: str | None) -> CurrentUser:
        if not token:
            raise AuthServiceError('unauthenticated', "UNAUTHORIZED", "请先登录。")
        token_hash = sha256_text(token)
        row = self.repository.session(token_hash)
        if row is None or row["revoked_at"]:
            raise AuthServiceError('unauthenticated', "UNAUTHORIZED", "登录态已失效。")
        if parse_local_datetime(str(row["expires_at"])) <= local_now():
            raise AuthServiceError('unauthenticated', "SESSION_EXPIRED", "登录态已过期。")
        self._require_account_tree(str(row["account_id"]))
        return _current_user(row, token_hash)

    def sign_out(self, token: str | None) -> None:
        if token:
            self.repository.revoke_session(sha256_text(token), local_now_iso())

    def update_identity(
        self,
        *,
        user: CurrentUser,
        account: str,
        account_name: str,
    ) -> CurrentUser:
        try:
            row = self.repository.update_identity(
                account_id=user.account_id,
                account=normalize_account(account),
                account_name=normalize_account_name(account_name),
                timestamp=local_now_iso(),
            )
        except AccountConflictError as exc:
            raise AuthServiceError(
                'conflict', "ACCOUNT_EXISTS", "该用户标识已被使用。"
            ) from exc
        except AccountNotFoundError as exc:
            raise AuthServiceError('unauthenticated', "UNAUTHORIZED", "账号不存在。") from exc
        return CurrentUser(
            account_id=user.account_id,
            account=str(row["account"]),
            account_name=str(row["account_name"]),
            session_token_hash=user.session_token_hash,
            expires_at=user.expires_at,
        )

    def change_password(
        self,
        *,
        user: CurrentUser,
        current_password: str,
        new_password: str,
        confirm_password: str,
    ) -> None:
        if not current_password or not new_password or not confirm_password:
            raise AuthServiceError(
                'invalid_input',
                "INVALID_REQUEST",
                "当前密码、新密码和确认密码均不能为空。",
            )
        if new_password != confirm_password:
            raise AuthServiceError(
                'invalid_input', "INVALID_REQUEST", "两次输入的新密码不一致。"
            )
        row = self.repository.account_by_id(user.account_id)
        if row is None or not verify_secret(
            current_password, str(row["password_hash"])
        ):
            raise AuthServiceError('unauthenticated', "SIGN_IN_FAILED", "当前密码不正确。")
        try:
            self.repository.change_password(
                account_id=user.account_id,
                password_hash=hash_secret(new_password),
                current_session_token_hash=user.session_token_hash,
                timestamp=local_now_iso(),
            )
        except AccountNotFoundError as exc:
            raise AuthServiceError('unauthenticated', "UNAUTHORIZED", "账号不存在。") from exc

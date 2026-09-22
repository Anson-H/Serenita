from __future__ import annotations
from backend.app.core.errors import SerenitaError

import secrets
import shutil
import uuid
from dataclasses import dataclass
from datetime import timedelta
import re

from backend.app.core.security import hash_secret, verify_secret
from backend.app.core.time import local_now, local_now_iso, parse_local_datetime
from backend.app.repositories.auth_repository import (
    AccountConflictError,
    AccountNotFoundError,
    AuthRepository,
    CredentialsChangedError,
)
from backend.app.storage.crypto import sha256_text
from backend.app.storage.paths import app_paths


SESSION_TTL = timedelta(days=183)
GUEST_ACCOUNT_PREFIX = "guest_"
GUEST_ACCOUNT_NAME = "临时访客"
_GUEST_ACCOUNT_PATTERN = re.compile(rf"{re.escape(GUEST_ACCOUNT_PREFIX)}[0-9a-f]{{14}}")


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


def is_guest_identity(account: str, account_name: str) -> bool:
    return bool(_GUEST_ACCOUNT_PATTERN.fullmatch(str(account))) and str(account_name) == GUEST_ACCOUNT_NAME


def normalize_guest_account(account: str) -> str:
    normalized = normalize_account(account)
    if not _GUEST_ACCOUNT_PATTERN.fullmatch(normalized):
        raise AuthServiceError(
            'invalid_input',
            "INVALID_REQUEST",
            "临时账号标识无效。",
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
        _allow_guest_identity: bool = False,
    ) -> tuple[CurrentUser, str]:
        account = normalize_account(account)
        account_name = normalize_account_name(account_name)
        if is_guest_identity(account, account_name) and not _allow_guest_identity:
            raise AuthServiceError(
                'invalid_input',
                "TEMPORARY_ACCOUNT_RESERVED",
                "该用户标识和账号名称由临时使用保留。",
            )
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

    def verify_credentials(self, *, account: str, password: str) -> dict:
        account = normalize_account(account)
        if not password:
            raise AuthServiceError('invalid_input', "INVALID_REQUEST", "密码不能为空。")
        row = self.repository.account_by_login(account)
        if row is None or not verify_secret(password, str(row["password_hash"])):
            raise AuthServiceError('unauthenticated', "SIGN_IN_FAILED", "账号或密码不正确。")
        return dict(row)

    def sign_in(self, *, account: str, password: str) -> tuple[CurrentUser, str]:
        row = self.verify_credentials(account=account, password=password)
        account_id = str(row["account_id"])
        self._require_account_tree(account_id)
        token, token_hash, timestamp, expires_at = _new_session_values()
        try:
            self.repository.create_session(
                session_token_hash=token_hash,
                account_id=account_id,
                verified_password_hash=str(row["password_hash"]),
                expires_at=expires_at,
                timestamp=timestamp,
            )
        except CredentialsChangedError as exc:
            raise AuthServiceError('unauthenticated', "SIGN_IN_FAILED", "账号或密码不正确。") from exc
        return CurrentUser(
            account_id=account_id,
            account=str(row["account"]),
            account_name=str(row["account_name"]),
            session_token_hash=token_hash,
            expires_at=expires_at,
        ), token

    def guest_sign_in(self, *, account: str, password: str) -> tuple[CurrentUser, str]:
        account = normalize_guest_account(account)
        if not password:
            raise AuthServiceError('invalid_input', "INVALID_REQUEST", "临时账号凭证不能为空。")

        existing = self.repository.account_by_login(account)
        if existing is not None:
            if not is_guest_identity(str(existing["account"]), str(existing["account_name"])):
                raise AuthServiceError('conflict', "GUEST_ACCOUNT_CONFLICT", "临时账号标识已被占用。")
            return self.sign_in(account=account, password=password)

        try:
            return self.sign_up(
                account=account,
                account_name=GUEST_ACCOUNT_NAME,
                password=password,
                confirm_password=password,
                _allow_guest_identity=True,
            )
        except AuthServiceError as exc:
            if exc.code != "ACCOUNT_EXISTS":
                raise
            existing = self.repository.account_by_login(account)
            if existing is None or not is_guest_identity(
                str(existing["account"]), str(existing["account_name"])
            ):
                raise AuthServiceError('conflict', "GUEST_ACCOUNT_CONFLICT", "临时账号标识已被占用。") from exc
            return self.sign_in(account=account, password=password)

    def close_guest_session(self, session_token: str | None) -> bool:
        if not session_token:
            return False
        row = self.repository.session(sha256_text(session_token))
        if row is None:
            return False
        if not is_guest_identity(str(row["account"]), str(row["account_name"])):
            raise AuthServiceError(
                'forbidden',
                "TEMPORARY_ACCOUNT_REQUIRED",
                "只有临时账号可以执行此清理操作。",
            )

        account_id = str(row["account_id"])
        account_root = self.paths.account_root(account_id)
        try:
            shutil.rmtree(account_root)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise AuthServiceError(
                'conflict',
                "ACCOUNT_STORAGE_DELETE_FAILED",
                "临时账号内容清理失败，请重试。",
            ) from exc
        from server.backend.models.repository import ModelServiceRepository

        ModelServiceRepository(paths=self.paths).delete_account_records(account_id)
        self.repository.delete_account(account_id)
        return True

    def create_local_session(self, account_id: str) -> tuple[CurrentUser, str]:
        """Issue a session for the sole identity validated by LocalWorkspaceService."""
        self._require_account_tree(account_id)
        row = self.repository.account_by_id(account_id)
        if row is None:
            raise AuthServiceError('conflict', "LOCAL_ACCOUNT_UNAVAILABLE", "本地工作区身份不存在。")
        token, token_hash, timestamp, expires_at = _new_session_values()
        self.repository.create_session(
            session_token_hash=token_hash, account_id=account_id,
            verified_password_hash=str(row["password_hash"]), expires_at=expires_at, timestamp=timestamp,
        )
        return CurrentUser(account_id, str(row["account"]), str(row["account_name"]), token_hash, expires_at), token

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
        if is_guest_identity(user.account, user.account_name):
            raise AuthServiceError(
                'forbidden',
                "TEMPORARY_ACCOUNT_READ_ONLY",
                "临时账号不能修改账号资料。",
            )
        normalized_account = normalize_account(account)
        normalized_account_name = normalize_account_name(account_name)
        if is_guest_identity(normalized_account, normalized_account_name):
            raise AuthServiceError(
                'invalid_input',
                "TEMPORARY_ACCOUNT_RESERVED",
                "该用户标识和账号名称由临时使用保留。",
            )
        try:
            row = self.repository.update_identity(
                account_id=user.account_id,
                account=normalized_account,
                account_name=normalized_account_name,
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
        if is_guest_identity(user.account, user.account_name):
            raise AuthServiceError(
                'forbidden',
                "TEMPORARY_ACCOUNT_READ_ONLY",
                "临时账号不能修改密码。",
            )
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
                verified_password_hash=str(row["password_hash"]),
                current_session_token_hash=user.session_token_hash,
                timestamp=local_now_iso(),
            )
        except AccountNotFoundError as exc:
            raise AuthServiceError('unauthenticated', "UNAUTHORIZED", "账号不存在。") from exc
        except CredentialsChangedError as exc:
            raise AuthServiceError('unauthenticated', "SIGN_IN_FAILED", "当前密码已经改变，请重新登录。") from exc

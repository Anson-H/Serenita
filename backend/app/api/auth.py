import json
import re
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response
from pydantic import BaseModel

from backend.app.core.security import hash_secret
from backend.app.storage.crypto import sha256_text
from backend.app.storage.paths import app_paths, data_root
from backend.app.storage.sqlite import connect

router = APIRouter(prefix="/api/auth", tags=["auth"])

ACCOUNT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
USER_NAME_SPACE_PATTERN = re.compile(r"\s")
SESSION_COOKIE_NAME = "serenita_auth_session_token"
LEGACY_SESSION_COOKIE_NAME = "serenita_session_token"


@dataclass(frozen=True)
class CurrentUser:
    account: str
    user_name: str
    session_token_hash: str
    expires_at: str


class SignUpRequest(BaseModel):
    account: str
    user_name: str
    password: str
    confirm_password: str


class SignInRequest(BaseModel):
    account: str
    password: str


class AccountUpdateRequest(BaseModel):
    user_name: str


class PasswordUpdateRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


def reset_auth_state_for_tests() -> None:
    shutil.rmtree(data_root(), ignore_errors=True)


def normalize_account(account: str) -> str:
    normalized = account.strip().lower()
    if not ACCOUNT_PATTERN.fullmatch(normalized):
        raise_error(400, "INVALID_REQUEST", "账号只能包含字母、数字、下划线和短横线，长度不超过 20。")
    return normalized


def normalize_user_name(user_name: str) -> str:
    normalized = user_name.strip()
    if not normalized:
        raise_error(400, "INVALID_REQUEST", "用户名称不能为空。")
    if USER_NAME_SPACE_PATTERN.search(user_name):
        raise_error(400, "INVALID_REQUEST", "用户名称不能包含空格。")
    return normalized


def raise_error(status_code: int, code: str, message: str):
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def expires_iso() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=183)).isoformat()


def _migrate_legacy_auth_storage() -> None:
    paths = app_paths()
    legacy_dir = paths.legacy_login_db.parent
    auth_dir = paths.auth_db.parent

    if paths.legacy_login_db.exists() and not paths.auth_db.exists():
        auth_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(paths.legacy_login_db), str(paths.auth_db))
        for suffix in ("-shm", "-wal"):
            legacy_sidecar = paths.legacy_login_db.with_name(f"{paths.legacy_login_db.name}{suffix}")
            if legacy_sidecar.exists():
                shutil.move(str(legacy_sidecar), str(paths.auth_db.with_name(f"{paths.auth_db.name}{suffix}")))

    if legacy_dir.exists():
        auth_dir.mkdir(parents=True, exist_ok=True)
        for child in legacy_dir.iterdir():
            if child.is_dir():
                destination = auth_dir / child.name
                if not destination.exists():
                    shutil.move(str(child), str(destination))
        try:
            legacy_dir.rmdir()
        except OSError:
            pass


def _migrate_legacy_auth_schema(connection) -> None:
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "login_accounts" in tables and "auth_accounts" not in tables:
        connection.execute("ALTER TABLE login_accounts RENAME TO auth_accounts")


def _init_auth_db() -> None:
    _migrate_legacy_auth_storage()
    with connect(app_paths().auth_db) as connection:
        _migrate_legacy_auth_schema(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_accounts (
                account TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                user_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                session_token_hash TEXT PRIMARY KEY,
                account TEXT NOT NULL,
                user_name TEXT,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (account) REFERENCES auth_accounts(account)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_account ON auth_sessions(account)"
        )


def _init_account_dirs(account: str) -> None:
    paths = app_paths()
    for directory in (
        paths.account_auth_dir(account),
        paths.account_root(account) / "config",
        paths.account_root(account) / "conversations" / "db_storage",
        paths.account_root(account) / "conversations" / "sessions",
        paths.account_root(account) / "conversations" / "attachments",
        paths.account_root(account) / "favorites" / "db_storage",
    ):
        directory.mkdir(parents=True, exist_ok=True)


def _write_session_summary(account: str, user_name: str, token_hash: str, expires_at: str) -> None:
    session_path = app_paths().account_auth_dir(account) / "session.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps(
            {
                "account": account,
                "user_name": user_name,
                "session_token_hash": token_hash,
                "authenticated": True,
                "expires_at": expires_at,
                "last_login_at": now_iso(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _extract_token(authorization: Optional[str], cookie_token: Optional[str] = None) -> Optional[str]:
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token
    return cookie_token


def _create_session(account: str, user_name: str) -> tuple[str, str]:
    _init_auth_db()
    token = secrets.token_urlsafe(32)
    token_hash = sha256_text(token)
    expires_at = expires_iso()
    timestamp = now_iso()
    with connect(app_paths().auth_db) as connection:
        connection.execute(
            """
            INSERT INTO auth_sessions (
                session_token_hash, account, user_name, expires_at, revoked_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, NULL, ?, ?)
            """,
            (token_hash, account, user_name, expires_at, timestamp, timestamp),
        )
    _write_session_summary(account, user_name, token_hash, expires_at)
    return token, expires_at


def _session_response(token: str, account: str, user_name: str, expires_at: str):
    return {
        "authenticated": True,
        "account": account,
        "user_name": user_name,
        "session_token": token,
        "expires_at": expires_at,
    }


def require_current_user(
    authorization: Optional[str] = Header(default=None),
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    legacy_session_token: Optional[str] = Cookie(default=None, alias=LEGACY_SESSION_COOKIE_NAME),
) -> CurrentUser:
    _init_auth_db()
    token = _extract_token(authorization, session_token or legacy_session_token)
    if not token:
        raise_error(401, "UNAUTHORIZED", "请先登录。")

    token_hash = sha256_text(token)
    with connect(app_paths().auth_db) as connection:
        row = connection.execute(
            """
            SELECT s.session_token_hash, s.account, a.user_name, s.expires_at, s.revoked_at
            FROM auth_sessions s
            JOIN auth_accounts a ON a.account = s.account
            WHERE s.session_token_hash = ?
            """,
            (token_hash,),
        ).fetchone()

    if not row or row["revoked_at"]:
        raise_error(401, "UNAUTHORIZED", "登录态已失效。")
    if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
        raise_error(401, "SESSION_EXPIRED", "登录态已过期。")

    return CurrentUser(
        account=row["account"],
        user_name=row["user_name"],
        session_token_hash=row["session_token_hash"],
        expires_at=row["expires_at"],
    )


@router.get("/session")
def get_session(
    authorization: Optional[str] = Header(default=None),
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    legacy_session_token: Optional[str] = Cookie(default=None, alias=LEGACY_SESSION_COOKIE_NAME),
):
    try:
        user = require_current_user(
            authorization=authorization,
            session_token=session_token,
            legacy_session_token=legacy_session_token,
        )
    except HTTPException:
        return {"authenticated": False}

    return {
        "authenticated": True,
        "account": user.account,
        "user_name": user.user_name,
        "expires_at": user.expires_at,
    }


@router.post("/sign_up")
def sign_up(payload: SignUpRequest, response: Response):
    _init_auth_db()
    account = normalize_account(payload.account)
    user_name = normalize_user_name(payload.user_name)

    if not payload.password:
        raise_error(400, "INVALID_REQUEST", "密码不能为空。")
    if payload.password != payload.confirm_password:
        raise_error(400, "INVALID_REQUEST", "两次输入的密码不一致。")

    timestamp = now_iso()
    with connect(app_paths().auth_db) as connection:
        existing = connection.execute(
            "SELECT account FROM auth_accounts WHERE account = ?",
            (account,),
        ).fetchone()
        if existing:
            raise_error(409, "ACCOUNT_EXISTS", "账号已存在。")
        connection.execute(
            """
            INSERT INTO auth_accounts(account, password_hash, user_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (account, hash_secret(payload.password), user_name, timestamp, timestamp),
        )

    _init_account_dirs(account)
    token, expires_at = _create_session(account, user_name)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        expires=expires_at,
    )
    return _session_response(token, account, user_name, expires_at)


@router.post("/sign_in")
def sign_in(payload: SignInRequest, response: Response):
    _init_auth_db()
    account = normalize_account(payload.account)
    if not payload.password:
        raise_error(400, "INVALID_REQUEST", "密码不能为空。")

    with connect(app_paths().auth_db) as connection:
        user = connection.execute(
            "SELECT account, user_name, password_hash FROM auth_accounts WHERE account = ?",
            (account,),
        ).fetchone()

    if not user or user["password_hash"] != hash_secret(payload.password):
        raise_error(401, "SIGN_IN_FAILED", "账号或密码不正确。")

    _init_account_dirs(account)
    token, expires_at = _create_session(account, user["user_name"])
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        expires=expires_at,
    )
    return _session_response(token, account, user["user_name"], expires_at)


@router.post("/sign_out")
def sign_out(
    response: Response,
    authorization: Optional[str] = Header(default=None),
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    legacy_session_token: Optional[str] = Cookie(default=None, alias=LEGACY_SESSION_COOKIE_NAME),
):
    _init_auth_db()
    token = _extract_token(authorization, session_token or legacy_session_token)
    if token:
        with connect(app_paths().auth_db) as connection:
            connection.execute(
                "UPDATE auth_sessions SET revoked_at = ?, updated_at = ? WHERE session_token_hash = ?",
                (now_iso(), now_iso(), sha256_text(token)),
            )
    response.delete_cookie(SESSION_COOKIE_NAME)
    response.delete_cookie(LEGACY_SESSION_COOKIE_NAME)
    return {"success": True, "message": "已 sign out"}


@router.patch("/account")
def update_account_profile(
    payload: AccountUpdateRequest,
    user: CurrentUser = Depends(require_current_user),
):
    return _update_account_profile(payload, user)


def _update_account_profile(payload: AccountUpdateRequest, user: CurrentUser):
    user_name = normalize_user_name(payload.user_name)

    timestamp = now_iso()
    with connect(app_paths().auth_db) as connection:
        connection.execute(
            "UPDATE auth_accounts SET user_name = ?, updated_at = ? WHERE account = ?",
            (user_name, timestamp, user.account),
        )
        connection.execute(
            """
            UPDATE auth_sessions
            SET user_name = ?, updated_at = ?
            WHERE account = ? AND revoked_at IS NULL
            """,
            (user_name, timestamp, user.account),
        )
    _write_session_summary(user.account, user_name, user.session_token_hash, user.expires_at)
    return {"account": user.account, "user_name": user_name, "updated_at": timestamp}


@router.patch("/password")
def change_password(
    payload: PasswordUpdateRequest,
    user: CurrentUser = Depends(require_current_user),
):
    return _change_password(payload, user)


def _change_password(payload: PasswordUpdateRequest, user: CurrentUser):
    if not payload.current_password or not payload.new_password or not payload.confirm_password:
        raise_error(400, "INVALID_REQUEST", "当前密码、新密码和确认密码均不能为空。")
    if payload.new_password != payload.confirm_password:
        raise_error(400, "INVALID_REQUEST", "两次输入的新密码不一致。")

    with connect(app_paths().auth_db) as connection:
        row = connection.execute(
            "SELECT password_hash FROM auth_accounts WHERE account = ?",
            (user.account,),
        ).fetchone()
        if not row or row["password_hash"] != hash_secret(payload.current_password):
            raise_error(401, "SIGN_IN_FAILED", "当前密码不正确。")

        timestamp = now_iso()
        connection.execute(
            "UPDATE auth_accounts SET password_hash = ?, updated_at = ? WHERE account = ?",
            (hash_secret(payload.new_password), timestamp, user.account),
        )
        connection.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = ?, updated_at = ?
            WHERE account = ? AND session_token_hash != ? AND revoked_at IS NULL
            """,
            (timestamp, timestamp, user.account, user.session_token_hash),
        )
    return {"success": True, "message": "密码已更新"}

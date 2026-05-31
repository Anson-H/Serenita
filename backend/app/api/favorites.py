import json
import sqlite3
import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.app.api.auth import CurrentUser, now_iso, raise_error, require_current_user
from backend.app.api.conversations import conversation_exists, source_message_for_favorite
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


class CreateFavoriteRequest(BaseModel):
    source_type: str
    source_session_id: str
    source_id: str
    tags: list[str] = []


class PatchFavoriteRequest(BaseModel):
    title: Optional[str] = None
    tags: Optional[list[str]] = None


class BatchDeleteRequest(BaseModel):
    favorite_ids: list[str]


def _init_favorites_db(account: str) -> None:
    with connect(app_paths().favorites_db(account)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS favorites (
                favorite_id TEXT PRIMARY KEY,
                account TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_session_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content_snapshot TEXT NOT NULL,
                content_summary TEXT NOT NULL,
                tags TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(account, source_type, source_session_id, source_id)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_favorites_account_time
            ON favorites(account, created_at)
            """
        )


def _summary(content: str) -> str:
    return content[:80]


def _favorite_response(row, include_snapshot: bool = True) -> dict:
    response = {
        "favorite_id": row["favorite_id"],
        "source_type": row["source_type"],
        "source_session_id": row["source_session_id"],
        "source_id": row["source_id"],
        "title": row["title"],
        "content_summary": row["content_summary"],
        "tags": json.loads(row["tags"] or "[]"),
        "created_at": row["created_at"],
    }
    if include_snapshot:
        response.update(
            {
                "account": row["account"],
                "source_available": conversation_exists(row["account"], row["source_session_id"])
                and source_message_for_favorite(
                    row["account"],
                    row["source_session_id"],
                    row["source_id"],
                )
                is not None,
                "content_snapshot": row["content_snapshot"],
                "updated_at": row["updated_at"],
            }
        )
    return response


def _favorite_row(account: str, favorite_id: str):
    _init_favorites_db(account)
    with connect(app_paths().favorites_db(account)) as connection:
        return connection.execute(
            "SELECT * FROM favorites WHERE account = ? AND favorite_id = ?",
            (account, favorite_id),
        ).fetchone()


@router.get("")
def list_favorites(user: CurrentUser = Depends(require_current_user)):
    _init_favorites_db(user.account)
    with connect(app_paths().favorites_db(user.account)) as connection:
        rows = connection.execute(
            """
            SELECT * FROM favorites
            WHERE account = ?
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (user.account,),
        ).fetchall()
    return {
        "favorites": [_favorite_response(row, include_snapshot=False) for row in rows],
        "has_more": False,
        "next_cursor": None,
    }


@router.post("")
def create_favorite(
    payload: CreateFavoriteRequest,
    user: CurrentUser = Depends(require_current_user),
):
    if payload.source_type != "message":
        raise_error(400, "INVALID_REQUEST", "v0.1.0 仅支持收藏 AI 回答。")
    source = source_message_for_favorite(user.account, payload.source_session_id, payload.source_id)
    if not source:
        raise_error(404, "NOT_FOUND", "来源消息不存在或不可收藏。")

    _init_favorites_db(user.account)
    timestamp = now_iso()
    favorite_id = str(uuid.uuid4())
    content = source["content"]
    title = source["title"] if source["title"] != "新对话" else content[:20]
    try:
        with connect(app_paths().favorites_db(user.account)) as connection:
            connection.execute(
                """
                INSERT INTO favorites (
                    favorite_id, account, source_type, source_session_id, source_id,
                    title, content_snapshot, content_summary, tags, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    favorite_id,
                    user.account,
                    payload.source_type,
                    payload.source_session_id,
                    payload.source_id,
                    title,
                    content,
                    _summary(content),
                    json.dumps(payload.tags, ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
    except sqlite3.IntegrityError:
        raise_error(409, "CONFLICT", "该回答已收藏。")

    return _favorite_response(_favorite_row(user.account, favorite_id))


@router.get("/{favorite_id}")
def get_favorite(favorite_id: str, user: CurrentUser = Depends(require_current_user)):
    row = _favorite_row(user.account, favorite_id)
    if not row:
        raise_error(404, "NOT_FOUND", "收藏不存在。")
    return _favorite_response(row)


@router.patch("/{favorite_id}")
def patch_favorite(
    favorite_id: str,
    payload: PatchFavoriteRequest,
    user: CurrentUser = Depends(require_current_user),
):
    row = _favorite_row(user.account, favorite_id)
    if not row:
        raise_error(404, "NOT_FOUND", "收藏不存在。")
    next_title = payload.title.strip() if payload.title is not None else row["title"]
    if not next_title:
        raise_error(400, "INVALID_REQUEST", "收藏标题不能为空。")
    next_tags = payload.tags if payload.tags is not None else json.loads(row["tags"] or "[]")
    with connect(app_paths().favorites_db(user.account)) as connection:
        connection.execute(
            """
            UPDATE favorites
            SET title = ?, tags = ?, updated_at = ?
            WHERE account = ? AND favorite_id = ?
            """,
            (
                next_title,
                json.dumps(next_tags, ensure_ascii=False),
                now_iso(),
                user.account,
                favorite_id,
            ),
        )
    return _favorite_response(_favorite_row(user.account, favorite_id))


@router.delete("/{favorite_id}")
def delete_favorite(favorite_id: str, user: CurrentUser = Depends(require_current_user)):
    row = _favorite_row(user.account, favorite_id)
    if not row:
        raise_error(404, "NOT_FOUND", "收藏不存在。")
    with connect(app_paths().favorites_db(user.account)) as connection:
        connection.execute(
            "DELETE FROM favorites WHERE account = ? AND favorite_id = ?",
            (user.account, favorite_id),
        )
    return {"success": True, "favorite_id": favorite_id, "message": "已取消收藏"}


@router.post("/batch-delete")
def batch_delete_favorites(
    payload: BatchDeleteRequest,
    user: CurrentUser = Depends(require_current_user),
):
    _init_favorites_db(user.account)
    deleted_ids = []
    failed = []
    with connect(app_paths().favorites_db(user.account)) as connection:
        for favorite_id in payload.favorite_ids:
            row = connection.execute(
                "SELECT favorite_id FROM favorites WHERE account = ? AND favorite_id = ?",
                (user.account, favorite_id),
            ).fetchone()
            if not row:
                failed.append({"favorite_id": favorite_id, "code": "NOT_FOUND"})
                continue
            connection.execute(
                "DELETE FROM favorites WHERE account = ? AND favorite_id = ?",
                (user.account, favorite_id),
            )
            deleted_ids.append(favorite_id)
    return {"success": True, "deleted_ids": deleted_ids, "failed": failed}

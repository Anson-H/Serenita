"""Authenticated public notification endpoints and metadata-only change stream."""

import asyncio
import json
from typing import Literal
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, StrictBool
from backend.app.api.dependencies import require_current_user, SESSION_COOKIE_NAME

router = APIRouter(tags=["notifications"])


def service(request: Request):
    return request.app.state.services.notifications


class PreferencesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notifications_enabled: StrictBool | None = None
    medication_due_enabled: StrictBool | None = None
    medication_expired_enabled: StrictBool | None = None
    answer_completed_enabled: StrictBool | None = None


class ActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["read"]


@router.get("/api/account-settings/notifications")
def preferences(user=Depends(require_current_user), notifications=Depends(service)):
    return notifications.preferences(user.account_id)


@router.put("/api/account-settings/notifications")
def save_preferences(
    payload: PreferencesInput,
    user=Depends(require_current_user),
    notifications=Depends(service),
):
    return notifications.set_preferences(user.account_id, **payload.model_dump(exclude_unset=True))


@router.get("/api/notifications")
def inbox(
    status: str = "pending",
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    user=Depends(require_current_user),
    notifications=Depends(service),
):
    return notifications.list(
        user.account_id, status=status, limit=limit, cursor=cursor
    )


@router.get("/api/notifications/summary")
def summary(user=Depends(require_current_user), notifications=Depends(service)):
    return notifications.summary(user.account_id)


@router.post("/api/notifications/{notification_id}/actions")
def action(
    notification_id: str,
    payload: ActionInput,
    user=Depends(require_current_user),
    notifications=Depends(service),
):
    return notifications.act(user.account_id, notification_id, payload.action)


@router.get("/api/notifications/events")
async def events(
    request: Request, user=Depends(require_current_user), notifications=Depends(service)
):
    async def stream():
        runtime = notifications.runtime
        queue = asyncio.Queue(maxsize=1)
        listener = (asyncio.get_running_loop(), queue)
        runtime.subscribe(user.account_id, listener)
        deadline = asyncio.get_running_loop().time() + 25
        try:
            yield (
                "retry: 1000\nevent: notifications_changed\ndata: "
                + json.dumps({"revision": runtime.revision(user.account_id)})
                + "\n\n"
            )
            while (
                asyncio.get_running_loop().time() < deadline
                and not await request.is_disconnected()
            ):
                heartbeat = False
                try:
                    await asyncio.wait_for(
                        queue.get(),
                        timeout=min(
                            10, max(0.01, deadline - asyncio.get_running_loop().time())
                        ),
                    )
                except TimeoutError:
                    heartbeat = True
                try:
                    current = await asyncio.to_thread(
                        request.app.state.services.auth.current_user,
                        request.cookies.get(SESSION_COOKIE_NAME),
                    )
                    if current.account_id != user.account_id:
                        raise PermissionError("账号已改变")
                except Exception:
                    yield "event: authentication_expired\ndata: {}\n\n"
                    break
                if heartbeat:
                    yield ": keep-alive\n\n"
                else:
                    yield (
                        "event: notifications_changed\ndata: "
                        + json.dumps({"revision": runtime.revision(user.account_id)})
                        + "\n\n"
                    )
            if asyncio.get_running_loop().time() >= deadline:
                yield "event: stream_renewal\ndata: {}\n\n"
        finally:
            runtime.unsubscribe(user.account_id, listener)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )

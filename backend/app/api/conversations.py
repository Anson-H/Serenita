from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from backend.app.api.auth import CurrentUser, require_current_user
from backend.app.api.dependencies import get_conversation_service
from backend.app.application.conversation_service import ConversationService

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ContextResourceRef(BaseModel):
    resource_type: str
    resource_id: str
    quote_text: Optional[str] = None
    name: Optional[str] = None


class SendMessageRequest(BaseModel):
    session_id: Optional[str] = None
    parent_message_id: Optional[str] = None
    raw_text: str
    model_id: Optional[str] = None
    thinking_mode: str = "default"
    context_resources: list[ContextResourceRef] = Field(default_factory=list)
    edited_from_message_id: Optional[str] = None


class RegenerateRequest(BaseModel):
    model_id: Optional[str] = None
    thinking_mode: Optional[str] = None


class CancelTurnRequest(BaseModel):
    preserve_partial: bool = True
    partial_content: str = ""
    partial_thinking: str = ""


class ActivePathRequest(BaseModel):
    active_path_message_ids: list[str]


def _dump_model(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()


@router.post("/context-resources")
async def upload_context_resource(
    session_id: Optional[str] = Form(default=None),
    model_id: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return await service.upload_context_resource(user.account, session_id, model_id, file)


@router.post("/messages")
def send_message(
    payload: SendMessageRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.send_message(
        user.account,
        payload.session_id,
        payload.parent_message_id,
        payload.raw_text,
        payload.model_id,
        payload.thinking_mode,
        [_dump_model(reference) for reference in payload.context_resources],
        payload.edited_from_message_id,
    )


@router.post("/{session_id}/messages/{message_id}/regenerate")
def regenerate_message(
    session_id: str,
    message_id: str,
    payload: RegenerateRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.regenerate_message(
        user.account,
        session_id,
        message_id,
        payload.model_id,
        payload.thinking_mode,
    )


@router.get("/streams/{stream_id}")
def stream_response(
    stream_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.stream_response(user.account, stream_id)


@router.post("/{session_id}/turns/{turn_id}/cancel")
def cancel_turn(
    session_id: str,
    turn_id: str,
    payload: CancelTurnRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.cancel_turn(
        user.account,
        session_id,
        turn_id,
        payload.preserve_partial,
        payload.partial_content,
        payload.partial_thinking,
    )


@router.get("/{session_id}/turns/{turn_id}")
def get_turn(
    session_id: str,
    turn_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.get_turn(user.account, session_id, turn_id)


@router.get("")
def list_conversations(
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.list_conversations(user.account)


@router.get("/{session_id}")
def get_conversation(
    session_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.get_conversation(user.account, session_id)


@router.delete("/{session_id}")
def delete_conversation(
    session_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.delete_conversation(user.account, session_id)


@router.patch("/{session_id}/active-path")
def update_active_path(
    session_id: str,
    payload: ActivePathRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.update_active_path(user.account, session_id, payload.active_path_message_ids)


def source_message_for_favorite(account: str, session_id: str, message_id: str):
    service = get_conversation_service()
    return service.source_message_for_favorite(account, session_id, message_id)


def conversation_exists(account: str, session_id: str) -> bool:
    service = get_conversation_service()
    return service.conversation_exists(account, session_id)

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.dependencies import get_conversation_service, require_current_user
from backend.app.application.auth_service import CurrentUser
from backend.app.application.conversations.service import ConversationService
from backend.app.application.conversations.inputs import MAX_FILE_BYTES

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ContextResourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_type: str
    resource_id: str
    source_record_id: Optional[str] = None
    annotation_text: Optional[str] = None
    member_id: Optional[str] = None


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: Optional[str] = None
    member_id: Optional[str] = None
    raw_text: str
    model_id: Optional[str] = None
    thinking_mode: str = "default"
    context_resources: list[ContextResourceRef] = Field(default_factory=list)


class EditMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str
    model_id: Optional[str] = None
    thinking_mode: str = "default"
    context_resources: list[ContextResourceRef] = Field(default_factory=list)


class ForkConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at_seq: Optional[int] = Field(default=None, ge=0)


class RegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: Optional[str] = None
    thinking_mode: Optional[str] = None


class CancelTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preserve_partial: bool = True


class QueueOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_ids: list[str]


class PatchConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(default=None, max_length=14)
    is_pinned: Optional[bool] = None


class BatchPinConversationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_ids: list[str] = Field(min_length=1, max_length=50)
    is_pinned: bool


class BatchDeleteConversationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_ids: list[str] = Field(min_length=1, max_length=50)


def _dump_model(value: Any) -> dict[str, Any]:
    return value.model_dump(exclude_none=True)


@router.get("/attachment-capabilities")
def attachment_capabilities(
    model_id: Optional[str] = None,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.inputs.attachment_capabilities(user.account_id, model_id)


@router.post("/context-resources")
async def upload_context_resource(
    member_id: Optional[str] = Form(default=None),
    session_id: Optional[str] = Form(default=None),
    model_id: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    content = await file.read(MAX_FILE_BYTES + 1)
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(service.inputs.upload_context_resource,
        user.account_id, session_id, model_id,
        {"content": content, "mime_type": file.content_type or "application/octet-stream",
         "original_filename": file.filename or "upload"},
        member_id=member_id,
    )


@router.get("/{session_id}/context-resources/{resource_id}")
def open_context_resource(
    session_id: str,
    resource_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    path, filename, mime_type = service.inputs.context_resource_download(
        user.account_id,
        session_id,
        resource_id,
    )
    return FileResponse(
        path=path,
        filename=filename,
        media_type=mime_type,
        content_disposition_type="inline",
    )


@router.post("/messages")
def send_message(
    payload: SendMessageRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    response = service.send_message(
        user.account_id,
        payload.session_id,
        payload.raw_text,
        payload.model_id,
        payload.thinking_mode,
        [_dump_model(reference) for reference in payload.context_resources],
        member_id=payload.member_id,
    )
    if response["disposition"] == "started":
        service.start_turn_job(
            user.account_id, response["session_id"], response["stream_id"]
        )
    return response


@router.post("/{session_id}/messages/{message_id}/regenerate")
def regenerate_message(
    session_id: str,
    message_id: str,
    payload: RegenerateRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    response = service.regenerate_message(
        user.account_id,
        session_id,
        message_id,
        payload.model_id,
        payload.thinking_mode,
    )
    service.start_turn_job(user.account_id, session_id, response["stream_id"])
    return response


@router.post("/{session_id}/messages/{message_id}/edit")
def edit_message(
    session_id: str,
    message_id: str,
    payload: EditMessageRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    response = service.edit_message(
        user.account_id,
        session_id,
        message_id,
        payload.raw_text,
        payload.model_id,
        payload.thinking_mode,
        [_dump_model(reference) for reference in payload.context_resources],
    )
    service.start_turn_job(user.account_id, session_id, response["stream_id"])
    return response


@router.post("/{session_id}/fork")
def fork_conversation(
    session_id: str,
    payload: Optional[ForkConversationRequest] = None,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.fork_conversation(
        user.account_id, session_id, None if payload is None else payload.at_seq
    )


@router.get("/{session_id}/streams/{stream_id}")
def stream_response(
    session_id: str,
    stream_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return StreamingResponse(
        service.stream_events(user.account_id, session_id, stream_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{session_id}/turns/{turn_id}/cancel")
def cancel_turn(
    session_id: str,
    turn_id: str,
    payload: CancelTurnRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.cancel_turn(
        user.account_id,
        session_id,
        turn_id,
        payload.preserve_partial,
    )


@router.patch("/{session_id}/queued-inputs/order")
def reorder_queued_inputs(
    session_id: str,
    payload: QueueOrderRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.reorder_queued_inputs(
        user.account_id, session_id, payload.input_ids
    )


@router.delete("/{session_id}/queued-inputs/{input_id}")
def delete_queued_input(
    session_id: str,
    input_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.remove_queued_input(user.account_id, session_id, input_id)


@router.post("/{session_id}/queued-inputs/{input_id}/restore-to-draft")
def restore_queued_input_to_draft(
    session_id: str,
    input_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.remove_queued_input(
        user.account_id,
        session_id,
        input_id,
        restore_to_draft=True,
    )


@router.post("/{session_id}/queued-inputs/{input_id}/run-now")
def run_queued_input_now(
    session_id: str,
    input_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.run_queued_input_now(user.account_id, session_id, input_id)


@router.get("/{session_id}/turns/{turn_id}")
def get_turn(
    session_id: str,
    turn_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.get_turn(user.account_id, session_id, turn_id)


@router.get("")
def list_conversations(
    cursor: str | None = None, limit: int = 24,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.list_conversations(user.account_id, cursor=cursor, limit=limit)


@router.post("/batch-pin")
def batch_pin_conversations(
    payload: BatchPinConversationsRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.batch_pin_conversations(
        user.account_id,
        payload.session_ids,
        payload.is_pinned,
    )


@router.post("/batch-delete")
def batch_delete_conversations(
    payload: BatchDeleteConversationsRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.batch_delete_conversations(user.account_id, payload.session_ids)


@router.patch("/{session_id}")
def update_conversation(
    session_id: str,
    payload: PatchConversationRequest,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.update_conversation(
        user.account_id,
        session_id,
        title=payload.title,
        is_pinned=payload.is_pinned,
    )


@router.get("/{session_id}")
def get_conversation(
    session_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.get_conversation(user.account_id, session_id)


@router.delete("/{session_id}")
def delete_conversation(
    session_id: str,
    user: CurrentUser = Depends(require_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    return service.delete_conversation(user.account_id, session_id)

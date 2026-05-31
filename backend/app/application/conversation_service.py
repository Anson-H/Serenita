import base64
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi.responses import StreamingResponse

from backend.app.api.auth import now_iso, raise_error
from backend.app.application.model_provider_service import ModelProviderService
from backend.app.providers.base import ProviderChatCompletionError
from backend.app.repositories.conversation_repository import ConversationRepository, UNTITLED_CONVERSATION

MAX_FILE_BYTES = 20 * 1024 * 1024
ALLOWED_MIME_TYPES = {
    "image/bmp": ".bmp",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "image/heic": ".heic",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "audio/amr": ".amr",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/3gpp": ".3gp",
    "audio/3gpp2": ".3gpp",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/aiff": ".aiff",
    "audio/x-aiff": ".aiff",
    "audio/aac": ".aac",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/x-m4a": ".m4a",
    "video/mp4": ".mp4",
    "video/mpeg": ".mpeg",
    "video/x-msvideo": ".avi",
    "video/x-matroska": ".mkv",
    "video/mov": ".mov",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "video/x-flv": ".flv",
    "video/x-ms-wmv": ".wmv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/msword": ".doc",
    "application/vnd.ms-excel": ".xls",
}
STREAM_CHUNK_CHARS = 16
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}
CANCELLED_ASSISTANT_CONTENT = "生成已取消。"
HEALTH_ASSISTANT_SYSTEM_PROMPT = """你是 Serenita 的患者健康问答助手。
回答必须使用清晰、克制、非诊断式的中文 Markdown。
每次最终回答至少包含“核心结论”和“下一步建议”两个部分。
当用户描述可能涉及风险时，优先说明需要关注的风险信号或就医时机。
不要替代医生诊断，不要编造不存在的检查结果。"""
TITLE_GENERATION_SYSTEM_PROMPT = """你负责为 Serenita 健康对话生成会话标题。
根据用户询问和助手回答，输出一个 4 到 12 个汉字的中文短标题。
标题要概括本轮对话的健康主题和处理方向，不要照抄用户问题或助手回答开头。
不要输出引号、标点、解释、前缀或列表，只输出标题。"""
ATTACHMENT_ONLY_USER_PROMPT = "请阅读并总结附件内容。"


class ConversationService:
    def __init__(
        self,
        repository: ConversationRepository | None = None,
        model_catalog: ModelProviderService | None = None,
    ):
        self.repository = repository or ConversationRepository()
        self.model_catalog = model_catalog or ModelProviderService()

    async def upload_context_resource(
        self,
        account: str,
        session_id: Optional[str],
        model_id: Optional[str],
        file,
    ) -> dict[str, Any]:
        self.repository.init_db(account)
        content = await file.read()
        if len(content) > MAX_FILE_BYTES:
            raise_error(413, "FILE_TOO_LARGE", "单文件大小不能超过 20MB。")
        mime_type = file.content_type or "application/octet-stream"
        if mime_type not in ALLOWED_MIME_TYPES:
            raise_error(415, "UNSUPPORTED_FILE_TYPE", "文件类型不支持。")
        model = self._validate_model(account, model_id, "default")
        self._validate_attachment_supported_for_conversation(account, model, mime_type)

        actual_session_id = self.repository.ensure_session(account, session_id.strip() if session_id else None)
        resource_id = self.repository.new_id()
        extension = ALLOWED_MIME_TYPES[mime_type]
        relative_path = f"conversations/attachments/{actual_session_id}/{resource_id}{extension}"
        absolute_path = self.repository.timeline_abs_path(account, relative_path)
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_bytes(content)
        timestamp = now_iso()
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        sha256 = __import__("hashlib").sha256(content).hexdigest()

        self.repository.insert_uploaded_resource(
            account=account,
            session_id=actual_session_id,
            resource_id=resource_id,
            name=file.filename or "upload",
            mime_type=mime_type,
            size_bytes=len(content),
            relative_path=relative_path,
            sha256=sha256,
            expires_at=expires_at,
            timestamp=timestamp,
        )

        return {
            "session_id": actual_session_id,
            "resource": {
                "resource_id": resource_id,
                "name": file.filename or "upload",
                "mime_type": mime_type,
                "size_bytes": len(content),
                "relative_path": relative_path,
                "thumb_path": None,
                "sha256": sha256,
                "source": "user_upload",
                "status": "uploaded",
                "usage_status": "pending",
                "expires_at": expires_at,
            },
        }

    def send_message(
        self,
        account: str,
        session_id: Optional[str],
        parent_message_id: Optional[str],
        raw_text: str,
        model_id: Optional[str],
        thinking_mode: str,
        context_resources: list[dict[str, Any]],
        edited_from_message_id: Optional[str] = None,
    ) -> dict[str, Any]:
        raw_text = raw_text.strip()

        actual_session_id = self.repository.ensure_session(account, session_id)
        self.repository.validate_no_pending_turn(account, actual_session_id)
        model = self._validate_model(account, model_id, thinking_mode)

        messages_by_id = self.repository.messages_by_id(account, actual_session_id)
        if parent_message_id and parent_message_id not in messages_by_id:
            raise_error(404, "NOT_FOUND", "父消息不存在。")

        normalized_context_resources = self._validate_context_resources(
            account,
            actual_session_id,
            context_resources,
            model,
        )
        if not raw_text and not normalized_context_resources:
            raise_error(400, "INVALID_REQUEST", "请输入问题或添加附件后再发送。")
        turn_id = self.repository.new_id()
        user_message_id = self.repository.new_id()
        stream_id = f"stream_{turn_id}"
        timestamp = now_iso()
        row = self.repository.session_row(account, actual_session_id)
        timeline_path = self.repository.timeline_abs_path(account, row["timeline_path"])
        thinking_message_id = self.repository.new_id()
        assistant_message_id = self.repository.new_id()
        assistant_parent_message_id = thinking_message_id or user_message_id
        self.repository.attach_file_resources(account, actual_session_id, normalized_context_resources)
        from backend.app.storage.jsonl import append_record

        append_record(
            timeline_path,
            {
                "timestamp": timestamp,
                "type": "user_message",
                "payload": {
                    "session_id": actual_session_id,
                    "turn_id": turn_id,
                    "message_id": user_message_id,
                    "parent_message_id": parent_message_id,
                    "model_id": model["model_id"],
                    "thinking_mode": thinking_mode,
                    "content": raw_text,
                    "context_resources": normalized_context_resources,
                    "edited_from_message_id": edited_from_message_id,
                    "created_at": timestamp,
                },
            },
        )
        self.repository.insert_turn(
            account=account,
            session_id=actual_session_id,
            turn_id=turn_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            thinking_message_id=thinking_message_id,
            stream_id=stream_id,
            status="streaming",
            error_code=None,
            error_message=None,
            created_at=timestamp,
            updated_at=timestamp,
        )

        active_path = self.repository.path_to_message(messages_by_id, parent_message_id) + [
            user_message_id,
        ]
        self.repository.update_session_after_message(account, actual_session_id, active_path, None, raw_text)
        return {
            "session_id": actual_session_id,
            "turn_id": turn_id,
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
            "assistant_parent_message_id": assistant_parent_message_id,
            "thinking_message_id": thinking_message_id,
            "model_id": model["model_id"],
            "message_status": "streaming",
            "stream_id": stream_id,
            "context_resources": normalized_context_resources,
            "content": "",
            "created_at": timestamp,
        }

    def regenerate_message(
        self,
        account: str,
        session_id: str,
        message_id: str,
        model_id: Optional[str] = None,
        thinking_mode: Optional[str] = None,
    ) -> dict[str, Any]:
        self.repository.ensure_session(account, session_id)
        messages_by_id = self.repository.messages_by_id(account, session_id)
        target = messages_by_id.get(message_id)
        if not target:
            raise_error(400, "INVALID_REQUEST", "只能重新生成用户提问或助手最终回复。")
        if target["role"] == "assistant":
            target_parent = messages_by_id.get(target.get("parent_message_id"))
            if target_parent and target_parent["role"] == "thinking":
                user_message = messages_by_id.get(target_parent.get("parent_message_id"))
            else:
                user_message = target_parent
        elif target["role"] == "user":
            user_message = target
        else:
            raise_error(400, "INVALID_REQUEST", "只能重新生成用户提问或助手最终回复。")
        if not user_message or user_message["role"] != "user":
            raise_error(400, "INVALID_REQUEST", "无法定位原始用户消息。")

        pending_rows = self.repository.list_pending_turn_rows(account, session_id)
        if pending_rows:
            for pending in pending_rows:
                if pending["user_message_id"] == user_message["message_id"]:
                    return self.pending_turn_response(
                        session_id=session_id,
                        turn=pending,
                        user_message=user_message,
                        target=target,
                    )
            raise_error(400, "INVALID_REQUEST", "当前会话有正在进行的生成任务。")

        next_thinking_mode = thinking_mode or user_message.get("thinking_mode", "default")
        model = self._validate_model(account, model_id or target.get("model_id"), next_thinking_mode)
        turn_id = self.repository.new_id()
        stream_id = f"stream_{turn_id}"
        thinking_message_id = self.repository.new_id()
        assistant_message_id = self.repository.new_id()
        assistant_parent_message_id = thinking_message_id or user_message["message_id"]
        timestamp = now_iso()
        self.repository.insert_turn(
            account=account,
            session_id=session_id,
            turn_id=turn_id,
            user_message_id=user_message["message_id"],
            assistant_message_id=assistant_message_id,
            thinking_message_id=thinking_message_id,
            stream_id=stream_id,
            status="streaming",
            error_code=None,
            error_message=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "user_message_id": user_message["message_id"],
            "assistant_message_id": assistant_message_id,
            "assistant_parent_message_id": assistant_parent_message_id,
            "thinking_message_id": thinking_message_id,
            "model_id": model["model_id"],
            "message_status": "streaming",
            "stream_id": stream_id,
            "content": "",
            "created_at": timestamp,
        }

    def cancel_turn(
        self,
        account: str,
        session_id: str,
        turn_id: str,
        preserve_partial: bool = True,
        partial_content: str = "",
        partial_thinking: str = "",
    ) -> dict[str, Any]:
        self.repository.ensure_session(account, session_id)
        turn = self.repository.turn_row(account, session_id, turn_id)
        if not turn:
            raise_error(404, "NOT_FOUND", "轮次不存在。")
        if turn["status"] == "cancelled":
            return {
                "session_id": session_id,
                "turn_id": turn_id,
                "status": "cancelled",
                "preserve_partial": preserve_partial,
                "stream_id": turn["stream_id"],
                "assistant_message_id": turn["assistant_message_id"],
                "thinking_message_id": turn["thinking_message_id"],
            }
        if turn["status"] not in {"queued", "streaming"}:
            raise_error(400, "INVALID_REQUEST", "当前轮次已结束，不能取消。")

        messages_by_id = self.repository.messages_by_id(account, session_id)
        user_message = messages_by_id.get(turn["user_message_id"] or "")
        if not user_message:
            raise_error(404, "NOT_FOUND", "用户消息不存在。")

        timestamp = now_iso()
        if preserve_partial:
            content = partial_content.strip() or CANCELLED_ASSISTANT_CONTENT
            thinking_content = partial_thinking.strip()
            final_thinking_message_id = turn["thinking_message_id"] if thinking_content else None
            thinking_duration_ms = (
                _elapsed_ms_between_iso(turn["created_at"], timestamp)
                if thinking_content
                else 0
            )
            self._append_cancelled_turn_messages(
                account=account,
                turn=turn,
                user_message=user_message,
                assistant_message_id=turn["assistant_message_id"],
                thinking_message_id=final_thinking_message_id,
                thinking_content=thinking_content,
                thinking_duration_ms=thinking_duration_ms,
                content=content,
                timestamp=timestamp,
            )
        else:
            self._append_turn_cancelled_record(
                account=account,
                turn=turn,
                preserve_partial=False,
                assistant_message_id=None,
                thinking_message_id=None,
                timestamp=timestamp,
            )
            self.repository.update_turn_cancelled(
                account,
                turn_id,
                None,
                None,
                timestamp=timestamp,
            )
            final_thinking_message_id = None

        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "status": "cancelled",
            "preserve_partial": preserve_partial,
            "stream_id": turn["stream_id"],
            "assistant_message_id": turn["assistant_message_id"] if preserve_partial else None,
            "thinking_message_id": final_thinking_message_id,
        }

    def pending_turn_response(
        self,
        session_id: str,
        turn,
        user_message: dict[str, Any],
        target: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "turn_id": turn["turn_id"],
            "user_message_id": user_message["message_id"],
            "assistant_message_id": turn["assistant_message_id"],
            "assistant_parent_message_id": turn["thinking_message_id"] or user_message["message_id"],
            "thinking_message_id": turn["thinking_message_id"],
            "model_id": target.get("model_id") or user_message.get("model_id"),
            "message_status": turn["status"],
            "stream_id": turn["stream_id"],
            "content": "",
            "created_at": turn["created_at"],
        }

    def stream_response(self, account: str, stream_id: str) -> StreamingResponse:
        self.repository.init_db(account)
        turn = self.repository.turn_by_stream_id(account, stream_id)
        if not turn:
            raise_error(404, "NOT_FOUND", "流式订阅不存在。")

        messages_by_id = self.repository.messages_by_id(account, turn["session_id"])
        assistant_message = messages_by_id.get(turn["assistant_message_id"] or "")
        thinking_message = (
            messages_by_id.get(turn["thinking_message_id"])
            if turn["thinking_message_id"]
            else None
        )
        if turn["status"] == "completed" and not assistant_message:
            raise_error(404, "NOT_FOUND", "流式内容不存在。")

        def events():
            if turn["status"] == "streaming" and not assistant_message:
                yield from self._stream_live_turn(account, turn, messages_by_id)
                return
            if thinking_message:
                for delta in _stream_text_chunks(thinking_message["content"]):
                    yield (
                        "event: thinking_delta\n"
                        f"data: {json.dumps({'session_id': turn['session_id'], 'turn_id': turn['turn_id'], 'message_id': turn['thinking_message_id'], 'delta': delta}, ensure_ascii=False)}\n\n"
                    )
            if assistant_message:
                for delta in _stream_text_chunks(assistant_message["content"]):
                    yield (
                        "event: content_delta\n"
                        f"data: {json.dumps({'session_id': turn['session_id'], 'turn_id': turn['turn_id'], 'message_id': turn['assistant_message_id'], 'delta': delta}, ensure_ascii=False)}\n\n"
                    )
            if turn["status"] == "failed":
                yield (
                    "event: failed\n"
                    f"data: {json.dumps({'session_id': turn['session_id'], 'turn_id': turn['turn_id'], 'code': turn['error_code'], 'message': turn['error_message']}, ensure_ascii=False)}\n\n"
                )
                return
            if turn["status"] == "cancelled":
                yield self._cancelled_stream_event(turn)
                return
            yield self._completed_stream_event(
                turn,
                turn["assistant_message_id"],
                turn["thinking_message_id"],
            )

        return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)

    def _stream_live_turn(self, account: str, turn, messages_by_id: dict[str, dict[str, Any]]):
        user_message = messages_by_id.get(turn["user_message_id"] or "")
        if not user_message:
            yield self._failed_stream_event(account, turn, "NOT_FOUND", "用户消息不存在。")
            return

        thinking_message_id = turn["thinking_message_id"]
        assistant_message_id = turn["assistant_message_id"]
        thinking_parts: list[str] = []
        content_parts: list[str] = []
        usage: dict[str, Any] = {}
        stop_reason = "end_turn"
        thinking_started_at = time.monotonic()
        thinking_completed_at: float | None = None

        try:
            chat_model = self._validate_model(
                account,
                user_message.get("model_id"),
                user_message.get("thinking_mode", "default"),
            )
            response_model = self._response_model_for_context_resources(
                account,
                turn["session_id"],
                user_message.get("context_resources", []),
                chat_model,
            )
            response_thinking_mode = self._thinking_mode_for_model(
                response_model,
                user_message.get("thinking_mode", "default"),
            )
            chunks = self.model_catalog.stream_chat_for_account(
                account=account,
                model=response_model,
                messages=self._provider_messages(
                    account,
                    turn["session_id"],
                    messages_by_id,
                    user_message.get("parent_message_id"),
                    user_message.get("content", ""),
                    user_message.get("context_resources", []),
                    response_model,
                ),
                thinking_mode=response_thinking_mode,
            )
            for chunk in chunks:
                if self._turn_is_cancelled(account, turn):
                    yield self._cancelled_stream_event(turn)
                    return
                if chunk.thinking_delta:
                    thinking_parts.append(chunk.thinking_delta)
                    yield (
                        "event: thinking_delta\n"
                        f"data: {json.dumps({'session_id': turn['session_id'], 'turn_id': turn['turn_id'], 'message_id': thinking_message_id, 'delta': chunk.thinking_delta}, ensure_ascii=False)}\n\n"
                    )
                if chunk.content_delta:
                    if thinking_parts and thinking_completed_at is None:
                        thinking_completed_at = time.monotonic()
                    content_parts.append(chunk.content_delta)
                    yield (
                        "event: content_delta\n"
                        f"data: {json.dumps({'session_id': turn['session_id'], 'turn_id': turn['turn_id'], 'message_id': assistant_message_id, 'delta': chunk.content_delta}, ensure_ascii=False)}\n\n"
                    )
                if chunk.usage:
                    usage.update(chunk.usage)
                if chunk.stop_reason:
                    stop_reason = chunk.stop_reason
        except ProviderChatCompletionError as exc:
            yield self._failed_stream_event(account, turn, "MODEL_ERROR", str(exc) or "模型服务调用失败。")
            return

        if self._turn_is_cancelled(account, turn):
            yield self._cancelled_stream_event(turn)
            return

        content = "".join(content_parts).strip()
        thinking_content = "".join(thinking_parts).strip()
        if not content:
            yield self._failed_stream_event(account, turn, "MODEL_ERROR", "模型服务返回了空回复。")
            return

        final_thinking_message_id = thinking_message_id if thinking_content else None
        thinking_duration_ms = (
            _elapsed_ms(thinking_started_at, thinking_completed_at or time.monotonic())
            if thinking_content
            else 0
        )
        completed_turn = self._append_completed_turn_messages(
            account=account,
            turn=turn,
            user_message=user_message,
            assistant_message_id=assistant_message_id,
            thinking_message_id=final_thinking_message_id,
            thinking_content=thinking_content,
            thinking_duration_ms=thinking_duration_ms,
            content=content,
            stop_reason=stop_reason,
            usage=usage,
        )
        yield self._completed_stream_event(
            turn,
            assistant_message_id,
            final_thinking_message_id,
        )
        self._finish_completed_turn_session_index(
            account,
            turn,
            user_message,
            content,
            completed_turn["active_path"],
        )

    def _append_completed_turn_messages(
        self,
        account: str,
        turn,
        user_message: dict[str, Any],
        assistant_message_id: str,
        thinking_message_id: Optional[str],
        thinking_content: str,
        thinking_duration_ms: int,
        content: str,
        stop_reason: str,
        usage: dict[str, Any],
    ) -> dict[str, Any]:
        row = self.repository.session_row(account, turn["session_id"])
        timeline_path = self.repository.timeline_abs_path(account, row["timeline_path"])
        timestamp = now_iso()
        from backend.app.storage.jsonl import append_record

        if thinking_message_id:
            append_record(
                timeline_path,
                {
                    "timestamp": timestamp,
                    "type": "thinking_process",
                    "payload": {
                        "session_id": turn["session_id"],
                        "turn_id": turn["turn_id"],
                        "message_id": thinking_message_id,
                        "parent_message_id": user_message["message_id"],
                        "model_id": user_message.get("model_id"),
                        "duration_ms": thinking_duration_ms,
                        "content": thinking_content,
                        "created_at": timestamp,
                    },
                },
            )
        append_record(
            timeline_path,
            {
                "timestamp": timestamp,
                "type": "assistant_message",
                "payload": {
                    "session_id": turn["session_id"],
                    "turn_id": turn["turn_id"],
                    "message_id": assistant_message_id,
                    "parent_message_id": thinking_message_id or user_message["message_id"],
                    "model_id": user_message.get("model_id"),
                    "status": "completed",
                    "stop_reason": stop_reason,
                    "duration_ms": 1,
                    "usage": usage,
                    "content": content,
                    "created_at": timestamp,
                },
            },
        )
        messages_by_id = self.repository.messages_by_id(account, turn["session_id"])
        active_path = self.repository.path_to_message(messages_by_id, user_message["message_id"])
        if thinking_message_id:
            active_path.append(thinking_message_id)
        active_path.append(assistant_message_id)
        self.repository.update_turn_completed(
            account,
            turn["turn_id"],
            assistant_message_id,
            thinking_message_id,
            timestamp,
        )
        return {
            "active_path": active_path,
            "timestamp": timestamp,
        }

    def _finish_completed_turn_session_index(
        self,
        account: str,
        turn,
        user_message: dict[str, Any],
        content: str,
        active_path: list[str],
    ) -> None:
        self.repository.update_session_after_message(
            account,
            turn["session_id"],
            active_path,
            self._generate_completed_turn_title(account, user_message, content),
            content,
            legacy_title_seed=user_message.get("content", ""),
        )

    def _completed_stream_event(
        self,
        turn,
        assistant_message_id: str | None,
        thinking_message_id: str | None,
    ) -> str:
        return (
            "event: completed\n"
            f"data: {json.dumps({'session_id': turn['session_id'], 'turn_id': turn['turn_id'], 'assistant_message_id': assistant_message_id, 'thinking_message_id': thinking_message_id}, ensure_ascii=False)}\n\n"
        )

    def _generate_completed_turn_title(
        self,
        account: str,
        user_message: dict[str, Any],
        assistant_content: str,
    ) -> str:
        question = user_message.get("content", "")
        fallback_title = self.repository.generate_session_title(
            self.repository.title_seed_from_turn(question, assistant_content)
        )
        model = self.model_catalog.default_model_for_account(
            account,
            "title",
        ) or self.model_catalog.default_model_for_account(account, "chat")
        if not model:
            return fallback_title

        try:
            result = self.model_catalog.complete_chat_for_account(
                account=account,
                model=model,
                messages=[
                    {"role": "system", "content": TITLE_GENERATION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "用户询问：\n"
                            f"{question}\n\n"
                            "助手回答：\n"
                            f"{assistant_content}\n\n"
                            "请根据以上完整内容生成会话标题，只输出标题。"
                        ),
                    },
                ],
                thinking_mode="default",
            )
        except Exception:
            return fallback_title

        generated_title = self.repository.clean_generated_session_title(result.content)
        return generated_title if generated_title != UNTITLED_CONVERSATION else fallback_title

    def _append_cancelled_turn_messages(
        self,
        account: str,
        turn,
        user_message: dict[str, Any],
        assistant_message_id: str,
        thinking_message_id: Optional[str],
        thinking_content: str,
        thinking_duration_ms: int,
        content: str,
        timestamp: str,
    ) -> None:
        row = self.repository.session_row(account, turn["session_id"])
        timeline_path = self.repository.timeline_abs_path(account, row["timeline_path"])
        from backend.app.storage.jsonl import append_record

        self._append_turn_cancelled_record(
            account=account,
            turn=turn,
            preserve_partial=True,
            assistant_message_id=assistant_message_id,
            thinking_message_id=thinking_message_id,
            timestamp=timestamp,
        )
        if thinking_message_id:
            append_record(
                timeline_path,
                {
                    "timestamp": timestamp,
                    "type": "thinking_process",
                    "payload": {
                        "session_id": turn["session_id"],
                        "turn_id": turn["turn_id"],
                        "message_id": thinking_message_id,
                        "parent_message_id": user_message["message_id"],
                        "model_id": user_message.get("model_id"),
                        "duration_ms": thinking_duration_ms,
                        "content": thinking_content,
                        "created_at": timestamp,
                    },
                },
            )
        append_record(
            timeline_path,
            {
                "timestamp": timestamp,
                "type": "assistant_message",
                "payload": {
                    "session_id": turn["session_id"],
                    "turn_id": turn["turn_id"],
                    "message_id": assistant_message_id,
                    "parent_message_id": thinking_message_id or user_message["message_id"],
                    "model_id": user_message.get("model_id"),
                    "status": "cancelled",
                    "stop_reason": "cancelled",
                    "duration_ms": 1,
                    "usage": {},
                    "content": content,
                    "created_at": timestamp,
                },
            },
        )
        messages_by_id = self.repository.messages_by_id(account, turn["session_id"])
        active_path = self.repository.path_to_message(messages_by_id, user_message["message_id"])
        if thinking_message_id:
            active_path.append(thinking_message_id)
        active_path.append(assistant_message_id)
        self.repository.update_turn_cancelled(
            account,
            turn["turn_id"],
            assistant_message_id,
            thinking_message_id,
            timestamp=timestamp,
        )
        self.repository.update_session_after_message(
            account,
            turn["session_id"],
            active_path,
            self.repository.generate_session_title(
                self.repository.title_seed_from_turn(user_message.get("content", ""), content)
            ),
            content,
            legacy_title_seed=user_message.get("content", ""),
        )

    def _append_turn_cancelled_record(
        self,
        account: str,
        turn,
        preserve_partial: bool,
        assistant_message_id: Optional[str],
        thinking_message_id: Optional[str],
        timestamp: str,
    ) -> None:
        row = self.repository.session_row(account, turn["session_id"])
        timeline_path = self.repository.timeline_abs_path(account, row["timeline_path"])
        from backend.app.storage.jsonl import append_record

        append_record(
            timeline_path,
            {
                "timestamp": timestamp,
                "type": "turn_cancelled",
                "payload": {
                    "session_id": turn["session_id"],
                    "turn_id": turn["turn_id"],
                    "user_message_id": turn["user_message_id"],
                    "assistant_message_id": assistant_message_id,
                    "thinking_message_id": thinking_message_id,
                    "stream_id": turn["stream_id"],
                    "preserve_partial": preserve_partial,
                    "created_at": timestamp,
                },
            },
        )

    def _turn_is_cancelled(self, account: str, turn) -> bool:
        current = self.repository.turn_row(account, turn["session_id"], turn["turn_id"])
        return bool(current and current["status"] == "cancelled")

    def _cancelled_stream_event(self, turn) -> str:
        return (
            "event: cancelled\n"
            f"data: {json.dumps({'session_id': turn['session_id'], 'turn_id': turn['turn_id'], 'code': 'CANCELLED', 'message': CANCELLED_ASSISTANT_CONTENT}, ensure_ascii=False)}\n\n"
        )

    def _failed_stream_event(self, account: str, turn, code: str, message: str) -> str:
        self.repository.update_turn_failed(account, turn["turn_id"], code, message)
        return (
            "event: failed\n"
            f"data: {json.dumps({'session_id': turn['session_id'], 'turn_id': turn['turn_id'], 'code': code, 'message': message}, ensure_ascii=False)}\n\n"
        )

    def get_turn(self, account: str, session_id: str, turn_id: str) -> dict[str, Any]:
        self.repository.ensure_session(account, session_id)
        row = self.repository.turn_row(account, session_id, turn_id)
        if not row:
            raise_error(404, "NOT_FOUND", "轮次不存在。")
        return {
            "session_id": row["session_id"],
            "turn_id": row["turn_id"],
            "status": row["status"],
            "stream_id": row["stream_id"],
            "user_message_id": row["user_message_id"],
            "assistant_message_id": row["assistant_message_id"],
            "thinking_message_id": row["thinking_message_id"],
            "error": None
            if not row["error_code"]
            else {"code": row["error_code"], "message": row["error_message"]},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_conversations(self, account: str) -> dict[str, Any]:
        rows = self.repository.list_sessions(account)
        return {
            "sessions": [
                {
                    "session_id": row["session_id"],
                    "title": row["title"],
                    "last_message_preview": row["last_message_preview"],
                    "created_at": row["created_at"],
                    "last_active_at": row["last_active_at"],
                }
                for row in rows
            ],
            "has_more": False,
            "next_cursor": None,
        }

    def get_conversation(self, account: str, session_id: str) -> dict[str, Any]:
        self.repository.backfill_generated_session_titles(account)
        row = self.repository.session_row(account, session_id)
        if not row:
            raise_error(404, "NOT_FOUND", "会话不存在。")
        messages_by_id = self.repository.messages_by_id(account, session_id)
        active_path = json.loads(row["active_path_message_ids"] or "[]")
        messages = [
            self.repository.message_response(messages_by_id[message_id])
            for message_id in active_path
            if message_id in messages_by_id
        ]
        all_messages = [self.repository.message_response(message) for message in messages_by_id.values()]
        pending_rows = self.repository.list_pending_turn_rows(account, session_id)
        return {
            "session_id": row["session_id"],
            "account": account,
            "title": row["title"],
            "pending_turns": [
                {
                    "turn_id": pending["turn_id"],
                    "status": pending["status"],
                    "stream_id": pending["stream_id"],
                    "user_message_id": pending["user_message_id"],
                    "created_at": pending["created_at"],
                    "updated_at": pending["updated_at"],
                }
                for pending in pending_rows
            ],
            "active_path_message_ids": active_path,
            "messages": messages,
            "all_messages": all_messages,
        }

    def delete_conversation(self, account: str, session_id: str) -> dict[str, Any]:
        self.repository.delete_conversation(account, session_id)
        return {"success": True, "session_id": session_id, "message": "会话已删除"}

    def update_active_path(self, account: str, session_id: str, active_path_message_ids: list[str]) -> dict[str, Any]:
        self.repository.ensure_session(account, session_id)
        messages_by_id = self.repository.messages_by_id(account, session_id)
        previous_id = None
        for index, message_id in enumerate(active_path_message_ids):
            message = messages_by_id.get(message_id)
            if not message:
                raise_error(400, "INVALID_REQUEST", "活动路径包含不存在的消息。")
            expected_parent = None if index == 0 else previous_id
            if message.get("parent_message_id") != expected_parent:
                raise_error(400, "INVALID_REQUEST", "活动路径不连续。")
            previous_id = message_id

        extended_path = self.extend_active_path_to_leaf(messages_by_id, active_path_message_ids)
        self.repository.update_active_path(account, session_id, extended_path)
        return {"success": True, "session_id": session_id}

    def extend_active_path_to_leaf(
        self,
        messages_by_id: dict[str, dict[str, Any]],
        active_path_message_ids: list[str],
    ) -> list[str]:
        if not active_path_message_ids:
            return active_path_message_ids

        children_by_parent: dict[str, list[dict[str, Any]]] = {}
        for message in messages_by_id.values():
            parent_id = message.get("parent_message_id")
            if parent_id:
                children_by_parent.setdefault(parent_id, []).append(message)

        path = list(active_path_message_ids)
        seen = set(path)
        current_id = path[-1]
        while True:
            candidates = [
                child
                for child in children_by_parent.get(current_id, [])
                if child["message_id"] not in seen
            ]
            if not candidates:
                return path
            child = candidates[-1]
            path.append(child["message_id"])
            seen.add(child["message_id"])
            current_id = child["message_id"]

    def source_message_for_favorite(self, account: str, session_id: str, message_id: str):
        return self.repository.source_message_for_favorite(account, session_id, message_id)

    def conversation_exists(self, account: str, session_id: str) -> bool:
        return self.repository.conversation_exists(account, session_id)

    def _validate_model(self, account: str, model_id: Optional[str], thinking_mode: str):
        chat_model = self.model_catalog.default_model_for_account(account, "chat")
        if not chat_model:
            raise_error(422, "MODEL_NOT_CONFIGURED", "请先在账号设置中配置模型并添加默认聊天模型。")
        if model_id:
            model = self.model_catalog.model_for_account(account, model_id)
            if not model:
                raise_error(404, "MODEL_NOT_FOUND", "模型不存在或未添加。")
            if model["model_id"] != chat_model["model_id"]:
                raise_error(400, "INVALID_REQUEST", "首页只能使用默认聊天模型。")
        else:
            model = chat_model
        if not model:
            raise_error(422, "MODEL_NOT_CONFIGURED", "请先在账号设置中配置模型并添加默认模型。")
        if thinking_mode not in model.get("thinking_modes", []):
            raise_error(400, "INVALID_REQUEST", "当前模型不支持所选推理强度。")
        return model

    def _validate_attachment_supported_for_conversation(
        self,
        account: str,
        model: dict[str, Any],
        mime_type: str,
    ) -> None:
        if self._model_can_forward_attachment(model, mime_type):
            return
        vision_model = self._vision_parse_model_for_attachment(account, mime_type)
        if vision_model:
            return
        if mime_type in model.get("file_mime_types", []):
            raise_error(422, "MODEL_ATTACHMENT_UNSUPPORTED", "当前模型服务不能原生上传该附件类型。")
        raise_error(
            422,
            "MODEL_FILE_UNSUPPORTED",
            "当前聊天模型不支持该文件格式，且未配置可用的视觉解析模型。",
        )

    def _model_can_forward_attachment(self, model: dict[str, Any], mime_type: str) -> bool:
        return (
            mime_type in model.get("file_mime_types", [])
            and self.model_catalog.provider_supports_native_attachment(model, mime_type)
        )

    def _vision_parse_model_for_attachment(self, account: str, mime_type: str) -> Optional[dict[str, Any]]:
        model = self.model_catalog.default_model_for_account(account, "vision_parse")
        if not model or mime_type not in model.get("file_mime_types", []):
            return None
        if not self.model_catalog.provider_supports_native_attachment(model, mime_type):
            raise_error(422, "MODEL_ATTACHMENT_UNSUPPORTED", "视觉解析模型服务不能原生上传该附件类型。")
        return model

    def _validate_context_resources(
        self,
        account: str,
        session_id: str,
        references: list[dict[str, Any]],
        model: dict[str, Any],
    ) -> list[dict[str, Any]]:
        normalized = []
        messages_by_id = self.repository.messages_by_id(account, session_id)
        for reference in references:
            resource_type = self._ref_value(reference, "resource_type")
            resource_id = self._ref_value(reference, "resource_id")
            if resource_type == "file":
                row = self.repository.resource_row(account, session_id, resource_id)
                if not row:
                    raise_error(404, "NOT_FOUND", "上下文资源不存在。")
                if row["usage_status"] in {"expired", "deleted"}:
                    raise_error(400, "INVALID_REQUEST", "上下文资源已过期。")
                if row["expires_at"] and datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
                    self.repository.set_resource_usage_status(account, row["resource_id"], "expired")
                    raise_error(400, "INVALID_REQUEST", "上下文资源已过期。")
                self._validate_attachment_supported_for_conversation(account, model, row["mime_type"])
                normalized.append(
                    {
                        "resource_type": "file",
                        "resource_id": row["resource_id"],
                        "name": row["name"],
                        "mime_type": row["mime_type"],
                        "size_bytes": row["size_bytes"],
                    }
                )
            elif resource_type == "message_quote":
                message = messages_by_id.get(resource_id)
                if not message:
                    raise_error(404, "NOT_FOUND", "引用消息不存在。")
                quote_text = self._ref_value(reference, "quote_text") or ""
                if quote_text not in message.get("content", ""):
                    raise_error(400, "INVALID_REQUEST", "引用文本不属于该消息。")
                normalized.append(
                    {
                        "resource_type": "message_quote",
                        "resource_id": resource_id,
                        "quote_text": quote_text,
                    }
                )
            else:
                raise_error(400, "INVALID_REQUEST", "上下文资源类型不支持。")
        self._response_model_for_context_resources(account, session_id, normalized, model)
        return normalized

    def _provider_messages(
        self,
        account: str,
        session_id: str,
        messages_by_id: dict[str, dict[str, Any]],
        parent_message_id: Optional[str],
        raw_text: str,
        context_resources: list[dict[str, Any]],
        model: dict[str, Any],
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": HEALTH_ASSISTANT_SYSTEM_PROMPT}
        ]
        for message_id in self.repository.path_to_message(messages_by_id, parent_message_id):
            message = messages_by_id[message_id]
            if message["role"] not in {"user", "assistant"}:
                continue
            messages.append({"role": message["role"], "content": message.get("content", "")})

        context_block = self._context_block(context_resources)
        if context_block:
            messages.append({"role": "system", "content": context_block})
        direct_context_resources = self._direct_context_resources_for_model(
            account,
            session_id,
            context_resources,
            model,
        )
        user_text = raw_text or (
            ATTACHMENT_ONLY_USER_PROMPT
            if any(resource.get("resource_type") == "file" for resource in context_resources)
            else raw_text
        )
        current_content = self._user_content_with_attachments(
            account, session_id, user_text, direct_context_resources
        )
        messages.append({"role": "user", "content": current_content})
        return messages

    def _response_model_for_context_resources(
        self,
        account: str,
        session_id: str,
        context_resources: list[dict[str, Any]],
        chat_model: dict[str, Any],
    ) -> dict[str, Any]:
        file_mime_types = self._context_file_mime_types(account, session_id, context_resources)
        if not file_mime_types:
            return chat_model
        if all(self._model_can_forward_attachment(chat_model, mime_type) for mime_type in file_mime_types):
            return chat_model
        vision_model = self.model_catalog.default_model_for_account(account, "vision_parse")
        if vision_model and all(
            self._model_can_forward_attachment(vision_model, mime_type)
            for mime_type in file_mime_types
        ):
            return vision_model
        raise_error(
            422,
            "MODEL_FILE_UNSUPPORTED",
            "当前聊天模型不支持本轮附件，且未配置可直接回答这些附件的视觉解析模型。",
        )

    def _context_file_mime_types(
        self,
        account: str,
        session_id: str,
        context_resources: list[dict[str, Any]],
    ) -> list[str]:
        mime_types = []
        for resource in context_resources:
            if resource.get("resource_type") != "file":
                continue
            row = self.repository.resource_row(account, session_id, resource["resource_id"])
            if row:
                mime_types.append(row["mime_type"])
        return mime_types

    def _direct_context_resources_for_model(
        self,
        account: str,
        session_id: str,
        context_resources: list[dict[str, Any]],
        model: dict[str, Any],
    ) -> list[dict[str, Any]]:
        direct_resources = []
        for resource in context_resources:
            if resource.get("resource_type") != "file":
                direct_resources.append(resource)
                continue
            row = self.repository.resource_row(account, session_id, resource["resource_id"])
            if row and self._model_can_forward_attachment(model, row["mime_type"]):
                direct_resources.append(resource)
        return direct_resources

    def _default_thinking_mode(self, model: dict[str, Any]) -> str:
        thinking_modes = model.get("thinking_modes", [])
        if "default" in thinking_modes:
            return "default"
        return thinking_modes[0] if thinking_modes else "default"

    def _thinking_mode_for_model(self, model: dict[str, Any], requested_mode: str) -> str:
        thinking_modes = model.get("thinking_modes", [])
        if requested_mode in thinking_modes:
            return requested_mode
        return self._default_thinking_mode(model)

    def _context_block(self, context_resources: list[dict[str, Any]]) -> str:
        if not context_resources:
            return ""
        lines = ["用户附加上下文："]
        for resource in context_resources:
            if resource["resource_type"] == "message_quote":
                lines.append(f"- 历史消息引用：{resource.get('quote_text', '')}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def _user_content_with_attachments(
        self,
        account: str,
        session_id: str,
        raw_text: str,
        context_resources: list[dict[str, Any]],
    ):
        file_resources = [
            resource for resource in context_resources if resource.get("resource_type") == "file"
        ]
        if not file_resources:
            return raw_text
        parts: list[dict[str, Any]] = []
        parts.append({"type": "text", "text": raw_text or ATTACHMENT_ONLY_USER_PROMPT})
        for resource in file_resources:
            parts.append(self._attachment_part(account, session_id, resource))
        return parts

    def _attachment_part(
        self, account: str, session_id: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        row = self.repository.resource_row(account, session_id, resource["resource_id"])
        if not row:
            raise ProviderChatCompletionError("上下文资源不存在。")
        path = self.repository.timeline_abs_path(account, row["relative_path"])
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ProviderChatCompletionError("读取附件失败。") from exc
        mime_type = str(row["mime_type"])
        if mime_type.startswith("image/"):
            part_type = "image"
        elif mime_type.startswith("audio/"):
            part_type = "audio"
        elif mime_type.startswith("video/"):
            part_type = "video"
        else:
            part_type = "file"
        return {
            "type": part_type,
            "mime_type": mime_type,
            "name": row["name"],
            "data_base64": base64.b64encode(content).decode("ascii"),
        }

    def _ref_value(self, reference: Any, key: str):
        if isinstance(reference, dict):
            return reference.get(key)
        return getattr(reference, key)


def _completion_thinking_content(completion: Any) -> str:
    thinking_content = getattr(completion, "thinking_content", "")
    return thinking_content.strip() if isinstance(thinking_content, str) else ""


def _elapsed_ms(start: float, end: float) -> int:
    return max(1, round((end - start) * 1000))


def _elapsed_ms_between_iso(start: str, end: str) -> int:
    try:
        start_time = datetime.fromisoformat(start)
        end_time = datetime.fromisoformat(end)
    except (TypeError, ValueError):
        return 1
    return max(1, round((end_time - start_time).total_seconds() * 1000))


def _stream_text_chunks(text: str):
    content = text or ""
    for index in range(0, len(content), STREAM_CHUNK_CHARS):
        delta = content[index : index + STREAM_CHUNK_CHARS]
        if delta:
            yield delta

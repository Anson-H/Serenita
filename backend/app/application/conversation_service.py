from backend.app.core.time import elapsed_ms
from backend.app.application.model_call_recorder import ModelCallRecorder
from backend.app.application.conversation_compaction import (
    ConversationCompaction,
    DEFAULT_RESERVED_OUTPUT_TOKENS,
)
from backend.app.session_activity import reduce_session_activity
from backend.app.application.conversation_cancellation import (
    interrupted_activity_specifications,
)
from backend.app.application.conversation_jobs import ConversationTurnJobs
from backend.app.application.conversation_queue import (
    ConversationQueue,
    ConversationQueueActions,
)
from backend.app.application.conversation_sse import (
    ConversationSSESubscriber,
    stream_text_chunks,
    CANCELLED_ASSISTANT_CONTENT,
)
from backend.app.application.conversation_titles import ConversationTitleTasks
import base64
import hashlib
import json
import re
import time
from datetime import timedelta
from pathlib import Path
from backend.app.storage.paths import app_paths
from backend.app.core.member_lifecycle import (
    member_lifecycle_operation,
    member_lifecycle_guard,
)
from backend.app.repositories.member_repository import MemberRepository
from backend.app.core.member_errors import member_error
from typing import Any, Callable, Optional

from backend.app.core.errors import SerenitaError

from backend.app.agent_runtime.prompts import (
    ATTACHED_ANNOTATION_PREFIX,
)
from backend.app.agent_runtime.model_types import (
    ModelRequest,
)
from backend.app.agent_runtime.compaction import (
    CompactionError,
)
from backend.app.agent_runtime.events import visible_workflow_event
from backend.app.core.errors import raise_error
from backend.app.application.model_provider_service import (
    ModelProviderService,
)
from backend.app.conversation_timeline import active_records, records_from_events
from backend.app.application.conversation_presenter import (
    record_response,
    message_response,
)
from backend.app.model_history import derive_model_messages, visible_loaded_skill_names
from backend.app.session_event_queries import (
    current_session_turn_ids,
    queued_inputs_from_events,
)
from backend.app.core.tabular_json import decode_tabular_json
from backend.app.core.markdown_text import markdown_selection_text
from backend.app.core.cancellation import (
    CancellationToken,
    OperationCancelledError,
)
from backend.app.core.time import local_now, local_now_iso, parse_local_datetime
from backend.app.model_capabilities import DEFAULT_CONTEXT_WINDOW_TOKENS
from backend.app.plugins.web.citations import export_web_citation_markdown
from backend.app.providers.errors import ProviderChatCompletionError
from backend.app.session_events import iso_to_epoch_ms
from backend.app.core.conversation_tasks import tasks_for_paths
from backend.app.session_title import SESSION_TITLE_MAX_CHARS
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.session_title import UNTITLED_CONVERSATION
from backend.app.storage.session_persistence import SessionEventWriteConflictError


now_iso = local_now_iso

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES_PER_TURN = 20
MAX_TOTAL_FILE_BYTES = 100 * 1024 * 1024
TURN_JOB_LEASE_SECONDS = 300
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
MODEL_RENDERABLE_ATTACHMENT_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/heic", "application/pdf"}
)


def _annotation_source_values(record: dict[str, Any]) -> list[Any] | None:
    kind = record.get("kind")
    if kind in {"user", "assistant"}:
        return [record.get("content")]
    if kind == "model" and record.get("channel") == "content":
        return [record.get("value")]
    return None


def _annotation_text_belongs_to_record(
    annotation_text: str,
    record: dict[str, Any],
) -> bool:
    values = _annotation_source_values(record)
    if values is None:
        return False
    normalized_annotation = re.sub(r"\s+", " ", annotation_text).strip()
    if not normalized_annotation:
        return False
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = [
                json.dumps(value, ensure_ascii=False, indent=2, default=str),
                json.dumps(
                    value, ensure_ascii=False, separators=(",", ":"), default=str
                ),
            ]
        for candidate in candidates:
            if annotation_text in candidate:
                return True
            if normalized_annotation in re.sub(r"\s+", " ", candidate).strip():
                return True
            # Browser selections omit Markdown syntax. Derive the visible text
            # from the trusted record, never from client-supplied source text.
            rendered_text = markdown_selection_text(candidate)
            if normalized_annotation in re.sub(r"\s+", " ", rendered_text).strip():
                return True
    return False


class ConversationService:
    def __init__(
        self,
        repository: ConversationRepository | None = None,
        model_catalog: ModelProviderService | None = None,
        *,
        paths=None,
        members=None,
        services=None,
    ):
        self.paths = paths or getattr(repository, "paths", None) or app_paths()
        self.members = members or MemberRepository(paths=self.paths)
        if services is None:
            from backend.app.application.services import ApplicationServices

            services = ApplicationServices(self.paths, members=self.members)
        self.services = services
        self.task_state = tasks_for_paths(self.paths)
        self.repository = repository or ConversationRepository(
            paths=self.paths, members=self.members
        )
        self.model_catalog = model_catalog or ModelProviderService(paths=self.paths)
        self.model_calls = ModelCallRecorder(
            self.repository,
            self.model_catalog,
            self.paths,
            self.task_state,
            ensure_active=lambda *args, **kwargs: self._raise_if_turn_cancelled(
                *args, **kwargs
            ),
            next_model_step=self._next_model_step,
        )
        self.compaction = ConversationCompaction(
            self.repository,
            self.model_catalog,
            self.paths,
            self.task_state,
            complete_model=lambda **kwargs: self.model_calls.complete_chat_with_events(
                **kwargs
            ),
            ensure_active=lambda *args, **kwargs: self._raise_if_turn_cancelled(
                *args, **kwargs
            ),
            thinking_mode_for_model=self._thinking_mode_for_model,
        )
        self.titles = ConversationTitleTasks(
            self.repository,
            self.model_catalog,
            self.task_state,
            prepare_attachments=lambda *args, **kwargs: (
                self._model_and_attachment_parts(*args, **kwargs)
            ),
            prepare_request=self._model_request_from_messages,
        )
        self.jobs = ConversationTurnJobs(
            self.repository,
            self.task_state,
            self.titles,
            execute_turn=lambda *args, **kwargs: self._execute_turn(*args, **kwargs),
            record_failure=lambda *args, **kwargs: self._record_turn_failure(
                *args, **kwargs
            ),
            promote_next=lambda *args, **kwargs: self.queue.promote_next(
                *args, **kwargs
            ),
        )
        self.queue = ConversationQueue(
            self.repository,
            self.paths,
            self.members,
            self.task_state,
            ConversationQueueActions(
                member_accessible=self._member_accessible,
                start_message=lambda **kwargs: self._start_message_turn(**kwargs),
                start_job=self.jobs.start,
                cancel_turn=lambda *args, **kwargs: self.cancel_turn(*args, **kwargs),
                get_turn=self.get_turn,
                member_access=self._session_member_access,
                current_records=self._current_records,
                drain_cleanup=self._drain_attachment_cleanup,
            ),
        )
        self.streams = ConversationSSESubscriber(
            self.repository,
            self.task_state.notifications,
            interrupt_expired_jobs=lambda account_id: self._interrupt_expired_turn_jobs(
                account_id
            ),
        )

    def start_turn_job(self, account_id: str, session_id: str, stream_id: str) -> None:
        return self.jobs.start(account_id, session_id, stream_id)

    def wait_for_turn_job(
        self,
        account_id: str,
        session_id: str,
        stream_id: str,
        timeout: float = 2.0,
    ) -> None:
        return self.jobs.wait(account_id, session_id, stream_id, timeout)

    def reorder_queued_inputs(
        self, account_id: str, session_id: str, input_ids: list[str]
    ) -> dict[str, Any]:
        return self.queue.reorder(account_id, session_id, input_ids)

    def remove_queued_input(
        self,
        account_id: str,
        session_id: str,
        input_id: str,
        *,
        restore_to_draft: bool = False,
    ) -> dict[str, Any]:
        return self.queue.remove(
            account_id, session_id, input_id, restore_to_draft=restore_to_draft
        )

    def run_queued_input_now(
        self, account_id: str, session_id: str, input_id: str
    ) -> dict[str, Any]:
        return self.queue.run_now(account_id, session_id, input_id)

    def stream_events(self, account_id: str, session_id: str, stream_id: str):
        return self.streams.stream_events(account_id, session_id, stream_id)

    def cancel_title_generation(self, account_id: str, session_id: str) -> bool:
        return self.titles.cancel(account_id, session_id)

    def session_binding(self, account_id: str, session_id: str) -> dict[str, Any]:
        row = self.repository.session_row(account_id, session_id)
        if row is None:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        return {"session_id": session_id, "member_id": row["member_id"]}

    def _session_member_access(self, account_id: str, session_id: str):
        row = self.repository.session_row(account_id, session_id)
        if row is None:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        if row["member_id"] is None:
            return None
        with self.members.access_guard(account_id, str(row["member_id"])) as access:
            return access

    def _member_accessible(self, account_id: str, session_id: str) -> bool:
        try:
            self._session_member_access(account_id, session_id)
            return True
        except SerenitaError as exc:
            if exc.kind in {"forbidden", "missing"}:
                return False
            raise

    def upload_context_resource(
        self,
        account_id: str,
        session_id: Optional[str],
        model_id: Optional[str],
        upload: dict[str, Any],
        *,
        member_id: str | None,
    ) -> dict[str, Any]:
        self._maintain_attachments(account_id)
        self.repository.init_db(account_id)
        content = upload["content"]
        if len(content) > MAX_FILE_BYTES:
            raise_error("resource_limit", "FILE_TOO_LARGE", "单文件大小不能超过 20MB。")
        mime_type = upload["mime_type"]
        if mime_type not in ALLOWED_MIME_TYPES:
            raise_error("unsupported", "UNSUPPORTED_FILE_TYPE", "文件类型不支持。")
        model = self._validate_model(account_id, model_id, "default")
        self._validate_attachment_supported_for_conversation(
            account_id, model, mime_type
        )

        actual_session_id = self.repository.ensure_session(
            account_id, session_id.strip() if session_id else None, member_id=member_id
        )
        self._session_member_access(account_id, actual_session_id)
        extension = ALLOWED_MIME_TYPES[mime_type]
        try:
            resource = self.repository.create_uploaded_resource(
                account_id=account_id,
                session_id=actual_session_id,
                original_filename=upload["original_filename"],
                fallback_extension=extension,
                mime_type=mime_type,
                content=content,
            )
        except Exception:
            # Drain any exact-path job created by a normal write failure.
            # A ready-transition failure intentionally leaves a recoverable
            # writing record and therefore creates no cleanup job.
            self._drain_attachment_cleanup(account_id)
            raise

        return {
            "session_id": actual_session_id,
            "member_id": member_id,
            "resource": {"member_id": member_id, **resource},
        }

    @member_lifecycle_operation
    def send_message(
        self,
        account_id: str,
        session_id: Optional[str],
        raw_text: str,
        model_id: Optional[str],
        thinking_mode: str,
        context_resources: list[dict[str, Any]],
        *,
        member_id: str | None,
    ) -> dict[str, Any]:
        self._maintain_attachments(account_id)
        actual_session_id = self.repository.ensure_session(
            account_id, session_id, member_id=member_id
        )
        self._session_member_access(account_id, actual_session_id)
        model = self._validate_model(account_id, model_id, thinking_mode)
        normalized_context_resources = self._validate_context_resources(
            account_id,
            actual_session_id,
            context_resources,
            model,
        )
        if not raw_text.strip() and not normalized_context_resources:
            raise_error(
                "invalid_input", "INVALID_REQUEST", "请输入问题或添加附件后再发送。"
            )
        message_text = raw_text if raw_text.strip() else ""

        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, actual_session_id),
        ):
            for _attempt in range(128):
                events = self.repository.session_events(
                    account_id,
                    actual_session_id,
                    repair=False,
                )
                self.repository.reconcile_session_indexes(
                    account_id,
                    actual_session_id,
                    events=events,
                )
                pending = self.repository.list_pending_turn_rows(
                    account_id,
                    actual_session_id,
                )
                waiting = queued_inputs_from_events(events)
                if pending or waiting:
                    response = self.queue.enqueue(
                        account_id=account_id,
                        session_id=actual_session_id,
                        raw_text=message_text,
                        model_id=str(model["model_id"]),
                        thinking_mode=thinking_mode,
                        context_resources=normalized_context_resources,
                    )
                    if not pending:
                        self.queue.promote_next(account_id, actual_session_id)
                        refreshed = self.queue.inputs(account_id, actual_session_id)
                        response["queued_inputs"] = refreshed
                        response["queued_input"] = next(
                            item
                            for item in refreshed
                            if item["input_id"] == response["queued_input"]["input_id"]
                        )
                    return response
                try:
                    return self._start_message_turn(
                        account_id=account_id,
                        session_id=actual_session_id,
                        raw_text=message_text,
                        model_id=str(model["model_id"]),
                        thinking_mode=thinking_mode,
                        context_resources=normalized_context_resources,
                        attach_resources=True,
                        current_events=events,
                        expected_seq=len(events),
                    )
                except SessionEventWriteConflictError:
                    continue
        raise_error(
            "conflict", "TURN_IN_PROGRESS", "当前聊天内容持续变化，请稍后重试。"
        )

    @staticmethod
    def _turn_start_is_persisted(events: list[Any], turn_id: str) -> bool:
        return any(
            event.type == "turn/start"
            and str(event.data.get("turn_id") or "") == turn_id
            for event in events
        )

    def _commit_turn_start(
        self,
        *,
        account_id: str,
        session_id: str,
        expected_seq: int,
        specifications: list[dict[str, Any]],
        turn_index: dict[str, Any],
        attached_resources: list[dict[str, Any]],
    ) -> None:
        turn_id = str(turn_index["turn_id"])
        try:
            self.repository.append_session_events(
                account_id,
                session_id,
                specifications,
                expected_seq=expected_seq,
            )
        except SessionEventWriteConflictError:
            raise
        except Exception:
            # Persistence may have committed before notification/index metadata
            # failed. The event log is the source of truth, so never append the
            # same logical turn a second time after an ambiguous outcome.
            persisted = self.repository.session_events(
                account_id,
                session_id,
                repair=False,
            )
            if not self._turn_start_is_persisted(persisted, turn_id):
                raise

        last_index_error: Exception | None = None
        for attempt in range(3):
            try:
                self.repository.insert_turn(**turn_index)
                last_index_error = None
                break
            except Exception as exc:
                last_index_error = exc
                persisted = self.repository.session_events(
                    account_id,
                    session_id,
                    repair=False,
                )
                if not self._turn_start_is_persisted(persisted, turn_id):
                    raise
                time.sleep(0.002 * (attempt + 1))
        if last_index_error is not None:
            persisted = self.repository.session_events(
                account_id,
                session_id,
                repair=False,
            )
            self.repository.reconcile_session_indexes(
                account_id,
                session_id,
                events=persisted,
            )
            if self.repository.turn_row(account_id, session_id, turn_id) is None:
                raise last_index_error

        self.repository.mark_file_resources_attached(
            account_id,
            session_id,
            [str(resource["resource_id"]) for resource in attached_resources],
        )

    def _start_message_turn(
        self,
        *,
        account_id: str,
        session_id: str,
        raw_text: str,
        model_id: str,
        thinking_mode: str,
        context_resources: list[dict[str, Any]],
        attach_resources: bool,
        current_events: list[Any],
        expected_seq: int,
        queued_input_id: str | None = None,
    ) -> dict[str, Any]:
        self._session_member_access(account_id, session_id)
        current_records = active_records(
            records_from_events(current_events),
            current_events,
        )
        parent_message_id = next(
            (
                str(record.get("message_id") or record.get("record_id"))
                for record in reversed(current_records)
                if record.get("kind") == "assistant"
            ),
            None,
        )
        title_seed = self.titles.seed(raw_text, context_resources)
        initial_session_title = self.repository.initial_session_title(title_seed)
        should_generate_session_title = (
            self.repository.session_row(account_id, session_id)["title"]
            == UNTITLED_CONVERSATION
        )
        turn_id = self.repository.new_id()
        user_message_id = self.repository.new_id()
        stream_id = f"stream_{turn_id}"
        timestamp = now_iso()
        final_assistant_message_id = self.repository.new_id()
        assistant_parent_message_id = user_message_id
        event_time = iso_to_epoch_ms(timestamp)
        attached_resources = (
            self.repository.file_resource_attachment_payloads(
                account_id,
                session_id,
                context_resources,
            )
            if attach_resources
            else []
        )
        specifications = [
            {
                "type": "turn/start",
                "timestamp": event_time,
                "data": {
                    "turn_id": turn_id,
                    "user_message_id": user_message_id,
                    "final_assistant_message_id": final_assistant_message_id,
                    "stream_id": stream_id,
                },
            },
            {
                "type": "user/message",
                "timestamp": event_time,
                "surface_op": "append",
                "data": {
                    "turn_id": turn_id,
                    "message_id": user_message_id,
                    "parent_message_id": parent_message_id,
                    "model_id": model_id,
                    "thinking_mode": thinking_mode,
                    "content": raw_text,
                    "context_resources": context_resources,
                    **(
                        {"queued_input_id": queued_input_id}
                        if queued_input_id is not None
                        else {}
                    ),
                    "generate_session_title": should_generate_session_title,
                    "initial_session_title": initial_session_title,
                    "created_at": timestamp,
                },
            },
            *[
                {"type": "resource/attached", "data": resource}
                for resource in attached_resources
            ],
        ]
        self._commit_turn_start(
            account_id=account_id,
            session_id=session_id,
            expected_seq=expected_seq,
            specifications=specifications,
            turn_index={
                "account_id": account_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "user_message_id": user_message_id,
                "final_assistant_message_id": final_assistant_message_id,
                "stream_id": stream_id,
                "status": "queued",
                "error_code": None,
                "error_message": None,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
            attached_resources=attached_resources,
        )

        if should_generate_session_title:
            self.repository.set_initial_session_title(
                account_id,
                session_id,
                initial_session_title,
            )
        self.repository.touch_session(account_id, session_id)
        return {
            "disposition": "started",
            "member_id": self.repository.session_row(account_id, session_id)[
                "member_id"
            ],
            "member_name": self.members.historical_member_name(
                account_id, "conversation", session_id
            ),
            "session_id": session_id,
            "turn_id": turn_id,
            "user_message_id": user_message_id,
            "final_assistant_message_id": final_assistant_message_id,
            "assistant_parent_message_id": assistant_parent_message_id,
            "model_id": model_id,
            "message_status": "streaming",
            "stream_id": stream_id,
            "title": self.repository.session_row(account_id, session_id)["title"],
            "context_resources": context_resources,
            "content": "",
            "created_at": timestamp,
        }

    def wait_for_all_jobs(self, timeout: float = 2.0) -> None:
        self.task_state.wait(timeout)

    @member_lifecycle_operation
    def regenerate_message(
        self,
        account_id: str,
        session_id: str,
        message_id: str,
        model_id: Optional[str] = None,
        thinking_mode: Optional[str] = None,
    ) -> dict[str, Any]:
        self._session_member_access(account_id, session_id)
        self.repository.ensure_session(account_id, session_id)
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            for _attempt in range(128):
                events = self.repository.session_events(
                    account_id, session_id, repair=False
                )
                self.repository.reconcile_session_indexes(
                    account_id,
                    session_id,
                    events=events,
                )
                if self.repository.list_pending_turn_rows(account_id, session_id):
                    raise_error(
                        "conflict", "TURN_IN_PROGRESS", "当前聊天有正在进行的生成任务。"
                    )

                latest = self._latest_current_turn(
                    account_id,
                    session_id,
                    events=events,
                )
                if latest is None or latest["status"] in {"queued", "streaming"}:
                    raise_error(
                        "conflict", "TURN_IN_PROGRESS", "当前聊天有正在进行的生成任务。"
                    )
                if str(latest["final_assistant_message_id"] or "") != message_id:
                    raise_error(
                        "conflict",
                        "MESSAGE_NOT_LATEST",
                        "只能重新生成最新一轮的助手回复。",
                    )

                current_records = active_records(records_from_events(events), events)
                messages_by_id = {
                    str(record.get("message_id") or record.get("record_id") or ""): {
                        **record,
                        "role": record.get("kind"),
                    }
                    for record in current_records
                    if record.get("kind") in {"user", "assistant"}
                }
                target = messages_by_id.get(message_id)
                user_message = messages_by_id.get(str(latest["user_message_id"] or ""))
                if not target or target.get("role") != "assistant" or not user_message:
                    raise_error(
                        "conflict",
                        "MESSAGE_NOT_LATEST",
                        "只能重新生成最新一轮的助手回复。",
                    )

                next_thinking_mode = thinking_mode or user_message.get(
                    "thinking_mode",
                    "default",
                )
                model = self._validate_model(
                    account_id,
                    model_id or target.get("model_id"),
                    next_thinking_mode,
                )
                turn_id = self.repository.new_id()
                stream_id = f"stream_{turn_id}"
                final_assistant_message_id = self.repository.new_id()
                assistant_parent_message_id = user_message["message_id"]
                timestamp = now_iso()
                try:
                    self._commit_turn_start(
                        account_id=account_id,
                        session_id=session_id,
                        expected_seq=len(events),
                        specifications=[
                            {
                                "type": "turn/start",
                                "timestamp": iso_to_epoch_ms(timestamp),
                                "data": {
                                    "turn_id": turn_id,
                                    "user_message_id": user_message["message_id"],
                                    "final_assistant_message_id": final_assistant_message_id,
                                    "stream_id": stream_id,
                                    "supersedes_turn_id": latest["turn_id"],
                                    "regenerated_from_message_id": message_id,
                                    "model_id": model["model_id"],
                                },
                            },
                            {
                                "type": "user/message-update",
                                "timestamp": iso_to_epoch_ms(timestamp),
                                "data": {
                                    "message_id": user_message["message_id"],
                                    "patch": {
                                        "model_id": model["model_id"],
                                        "thinking_mode": next_thinking_mode,
                                    },
                                },
                            },
                        ],
                        turn_index={
                            "account_id": account_id,
                            "session_id": session_id,
                            "turn_id": turn_id,
                            "user_message_id": user_message["message_id"],
                            "final_assistant_message_id": final_assistant_message_id,
                            "stream_id": stream_id,
                            "status": "queued",
                            "error_code": None,
                            "error_message": None,
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                        attached_resources=[],
                    )
                except SessionEventWriteConflictError:
                    continue
                session = self.repository.session_row(account_id, session_id)
                return {
                    "session_id": session_id,
                    "title": session["title"],
                    "member_id": session["member_id"],
                    "member_name": self.members.historical_member_name(
                        account_id, "conversation", session_id
                    ),
                    "turn_id": turn_id,
                    "user_message_id": user_message["message_id"],
                    "final_assistant_message_id": final_assistant_message_id,
                    "assistant_parent_message_id": assistant_parent_message_id,
                    "model_id": model["model_id"],
                    "message_status": "streaming",
                    "stream_id": stream_id,
                    "content": "",
                    "created_at": timestamp,
                }
        raise_error(
            "conflict", "TURN_IN_PROGRESS", "当前聊天内容持续变化，请稍后重试。"
        )

    @member_lifecycle_operation
    def edit_message(
        self,
        account_id: str,
        session_id: str,
        message_id: str,
        raw_text: str,
        model_id: Optional[str],
        thinking_mode: str,
        context_resources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self._session_member_access(account_id, session_id)
        self.repository.ensure_session(account_id, session_id)
        raw_text = raw_text.strip()
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            for _attempt in range(128):
                events = self.repository.session_events(
                    account_id, session_id, repair=False
                )
                self.repository.reconcile_session_indexes(
                    account_id,
                    session_id,
                    events=events,
                )
                if self.repository.list_pending_turn_rows(account_id, session_id):
                    raise_error(
                        "conflict", "TURN_IN_PROGRESS", "当前聊天有正在进行的生成任务。"
                    )
                latest = self._latest_current_turn(
                    account_id,
                    session_id,
                    events=events,
                )
                if latest is None or latest["status"] in {"queued", "streaming"}:
                    raise_error(
                        "conflict", "TURN_IN_PROGRESS", "当前聊天有正在进行的生成任务。"
                    )
                if str(latest["user_message_id"] or "") != message_id:
                    raise_error(
                        "conflict", "MESSAGE_NOT_LATEST", "只能编辑最新一轮的用户问题。"
                    )

                model = self._validate_model(account_id, model_id, thinking_mode)
                normalized_resources = self._validate_context_resources(
                    account_id,
                    session_id,
                    context_resources,
                    model,
                )
                if not raw_text and not normalized_resources:
                    raise_error(
                        "invalid_input",
                        "INVALID_REQUEST",
                        "请输入问题或添加附件后再发送。",
                    )
                attached_resources = self.repository.file_resource_attachment_payloads(
                    account_id,
                    session_id,
                    normalized_resources,
                )

                turn_id = self.repository.new_id()
                final_assistant_message_id = self.repository.new_id()
                stream_id = f"stream_{turn_id}"
                timestamp = now_iso()
                try:
                    self._commit_turn_start(
                        account_id=account_id,
                        session_id=session_id,
                        expected_seq=len(events),
                        specifications=[
                            {
                                "type": "turn/start",
                                "timestamp": iso_to_epoch_ms(timestamp),
                                "data": {
                                    "turn_id": turn_id,
                                    "user_message_id": message_id,
                                    "final_assistant_message_id": final_assistant_message_id,
                                    "stream_id": stream_id,
                                    "supersedes_turn_id": latest["turn_id"],
                                    "edited_message_id": message_id,
                                    "model_id": model["model_id"],
                                },
                            },
                            {
                                "type": "user/message-update",
                                "timestamp": iso_to_epoch_ms(timestamp),
                                "data": {
                                    "message_id": message_id,
                                    "patch": {
                                        "content": raw_text,
                                        "model_id": model["model_id"],
                                        "thinking_mode": thinking_mode,
                                        "context_resources": normalized_resources,
                                    },
                                },
                            },
                            *[
                                {"type": "resource/attached", "data": resource}
                                for resource in attached_resources
                            ],
                        ],
                        turn_index={
                            "account_id": account_id,
                            "session_id": session_id,
                            "turn_id": turn_id,
                            "user_message_id": message_id,
                            "final_assistant_message_id": final_assistant_message_id,
                            "stream_id": stream_id,
                            "status": "queued",
                            "error_code": None,
                            "error_message": None,
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                        attached_resources=attached_resources,
                    )
                except SessionEventWriteConflictError:
                    continue
                self.repository.touch_session(account_id, session_id)
                session = self.repository.session_row(account_id, session_id)
                return {
                    "session_id": session_id,
                    "title": session["title"],
                    "member_id": session["member_id"],
                    "member_name": self.members.historical_member_name(
                        account_id, "conversation", session_id
                    ),
                    "turn_id": turn_id,
                    "user_message_id": message_id,
                    "final_assistant_message_id": final_assistant_message_id,
                    "assistant_parent_message_id": message_id,
                    "model_id": model["model_id"],
                    "message_status": "streaming",
                    "stream_id": stream_id,
                    "context_resources": normalized_resources,
                    "content": "",
                    "created_at": timestamp,
                }
        raise_error(
            "conflict", "TURN_IN_PROGRESS", "当前聊天内容持续变化，请稍后重试。"
        )

    def interrupt_member_session(self, account_id: str, session_id: str) -> None:
        """Discard queued work before cancelling; cancellation must not promote it."""
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            for queued in self.queue.inputs(account_id, session_id):
                self.queue.remove(account_id, session_id, queued["input_id"])
            for turn in self.repository.list_pending_turn_rows(account_id, session_id):
                self.cancel_turn(account_id, session_id, turn["turn_id"])

    @member_lifecycle_operation
    def cancel_turn(
        self,
        account_id: str,
        session_id: str,
        turn_id: str,
        preserve_partial: bool = True,
        *,
        reason: str = "cancelled",
    ) -> dict[str, Any]:
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            return self._cancel_turn_locked(
                account_id,
                session_id,
                turn_id,
                preserve_partial=preserve_partial,
                reason=reason,
            )

    def _cancel_turn_locked(
        self,
        account_id: str,
        session_id: str,
        turn_id: str,
        *,
        preserve_partial: bool,
        reason: str,
    ) -> dict[str, Any]:
        self.repository.ensure_session(account_id, session_id)
        turn = self.repository.turn_row(account_id, session_id, turn_id)
        if not turn:
            raise_error("missing", "NOT_FOUND", "轮次不存在。")
        if turn["status"] == "cancelled":
            self.jobs.cancel(account_id, session_id, turn["stream_id"])
            self.queue.promote_next(account_id, session_id)
            return {
                "session_id": session_id,
                "turn_id": turn_id,
                "status": "cancelled",
                "preserve_partial": preserve_partial,
                "stream_id": turn["stream_id"],
                "final_assistant_message_id": turn["final_assistant_message_id"],
            }
        if turn["status"] not in {"queued", "streaming"}:
            raise_error(
                "invalid_input", "INVALID_REQUEST", "当前轮次已结束，不能取消。"
            )

        self.jobs.cancel(account_id, session_id, turn["stream_id"])
        records = self._current_records(account_id, session_id)
        messages_by_id = {
            str(record.get("message_id") or record.get("record_id") or ""): {
                **record,
                "role": record.get("kind"),
            }
            for record in records
            if record.get("kind") in {"user", "assistant"}
        }
        user_message = messages_by_id.get(turn["user_message_id"] or "")
        if not user_message:
            raise_error("missing", "NOT_FOUND", "用户消息不存在。")

        timestamp = now_iso()
        if preserve_partial:
            persisted_assistant = (
                messages_by_id.get(turn["final_assistant_message_id"] or "") or {}
            )
            persisted_content = str(persisted_assistant.get("content") or "")
            # The live answer exists as model content before the terminal assistant
            # message is materialized. Preserve that durable text, never a browser
            # snapshot, reasoning, a nested model call, or another turn's output.
            model_content = next(
                (
                    str(record.get("value") or "")
                    for record in reversed(records)
                    if record.get("turn_id") == turn_id
                    and record.get("kind") == "model"
                    and record.get("channel") == "content"
                    and record.get("purpose") == "agent_action"
                    and not record.get("parent_tool_call_id")
                ),
                "",
            )
            if model_content.startswith(persisted_content):
                persisted_content = model_content
            content = persisted_content or CANCELLED_ASSISTANT_CONTENT
            self._append_cancelled_turn_messages(
                account_id=account_id,
                turn=turn,
                user_message=user_message,
                final_assistant_message_id=turn["final_assistant_message_id"],
                content=content,
                timestamp=timestamp,
                reason=reason,
            )
        else:
            self._append_turn_cancelled_record(
                account_id=account_id,
                turn=turn,
                preserve_partial=False,
                final_assistant_message_id=None,
                timestamp=timestamp,
                reason=reason,
            )
            self.repository.update_turn_cancelled(
                account_id,
                session_id,
                turn_id,
                None,
                error_code="STEERED" if reason == "steered" else "CANCELLED",
                error_message=(
                    "已因调整方向中断。" if reason == "steered" else "生成已取消。"
                ),
                timestamp=timestamp,
            )

        self.queue.promote_next(account_id, session_id)

        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "status": "cancelled",
            "preserve_partial": preserve_partial,
            "stream_id": turn["stream_id"],
            "final_assistant_message_id": turn["final_assistant_message_id"]
            if preserve_partial
            else None,
        }

    def _interrupt_expired_turn_jobs(self, account_id: str) -> None:
        cutoff = (local_now() - timedelta(seconds=TURN_JOB_LEASE_SECONDS)).isoformat()
        for turn in self.repository.expire_turn_jobs(account_id, cutoff):
            self.repository.append_session_events(
                account_id,
                turn["session_id"],
                [
                    *self._interrupted_activity_specifications(account_id, turn),
                    *self._open_step_end_specifications(
                        account_id,
                        turn,
                        status="interrupted",
                        error={
                            "code": "TURN_INTERRUPTED",
                            "message": "Agent Turn 运行租约已过期，任务已中断。",
                        },
                    ),
                    {
                        "type": "turn/end",
                        "data": {
                            "turn_id": turn["turn_id"],
                            "reason": {
                                "kind": "interrupted",
                                "code": "TURN_INTERRUPTED",
                                "message": "Agent Turn 运行租约已过期，任务已中断。",
                            },
                        },
                    },
                ],
            )
            self.queue.promote_next(account_id, str(turn["session_id"]))

    def _resume_session_work(self, account_id: str, session_id: str) -> None:
        pending = self.repository.list_pending_turn_rows(account_id, session_id)
        if any(turn["status"] == "streaming" for turn in pending) and self._member_accessible(account_id, session_id):
            # A leased worker already owns this turn. Reading its page must not
            # wait for its write lock or rebuild the indexes it is updating.
            return
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            if self.repository.session_row(account_id, session_id) is None:
                return
            events = self.repository.session_events(
                account_id, session_id, repair=False
            )
            self.repository.reconcile_session_indexes(
                account_id,
                session_id,
                events=events,
            )
            pending = self.repository.list_pending_turn_rows(account_id, session_id)
            if not self._member_accessible(account_id, session_id):
                for turn in pending:
                    self.cancel_turn(
                        account_id,
                        session_id,
                        str(turn["turn_id"]),
                        preserve_partial=True,
                        reason="permission_revoked",
                    )
                return
            if pending:
                first = pending[0]
                if first["status"] == "queued":
                    self.start_turn_job(account_id, session_id, str(first["stream_id"]))
                return
            self.queue.promote_next(account_id, session_id)

    def _execute_turn(
        self,
        account_id: str,
        turn,
        messages_by_id: dict[str, dict[str, Any]],
        *,
        cancellation_token: CancellationToken | None = None,
    ):

        def append_active_event(*args, **kwargs):
            with (
                member_lifecycle_guard(paths=self.paths),
                self.task_state.session_lock(account_id, turn["session_id"]),
            ):
                self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
                return self.repository.append_session_event(*args, **kwargs)

        self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
        user_message = messages_by_id.get(turn["user_message_id"] or "")
        if not user_message:
            self._record_turn_failure(account_id, turn, "NOT_FOUND", "用户消息不存在。")
            return

        final_assistant_message_id = turn["final_assistant_message_id"]
        model_call_id = self.repository.new_id()
        content_event_seqs: list[int] = []
        content_parts: list[str] = []
        response_started = False
        usage: dict[str, Any] = {}
        stop_reason = "end_turn"
        turn_started_at = time.monotonic()

        def append_assistant_chunk(chunk_payload: dict[str, Any]) -> int:
            self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
            event = append_active_event(
                account_id,
                turn["session_id"],
                "assistant/chunk",
                {
                    "turn_id": turn["turn_id"],
                    "step": self._current_model_step(account_id, turn),
                    "call_id": model_call_id,
                    "message_id": final_assistant_message_id,
                    "parent_message_id": user_message["message_id"],
                    "final_assistant_message_id": final_assistant_message_id,
                    "model_id": user_message.get("model_id"),
                    "duration_ms": elapsed_ms(
                        turn_started_at,
                        time.monotonic(),
                    ),
                    "created_at": now_iso(),
                    "chunk": chunk_payload,
                },
            )
            return event.seq

        def record_workflow(payload: dict[str, Any]) -> None:
            self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
            visible = visible_workflow_event(payload)
            if visible is None:
                return
            stage = visible["stage"]
            if stage == "tool":
                return
            append_active_event(
                account_id,
                turn["session_id"],
                "workflow/trace",
                {
                    "turn_id": turn["turn_id"],
                    "payload": dict(payload),
                    "created_at": now_iso(),
                },
            )

        def emit_workflow_record(payload: dict[str, Any]) -> None:
            self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
            record_workflow(payload)

        def stream_terminal_response_delta(delta: str) -> None:
            nonlocal response_started
            if not delta:
                return
            self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
            content_event_seqs.append(
                append_assistant_chunk({"type": "text-delta", "delta": delta})
            )
            content_parts.append(delta)
            if not response_started:
                response_started = True
                emit_workflow_record(
                    {
                        "stage": "content",
                        "status": "started",
                        "label": "流式输出阶段正文",
                        "detail": "正文会在聊天中同步出现",
                    }
                )

        def persist_failed_output(code: str, message: str) -> None:
            """Materialize already-streamed output before exposing turn failure."""
            if content_parts:
                timestamp = now_iso()
                append_active_event(
                    account_id,
                    turn["session_id"],
                    "assistant/message",
                    {
                        "turn_id": turn["turn_id"],
                        "message_id": final_assistant_message_id,
                        "parent_message_id": user_message["message_id"],
                        "model_id": user_message.get("model_id"),
                        "status": "failed",
                        "stop_reason": "error",
                        "usage": usage,
                        "content": "".join(content_parts),
                        "created_at": timestamp,
                        "error": {"code": code, "message": message},
                    },
                    timestamp=iso_to_epoch_ms(timestamp),
                    source_event_seqs=content_event_seqs,
                    surface_op="append",
                )
            self._record_turn_failure(account_id, turn, code, message)
            if content_parts:
                self.repository.touch_session(account_id, turn["session_id"])

        try:
            harness_results = [
                self._execute_agent_harness(
                    account_id,
                    turn,
                    user_message,
                    on_workflow_event=emit_workflow_record,
                    on_response_delta=stream_terminal_response_delta,
                    cancellation_token=cancellation_token,
                )
            ]
            terminal = harness_results[0].get("terminal_action")
            if not isinstance(terminal, dict):
                raise ValueError("Agent Harness 未产生自然语言终态内容。")
            terminal_content = str(terminal.get("content") or "")
            if not terminal_content.strip():
                raise ValueError("Agent Harness 返回了空内容。")
            streamed_content = "".join(content_parts)
            if streamed_content != terminal_content:
                if not terminal_content.startswith(streamed_content):
                    raise ValueError("Agent Harness 流式正文与最终动作内容不一致。")
                for delta in stream_text_chunks(
                    terminal_content[len(streamed_content) :]
                ):
                    stream_terminal_response_delta(delta)
            append_assistant_chunk({"type": "stop", "reason": stop_reason})
            if response_started:
                content_completed = {
                    "stage": "content",
                    "status": "completed",
                    "label": "流式输出阶段正文",
                    "detail": "本轮回复已完成",
                }
                emit_workflow_record(content_completed)
        except OperationCancelledError:
            return
        except ProviderChatCompletionError as exc:
            if self._turn_cancelled(
                account_id,
                turn,
                cancellation_token,
            ):
                return
            error_message = str(exc) or "模型服务调用失败。"
            persist_failed_output("MODEL_ERROR", error_message)
            return
        except Exception as exc:
            if self._turn_cancelled(
                account_id,
                turn,
                cancellation_token,
            ):
                return
            error_message = str(exc) or "生成过程发生内部错误。"
            append_active_event(
                account_id,
                turn["session_id"],
                "workflow/trace",
                {
                    "turn_id": turn["turn_id"],
                    "payload": {
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "message": error_message,
                    },
                },
            )
            persist_failed_output("INTERNAL_ERROR", error_message)
            return

        if self._turn_cancelled(account_id, turn, cancellation_token):
            return

        content = "".join(content_parts).strip()
        if not content:
            self._record_turn_failure(
                account_id, turn, "MODEL_ERROR", "模型服务返回了空回复。"
            )
            return

        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, turn["session_id"]),
        ):
            self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
            self._append_completed_turn_messages(
                account_id=account_id,
                turn=turn,
                user_message=user_message,
                final_assistant_message_id=final_assistant_message_id,
                content=content,
                stop_reason=stop_reason,
                usage=usage,
                source_event_seqs=content_event_seqs,
            )
        self._finish_completed_turn_session_index(
            account_id,
            turn,
        )

    def _trusted_attachment_resource(
        self,
        account_id: str,
        session_id: str,
        resource_id: str,
    ) -> dict[str, Any] | None:
        row = self.repository.resource_row(account_id, session_id, resource_id)
        if (
            row is None
            or row["storage_status"] != "ready"
            or row["lifecycle_status"] in {"expired", "deleted"}
        ):
            return None
        path = self.repository.attachment_cleanup_path(
            account_id, str(row["relative_path"])
        )
        if path is None or not path.is_file():
            return None
        return {
            "resource_id": resource_id,
            "path": str(path.resolve()),
            "original_filename": str(row["original_filename"]),
            "mime_type": str(row["mime_type"]),
            "sha256": str(row["sha256"]),
        }

    def context_resource_download(
        self,
        account_id: str,
        session_id: str,
        resource_id: str,
    ) -> tuple[Path, str, str]:
        """Resolve one account_id-scoped conversation attachment for user preview."""

        self._maintain_attachments(account_id)
        row = self.repository.resource_row(account_id, session_id, resource_id)
        if (
            row is None
            or row["storage_status"] != "ready"
            or row["lifecycle_status"] in {"expired", "deleted"}
        ):
            raise_error("missing", "RESOURCE_NOT_FOUND", "附件不存在或已过期。")
        resource = self._trusted_attachment_resource(
            account_id,
            session_id,
            resource_id,
        )
        if resource is None:
            raise_error("missing", "RESOURCE_NOT_FOUND", "附件不存在或已过期。")
        return (
            Path(str(resource["path"])),
            str(resource["original_filename"]),
            str(resource["mime_type"]),
        )

    def _visible_attachments_for_messages(
        self,
        account_id: str,
        session_id: str,
        messages_by_id: dict[str, dict[str, Any]],
        visible_message_ids: set[str],
    ) -> dict[str, dict[str, Any]]:
        """Trusted metadata for every branch-visible file, including past turns."""

        visible_attachments: dict[str, dict[str, Any]] = {}
        for message_id in sorted(visible_message_ids):
            visible_message = messages_by_id.get(message_id)
            if not isinstance(visible_message, dict):
                continue
            if visible_message.get("role") != "user":
                continue
            for resource in visible_message.get("context_resources", []):
                if not isinstance(resource, dict):
                    continue
                if resource.get("resource_type") != "file":
                    continue
                resource_id = str(resource.get("resource_id") or "")
                if not resource_id or resource_id in visible_attachments:
                    continue
                trusted_resource = self._trusted_attachment_resource(
                    account_id, session_id, resource_id
                )
                if trusted_resource is None:
                    continue
                visible_attachments[resource_id] = trusted_resource
        return visible_attachments

    def _execute_agent_harness(
        self,
        account_id: str,
        turn,
        user_message: dict[str, Any],
        *,
        on_workflow_event: Callable[[dict[str, Any]], None],
        on_response_delta: Callable[[str], None] | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, Any]:
        """Run one Harness Turn, restoring Skills visible in this session."""

        self._raise_if_turn_cancelled(account_id, turn, cancellation_token)

        from backend.app.agent_runtime.context import AgentContext
        from backend.app.agent_runtime.runtime import AgentHarnessRuntime
        from backend.app.agent_runtime.tools.registry import ToolRegistry
        from backend.app.plugins import (
            PluginRuntimeContext,
            build_available_tools,
            resolve_plugin_input_model_resources,
            resolve_plugin_model_resource_refs,
        )

        session_id = str(turn["session_id"])
        turn_id = str(turn["turn_id"])
        session_events = self.repository.session_events(
            account_id, session_id, repair=False
        )
        current_message_records = {
            str(record.get("message_id") or record.get("record_id") or ""): {
                **record,
                "role": record.get("kind"),
            }
            for record in self._current_records(account_id, session_id)
            if record.get("kind") in {"user", "assistant"}
        }
        visible_message_ids = {
            str(record.get("message_id") or record.get("record_id") or "")
            for record in current_message_records.values()
        }
        initial_skill_names = visible_loaded_skill_names(
            session_events,
            current_turn_ids=[turn_id],
        )
        base_decision_model = self._validate_model(
            account_id,
            user_message.get("model_id"),
            user_message.get("thinking_mode", "default"),
        )
        active_user_message_records = [
            record
            for record in current_message_records.values()
            if record.get("role") == "user"
        ]
        session_file_resources: list[dict[str, Any]] = []
        seen_file_resource_ids: set[str] = set()
        for message_record in active_user_message_records:
            for resource in message_record.get("context_resources", []):
                if not isinstance(resource, dict):
                    continue
                if resource.get("resource_type") != "file":
                    continue
                resource_id = str(resource.get("resource_id") or "")
                if not resource_id or resource_id in seen_file_resource_ids:
                    continue
                seen_file_resource_ids.add(resource_id)
                session_file_resources.append(dict(resource))
        decision_model, session_attachment_parts = self._model_and_attachment_parts(
            account_id,
            session_id,
            session_file_resources,
            base_decision_model,
        )
        attachment_parts_by_resource_id: dict[str, list[dict[str, Any]]] = {}
        for part in session_attachment_parts:
            resource_id = str(part.get("source_resource_id") or "")
            if resource_id:
                attachment_parts_by_resource_id.setdefault(resource_id, []).append(part)
        current_parent_tool_call_id: dict[str, str | None] = {"value": None}

        def resolve_conversation_resource(resource_id: str) -> dict[str, Any] | None:
            return self._trusted_attachment_resource(
                account_id, session_id, resource_id
            )

        def resolve_message(message_id: str) -> dict[str, Any] | None:
            return self.repository.messages_by_id(account_id, session_id).get(
                message_id
            )

        def resolve_tool_observation(
            *,
            call_id: str,
            allowed_tools: set[str],
            session_id: str,
            visible_message_ids: set[str],
        ) -> dict[str, Any] | None:
            """Resolve one branch-visible Tool result as trusted execution evidence."""

            if session_id != str(turn["session_id"]):
                return None
            events = self.repository.session_events(
                account_id, session_id, repair=False
            )
            turn_users = {
                str(event.data.get("turn_id") or ""): str(
                    event.data.get("user_message_id") or ""
                )
                for event in events
                if event.type == "turn/start"
            }
            matched_call = None
            for event in events:
                if event.type != "tool/call":
                    continue
                if str(event.data.get("call_id") or "") != call_id:
                    continue
                if str(event.data.get("name") or "") not in allowed_tools:
                    continue
                source_message_id = turn_users.get(
                    str(event.data.get("turn_id") or ""), ""
                )
                if source_message_id not in visible_message_ids:
                    continue
                matched_call = (event, source_message_id)
            if matched_call is None:
                return None
            call_event, source_message_id = matched_call
            raw_result = None
            for event in events:
                if event.type != "tool/result":
                    continue
                if any(
                    event.data.get(key) != call_event.data.get(key)
                    for key in ("turn_id", "tool_call_id", "name")
                ):
                    continue
                if str(event.data.get("call_id") or "") != call_id:
                    continue
                if str(event.data.get("name") or "") not in allowed_tools:
                    continue
                if str(event.data.get("status") or "") != "completed":
                    details = (event.data.get("error") or {}).get("details") or {}
                    if details.get("execution_completed") is not True:
                        continue
                raw_result = event.data.get("result")
            if not isinstance(raw_result, dict):
                return None
            output = raw_result.get("output")
            if raw_result.get("type") != "tool_result" or not isinstance(output, dict):
                output = raw_result
            return {
                "call_id": call_id,
                "tool_name": str(call_event.data.get("name") or ""),
                "session_id": session_id,
                "source_message_id": source_message_id,
                "output": decode_tabular_json(output),
            }

        member_access = self._session_member_access(account_id, session_id)
        member_metadata: dict[str, Any] = {}
        if member_access is not None:
            with member_access.guard() as live:
                member_metadata = self.members.detail(live, self.paths)
        tool_registry = ToolRegistry()
        plugin_runtime_context = PluginRuntimeContext(
            service_factory=lambda plugin_id: self.services.plugin_service(
                account_id,
                member_access.member_id if member_access else None,
                plugin_id,
            ),
            account_id=account_id,
            member_id=member_access.member_id if member_access is not None else None,
            event_recorder=on_workflow_event,
            observation_resolver=resolve_tool_observation,
            conversation_resource_resolver=resolve_conversation_resource,
            message_resolver=resolve_message,
        )
        for tool in build_available_tools(runtime_context=plugin_runtime_context):
            tool_registry.register(tool)

        visible_attachments = self._visible_attachments_for_messages(
            account_id,
            session_id,
            current_message_records,
            visible_message_ids,
        )

        runtime_model_resource_observations: list[dict[str, Any]] = []

        def model_resource_parts(
            refs: list[dict[str, Any]],
            current_model: dict[str, Any],
            *,
            resolved_resources: list[dict[str, Any]] | None = None,
        ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
            resources = (
                resolved_resources
                if resolved_resources is not None
                else resolve_plugin_model_resource_refs(
                    runtime_context=plugin_runtime_context,
                    resource_refs=refs,
                )
            )
            resolved = [
                (
                    resource,
                    (
                        Path(str(resource["path"]))
                        if str(resource.get("path") or "")
                        else None
                    ),
                    str(resource.get("original_filename") or ""),
                    str(resource.get("mime_type") or ""),
                )
                for resource in resources
            ]

            def can_read(model: dict[str, Any], mime_type: str) -> bool:
                if mime_type == "text/plain":
                    return True
                return self._model_can_forward_attachment(model, mime_type) or (
                    mime_type == "application/pdf"
                    and self._model_can_forward_attachment(model, "image/jpeg")
                )

            candidates = [current_model]
            fallback = self.model_catalog.default_model_for_account(
                account_id, "vision_parse"
            )
            if fallback and fallback.get("model_id") != current_model.get("model_id"):
                candidates.append(fallback)
            selected = next(
                (
                    model
                    for model in candidates
                    if all(
                        can_read(model, mime_type)
                        for _ref, _path, _name, mime_type in resolved
                    )
                ),
                None,
            )
            if selected is None:
                raise_error(
                    "invalid_structure",
                    "MODEL_FILE_UNSUPPORTED",
                    "当前聊天模型和视觉后备模型都不能读取工具返回的原件资源。",
                )

            parts: list[dict[str, Any]] = []
            for ref, path, name, mime_type in resolved:
                safe_ref = {
                    key: value
                    for key, value in ref.items()
                    if key not in {"path", "text"}
                }
                identifiers = {"model_resource_ref": safe_ref}
                if mime_type == "text/plain":
                    source_text = ref.get("text")
                    if not isinstance(source_text, str):
                        if path is None:
                            raise ProviderChatCompletionError(
                                "模型文本资源缺少可读取内容。"
                            )
                        try:
                            source_text = path.read_text(encoding="utf-8")
                        except (OSError, UnicodeDecodeError) as exc:
                            raise ProviderChatCompletionError(
                                "工具返回的文本原件无法读取。"
                            ) from exc
                    parts.append(
                        {
                            "type": "text",
                            "text": source_text,
                            "name": name,
                            **identifiers,
                        }
                    )
                    continue
                if (
                    mime_type == "application/pdf"
                    and not self._model_can_forward_attachment(selected, mime_type)
                ):
                    if path is None:
                        raise ProviderChatCompletionError(
                            "模型 PDF 资源缺少可读取原件。"
                        )
                    from backend.app.application.attachment_rendering import (
                        model_file_parts,
                    )

                    rendered = model_file_parts(
                        path,
                        mime_type,
                        deadline=time.monotonic() + 60,
                    )
                    parts.extend({**dict(page), **identifiers} for page in rendered)
                    continue
                if path is None:
                    raise ProviderChatCompletionError("模型资源缺少可读取原件。")
                try:
                    content = path.read_bytes()
                except OSError as exc:
                    raise ProviderChatCompletionError(
                        "工具返回的原件无法读取。"
                    ) from exc
                part_type = "image" if mime_type.startswith("image/") else "file"
                parts.append(
                    {
                        "type": part_type,
                        "mime_type": mime_type,
                        "name": name,
                        "data_base64": base64.b64encode(content).decode("ascii"),
                        **identifiers,
                    }
                )
            return selected, parts

        input_model_resources = resolve_plugin_input_model_resources(
            runtime_context=plugin_runtime_context,
            resource_refs=[
                dict(resource)
                for resource in user_message.get("context_resources", [])
                if isinstance(resource, dict)
            ],
        )
        decision_model, runtime_context_resource_parts = model_resource_parts(
            [],
            decision_model,
            resolved_resources=input_model_resources,
        )
        annotation_input_parts = [
            {
                "type": "text",
                "text": ATTACHED_ANNOTATION_PREFIX
                + json.dumps(
                    {
                        "resource_id": resource.get("resource_id"),
                        "source_record_id": resource.get("source_record_id"),
                        "annotation_text": resource.get("annotation_text"),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "name": "注释",
                "model_resource_ref": {
                    "resource_type": "record_annotation",
                    "resource_id": resource.get("resource_id"),
                    "source_record_id": resource.get("source_record_id"),
                },
            }
            for resource in user_message.get("context_resources", [])
            if isinstance(resource, dict)
            and resource.get("resource_type") == "record_annotation"
        ]
        current_runtime_input_parts = [
            *annotation_input_parts,
            *runtime_context_resource_parts,
        ]
        requested_thinking_mode = self._thinking_mode_for_model(
            decision_model,
            str(user_message.get("thinking_mode") or "default"),
        )
        effective_thinking_mode, thinking_mode_reasons = (
            self._effective_thinking_mode_for_turn(
                decision_model,
                requested_thinking_mode,
                has_tools=tool_registry.has_tools(),
                attachment_parts=[
                    *session_attachment_parts,
                    *runtime_context_resource_parts,
                ],
            )
        )
        if effective_thinking_mode != requested_thinking_mode:
            self.repository.append_session_event(
                account_id,
                turn["session_id"],
                "turn/thinking_mode_changed",
                {
                    "turn_id": turn["turn_id"],
                    "requested_mode": requested_thinking_mode,
                    "effective_mode": effective_thinking_mode,
                    "reasons": thinking_mode_reasons,
                    "created_at": now_iso(),
                },
            )

        def append_model_surface(
            *,
            role: str,
            content: Any,
            message_id: str,
            tool_calls: list[dict[str, Any]] | None = None,
        ) -> None:
            self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
            event_type = "assistant/message" if role == "assistant" else "user/message"
            data = {
                "turn_id": turn["turn_id"],
                "message_id": message_id,
                "parent_message_id": user_message["message_id"],
                "model_id": user_message.get("model_id"),
                "branch_addressable": False,
                "status": "completed",
                "content": content,
                "created_at": now_iso(),
            }
            if tool_calls is not None:
                data["tool_calls"] = tool_calls
            self.repository.append_session_event(
                account_id,
                turn["session_id"],
                event_type,
                data,
                surface_op="append",
            )

        def handle_runtime_event(event) -> None:
            nonlocal decision_model
            payload = dict(getattr(event, "payload", {}) or {})
            if event.type in {"tool_result", "tool_error"}:
                persisted = self._persist_runtime_tool_result(
                    account_id,
                    turn,
                    payload,
                    failed=event.type == "tool_error",
                    cancellation_token=cancellation_token,
                )
                # Cancellation stops subsequent actions, not the audit of an
                # already executed call. Do not expand resources after cancel.
                self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
                if not persisted:
                    return
            else:
                self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
            if event.type == "assistant_tool_calls":
                calls = list(payload.get("tool_calls") or [])
                append_model_surface(
                    role="assistant",
                    content=payload.get("content"),
                    message_id=(
                        "assistant_tools_"
                        + str(calls[0].get("id") if calls else self.repository.new_id())
                    ),
                    tool_calls=calls,
                )
                return
            if event.type == "assistant_intermediate":
                append_model_surface(
                    role="assistant",
                    content=payload.get("content", ""),
                    message_id=f"assistant_internal_{self.repository.new_id()}",
                )
                return
            if event.type == "harness_observation":
                step = self._current_model_step(account_id, turn)
                self.repository.append_session_event(
                    account_id,
                    turn["session_id"],
                    "harness/observation",
                    {
                        "turn_id": turn["turn_id"],
                        "step": step,
                        "call_id": current_parent_tool_call_id["value"],
                        "observation": payload,
                        "status": "failed" if payload.get("error") else "completed",
                        "created_at": now_iso(),
                    },
                )
                return
            if event.type == "tool_call":
                tool_name = str(payload.get("tool") or "")
                call_id = str(payload.get("call_id") or "")
                current_parent_tool_call_id["value"] = str(
                    payload.get("tool_call_id") or payload.get("call_id") or ""
                )
                self.repository.append_session_event(
                    account_id,
                    turn["session_id"],
                    "tool/call",
                    {
                        "turn_id": turn["turn_id"],
                        "step": self._current_model_step(account_id, turn),
                        "call_id": str(payload.get("call_id")),
                        "tool_call_id": str(payload.get("tool_call_id")),
                        "name": tool_name,
                        "arguments": payload.get("arguments", {}),
                        "created_at": now_iso(),
                    },
                )
                on_workflow_event(
                    {
                        "stage": "tool",
                        "status": "started",
                        "label": tool_name,
                        "detail": "正在执行工具调用",
                        "_persisted_call_id": payload.get("call_id"),
                        "_tool_call_id": payload.get("tool_call_id"),
                        "_step": self._current_model_step(account_id, turn),
                        "_tool_name": tool_name,
                        "_raw_input": payload.get("arguments"),
                    }
                )
                return
            if event.type in {"tool_result", "tool_error"}:
                tool_name = str(payload.get("tool") or "")
                failed = event.type == "tool_error"
                call_id = str(payload.get("call_id") or "")
                if not failed:
                    observation = payload.get("output")
                    effects = (
                        observation.get("effects")
                        if isinstance(observation, dict)
                        else None
                    )
                    refs = (
                        effects.get("model_resource_refs")
                        if isinstance(effects, dict)
                        else None
                    )
                    if isinstance(refs, list) and refs:
                        decision_model, parts = model_resource_parts(
                            [dict(item) for item in refs if isinstance(item, dict)],
                            decision_model,
                        )
                        runtime_model_resource_observations.append(
                            {
                                "call_id": call_id,
                                "refs": [
                                    dict(item)
                                    for item in refs
                                    if isinstance(item, dict)
                                ],
                                "parts": parts,
                            }
                        )
                on_workflow_event(
                    {
                        "stage": "tool",
                        "status": "failed" if failed else "completed",
                        "label": tool_name,
                        "detail": "工具调用失败，结果已返回 Agent"
                        if failed
                        else "工具调用已完成",
                        "_persisted_call_id": payload.get("call_id"),
                        "_tool_call_id": payload.get("tool_call_id"),
                        "_step": self._current_model_step(account_id, turn),
                        "_tool_name": tool_name,
                        "_raw_output": None if failed else payload.get("output"),
                        **({"_raw_error": payload.get("error")} if failed else {}),
                    }
                )
                current_parent_tool_call_id["value"] = None

        def derive_runtime_messages(surface_events=None) -> list[dict[str, Any]]:
            self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
            messages = derive_model_messages(
                surface_events
                if surface_events is not None
                else self.repository.session_events(
                    account_id, session_id, repair=False
                ),
                current_turn_ids=[turn_id],
                include_user_context=True,
            )
            current_message_id = str(user_message.get("message_id") or "")
            included_user_message_ids: set[str] = set()
            for message in messages:
                message_id = str(message.pop("_message_id", "") or "")
                resources = message.pop("_context_resources", [])
                if message.get("role") != "user" or not message_id:
                    continue
                included_user_message_ids.add(message_id)
                input_parts: list[dict[str, Any]] = []
                for resource in resources:
                    if not isinstance(resource, dict):
                        continue
                    resource_id = str(resource.get("resource_id") or "")
                    input_parts.extend(
                        dict(part)
                        for part in attachment_parts_by_resource_id.get(resource_id, [])
                    )
                if message_id == current_message_id:
                    input_parts.extend(
                        dict(part) for part in current_runtime_input_parts
                    )
                if not input_parts:
                    continue
                content = message.get("content")
                if isinstance(content, list):
                    message["content"] = [*content, *input_parts]
                else:
                    message["content"] = [
                        {"type": "text", "text": str(content or "")},
                        *input_parts,
                    ]
            compacted_attachment_messages: list[dict[str, Any]] = []
            for message_record in active_user_message_records:
                message_id = str(
                    message_record.get("message_id")
                    or message_record.get("record_id")
                    or ""
                )
                if not message_id or message_id in included_user_message_ids:
                    continue
                input_parts: list[dict[str, Any]] = []
                for resource in message_record.get("context_resources", []):
                    if not isinstance(resource, dict):
                        continue
                    resource_id = str(resource.get("resource_id") or "")
                    input_parts.extend(
                        dict(part)
                        for part in attachment_parts_by_resource_id.get(resource_id, [])
                    )
                if input_parts:
                    compacted_attachment_messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "历史附件原文（相关用户请求见历史摘要）。",
                                },
                                *input_parts,
                            ],
                        }
                    )
            if compacted_attachment_messages:
                messages = [*compacted_attachment_messages, *messages]
            resource_messages: list[dict[str, Any]] = []
            for observation in runtime_model_resource_observations:
                resource_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "TOOL_RESOURCE_OBSERVATION\n"
                                + json.dumps(
                                    {
                                        "tool_call_id": observation["call_id"],
                                        "resources": observation["refs"],
                                    },
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                            },
                            *observation["parts"],
                        ],
                    }
                )
            # Resource observations are user messages. Keep them outside a
            # pending native tool group while checking a candidate result.
            pending_ids: set[str] = set()
            pending_start = len(messages)
            for index, message in enumerate(messages):
                if message.get("role") == "assistant" and message.get("tool_calls"):
                    pending_start = index
                    pending_ids = {str(call["id"]) for call in message["tool_calls"]}
                elif message.get("role") == "tool":
                    pending_ids.discard(str(message.get("tool_call_id") or ""))
            insertion = pending_start if pending_ids else len(messages)
            messages[insertion:insertion] = resource_messages
            seen_parts: set[str] = set()
            for message in messages:
                if not isinstance(message.get("content"), list):
                    continue
                unique_parts = []
                for part in message["content"]:
                    if not isinstance(part, dict) or (
                        part.get("type") == "text"
                        and not part.get("source_resource_id")
                        and not part.get("model_resource_ref")
                    ):
                        unique_parts.append(part)
                        continue
                    key = hashlib.sha256(
                        json.dumps(part, sort_keys=True).encode()
                    ).hexdigest()
                    if key not in seen_parts:
                        unique_parts.append(part)
                        seen_parts.add(key)
                message["content"] = unique_parts
            return [message for message in messages if message.get("content") != []]

        def refresh_member_context():
            self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
            if member_access is not None:
                with member_access.guard() as live:
                    member_metadata.clear()
                    member_metadata.update(self.members.detail(live, self.paths))

        def complete_agent_step(request: ModelRequest):
            self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
            return self.model_calls.complete_chat_with_events(
                account_id=account_id,
                turn=turn,
                user_message=user_message,
                model=decision_model,
                model_request=request,
                thinking_mode=self._thinking_mode_for_model(
                    decision_model,
                    effective_thinking_mode,
                ),
                purpose="agent_action",
                timeout_seconds=90,
                cancellation_token=cancellation_token,
            )

        runtime = AgentHarnessRuntime(tool_registry=tool_registry)
        authorized_resource_ids: dict[str, list[str]] = {}
        for resource in user_message.get("context_resources", []):
            resource_type = str(resource.get("resource_type") or "").strip()
            resource_id = str(resource.get("resource_id") or "").strip()
            if resource_type and resource_id:
                authorized_resource_ids.setdefault(resource_type, []).append(
                    resource_id
                )
        agent_context = AgentContext(
            account_id=account_id,
            member_id=member_access.member_id if member_access is not None else None,
            task_type="conversation",
            input_text=str(user_message.get("content") or ""),
            session_id=str(turn["session_id"]),
            model_id=user_message.get("model_id"),
            resources=list(user_message.get("context_resources", [])),
            memory={
                "current_message_id": str(user_message.get("message_id") or ""),
                "visible_message_ids": sorted(visible_message_ids),
                "visible_attachments": visible_attachments,
                "attachment_parts": session_attachment_parts,
                "authorized_resource_ids": authorized_resource_ids,
                **({"member": member_metadata} if member_metadata else {}),
            },
        )
        failed_compactions: set[str] = set()

        def derive_skill_names():
            return visible_loaded_skill_names(
                self.repository.session_events(account_id, session_id, repair=False),
                current_turn_ids=[turn_id],
            )

        def prepare_action_request(
            request: ModelRequest, force: bool = False, *, tool_result=False
        ):
            refresh_member_context()
            assembly_time = local_now()
            # The candidate tool result has not been persisted and is never a
            # checkpoint source. Keep it attached during budget validation.
            pending_messages = [dict(request.messages[-1])] if tool_result else []
            allowed_names = {tool.name for tool in request.tools}
            suspended = {
                item["name"]
                for item in tool_registry.catalog(context=agent_context)
                if item["name"] not in allowed_names
            }

            def rebuild(surface_events):
                refresh_member_context()
                read_skills = {
                    name: runtime.skill_registry.get(name).read(agent_context)
                    for name in visible_loaded_skill_names(
                        surface_events,
                        current_turn_ids=[turn_id],
                    )
                }
                return runtime.rebuild_request(
                    read_skills=read_skills,
                    context=agent_context,
                    suspended_tools=suspended,
                    template=request,
                    runtime_context_overrides={
                        "current_time": assembly_time.isoformat(),
                        "current_date": assembly_time.date().isoformat(),
                    },
                    messages=[
                        *derive_runtime_messages(surface_events),
                        *pending_messages,
                    ],
                )

            try:
                return self.compaction.compact_model_request_if_needed(
                    account_id=account_id,
                    turn=turn,
                    user_message=user_message,
                    model=decision_model,
                    model_request=request,
                    thinking_mode=effective_thinking_mode,
                    rebuild_request=rebuild,
                    cancellation_token=cancellation_token,
                    force=force,
                    reason="tool_result" if tool_result else "threshold",
                    failed_fingerprints=failed_compactions,
                    allow_pending=tool_result,
                )
            except CompactionError:
                if tool_result:
                    # The runtime returns a bounded, truthful size error for
                    # this already-executed call, then resumes its action loop.
                    return request
                raise

        result = runtime.execute(
            agent_context,
            initial_skill_names=initial_skill_names,
            on_event=handle_runtime_event,
            derive_messages=derive_runtime_messages,
            complete_model=complete_agent_step,
            before_model_request=refresh_member_context,
            derive_skill_names=derive_skill_names,
            prepare_request=prepare_action_request,
            before_tool_result=lambda request: prepare_action_request(
                request, tool_result=True
            ),
            estimate_request_tokens=lambda request: (
                self.compaction.estimate_model_request_tokens(
                    ModelProviderService.prepare_transport_request(
                        decision_model, request, effective_thinking_mode
                    )
                )
            ),
            context_window_tokens=(
                int(
                    decision_model.get("context_window_tokens")
                    or DEFAULT_CONTEXT_WINDOW_TOKENS
                )
            ),
            reserved_output_tokens=int(
                decision_model.get("max_output_tokens")
                or DEFAULT_RESERVED_OUTPUT_TOKENS
            ),
        )
        self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
        return result.output

    def _append_completed_turn_messages(
        self,
        account_id: str,
        turn,
        user_message: dict[str, Any],
        final_assistant_message_id: str,
        content: str,
        stop_reason: str,
        usage: dict[str, Any],
        source_event_seqs: list[int],
    ) -> dict[str, Any]:
        timestamp = now_iso()
        durable_sources = list(source_event_seqs)
        assistant_payload = {
            "turn_id": turn["turn_id"],
            "message_id": final_assistant_message_id,
            "parent_message_id": user_message["message_id"],
            "model_id": user_message.get("model_id"),
            "status": "completed",
            "stop_reason": stop_reason,
            "duration_ms": 1,
            "usage": usage,
            "content": content,
            "created_at": timestamp,
        }
        self.repository.append_session_events(
            account_id,
            turn["session_id"],
            [
                *self._interrupted_activity_specifications(account_id, turn),
                {
                    "type": "assistant/message",
                    "timestamp": iso_to_epoch_ms(timestamp),
                    "surface_op": "append",
                    "source_event_seqs": durable_sources,
                    "data": assistant_payload,
                },
                {
                    "type": "turn/end",
                    "timestamp": iso_to_epoch_ms(timestamp),
                    "data": {
                        "turn_id": turn["turn_id"],
                        "reason": {"kind": "completed"},
                    },
                },
            ],
        )
        self.repository.update_turn_completed(
            account_id,
            turn["session_id"],
            turn["turn_id"],
            final_assistant_message_id,
            timestamp,
        )
        return {"timestamp": timestamp}

    def _finish_completed_turn_session_index(
        self,
        account_id: str,
        turn,
    ) -> None:
        self.repository.touch_session(account_id, turn["session_id"])

    def _append_cancelled_turn_messages(
        self,
        account_id: str,
        turn,
        user_message: dict[str, Any],
        final_assistant_message_id: str,
        content: str,
        timestamp: str,
        reason: str,
    ) -> None:
        error_code = "STEERED" if reason == "steered" else "CANCELLED"
        error_message = "已因调整方向中断。" if reason == "steered" else "生成已取消。"
        specifications: list[dict[str, Any]] = (
            self._interrupted_activity_specifications(
                account_id,
                turn,
            )
        )
        specifications.extend(
            self._open_step_end_specifications(
                account_id,
                turn,
                status="interrupted",
                error={
                    "code": error_code,
                    "message": error_message,
                },
            )
        )
        specifications.extend(
            [
                {
                    "type": "assistant/message",
                    "timestamp": iso_to_epoch_ms(timestamp),
                    "surface_op": "append",
                    "data": {
                        "turn_id": turn["turn_id"],
                        "message_id": final_assistant_message_id,
                        "parent_message_id": user_message["message_id"],
                        "model_id": user_message.get("model_id"),
                        "status": "cancelled",
                        "stop_reason": reason,
                        "duration_ms": 1,
                        "usage": {},
                        "content": content,
                        "created_at": timestamp,
                    },
                },
                {
                    "type": "turn/end",
                    "timestamp": iso_to_epoch_ms(timestamp),
                    "data": {
                        "turn_id": turn["turn_id"],
                        "reason": {
                            "kind": reason,
                            "preserve_partial": True,
                            "code": error_code,
                            "message": error_message,
                        },
                    },
                },
            ]
        )
        self.repository.append_session_events(
            account_id,
            turn["session_id"],
            specifications,
        )
        self.repository.update_turn_cancelled(
            account_id,
            turn["session_id"],
            turn["turn_id"],
            final_assistant_message_id,
            error_code=error_code,
            error_message=error_message,
            timestamp=timestamp,
        )
        self.repository.touch_session(account_id, turn["session_id"])

    def _append_turn_cancelled_record(
        self,
        account_id: str,
        turn,
        preserve_partial: bool,
        final_assistant_message_id: Optional[str],
        timestamp: str,
        reason: str,
    ) -> None:
        error_code = "STEERED" if reason == "steered" else "CANCELLED"
        error_message = "已因调整方向中断。" if reason == "steered" else "生成已取消。"
        self.repository.append_session_events(
            account_id,
            turn["session_id"],
            [
                *self._interrupted_activity_specifications(account_id, turn),
                *self._open_step_end_specifications(
                    account_id,
                    turn,
                    status="interrupted",
                    error={
                        "code": error_code,
                        "message": error_message,
                    },
                ),
                {
                    "type": "turn/end",
                    "timestamp": iso_to_epoch_ms(timestamp),
                    "data": {
                        "turn_id": turn["turn_id"],
                        "reason": {
                            "kind": reason,
                            "preserve_partial": preserve_partial,
                            "final_assistant_message_id": final_assistant_message_id,
                        },
                    },
                },
            ],
        )

    def _turn_is_cancelled(self, account_id: str, turn) -> bool:
        current = self.repository.turn_row(
            account_id, turn["session_id"], turn["turn_id"]
        )
        return bool(current and current["status"] == "cancelled")

    def _turn_cancelled(
        self,
        account_id: str,
        turn,
        cancellation_token: CancellationToken | None,
    ) -> bool:
        if cancellation_token is not None:
            return cancellation_token.is_cancelled or self._turn_is_cancelled(
                account_id, turn
            )
        return self._turn_is_cancelled(account_id, turn)

    def _raise_if_turn_cancelled(
        self,
        account_id: str,
        turn,
        cancellation_token: CancellationToken | None,
    ) -> None:
        self._session_member_access(account_id, str(turn["session_id"]))
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()
        if self._turn_is_cancelled(account_id, turn):
            raise OperationCancelledError("Agent Turn 已取消。")

    def _next_model_step(self, account_id: str, turn) -> int:
        return self._current_model_step(account_id, turn) + 1

    def _current_model_step(self, account_id: str, turn) -> int:
        return max(
            (
                int(event.data.get("step") or 0)
                for event in self.repository.session_events(
                    account_id, turn["session_id"], repair=False
                )
                if event.type == "step/start"
                and str(event.data.get("turn_id") or "") == str(turn["turn_id"])
            ),
            default=0,
        )

    def _interrupted_activity_specifications(
        self, account_id: str, turn
    ) -> list[dict[str, Any]]:
        return interrupted_activity_specifications(
            self.repository.session_events(
                account_id, turn["session_id"], repair=False
            ),
            str(turn["turn_id"]),
        )

    def _open_step_end_specifications(
        self,
        account_id: str,
        turn,
        *,
        status: str,
        error: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        activity = reduce_session_activity(
            self.repository.session_events(account_id, turn["session_id"], repair=False)
        )
        open_steps = activity.for_turn(str(turn["turn_id"])).steps
        return [
            {
                "type": "step/end",
                "data": {
                    "turn_id": turn["turn_id"],
                    "step": step,
                    "status": status,
                    **({"error": error} if error else {}),
                },
            }
            for step in sorted(open_steps)
        ]

    def _persist_runtime_tool_result(
        self,
        account_id: str,
        turn,
        payload: dict[str, Any],
        *,
        failed: bool,
        cancellation_token: CancellationToken | None = None,
    ) -> bool:
        """Finalize an existing call once, including after cancellation."""
        session_id, turn_id = str(turn["session_id"]), str(turn["turn_id"])
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            self._session_member_access(account_id, session_id)
            if failed:
                details = (payload.get("error") or {}).get("details") or {}
                if details.get("execution_completed") is not True:
                    self._raise_if_turn_cancelled(account_id, turn, cancellation_token)
            events = self.repository.session_events(
                account_id, session_id, repair=False
            )
            identity = {
                "turn_id": turn_id,
                "call_id": str(payload.get("call_id") or ""),
                "tool_call_id": str(payload.get("tool_call_id") or ""),
                "name": str(payload.get("tool") or ""),
            }
            calls = [
                event
                for event in events
                if event.type == "tool/call"
                and all(event.data.get(key) == value for key, value in identity.items())
            ]
            if (
                not all(identity.values())
                or len(calls) != 1
                or not any(
                    event.type == "turn/start" and event.data.get("turn_id") == turn_id
                    for event in events
                )
            ):
                raise_error(
                    "conflict",
                    "TOOL_RESULT_CALL_MISMATCH",
                    "工具结果没有匹配的既有工具调用。",
                )
            data = {
                **identity,
                "step": calls[0].data.get("step", 0),
                "result": payload.get("output"),
                "status": "failed" if failed else "completed",
                **({"error": payload.get("error")} if failed else {}),
            }
            previous = next(
                (
                    event
                    for event in reversed(events)
                    if event.type == "tool/result"
                    and event.data.get("turn_id") == turn_id
                    and event.data.get("call_id") == identity["call_id"]
                ),
                None,
            )
            specification: dict[str, Any] = {
                "type": "tool/result",
                "data": {**data, "created_at": now_iso()},
                "surface_op": "append",
            }
            if previous is not None:
                if all(previous.data.get(key) == value for key, value in data.items()):
                    return False
                if not (
                    all(
                        previous.data.get(key) == value
                        for key, value in identity.items()
                    )
                    and previous.data.get("status") == "interrupted"
                    and previous.data.get("result") is None
                    and (previous.data.get("error") or {}).get("code")
                    == "TOOL_OUTCOME_UNKNOWN"
                ):
                    raise_error(
                        "conflict",
                        "TOOL_RESULT_CONFLICT",
                        "该工具调用已保存不同的结果。",
                    )
                specification.update(
                    source_event_seqs=[previous.seq],
                    surface_op={
                        "op": "replace",
                        "start": previous.seq,
                        "end": previous.seq + 1,
                    },
                )
            self.repository.append_session_events(
                account_id,
                session_id,
                [specification],
                expected_seq=events[-1].seq + 1,
            )
            return True

    def _record_turn_failure(
        self, account_id: str, turn, code: str, message: str
    ) -> None:
        self.repository.append_session_events(
            account_id,
            turn["session_id"],
            [
                *self._interrupted_activity_specifications(account_id, turn),
                {
                    "type": "turn/end",
                    "data": {
                        "turn_id": turn["turn_id"],
                        "reason": {
                            "kind": "error",
                            "code": code,
                            "message": message,
                        },
                    },
                },
            ],
        )
        self.repository.update_turn_failed(
            account_id, turn["session_id"], turn["turn_id"], code, message
        )

    def get_turn(
        self, account_id: str, session_id: str, turn_id: str
    ) -> dict[str, Any]:
        self.repository.ensure_session(account_id, session_id)
        row = self.repository.turn_row(account_id, session_id, turn_id)
        if not row:
            raise_error("missing", "NOT_FOUND", "轮次不存在。")
        return {
            "session_id": row["session_id"],
            "turn_id": row["turn_id"],
            "status": row["status"],
            "stream_id": row["stream_id"],
            "user_message_id": row["user_message_id"],
            "final_assistant_message_id": row["final_assistant_message_id"],
            "error": None
            if not row["error_code"]
            else {"code": row["error_code"], "message": row["error_message"]},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_conversations(self, account_id: str) -> dict[str, Any]:
        self._maintain_attachments(account_id)
        self._interrupt_expired_turn_jobs(account_id)
        rows = self.repository.list_sessions(account_id)
        summaries = [self._conversation_summary(account_id, row) for row in rows]
        for summary in summaries:
            if summary["pending_turn_status"] == "queued" or (
                summary["pending_turn_status"] is None and summary["queued_input_count"]
            ):
                self._resume_session_work(account_id, summary["session_id"])
        return {
            "sessions": summaries,
            "has_more": False,
            "next_cursor": None,
        }

    def update_conversation(
        self,
        account_id: str,
        session_id: str,
        *,
        title: str | None = None,
        is_pinned: bool | None = None,
    ) -> dict[str, Any]:
        normalized_title: str | None = None
        if title is not None:
            normalized_title = re.sub(r"\s+", " ", title).strip()
            if not normalized_title:
                raise_error("invalid_input", "INVALID_REQUEST", "聊天标题不能为空。")
            if len(normalized_title) > SESSION_TITLE_MAX_CHARS:
                raise_error(
                    "invalid_input",
                    "INVALID_REQUEST",
                    f"聊天标题不能超过 {SESSION_TITLE_MAX_CHARS} 个字符。",
                )
            self.titles.cancel(account_id, session_id)

        row = self.repository.update_session_metadata(
            account_id,
            session_id,
            title=normalized_title,
            is_pinned=is_pinned,
        )
        return {"session": self._conversation_summary(account_id, row)}

    def batch_pin_conversations(
        self,
        account_id: str,
        session_ids: list[str],
        is_pinned: bool,
    ) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(str(value).strip() for value in session_ids))
        if any(not session_id for session_id in unique_ids):
            raise_error("invalid_input", "INVALID_REQUEST", "聊天标识不能为空。")
        rows = self.repository.batch_set_pinned(account_id, unique_ids, is_pinned)
        return {
            "sessions": [self._conversation_summary(account_id, row) for row in rows]
        }

    def batch_delete_conversations(
        self,
        account_id: str,
        session_ids: list[str],
    ) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(str(value).strip() for value in session_ids))
        if not unique_ids or any(not session_id for session_id in unique_ids):
            raise_error("invalid_input", "INVALID_REQUEST", "请选择至少一个有效聊天。")
        deleted_ids: list[str] = []
        failed: list[dict[str, str]] = []
        for session_id in unique_ids:
            try:
                self.delete_conversation(account_id, session_id)
                deleted_ids.append(session_id)
            except SerenitaError as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {}
                failed.append(
                    {
                        "session_id": session_id,
                        "code": str(detail.get("code") or "DELETE_FAILED"),
                        "message": str(detail.get("message") or exc.detail),
                    }
                )
            except Exception as exc:
                failed.append(
                    {
                        "session_id": session_id,
                        "code": "DELETE_FAILED",
                        "message": str(exc) or "删除聊天失败。",
                    }
                )
        return {
            "success": not failed,
            "deleted_ids": deleted_ids,
            "failed": failed,
        }

    @member_lifecycle_operation
    def fork_conversation(
        self,
        account_id: str,
        session_id: str,
        at_seq: Optional[int] = None,
    ) -> dict[str, Any]:
        self._session_member_access(account_id, session_id)
        row = self.repository.session_row(account_id, session_id)
        if row is None:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        events = self.repository.session_events(account_id, session_id, repair=False)
        if at_seq is None:
            boundary = next(
                (event for event in reversed(events) if event.type == "turn/end"),
                None,
            )
        else:
            anchor = next((event for event in events if event.seq == at_seq), None)
            turn_id = str(anchor.data.get("turn_id") or "") if anchor else ""
            boundary = next(
                (
                    event
                    for event in events
                    if event.type == "turn/end"
                    and str(event.data.get("turn_id") or "") == turn_id
                ),
                None,
            )
        if boundary is None:
            raise_error(
                "conflict", "FORK_UNAVAILABLE", "所选位置没有已结束的稳定轮次边界。"
            )

        next_turn = next(
            (
                event
                for event in events
                if event.type == "turn/start" and event.seq > boundary.seq
            ),
            None,
        )
        cutoff = next_turn.seq if next_turn is not None else len(events)
        seed = list(events[:cutoff])
        if not seed or seed[-1].seq != cutoff - 1:
            raise_error("conflict", "FORK_UNAVAILABLE", "无法形成连续的稳定聊天前缀。")

        child = self.repository.create_fork(
            account_id,
            session_id,
            seed,
            title=self._increment_fork_title(
                str(row["title"] or UNTITLED_CONVERSATION)
            ),
        )
        return {"session": self._conversation_summary(account_id, child)}

    def get_conversation(self, account_id: str, session_id: str) -> dict[str, Any]:
        self._maintain_attachments(account_id)
        row = self.repository.session_row(account_id, session_id)
        if not row:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        self._interrupt_expired_turn_jobs(account_id)
        self._resume_session_work(account_id, session_id)
        events = self.repository.session_events(account_id, session_id, repair=False)
        self.repository.reconcile_session_indexes(account_id, session_id, events=events)
        row = self.repository.session_row(account_id, session_id)
        projected_records = records_from_events(events)
        current_records = active_records(projected_records, events)
        fork_anchor_seqs = self._fork_anchor_seqs(current_records, events)
        latest = self._latest_current_turn(account_id, session_id, events=events)
        member_accessible = self._member_accessible(account_id, session_id)
        latest_terminal = (
            member_accessible
            and latest is not None
            and latest["status"]
            not in {
                "queued",
                "streaming",
            }
        )
        records = [
            self._conversation_record_response(
                record,
                editable=(
                    latest_terminal
                    and record.get("kind") == "user"
                    and str(record.get("message_id") or record.get("record_id") or "")
                    == str(latest["user_message_id"] or "")
                ),
                regenerable=(
                    latest_terminal
                    and record.get("kind") == "assistant"
                    and str(record.get("message_id") or record.get("record_id") or "")
                    == str(latest["final_assistant_message_id"] or "")
                ),
                fork_anchor_seq=fork_anchor_seqs.get(
                    str(record.get("record_id") or record.get("message_id") or "")
                ),
            )
            for record in current_records
        ]
        pending_rows = self.repository.list_pending_turn_rows(account_id, session_id)
        return {
            "session_id": row["session_id"],
            "title": row["title"],
            "parent_session_id": row["parent_session_id"],
            "seed_event_count": int(row["seed_event_count"] or 0),
            "fork_available": member_accessible and self._fork_available(events),
            "member_id": row["member_id"],
            "member_name": self.members.historical_member_name(
                account_id, "conversation", row["session_id"]
            ),
            "access_state": "available" if member_accessible else "history_only",
            "pending_turns": [
                {
                    "turn_id": pending["turn_id"],
                    "status": pending["status"],
                    "stream_id": pending["stream_id"],
                    "user_message_id": pending["user_message_id"],
                    "final_assistant_message_id": pending["final_assistant_message_id"],
                    "created_at": pending["created_at"],
                    "updated_at": pending["updated_at"],
                }
                for pending in pending_rows
            ],
            "queued_inputs": queued_inputs_from_events(events),
            "records": records,
            "resource_states": self._conversation_resource_states(
                account_id, row["member_id"], current_records
            ),
        }

    def _conversation_resource_states(
        self, account_id: str, member_id: str | None, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        resource_refs: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        def append_references(value: Any) -> None:
            if not isinstance(value, list):
                return
            for reference in value:
                if not isinstance(reference, dict):
                    continue
                resource_type = str(reference.get("resource_type") or "").strip()
                resource_id = str(reference.get("resource_id") or "").strip()
                key = (
                    str(reference.get("member_id") or ""),
                    resource_type,
                    resource_id,
                )
                if not resource_type or not resource_id or key in seen:
                    continue
                seen.add(key)
                resource_refs.append(
                    {
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "member_id": reference.get("member_id"),
                    }
                )

        for record in records:
            if record.get("kind") == "user":
                append_references(record.get("context_resources"))
                continue
            if record.get("kind") != "tool":
                continue
            result = record.get("result")
            effects = result.get("effects") if isinstance(result, dict) else None
            if not isinstance(effects, dict):
                continue
            append_references(effects.get("resource_refs"))
            append_references(effects.get("affected_resource_refs"))

        if not resource_refs:
            return []
        from backend.app.plugins import (
            PluginRuntimeContext,
            resolve_plugin_resource_states,
        )

        return resolve_plugin_resource_states(
            runtime_context=PluginRuntimeContext(
                service_factory=lambda plugin_id: self.services.plugin_service(
                    account_id, member_id, plugin_id
                ),
                account_id=account_id,
                member_id=member_id,
                event_recorder=lambda _event: None,
            ),
            resource_refs=resource_refs,
        )

    def _conversation_record_response(
        self,
        record: dict[str, Any],
        *,
        editable: bool = False,
        regenerable: bool = False,
        fork_anchor_seq: Optional[int] = None,
    ) -> dict[str, Any]:
        if record.get("kind") not in {"user", "assistant"}:
            return record_response(record)
        message = {**record, "role": record["kind"]}
        response = message_response(message)
        return {
            **response,
            "record_id": record["record_id"],
            "kind": record["kind"],
            "time": record.get("time"),
            "source_event_seqs": list(record.get("source_event_seqs") or []),
            **({"editable": editable} if record.get("kind") == "user" else {}),
            **(
                {
                    "regenerable": regenerable,
                    "fork_anchor_seq": fork_anchor_seq,
                }
                if record.get("kind") == "assistant"
                else {}
            ),
        }

    def delete_conversation(self, account_id: str, session_id: str) -> dict[str, Any]:
        self._maintain_attachments(account_id)
        self.titles.cancel(account_id, session_id)
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            pending = self.repository.list_pending_turn_rows(account_id, session_id)
            for turn in pending:
                self.jobs.cancel(account_id, session_id, str(turn["stream_id"]))
            for turn in pending:
                self.wait_for_turn_job(
                    account_id, session_id, str(turn["stream_id"]), timeout=5.0
                )
            self.repository.delete_conversation(account_id, session_id)
        self._drain_attachment_cleanup(account_id)
        return {"success": True, "session_id": session_id, "message": "聊天已删除"}

    def _current_records(
        self, account_id: str, session_id: str
    ) -> list[dict[str, Any]]:
        events = self.repository.session_events(account_id, session_id, repair=False)
        return active_records(records_from_events(events), events)

    def _latest_current_turn(
        self,
        account_id: str,
        session_id: str,
        *,
        events: Optional[list[Any]] = None,
    ):
        event_list = events or self.repository.session_events(
            account_id, session_id, repair=False
        )
        current_ids = current_session_turn_ids(event_list)
        latest_id = next(
            (
                str(event.data.get("turn_id") or "")
                for event in reversed(event_list)
                if event.type == "turn/start"
                and str(event.data.get("turn_id") or "") in current_ids
            ),
            "",
        )
        return (
            self.repository.turn_row(account_id, session_id, latest_id)
            if latest_id
            else None
        )

    def _conversation_summary(self, account_id: str, row) -> dict[str, Any]:
        events = self.repository.session_events(
            account_id, str(row["session_id"]), repair=False
        )
        row_keys = set(row.keys())
        pending_turn_status = (
            row["pending_turn_status"]
            if "pending_turn_status" in row_keys
            else self.repository.pending_turn_status(account_id, str(row["session_id"]))
        )
        member_accessible = self._member_accessible(account_id, str(row["session_id"]))
        return {
            "session_id": row["session_id"],
            "title": row["title"],
            "member_id": row["member_id"],
            "member_name": self.members.historical_member_name(
                account_id, "conversation", row["session_id"]
            ),
            "access_state": "available"
            if member_accessible
            else "history_only",
            "created_at": row["created_at"],
            "last_active_at": row["last_active_at"],
            "parent_session_id": row["parent_session_id"],
            "seed_event_count": int(row["seed_event_count"] or 0),
            "is_pinned": bool(row["is_pinned"]),
            "pending_turn_status": pending_turn_status,
            "queued_input_count": len(queued_inputs_from_events(events)),
            "fork_available": member_accessible and self._fork_available(events),
        }

    @staticmethod
    def _fork_available(events: list[Any]) -> bool:
        return any(event.type == "turn/end" for event in events)

    @staticmethod
    def _fork_anchor_seq(record: dict[str, Any], events: list[Any]) -> Optional[int]:
        record_id = str(record.get("record_id") or record.get("message_id") or "")
        return ConversationService._fork_anchor_seqs([record], events).get(record_id)

    @staticmethod
    def _fork_anchor_seqs(
        records: list[dict[str, Any]], events: list[Any]
    ) -> dict[str, int]:
        previous_event_seq_by_turn: dict[str, int] = {}
        stable_anchors: set[tuple[str, int]] = set()
        for event in events:
            turn_id = str(event.data.get("turn_id") or "")
            if not turn_id:
                continue
            previous_seq = previous_event_seq_by_turn.get(turn_id)
            if event.type == "turn/end" and previous_seq is not None:
                stable_anchors.add((turn_id, previous_seq))
            previous_event_seq_by_turn[turn_id] = event.seq

        anchors: dict[str, int] = {}
        for record in records:
            if record.get("kind") != "assistant":
                continue
            record_id = str(record.get("record_id") or record.get("message_id") or "")
            if not record_id:
                continue
            turn_id = str(record.get("turn_id") or "")
            anchor_seq = max(
                [
                    int(record.get("seq") or -1),
                    *(int(value) for value in record.get("source_event_seqs") or []),
                ]
            )
            if (turn_id, anchor_seq) in stable_anchors:
                anchors[record_id] = anchor_seq
        return anchors

    @staticmethod
    def _increment_fork_title(title: str) -> str:
        match = re.search(r"(\s*)([（(])(\d+)([）)])$", title)
        if match and ((match.group(2), match.group(4)) in {("(", ")"), ("（", "）")}):
            base = title[: match.start()]
            return (
                f"{base}{match.group(1)}{match.group(2)}"
                f"{int(match.group(3)) + 1}{match.group(4)}"
            )
        return f"{title} (1)"

    def source_message_for_favorite(
        self, account_id: str, session_id: str, message_id: str
    ):
        source = self.repository.source_message_for_favorite(
            account_id, session_id, message_id
        )
        if source is None:
            return None
        turn_id = str(source.pop("_turn_id", ""))
        source["content"] = export_web_citation_markdown(
            str(source.get("content") or ""),
            self.repository.session_events(account_id, session_id, repair=False),
            turn_id,
        )
        return source

    def conversation_exists(self, account_id: str, session_id: str) -> bool:
        return self.repository.conversation_exists(account_id, session_id)

    def _validate_model(
        self, account_id: str, model_id: Optional[str], thinking_mode: str
    ):
        chat_model = self.model_catalog.default_model_for_account(account_id, "chat")
        if not chat_model:
            raise_error(
                "invalid_structure",
                "MODEL_NOT_CONFIGURED",
                "请先在账号设置中配置模型并添加默认聊天模型。",
            )
        if model_id:
            model = self.model_catalog.model_for_account(account_id, model_id)
            if not model:
                raise_error("missing", "MODEL_NOT_FOUND", "模型不存在或未添加。")
            if model["model_id"] != chat_model["model_id"]:
                raise_error(
                    "invalid_input", "INVALID_REQUEST", "首页只能使用默认聊天模型。"
                )
        else:
            model = chat_model
        if not model:
            raise_error(
                "invalid_structure",
                "MODEL_NOT_CONFIGURED",
                "请先在账号设置中配置模型并添加默认模型。",
            )
        if thinking_mode not in model.get("thinking_modes", []):
            raise_error(
                "invalid_input", "INVALID_REQUEST", "当前模型不支持所选推理强度。"
            )
        return model

    def attachment_capabilities(self, account_id: str, model_id: str | None = None):
        model = (
            self.model_catalog.model_for_account(account_id, model_id)
            if model_id
            else self.model_catalog.default_model_for_account(account_id, "chat")
        )
        if model_id and not model:
            raise_error("missing", "MODEL_NOT_FOUND", "模型不存在或未添加。")
        if not model:
            return {"model_id": None, "file_mime_types": []}
        vision = self.model_catalog.default_model_for_account(
            account_id, "vision_parse"
        )
        candidates = (
            set(model.get("file_mime_types", []))
            | set((vision or {}).get("file_mime_types", []))
            | MODEL_RENDERABLE_ATTACHMENT_MIME_TYPES
        )
        accepted = []
        for mime_type in sorted(candidates & ALLOWED_MIME_TYPES.keys()):
            try:
                self._validate_attachment_supported_for_conversation(
                    account_id, model, mime_type
                )
            except SerenitaError as exc:
                if exc.detail.get("code") not in {
                    "MODEL_ATTACHMENT_UNSUPPORTED",
                    "MODEL_FILE_UNSUPPORTED",
                }:
                    raise
            else:
                accepted.append(mime_type)
        return {"model_id": model["model_id"], "file_mime_types": accepted}

    def _validate_attachment_supported_for_conversation(
        self,
        account_id: str,
        model: dict[str, Any],
        mime_type: str,
    ) -> None:
        if self._model_can_forward_attachment(model, mime_type):
            return
        if self._can_render_attachment_for_model(account_id, model, mime_type):
            return
        vision_model = self._vision_parse_model_for_attachment(account_id, mime_type)
        if vision_model:
            return
        if mime_type in model.get("file_mime_types", []):
            raise_error(
                "invalid_structure",
                "MODEL_ATTACHMENT_UNSUPPORTED",
                "当前模型服务不能原生上传该附件类型。",
            )
        raise_error(
            "invalid_structure",
            "MODEL_FILE_UNSUPPORTED",
            "当前聊天模型不支持该文件格式，且未配置可用的视觉解析模型。",
        )

    def _model_can_forward_attachment(
        self, model: dict[str, Any], mime_type: str
    ) -> bool:
        return mime_type in model.get(
            "file_mime_types", []
        ) and self.model_catalog.provider_supports_native_attachment(model, mime_type)

    def _vision_parse_model_for_attachment(
        self, account_id: str, mime_type: str
    ) -> Optional[dict[str, Any]]:
        model = self.model_catalog.default_model_for_account(account_id, "vision_parse")
        if not model or mime_type not in model.get("file_mime_types", []):
            return None
        if not self.model_catalog.provider_supports_native_attachment(model, mime_type):
            raise_error(
                "invalid_structure",
                "MODEL_ATTACHMENT_UNSUPPORTED",
                "视觉解析模型服务不能原生上传该附件类型。",
            )
        return model

    def _can_render_attachment_for_model(
        self,
        account_id: str,
        chat_model: dict[str, Any],
        mime_type: str,
    ) -> bool:
        if mime_type not in MODEL_RENDERABLE_ATTACHMENT_MIME_TYPES:
            return False
        if self._model_can_forward_attachment(chat_model, mime_type):
            return True
        vision_model = self.model_catalog.default_model_for_account(
            account_id, "vision_parse"
        )
        required_mime = "image/jpeg" if mime_type == "application/pdf" else mime_type
        return bool(
            vision_model
            and self._model_can_forward_attachment(vision_model, required_mime)
        )

    def _validate_context_resources(
        self,
        account_id: str,
        session_id: str,
        references: list[dict[str, Any]],
        model: dict[str, Any],
    ) -> list[dict[str, Any]]:
        normalized = []
        seen_plugin_resources: set[tuple[str, str]] = set()
        file_count = sum(
            1
            for reference in references
            if self._ref_value(reference, "resource_type") == "file"
        )
        if file_count > MAX_FILES_PER_TURN:
            raise_error("resource_limit", "TOO_MANY_FILES", "单次最多发送 20 个文件。")
        total_file_bytes = 0
        records_by_id = {
            str(record.get("record_id") or ""): record
            for record in self._current_records(account_id, session_id)
            if record.get("record_id")
        }
        member_access = self._session_member_access(account_id, session_id)
        member_id = member_access.member_id if member_access is not None else None
        for reference in references:
            if self._ref_value(reference, "member_id") not in {None, "", member_id}:
                member_error("MEMBER_MISMATCH", "不能引用其他成员的资源。", "conflict")
            resource_type = self._ref_value(reference, "resource_type")
            resource_id = self._ref_value(reference, "resource_id")
            if resource_type == "file":
                row = self.repository.resource_row(account_id, session_id, resource_id)
                if not row:
                    raise_error("missing", "NOT_FOUND", "上下文资源不存在。")
                if row["storage_status"] != "ready":
                    raise_error(
                        "conflict", "RESOURCE_NOT_READY", "上下文资源尚未完成写入。"
                    )
                if row["lifecycle_status"] in {"expired", "deleted"}:
                    raise_error(
                        "invalid_input", "INVALID_REQUEST", "上下文资源已过期。"
                    )
                if (
                    row["expires_at"]
                    and parse_local_datetime(row["expires_at"]) <= local_now()
                ):
                    self.repository.expire_resource(
                        account_id, session_id, row["resource_id"]
                    )
                    self._drain_attachment_cleanup(account_id)
                    raise_error(
                        "invalid_input", "INVALID_REQUEST", "上下文资源已过期。"
                    )
                self._validate_attachment_supported_for_conversation(
                    account_id, model, row["mime_type"]
                )
                if int(row["size_bytes"]) > MAX_FILE_BYTES:
                    raise_error(
                        "resource_limit", "FILE_TOO_LARGE", "单文件大小不能超过 20MB。"
                    )
                total_file_bytes += int(row["size_bytes"])
                if total_file_bytes > MAX_TOTAL_FILE_BYTES:
                    raise_error(
                        "resource_limit",
                        "FILES_TOO_LARGE",
                        "单次发送文件总大小不能超过 100MB。",
                    )
                normalized.append(
                    {
                        "resource_type": "file",
                        "resource_id": row["resource_id"],
                        "original_filename": row["original_filename"],
                        "mime_type": row["mime_type"],
                        "size_bytes": row["size_bytes"],
                    }
                )
            elif resource_type == "record_annotation":
                source_record_id = self._ref_value(reference, "source_record_id")
                source_record = records_by_id.get(source_record_id)
                if not source_record:
                    raise_error("missing", "NOT_FOUND", "注释来源记录不存在。")
                if _annotation_source_values(source_record) is None:
                    raise_error(
                        "invalid_input",
                        "INVALID_REQUEST",
                        "只有用户输入和助手回答可以添加为注释。",
                    )
                annotation_text = self._ref_value(reference, "annotation_text") or ""
                if not _annotation_text_belongs_to_record(
                    annotation_text, source_record
                ):
                    raise_error(
                        "invalid_input", "INVALID_REQUEST", "注释文本不属于来源记录。"
                    )
                normalized.append(
                    {
                        "resource_type": "record_annotation",
                        "resource_id": resource_id or self.repository.new_id(),
                        "source_record_id": source_record_id,
                        "annotation_text": annotation_text,
                    }
                )
            else:
                resource_key = (str(resource_type), str(resource_id))
                if resource_key in seen_plugin_resources:
                    continue
                try:
                    from backend.app.plugins import (
                        PluginRuntimeContext,
                        resolve_plugin_resource_refs,
                    )

                    resolved = resolve_plugin_resource_refs(
                        runtime_context=PluginRuntimeContext(
                            service_factory=lambda plugin_id: (
                                self.services.plugin_service(
                                    account_id, member_id, plugin_id
                                )
                            ),
                            account_id=account_id,
                            member_id=member_id,
                            event_recorder=lambda _event: None,
                        ),
                        resource_refs=[
                            {
                                "resource_type": resource_type,
                                "resource_id": resource_id,
                                "member_id": reference.get("member_id"),
                            }
                        ],
                    )
                    if not resolved:
                        raise LookupError(resource_id)
                    plugin_resource = resolved[0]
                except Exception as exc:
                    if isinstance(exc, SerenitaError):
                        raise
                    raise_error(
                        "missing", "RESOURCE_NOT_FOUND", "插件资源不存在或无权访问。"
                    )
                normalized.append(dict(plugin_resource))
                seen_plugin_resources.add(resource_key)
        # A model may inspect a PDF through images rendered by the backend even
        # when the provider cannot accept PDF as a native chat attachment.
        direct_response_resources = [
            resource
            for resource in normalized
            if not (
                resource.get("resource_type") == "file"
                and resource.get("mime_type") == "application/pdf"
                and self._can_render_attachment_for_model(
                    account_id, model, "application/pdf"
                )
            )
        ]
        self._response_model_for_context_resources(
            account_id, session_id, direct_response_resources, model
        )
        return normalized

    def _maintain_attachments(self, account_id: str) -> None:
        """Recover writes, expire drafts, and drain account-scoped cleanup work."""
        self.repository.recover_writing_resources(account_id, limit=100)
        self.repository.expire_due_resources(account_id, limit=100)
        self._drain_attachment_cleanup(account_id)

    def _drain_attachment_cleanup(self, account_id: str, *, limit: int = 32) -> None:
        for job in self.repository.attachment_cleanup_jobs(account_id, limit=limit):
            cleanup_id = job["cleanup_id"]
            path = self.repository.attachment_cleanup_path(
                account_id, job["relative_path"]
            )
            if path is None:
                # Invalid persisted paths are discarded without touching disk.
                self.repository.complete_attachment_cleanup(account_id, cleanup_id)
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                self.repository.record_attachment_cleanup_attempt(
                    account_id, cleanup_id
                )
                continue
            self.repository.complete_attachment_cleanup(account_id, cleanup_id)
            self.repository.remove_empty_attachment_dirs(account_id, path.parent)

    @staticmethod
    def _model_request_from_messages(
        messages: list[dict[str, Any]],
        *,
        purpose: str,
        parent_tool_call_id: str | None = None,
    ) -> ModelRequest:
        system_parts = [
            str(message.get("content") or "")
            for message in messages
            if message.get("role") == "system"
        ]
        return ModelRequest.build(
            system="\n\n".join(item for item in system_parts if item),
            messages=[
                dict(message) for message in messages if message.get("role") != "system"
            ],
            tools=(),
            tool_choice=None,
            model_config={
                "purpose": purpose,
                **(
                    {"parent_tool_call_id": parent_tool_call_id}
                    if parent_tool_call_id
                    else {}
                ),
            },
        )

    def _response_model_for_context_resources(
        self,
        account_id: str,
        session_id: str,
        context_resources: list[dict[str, Any]],
        chat_model: dict[str, Any],
    ) -> dict[str, Any]:
        file_mime_types = self._context_file_mime_types(
            account_id, session_id, context_resources
        )
        if not file_mime_types:
            return chat_model
        if all(
            self._model_can_forward_attachment(chat_model, mime_type)
            for mime_type in file_mime_types
        ):
            return chat_model
        vision_model = self.model_catalog.default_model_for_account(
            account_id, "vision_parse"
        )
        if vision_model and all(
            self._model_can_forward_attachment(vision_model, mime_type)
            for mime_type in file_mime_types
        ):
            return vision_model
        raise_error(
            "invalid_structure",
            "MODEL_FILE_UNSUPPORTED",
            "当前聊天模型不支持本轮附件，且未配置可直接回答这些附件的视觉解析模型。",
        )

    def _model_and_attachment_parts(
        self,
        account_id: str,
        session_id: str,
        context_resources: list[dict[str, Any]],
        chat_model: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        file_rows: list[tuple[dict[str, Any], Any]] = []
        for resource in context_resources:
            if resource.get("resource_type") != "file":
                continue
            row = self.repository.resource_row(
                account_id, session_id, str(resource.get("resource_id") or "")
            )
            if row is None:
                continue
            file_rows.append((resource, row))
        if not file_rows:
            return chat_model, []

        candidate_models = [chat_model]
        vision_model = self.model_catalog.default_model_for_account(
            account_id, "vision_parse"
        )
        if vision_model and vision_model.get("model_id") != chat_model.get("model_id"):
            candidate_models.append(vision_model)
        selected_model = next(
            (
                model
                for model in candidate_models
                if all(
                    self._model_can_forward_attachment(model, str(row["mime_type"]))
                    or (
                        str(row["mime_type"]) == "application/pdf"
                        and self._model_can_forward_attachment(model, "image/jpeg")
                    )
                    for _resource, row in file_rows
                )
            ),
            None,
        )
        if selected_model is None:
            raise_error(
                "invalid_structure",
                "MODEL_FILE_UNSUPPORTED",
                "当前聊天模型和视觉解析模型都不能读取本聊天中的附件。",
            )

        parts: list[dict[str, Any]] = []
        for resource, row in file_rows:
            resource_id = str(resource.get("resource_id") or "")
            mime_type = str(row["mime_type"])
            if (
                mime_type == "application/pdf"
                and not self._model_can_forward_attachment(selected_model, mime_type)
            ):
                path = self.repository.timeline_abs_path(
                    account_id, str(row["relative_path"])
                )
                from backend.app.application.attachment_rendering import (
                    model_file_parts,
                )

                rendered = model_file_parts(
                    path,
                    mime_type,
                    deadline=time.monotonic() + 60,
                )
                for page in rendered:
                    parts.append(
                        {
                            **dict(page),
                            "source_resource_id": resource_id,
                        }
                    )
                continue
            part = self._attachment_part(account_id, session_id, resource)
            part["source_resource_id"] = resource_id
            parts.append(part)
        return selected_model, parts

    def _context_file_mime_types(
        self,
        account_id: str,
        session_id: str,
        context_resources: list[dict[str, Any]],
    ) -> list[str]:
        mime_types = []
        for resource in context_resources:
            if resource.get("resource_type") != "file":
                continue
            row = self.repository.resource_row(
                account_id, session_id, resource["resource_id"]
            )
            if row:
                mime_types.append(row["mime_type"])
        return mime_types

    def _default_thinking_mode(self, model: dict[str, Any]) -> str:
        thinking_modes = model.get("thinking_modes", [])
        if "default" in thinking_modes:
            return "default"
        return thinking_modes[0] if thinking_modes else "default"

    def _thinking_mode_for_model(
        self, model: dict[str, Any], requested_mode: str
    ) -> str:
        thinking_modes = model.get("thinking_modes", [])
        if requested_mode == "off":
            profiles = model.get("capability_profiles")
            non_thinking = (
                profiles.get("non_thinking") if isinstance(profiles, dict) else None
            )
            if (
                isinstance(non_thinking, dict)
                and non_thinking.get("availability") != "unavailable"
            ):
                return "off"
        if requested_mode in thinking_modes:
            return requested_mode
        return self._default_thinking_mode(model)

    def _effective_thinking_mode_for_turn(
        self,
        model: dict[str, Any],
        requested_mode: str,
        *,
        has_tools: bool,
        attachment_parts: list[dict[str, Any]],
    ) -> tuple[str, list[str]]:
        profiles = model.get("capability_profiles")
        if not isinstance(profiles, dict):
            return requested_mode, []

        requested_state = self._thinking_state_for_mode(
            requested_mode,
            profiles,
        )
        alternate_state = (
            "thinking" if requested_state == "non_thinking" else "non_thinking"
        )
        required_mime_types = {
            str(part.get("mime_type") or "")
            for part in attachment_parts
            if isinstance(part, dict) and str(part.get("mime_type") or "")
        }
        reasons = self._unsupported_mode_requirements(
            profiles.get(requested_state),
            has_tools=has_tools,
            required_mime_types=required_mime_types,
        )
        if not reasons:
            return requested_mode, []
        if self._unsupported_mode_requirements(
            profiles.get(alternate_state),
            has_tools=has_tools,
            required_mime_types=required_mime_types,
        ):
            return requested_mode, []
        if alternate_state == "non_thinking":
            return "off", reasons
        thinking_modes = [
            str(mode)
            for mode in model.get("thinking_modes", [])
            if str(mode) not in {"", "off"}
        ]
        if profiles.get("default_state") == "thinking" and "default" in thinking_modes:
            return "default", reasons
        explicit_mode = next(
            (mode for mode in thinking_modes if mode != "default"),
            None,
        )
        return (explicit_mode, reasons) if explicit_mode else (requested_mode, [])

    @staticmethod
    def _thinking_state_for_mode(mode: str, profiles: dict[str, Any]) -> str:
        if mode == "off":
            return "non_thinking"
        if mode == "default":
            state = str(profiles.get("default_state") or "unknown")
            return state if state in {"thinking", "non_thinking"} else "non_thinking"
        return "thinking"

    @staticmethod
    def _unsupported_mode_requirements(
        profile: Any,
        *,
        has_tools: bool,
        required_mime_types: set[str],
    ) -> list[str]:
        if (
            not isinstance(profile, dict)
            or profile.get("availability") == "unavailable"
        ):
            return ["text"]
        reasons: list[str] = []
        if not bool(profile.get("supports_text")):
            reasons.append("text")
        if has_tools and not bool(profile.get("supports_tool_calling")):
            reasons.append("tool_calling")
        supported_types = {
            str(mime_type)
            for mime_type in profile.get("file_mime_types", [])
            if isinstance(mime_type, str)
        }
        for mime_type in sorted(required_mime_types - supported_types):
            if mime_type.startswith("image/"):
                reason = "image_input"
            elif mime_type.startswith("audio/"):
                reason = "audio_input"
            elif mime_type.startswith("video/"):
                reason = "video_input"
            else:
                reason = "file_input"
            if reason not in reasons:
                reasons.append(reason)
        return reasons

    def _attachment_part(
        self, account_id: str, session_id: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        row = self.repository.resource_row(
            account_id, session_id, resource["resource_id"]
        )
        if not row:
            raise ProviderChatCompletionError("上下文资源不存在。")
        path = self.repository.timeline_abs_path(account_id, row["relative_path"])
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
            "name": str(row["original_filename"]),
            "data_base64": base64.b64encode(content).decode("ascii"),
        }

    def _ref_value(self, reference: Any, key: str):
        if isinstance(reference, dict):
            return reference.get(key)
        return getattr(reference, key)

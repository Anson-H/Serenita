"""校验并提交用户输入、消息编辑和重新生成请求，创建对应的会话轮次。"""

import time
from backend.app.core.member_lifecycle import member_lifecycle_operation, member_lifecycle_guard
from typing import Any, Optional
from backend.app.core.errors import raise_error
from backend.app.domain.conversations.timeline import active_records, records_from_events
from backend.app.domain.conversations.queries import queued_inputs_from_events
from backend.app.core.time import local_now_iso
from backend.app.domain.conversations.events import SessionEvent, iso_to_epoch_ms
from backend.app.domain.conversations.titles import UNTITLED_CONVERSATION
from backend.app.storage.session_persistence import SessionEventWriteConflictError

now_iso = local_now_iso

class ConversationSubmissions:
    def __init__(self, *, repository, paths, members, events, inputs, task_state, titles, queue, queries):
        self.repository = repository
        self.paths = paths
        self.members = members
        self.events = events
        self.inputs = inputs
        self.task_state = task_state
        self.titles = titles
        self.queue = queue
        self.queries = queries

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
        self.inputs.maintain_attachments(account_id)
        actual_session_id = self.repository.ensure_session(
            account_id, session_id, member_id=member_id
        )
        self.queries.member_access(account_id, actual_session_id)
        model = self.inputs.validate_model(account_id, model_id, thinking_mode)
        normalized_context_resources = self.inputs.validate_context_resources(
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
                events = list(self.events.view(account_id, actual_session_id).events)
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
                    return self.start_message_turn(
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
            persisted = list(self.events.view(account_id, session_id).events)
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
                persisted = list(self.events.view(account_id, session_id).events)
                if not self._turn_start_is_persisted(persisted, turn_id):
                    raise
                time.sleep(0.002 * (attempt + 1))
        if last_index_error is not None:
            persisted = list(self.events.view(account_id, session_id).events)
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


    def start_message_turn(
        self,
        *,
        account_id: str,
        session_id: str,
        raw_text: str,
        model_id: str,
        thinking_mode: str,
        context_resources: list[dict[str, Any]],
        attach_resources: bool,
        current_events: list[SessionEvent],
        expected_seq: int,
        queued_input_id: str | None = None,
    ) -> dict[str, Any]:
        """Commit one user message and its queued turn against the given history."""
        self.queries.member_access(account_id, session_id)
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


    @member_lifecycle_operation
    def regenerate_message(
        self,
        account_id: str,
        session_id: str,
        message_id: str,
        model_id: Optional[str] = None,
        thinking_mode: Optional[str] = None,
    ) -> dict[str, Any]:
        self.queries.member_access(account_id, session_id)
        self.repository.ensure_session(account_id, session_id)
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            for _attempt in range(128):
                events = list(self.events.view(account_id, session_id).events)
                self.repository.reconcile_session_indexes(
                    account_id,
                    session_id,
                    events=events,
                )
                if self.repository.list_pending_turn_rows(account_id, session_id):
                    raise_error(
                        "conflict", "TURN_IN_PROGRESS", "当前聊天有正在进行的生成任务。"
                    )

                latest = self.queries.latest_turn(
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
                model = self.inputs.validate_model(
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
        self.queries.member_access(account_id, session_id)
        self.repository.ensure_session(account_id, session_id)
        raw_text = raw_text.strip()
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            for _attempt in range(128):
                events = list(self.events.view(account_id, session_id).events)
                self.repository.reconcile_session_indexes(
                    account_id,
                    session_id,
                    events=events,
                )
                if self.repository.list_pending_turn_rows(account_id, session_id):
                    raise_error(
                        "conflict", "TURN_IN_PROGRESS", "当前聊天有正在进行的生成任务。"
                    )
                latest = self.queries.latest_turn(
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

                model = self.inputs.validate_model(account_id, model_id, thinking_mode)
                normalized_resources = self.inputs.validate_context_resources(
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

"""保存会话轮次的完成、取消和失败状态，并恢复尚未完成的执行。"""

from backend.app.core.time import elapsed_ms
from backend.app.domain.conversations.queries import reduce_session_activity
from backend.app.application.conversations.cancellation import (
    CANCELLED_ASSISTANT_CONTENT,
    interrupted_activity_specifications,
)
from backend.app.application.conversations.streaming import stream_text_chunks
import time
from datetime import timedelta
from backend.app.core.member_lifecycle import member_lifecycle_operation, member_lifecycle_guard
from typing import Any, Mapping, Optional
from backend.app.agent_runtime.events import visible_workflow_event
from backend.app.core.errors import raise_error
from backend.app.core.cancellation import CancellationToken, OperationCancelledError
from backend.app.core.time import local_now, local_now_iso
from backend.app.providers.errors import ProviderChatCompletionError
from backend.app.domain.conversations.events import iso_to_epoch_ms

now_iso = local_now_iso

TURN_JOB_LEASE_SECONDS = 300

class ConversationTurnLifecycle:
    def __init__(self, *, repository, paths, events, execution, guard, jobs, queue, task_state, queries, notifications):
        self.repository = repository
        self.paths = paths
        self.events = events
        self.execution = execution
        self.guard = guard
        self.jobs = jobs
        self.queue = queue
        self.task_state = task_state
        self.queries = queries
        self.notifications = notifications

    def interrupt_member_session(self, account_id: str, session_id: str, *, before: str | None = None) -> None:
        """Discard queued work before cancelling; cancellation must not promote it."""
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            for queued in self.queue.inputs(account_id, session_id):
                if before is None or queued["created_at"] <= before:
                    self.queue.remove(account_id, session_id, queued["input_id"])
            for turn in self.repository.list_pending_turn_rows(account_id, session_id):
                if before is None or turn["created_at"] <= before:
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
        records = self.queries.current_records(account_id, session_id)
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
            model_content_record = next(
                (
                    record
                    for record in reversed(records)
                    if record.get("turn_id") == turn_id
                    and record.get("kind") == "model"
                    and record.get("channel") == "content"
                    and record.get("purpose") == "agent_action"
                    and not record.get("parent_tool_call_id")
                ),
                {},
            )
            response_model_id = persisted_assistant.get("model_id")
            model_content = str(model_content_record.get("value") or "")
            if model_content and model_content.startswith(persisted_content):
                persisted_content = model_content
                response_model_id = model_content_record.get("model_id")
            content = persisted_content or CANCELLED_ASSISTANT_CONTENT
            self._append_cancelled_turn_messages(
                account_id=account_id,
                turn=turn,
                user_message=user_message,
                final_assistant_message_id=turn["final_assistant_message_id"],
                content=content,
                timestamp=timestamp,
                reason=reason,
                response_model_id=response_model_id,
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


    def interrupt_expired_turn_jobs(self, account_id: str) -> None:
        """Close expired job leases and release eligible queued inputs."""
        cutoff = (local_now() - timedelta(seconds=TURN_JOB_LEASE_SECONDS)).isoformat()
        for session_id in self.repository.expired_turn_job_sessions(account_id, cutoff):
            with (
                member_lifecycle_guard(paths=self.paths),
                self.task_state.session_lock(account_id, session_id),
            ):
                for turn in self.repository.expire_turn_jobs(account_id, session_id, cutoff):
                    self.jobs.cancel(account_id, turn["session_id"], turn["stream_id"])
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


    def resume_session_work(self, account_id: str, session_id: str) -> None:
        """Resume persisted work after checking the current session state."""
        pending = self.repository.list_pending_turn_rows(account_id, session_id)
        if any(
            turn["status"] == "streaming" for turn in pending
        ) and self.queries.member_accessible(account_id, session_id):
            # A leased worker already owns this turn. Reading its page must not
            # wait for its write lock or rebuild the indexes it is updating.
            return
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            if self.repository.session_row(account_id, session_id) is None:
                return
            events = list(self.events.view(account_id, session_id).events)
            self.repository.reconcile_session_indexes(
                account_id,
                session_id,
                events=events,
            )
            pending = self.repository.list_pending_turn_rows(account_id, session_id)
            if not self.queries.member_accessible(account_id, session_id):
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
                    self.jobs.start(account_id, session_id, str(first["stream_id"]))
                return
            self.queue.promote_next(account_id, session_id)


    def execute_turn(
        self,
        account_id: str,
        turn: Mapping[str, Any],
        messages_by_id: dict[str, dict[str, Any]],
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        """Run the Harness and persist the completed or failed turn outcome."""

        def append_active_event(*args, **kwargs):
            with (
                member_lifecycle_guard(paths=self.paths),
                self.task_state.session_lock(account_id, turn["session_id"]),
            ):
                self.guard.ensure_active(account_id, turn, cancellation_token)
                return self.repository.append_session_event(*args, **kwargs)

        self.guard.ensure_active(account_id, turn, cancellation_token)
        user_message = messages_by_id.get(turn["user_message_id"] or "")
        if not user_message:
            self.record_turn_failure(account_id, turn, "NOT_FOUND", "用户消息不存在。")
            return

        final_assistant_message_id = turn["final_assistant_message_id"]
        model_call_id = self.repository.new_id()
        response_model_id: str | None = None
        content_event_seqs: list[int] = []
        content_parts: list[str] = []
        response_started = False
        usage: dict[str, Any] = {}
        stop_reason = "end_turn"
        turn_started_at = time.monotonic()

        def append_assistant_chunk(chunk_payload: dict[str, Any]) -> int:
            self.guard.ensure_active(account_id, turn, cancellation_token)
            event = append_active_event(
                account_id,
                turn["session_id"],
                "assistant/chunk",
                {
                    "turn_id": turn["turn_id"],
                    "step": self.events.current_model_step(account_id, turn),
                    "call_id": model_call_id,
                    "message_id": final_assistant_message_id,
                    "parent_message_id": user_message["message_id"],
                    "final_assistant_message_id": final_assistant_message_id,
                    "model_id": response_model_id,
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
            self.guard.ensure_active(account_id, turn, cancellation_token)
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
            self.guard.ensure_active(account_id, turn, cancellation_token)
            record_workflow(payload)

        def stream_terminal_response_delta(delta: str) -> None:
            nonlocal response_started
            if not delta:
                return
            self.guard.ensure_active(account_id, turn, cancellation_token)
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
            with (
                member_lifecycle_guard(paths=self.paths),
                self.task_state.session_lock(account_id, turn["session_id"]),
            ):
                current = self.repository.turn_row(account_id, turn["session_id"], turn["turn_id"])
                if current is None or current["status"] not in {"queued", "streaming"}:
                    return
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
                            "model_id": response_model_id,
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
                self.record_turn_failure(account_id, turn, code, message)
                if content_parts:
                    self.repository.touch_session(account_id, turn["session_id"])

        try:
            harness_results = [
                self.execution.run(
                    account_id,
                    turn,
                    user_message,
                    on_workflow_event=emit_workflow_record,
                    on_response_delta=stream_terminal_response_delta,
                    cancellation_token=cancellation_token,
                )
            ]
            response_model_id = harness_results[0]["model_id"]
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
            if self.guard.cancelled(
                account_id,
                turn,
                cancellation_token,
            ):
                return
            error_message = str(exc) or "模型服务调用失败。"
            persist_failed_output("MODEL_ERROR", error_message)
            return
        except Exception as exc:
            if self.guard.cancelled(
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

        if self.guard.cancelled(account_id, turn, cancellation_token):
            return

        content = "".join(content_parts).strip()
        if not content:
            self.record_turn_failure(
                account_id, turn, "MODEL_ERROR", "模型服务返回了空回复。"
            )
            return

        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, turn["session_id"]),
        ):
            self.guard.ensure_active(account_id, turn, cancellation_token)
            self._append_completed_turn_messages(
                account_id=account_id,
                turn=turn,
                user_message=user_message,
                final_assistant_message_id=final_assistant_message_id,
                content=content,
                stop_reason=stop_reason,
                usage=usage,
                source_event_seqs=content_event_seqs,
                response_model_id=response_model_id,
            )
        self._finish_completed_turn_session_index(
            account_id,
            turn,
        )


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
        response_model_id: str,
    ) -> dict[str, Any]:
        timestamp = now_iso()
        durable_sources = list(source_event_seqs)
        assistant_payload = {
            "turn_id": turn["turn_id"],
            "message_id": final_assistant_message_id,
            "parent_message_id": user_message["message_id"],
            "model_id": response_model_id,
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
        from backend.app.application.conversations.notifications import completion_event
        self.repository.update_turn_completed(
            account_id,
            turn["session_id"],
            turn["turn_id"],
            final_assistant_message_id,
            timestamp,
            notification_event=completion_event(account_id, turn["session_id"], turn["turn_id"], timestamp),
        )
        self.notifications.runtime.changed([account_id])
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
        response_model_id: str | None,
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
                        "model_id": response_model_id,
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


    def _interrupted_activity_specifications(
        self, account_id: str, turn
    ) -> list[dict[str, Any]]:
        return interrupted_activity_specifications(
            list(self.events.view(account_id, turn["session_id"]).events),
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
            list(self.events.view(account_id, turn["session_id"]).events)
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


    def record_turn_failure(
        self, account_id: str, turn: Mapping[str, Any], code: str, message: str
    ) -> None:
        """Record failure only while the current turn is still active."""
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, turn["session_id"]),
        ):
            current = self.repository.turn_row(account_id, turn["session_id"], turn["turn_id"])
            if current is None or current["status"] not in {"queued", "streaming"}:
                return
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

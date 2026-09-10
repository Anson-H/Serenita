"""订阅已保存的会话事件，维护增量投影并发送 SSE 更新。"""

import time
from typing import Any


from backend.app.core.errors import raise_error
from backend.app.application.conversations.cancellation import CANCELLED_ASSISTANT_CONTENT
from backend.app.application.conversations.streaming import sse_event, stream_text_chunks
from backend.app.domain.conversations.timeline import ConversationTimelineProjector
from backend.app.application.conversations.presenter import record_response


class ConversationSSESubscriber:
    def __init__(self, repository, notifications, *, interrupt_expired_jobs):
        self.repository = repository
        self.notifications = notifications
        self.interrupt_expired_jobs = interrupt_expired_jobs

    def stream_events(self, account_id: str, session_id: str, stream_id: str):
        self.repository.init_db(account_id)
        self.interrupt_expired_jobs(account_id)
        turn = self.repository.turn_by_stream_id(account_id, session_id, stream_id)
        if not turn:
            raise_error("missing", "NOT_FOUND", "流式订阅不存在。")
        messages_by_id = self.repository.messages_by_id(account_id, turn["session_id"])
        assistant_message = messages_by_id.get(turn["final_assistant_message_id"] or "")
        if turn["status"] == "completed" and not assistant_message:
            raise_error("missing", "NOT_FOUND", "流式内容不存在。")

        def events():
            yield ": connected\n\n"
            current_turn = turn
            user = messages_by_id.get(current_turn["user_message_id"] or "") or {}
            last_title = str(user.get("initial_session_title") or "")
            last_activity_at = time.monotonic()
            sent_records: dict[str, dict[str, Any]] = {}
            snapshot = self.repository.session_event_snapshot(
                account_id, current_turn["session_id"]
            )
            if snapshot is None:
                raise_error("missing", "NOT_FOUND", "流式内容不存在。")
            projector = ConversationTimelineProjector(snapshot.events)
            next_event_seq = len(snapshot.events)
            last_event_revision = snapshot.revision
            last_event_lineage = snapshot.lineage
            initial_projection_pending = True
            sent_thinking_mode_event_seqs: set[int] = set()
            pending_thinking_mode_events = self.thinking_mode_events_for_turn(
                snapshot.events,
                str(current_turn["turn_id"]),
            )

            while True:
                self.interrupt_expired_jobs(account_id)
                refreshed = self.repository.turn_by_stream_id(
                    account_id, session_id, stream_id
                )
                if refreshed is None:
                    raise_error("missing", "NOT_FOUND", "流式订阅不存在。")
                current_turn = refreshed
                emitted = False
                if initial_projection_pending:
                    projected_records = projector.records_for_turn(
                        str(current_turn["turn_id"])
                    )
                    initial_projection_pending = False
                else:
                    projected_records = []
                    persisted_events_pending = self.notifications.has_events_from(
                        account_id,
                        current_turn["session_id"],
                        next_event_seq,
                    )
                    current_revision = self.repository.session_event_revision(
                        account_id, current_turn["session_id"]
                    )
                    if (
                        persisted_events_pending
                        or current_revision != last_event_revision
                    ):
                        tail = self.repository.session_event_tail(
                            account_id,
                            current_turn["session_id"],
                            next_event_seq,
                        )
                        if tail is None:
                            raise_error("missing", "NOT_FOUND", "流式内容不存在。")
                        tail_events = list(tail.events)
                        tail_is_contiguous = (
                            bool(tail_events)
                            and tail_events[0].seq == next_event_seq
                            and tail.lineage == last_event_lineage
                        )
                        if tail_is_contiguous:
                            pending_thinking_mode_events.extend(
                                self.thinking_mode_events_for_turn(
                                    tail_events,
                                    str(current_turn["turn_id"]),
                                )
                            )
                            changed_record_ids = projector.apply_events(tail_events)
                            next_event_seq = tail_events[-1].seq + 1
                            projected_records = projector.records_for_ids(
                                changed_record_ids
                            )
                            last_event_revision = tail.revision
                            last_event_lineage = tail.lineage
                        elif not tail_events:
                            last_event_revision = tail.revision
                            last_event_lineage = tail.lineage
                        else:
                            replacement = self.repository.session_event_snapshot(
                                account_id, current_turn["session_id"]
                            )
                            if replacement is None:
                                raise_error("missing", "NOT_FOUND", "流式内容不存在。")
                            projector = ConversationTimelineProjector(
                                replacement.events
                            )
                            pending_thinking_mode_events.extend(
                                self.thinking_mode_events_for_turn(
                                    replacement.events,
                                    str(current_turn["turn_id"]),
                                )
                            )
                            next_event_seq = len(replacement.events)
                            last_event_revision = replacement.revision
                            last_event_lineage = replacement.lineage
                            projected_records = projector.records_for_turn(
                                str(current_turn["turn_id"])
                            )

                for event in pending_thinking_mode_events:
                    if event.seq in sent_thinking_mode_event_seqs:
                        continue
                    yield self.thinking_mode_changed_stream_event(
                        current_turn,
                        event.data,
                    )
                    sent_thinking_mode_event_seqs.add(event.seq)
                    emitted = True
                pending_thinking_mode_events = []

                for record in projected_records:
                    if str(record.get("turn_id") or "") != str(current_turn["turn_id"]):
                        continue
                    if record.get("kind") == "user":
                        continue
                    record_id = str(
                        record.get("record_id") or record.get("message_id") or ""
                    )
                    if not record_id:
                        continue
                    sent = sent_records.get(record_id)
                    if sent is None:
                        sent = {
                            "reasoning": "",
                            "content": "",
                            "raw_content": "",
                            "completed": False,
                        }
                        sent_records[record_id] = sent
                        yield self.projected_record_started_stream_event(
                            current_turn,
                            record,
                        )
                        if (
                            record.get("kind") == "model"
                            and record.get("channel") == "tool_request"
                        ):
                            sent["name"] = str(record.get("name") or "")
                            sent["arguments"] = str(record.get("arguments") or "")
                        emitted = True

                    if record.get("kind") == "model" and record.get("channel") in {
                        "reasoning",
                        "content",
                        "raw_output",
                    }:
                        value = str(record.get("value") or "")
                        previous_value = str(sent.get("value") or "")
                        if value.startswith(previous_value):
                            delta = value[len(previous_value) :]
                            offset = len(previous_value.encode("utf-16-le")) // 2
                            for part in stream_text_chunks(delta):
                                yield self.record_delta_stream_event(
                                    current_turn,
                                    record_id=record_id,
                                    kind="model",
                                    delta=part,
                                    offset=offset,
                                    channel=str(record.get("channel") or ""),
                                )
                                offset += len(part.encode("utf-16-le")) // 2
                                emitted = True
                        sent["value"] = value
                    elif record.get("kind") == "assistant":
                        content = str(record.get("content") or "")
                        previous_content = str(sent.get("content") or "")
                        if content.startswith(previous_content):
                            delta = content[len(previous_content) :]
                            offset = len(previous_content.encode("utf-16-le")) // 2
                            for part in stream_text_chunks(delta):
                                yield self.record_delta_stream_event(
                                    current_turn,
                                    record_id=record_id,
                                    kind="assistant",
                                    delta=part,
                                    offset=offset,
                                )
                                offset += len(part.encode("utf-16-le")) // 2
                                emitted = True
                        sent["content"] = content
                    elif (
                        record.get("kind") == "model"
                        and record.get("channel") == "tool_request"
                    ):
                        for field in ("name", "arguments"):
                            value = str(record.get(field) or "")
                            previous_value = str(sent.get(field) or "")
                            if value.startswith(previous_value):
                                delta = value[len(previous_value) :]
                                if delta:
                                    yield self.record_delta_stream_event(
                                        current_turn,
                                        record_id=record_id,
                                        kind="model",
                                        delta=delta,
                                        offset=len(previous_value.encode("utf-16-le"))
                                        // 2,
                                        channel=field,
                                    )
                                    emitted = True
                            sent[field] = value

                    record_terminal = self.projected_record_is_terminal(record)
                    if record_terminal and not bool(sent.get("completed")):
                        yield self.projected_record_completed_stream_event(
                            current_turn,
                            record,
                        )
                        sent["completed"] = True
                        emitted = True
                    elif not record_terminal:
                        sent["completed"] = False

                session_row = self.repository.session_row(
                    account_id,
                    current_turn["session_id"],
                )
                if session_row is None:
                    raise_error("missing", "NOT_FOUND", "流式订阅不存在。")
                current_title = str(session_row["title"] or "")
                if current_title and current_title != last_title:
                    yield self.session_title_updated_stream_event(
                        current_turn,
                        current_title,
                    )
                    last_title = current_title
                    emitted = True

                if current_turn["status"] not in {"queued", "streaming"}:
                    if current_turn["status"] == "failed":
                        yield sse_event(
                            "turn_failed",
                            {
                                "session_id": current_turn["session_id"],
                                "turn_id": current_turn["turn_id"],
                                "code": current_turn["error_code"],
                                "message": current_turn["error_message"],
                            },
                        )
                        return
                    if current_turn["status"] == "cancelled":
                        yield self.cancelled_stream_event(current_turn)
                        return
                    current_messages = self.repository.messages_by_id(
                        account_id,
                        current_turn["session_id"],
                    )
                    if not current_messages.get(
                        current_turn["final_assistant_message_id"] or ""
                    ):
                        raise_error("missing", "NOT_FOUND", "流式内容不存在。")
                    yield self.completed_stream_event(
                        current_turn,
                        current_turn["final_assistant_message_id"],
                    )
                    return

                if emitted:
                    last_activity_at = time.monotonic()
                elif time.monotonic() - last_activity_at >= SSE_HEARTBEAT_SECONDS:
                    yield ": keep-alive\n\n"
                    last_activity_at = time.monotonic()
                if not emitted:
                    self.notifications.wait_for_events(
                        account_id,
                        current_turn["session_id"],
                        next_event_seq,
                        timeout=SSE_POLL_SECONDS,
                    )

        return events()

    @staticmethod
    def projected_record_is_terminal(record: dict[str, Any]) -> bool:
        return str(record.get("status") or "completed") not in {
            "queued",
            "running",
            "streaming",
        }

    def projected_record_started_stream_event(
        self,
        turn,
        record: dict[str, Any],
    ) -> str:
        kind = record["kind"]
        if kind not in {
            "context",
            "error",
            "model",
            "observation",
            "tool",
            "assistant",
        }:
            return ""
        started = record_response(record)
        if kind == "assistant":
            started.update(content="", status="streaming")
        elif kind == "model":
            started["status"] = "streaming"
            if record.get("channel") in {"reasoning", "content", "raw_output"}:
                started["value"] = ""
        elif kind == "tool":
            started.update(result=None, status="running")
        return sse_event(
            "record_started", {**started, "session_id": turn["session_id"]}
        )

    def projected_record_completed_stream_event(
        self,
        turn,
        record: dict[str, Any],
    ) -> str:
        completed = record_response(record)
        if record["kind"] == "model":
            completed["content"] = completed.get("value")
        return sse_event(
            "record_completed", {**completed, "session_id": turn["session_id"]}
        )

    def completed_stream_event(
        self,
        turn,
        final_assistant_message_id: str | None,
    ) -> str:
        return sse_event(
            "turn_completed",
            {
                "session_id": turn["session_id"],
                "turn_id": turn["turn_id"],
                "final_assistant_message_id": final_assistant_message_id,
            },
        )

    @staticmethod
    def record_delta_stream_event(
        turn,
        *,
        record_id: str,
        kind: str,
        delta: str,
        offset: int,
        channel: str | None = None,
    ) -> str:
        payload = {
            "session_id": turn["session_id"],
            "turn_id": turn["turn_id"],
            "record_id": record_id,
            "kind": kind,
            "delta": delta,
            "offset": offset,
        }
        if channel:
            payload["channel"] = channel
        return sse_event("record_delta", payload)

    @staticmethod
    def session_title_updated_stream_event(turn, title: str) -> str:
        return sse_event(
            "session_title_updated",
            {
                "session_id": turn["session_id"],
                "turn_id": turn["turn_id"],
                "title": title,
            },
        )

    @staticmethod
    def thinking_mode_events_for_turn(events, turn_id: str):
        return [
            event
            for event in events
            if event.type == "turn/thinking_mode_changed"
            and str(event.data.get("turn_id") or "") == turn_id
        ]

    @staticmethod
    def thinking_mode_changed_stream_event(turn, data: dict[str, Any]) -> str:
        return sse_event(
            "thinking_mode_changed",
            {
                "session_id": turn["session_id"],
                "turn_id": turn["turn_id"],
                "requested_mode": str(data.get("requested_mode") or "default"),
                "effective_mode": str(data.get("effective_mode") or "default"),
                "reasons": [
                    str(reason) for reason in data.get("reasons", []) if str(reason)
                ],
            },
        )

    def cancelled_stream_event(self, turn) -> str:
        return sse_event(
            "turn_cancelled",
            {
                "session_id": turn["session_id"],
                "turn_id": turn["turn_id"],
                "code": "CANCELLED",
                "message": CANCELLED_ASSISTANT_CONTENT,
            },
        )


SSE_POLL_SECONDS = 0.05

SSE_HEARTBEAT_SECONDS = 10.0

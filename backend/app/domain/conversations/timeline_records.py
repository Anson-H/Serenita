"""消息、工具、上下文与轮次状态的增量投影。"""

from __future__ import annotations
from typing import TYPE_CHECKING
from backend.app.domain.conversations.events import SessionEvent

if TYPE_CHECKING:
    from backend.app.domain.conversations.timeline_state import TurnTimelineState
from backend.app.domain.conversations.timeline_model import _retry_message


class RecordTimelineHandlers:
    def __init__(self, state: TurnTimelineState) -> None:
        self.state = state

    def on_turn_start(self, event: SessionEvent) -> None:
        data = event.data
        self.state.turn_start[str(data.get("turn_id") or "")] = event.time
        return

    def on_message(self, event: SessionEvent) -> None:
        data = event.data
        kind = "user" if event.type == "user/message" else "assistant"
        if data.get("branch_addressable") is False:
            return
        message_id = str(data.get("message_id") or "")
        if not message_id:
            return
        existing = self.state.messages.get(message_id)
        if existing is not None and kind == "assistant":
            existing.update(data)
            existing["seq"] = event.seq
            existing["time"] = event.time
            existing["source_event_seqs"] = list(
                dict.fromkeys(
                    [
                        *existing.get("source_event_seqs", []),
                        *(event.source_event_seqs or ()),
                        event.seq,
                    ]
                )
            )
            self.state.mark_changed(existing)
            return
        record = {
            **data,
            "record_id": message_id,
            "kind": kind,
            "seq": event.seq,
            "time": event.time,
            "source_event_seqs": list(event.source_event_seqs or (event.seq,)),
        }
        self.state.messages[message_id] = record
        self.state.add_record(record)
        return

    def on_compaction_status(self, event: SessionEvent) -> None:
        data = event.data
        record_id = str(data["message_id"])
        record = self.state.compaction_statuses.get(record_id)
        if record is None:
            record = {
                "record_id": record_id,
                "call_id": record_id,
                "context_id": record_id,
                "kind": "context",
                "context_type": "compaction_status",
                "label": "上下文压缩",
                "purpose": "context_compaction",
                "seq": event.seq,
                "time": event.time,
                "source_event_seqs": [],
            }
            self.state.compaction_statuses[record_id] = record
            self.state.add_record(record)
        for field in ("estimated_tokens_after", "error"):
            record.pop(field, None)
        record.update(data)
        self.state.append_source(record, event.seq)
        self.state.apply_compaction_commit(record)
        return

    def on_compaction_checkpoint(self, event: SessionEvent) -> None:
        data = event.data
        compaction_id = data["compaction_id"]
        self.state.committed_compactions[compaction_id] = event
        if compaction_id in self.state.compaction_statuses:
            self.state.apply_compaction_commit(
                self.state.compaction_statuses[compaction_id]
            )
        record_id = str(data.get("message_id") or f"compaction_{event.seq}")
        self.state.add_record(
            {
                **data,
                "record_id": record_id,
                "call_id": record_id,
                "context_id": record_id,
                "kind": "context",
                "context_type": "compacted_summary",
                "label": "上下文压缩摘要",
                "purpose": "context_compaction",
                "status": "completed",
                "content": data.get("content"),
                "seq": event.seq,
                "time": event.time,
                "source_event_seqs": [*(event.source_event_seqs or ()), event.seq],
            }
        )
        return

    def on_message_update(self, event: SessionEvent) -> None:
        data = event.data
        message_id = str(data.get("message_id") or "")
        patch = data.get("patch")
        if message_id in self.state.messages and isinstance(patch, dict):
            self.state.messages[message_id].update(patch)
            self.state.append_source(self.state.messages[message_id], event.seq)
        return

    def on_request_context(self, event: SessionEvent) -> None:
        data = event.data
        call_id = str(data.get("call_id") or "")
        context = data.get("context")
        if not call_id or not isinstance(context, dict):
            return
        purpose = str(
            context.get("purpose") or self.state.purpose_by_call.get(call_id) or ""
        )
        record_id = str(context.get("record_id") or f"context_{call_id}_{event.seq}")
        header = self.state.headers_by_call.get(call_id, {})
        self.state.add_record(
            {
                "record_id": record_id,
                "kind": "context",
                "turn_id": data.get("turn_id"),
                "call_id": call_id,
                "context_id": context.get("context_id") or record_id,
                "context_type": context.get("context_type") or "system_prompt",
                "label": context.get("label") or _context_purpose_label(purpose),
                "purpose": purpose,
                "step": data.get("step"),
                "transport_mode": context.get("transport_mode")
                or header.get("transport_mode"),
                "parent_tool_call_id": context.get("parent_tool_call_id")
                or header.get("parent_tool_call_id"),
                "content": context.get("content"),
                "provider_source": context.get("provider_source"),
                "status": context.get("status") or "completed",
                "created_at": context.get("created_at"),
                "duration_ms": int(context.get("duration_ms") or 0),
                "seq": event.seq,
                "time": event.time,
                "source_event_seqs": [event.seq],
            }
        )
        self.state.context_defaults[record_id] = {
            field
            for field in ("label", "purpose", "transport_mode", "parent_tool_call_id")
            if not context.get(field)
        }
        return

    def on_observation(self, event: SessionEvent) -> None:
        data = event.data
        observation = data.get("observation")
        if not isinstance(observation, dict):
            return
        self.state.add_record(
            {
                "record_id": f"observation_{event.seq}",
                "kind": "observation",
                "turn_id": data.get("turn_id"),
                "call_id": data.get("call_id"),
                "step": data.get("step"),
                "observation": observation,
                "status": data.get("status") or "completed",
                "error": observation.get("error"),
                "created_at": data.get("created_at"),
                "duration_ms": 0,
                "seq": event.seq,
                "time": event.time,
                "source_event_seqs": [event.seq],
            }
        )
        return

    def on_tool_call(self, event: SessionEvent) -> None:
        data = event.data
        call_id = str(data.get("call_id") or "")
        if not call_id:
            return
        record = {
            "record_id": f"tool_{call_id}",
            "kind": "tool",
            "turn_id": data.get("turn_id"),
            "call_id": call_id,
            "tool_call_id": data.get("tool_call_id"),
            "step": data.get("step"),
            "name": data.get("name"),
            "arguments": data.get("arguments"),
            "result": None,
            "status": "running",
            "created_at": data.get("created_at"),
            "duration_ms": 0,
            "seq": event.seq,
            "time": event.time,
            "source_event_seqs": [event.seq],
        }
        self.state.tools[call_id] = record
        self.state.add_record(record)
        return

    def on_tool_result(self, event: SessionEvent) -> None:
        data = event.data
        call_id = str(data.get("call_id") or "")
        record = self.state.tools.get(call_id)
        if record is not None:
            record.update(
                {
                    "result": data.get("result"),
                    "status": data.get("status", "completed"),
                    "error": data.get("error"),
                    "duration_ms": data.get(
                        "duration_ms", record.get("duration_ms", 0)
                    ),
                }
            )
            self.state.append_source(record, event.seq)
        return

    def on_turn_end(self, event: SessionEvent) -> None:
        data = event.data
        turn_id = str(data.get("turn_id") or "")
        self.state.turn_end_time[turn_id] = event.time
        self.state.refresh_turn_duration()
        for record in self.state.retries.values():
            if record.get("turn_id") == turn_id and record.get("status") == "running":
                retry = {**record["retry"], "status": "cancelled", "delay_seconds": 0}
                record.update(
                    status="interrupted",
                    retry=retry,
                    value=_retry_message(retry),
                    error=None,
                )
                self.state.append_source(record, event.seq)
        for record in self.state.compaction_statuses.values():
            if record.get("turn_id") == turn_id and record.get("status") == "running":
                record.update(
                    status="failed",
                    error={
                        "code": "CONTEXT_COMPACTION_INTERRUPTED",
                        "message": "轮次已结束，上下文压缩未完成。",
                    },
                )
                self.state.append_source(record, event.seq)
        reason = data.get("reason")
        if not isinstance(reason, dict):
            return
        reason_kind = str(reason.get("kind") or "")
        if reason_kind in {"completed", "cancelled", "aborted", "steered"}:
            return
        self.state.add_record(
            {
                "record_id": f"turn_error_{event.seq}",
                "kind": "error",
                "turn_id": turn_id,
                "status": "failed",
                "error": dict(reason),
                "duration_ms": 0,
                "seq": event.seq,
                "time": event.time,
                "source_event_seqs": [event.seq],
            }
        )


def _context_purpose_label(purpose: str) -> str:
    return {
        "agent_action": "Agent 行动上下文",
        "vision_parse": "医疗报告解析上下文",
    }.get(purpose, "模型请求上下文")

"""持有单个轮次的投影状态、索引和本次增量；不保存或重放事件历史。"""

from __future__ import annotations
from typing import Any
from backend.app.domain.conversations.events import SessionEvent
from backend.app.domain.conversations.timeline_model import ModelTimelineHandlers
from backend.app.domain.conversations.timeline_records import (
    RecordTimelineHandlers,
    _context_purpose_label,
)


class TurnTimelineState:
    def __init__(self) -> None:
        self.headers_by_call = {}
        self.purpose_by_call = {}
        self.records = {}
        self.messages = {}
        self.compaction_statuses = {}
        self.committed_compactions = {}
        self.tools = {}
        self.model_channels = {}
        self.retries = {}
        self.model_tool_requests = {}
        self.turn_start = {}
        self.turn_end_time = {}
        self.context_defaults = {}
        self.records_by_call = {}
        self.source_seqs = {}
        self.changed = set()
        self.new_records = []
        model = ModelTimelineHandlers(self)
        record = RecordTimelineHandlers(self)
        self.handlers = {
            "turn/start": record.on_turn_start,
            "user/message": record.on_message,
            "assistant/message": record.on_message,
            "user/message-update": record.on_message_update,
            "assistant/message-update": record.on_message_update,
            "compaction/status": record.on_compaction_status,
            "compaction/checkpoint": record.on_compaction_checkpoint,
            "request/context": record.on_request_context,
            "model/retry": model.on_retry,
            "request/header": model.on_request_header,
            "assistant/chunk": model.on_chunk,
            "model/result": model.on_result,
            "harness/observation": record.on_observation,
            "tool/call": record.on_tool_call,
            "tool/result": record.on_tool_result,
            "turn/end": record.on_turn_end,
        }

    def apply_event(self, event: SessionEvent) -> None:
        handler = self.handlers.get(event.type)
        if handler is not None:
            handler(event)

    def mark_changed(self, record: dict[str, Any]) -> None:
        self.changed.add(record["record_id"])
        self._set_duration(record)

    def _set_duration(self, record: dict[str, Any]) -> None:
        turn_id = str(record.get("turn_id") or "")
        start, end = self.turn_start.get(turn_id), self.turn_end_time.get(turn_id)
        if start is not None and end is not None:
            record["turn_duration_ms"] = max(0, end - start)

    def refresh_turn_duration(self) -> None:
        for record in self.records.values():
            self.mark_changed(record)

    def add_record(self, record: dict[str, Any]) -> None:
        record_id = record["record_id"]
        self.records[record_id] = record
        self.new_records.append(record)
        self.source_seqs[record_id] = set(record["source_event_seqs"])
        call_id = record.get("call_id")
        if call_id:
            self.records_by_call.setdefault(call_id, {})[record_id] = record
        self.mark_changed(record)

    def append_source(self, record: dict[str, Any], seq: int) -> None:
        record_id = record["record_id"]
        if record_id not in self.source_seqs:
            self.source_seqs[record_id] = set(record["source_event_seqs"])
        seen = self.source_seqs[record_id]
        if seq not in seen:
            record["source_event_seqs"].append(seq)
            seen.add(seq)
        self.mark_changed(record)

    def register_header(self, event: SessionEvent) -> None:
        data = event.data
        call_id, header = str(data.get("call_id") or ""), data.get("header")
        if not call_id or not isinstance(header, dict):
            return
        self.headers_by_call[call_id] = header
        purpose = str(data.get("purpose") or "")
        self.purpose_by_call[call_id] = purpose
        model = header.get("model") or {}
        # Context events may precede headers, including across separate SSE batches.
        for record_id, record in self.records_by_call.get(call_id, {}).items():
            if record.get("kind") == "model":
                record.update(
                    model_id=model.get("model_id"),
                    context_window_tokens=model.get("context_window_tokens"),
                    summary_kind=(header.get("model_config") or {}).get("summary_kind"),
                    transport_mode=header.get("transport_mode"),
                    parent_tool_call_id=header.get("parent_tool_call_id"),
                )
                if not record.get("purpose"):
                    record["purpose"] = purpose
                if not record.get("retry") and header.get("retry"):
                    record.update(
                        retry=dict(header["retry"]),
                        first_call_id=header.get("first_call_id"),
                    )
                self.mark_changed(record)
            elif record_id in self.context_defaults:
                defaults = self.context_defaults[record_id]
                for field in defaults - {"purpose", "label"}:
                    record[field] = header.get(field)
                if "purpose" in defaults:
                    record["purpose"] = purpose
                if "label" in defaults:
                    record["label"] = _context_purpose_label(record["purpose"])
                self.mark_changed(record)

    def apply_compaction_commit(self, record: dict[str, Any]) -> None:
        checkpoint = self.committed_compactions.get(record["record_id"])
        if checkpoint is None or checkpoint.data["turn_id"] != record.get("turn_id"):
            return
        record["status"] = "completed"
        record.pop("error", None)
        for field in (
            "estimated_tokens_before",
            "estimated_tokens_after",
            "target_tokens",
        ):
            record[field] = checkpoint.data[field]
        self.append_source(record, checkpoint.seq)
        record["source_event_seqs"].sort()

    def model_record(
        self,
        *,
        call_id: str,
        channel: str,
        event: SessionEvent,
        data: dict[str, Any],
        value: Any,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        header = self.headers_by_call.get(call_id, {})
        header_model = header.get("model") or {}
        return {
            "record_id": record_id or f"model_{call_id}_{channel}",
            "kind": "model",
            "channel": channel,
            "turn_id": data.get("turn_id"),
            "call_id": call_id,
            "purpose": data.get("purpose") or self.purpose_by_call.get(call_id),
            "summary_kind": (header.get("model_config") or {}).get("summary_kind"),
            "step": data.get("step"),
            "model_id": header_model.get("model_id"),
            "context_window_tokens": header_model.get("context_window_tokens"),
            "transport_mode": header.get("transport_mode"),
            "parent_tool_call_id": header.get("parent_tool_call_id"),
            "value": value,
            "status": "streaming" if channel != "input" else "completed",
            "error": None,
            "created_at": data.get("created_at"),
            "duration_ms": int(data.get("duration_ms") or 0),
            "seq": event.seq,
            "time": event.time,
            "source_event_seqs": [event.seq],
            **(
                {
                    "retry": dict(data.get("retry") or header["retry"]),
                    "first_call_id": data.get("first_call_id")
                    or header.get("first_call_id"),
                }
                if data.get("retry") or header.get("retry")
                else {}
            ),
        }

    def upsert_text_channel(
        self,
        *,
        call_id: str,
        channel: str,
        text: str,
        event: SessionEvent,
        data: dict[str, Any],
        replace: bool = False,
    ) -> dict[str, Any] | None:
        key = (call_id, channel)
        record = self.model_channels.get(key)
        if record is None:
            if not text or (channel == "reasoning" and (not text.strip())):
                return None
            record = self.model_record(
                call_id=call_id, channel=channel, event=event, data=data, value=text
            )
            self.model_channels[key] = record
            self.add_record(record)
            return record
        record["value"] = text if replace else str(record.get("value") or "") + text
        if not replace:
            record["status"] = "streaming"
            record["error"] = None
        record["duration_ms"] = max(
            int(record.get("duration_ms") or 0), int(data.get("duration_ms") or 0)
        )
        self.append_source(record, event.seq)
        return record

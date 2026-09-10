"""将会话事件投影为界面时间线，并计算流式更新需要的记录变化。"""

from __future__ import annotations

from collections import OrderedDict
import json
from typing import Any, Iterable

from backend.app.domain.conversations.events import SessionEvent
from backend.app.domain.conversations.queries import current_session_turn_ids


def _project_records_for_events(events: Iterable[SessionEvent]) -> list[dict[str, Any]]:
    """Project the durable log as one flat, truthful execution timeline."""

    materialized = list(events)
    headers_by_call = {
        str(event.data.get("call_id") or ""): dict(event.data.get("header") or {})
        for event in materialized
        if event.type == "request/header" and event.data.get("call_id")
    }
    purpose_by_call = {
        str(event.data.get("call_id") or ""): str(event.data.get("purpose") or "")
        for event in materialized
        if event.type == "request/header" and event.data.get("call_id")
    }
    records: list[dict[str, Any]] = []
    messages: dict[str, dict[str, Any]] = {}
    compaction_statuses: dict[str, dict[str, Any]] = {}
    committed_compactions: dict[str, SessionEvent] = {}
    tools: OrderedDict[str, dict[str, Any]] = OrderedDict()
    model_channels: dict[tuple[str, str], dict[str, Any]] = {}
    model_tool_requests: dict[tuple[str, int], dict[str, Any]] = {}
    turn_start: dict[str, int] = {}
    turn_end_time: dict[str, int] = {}

    def append_source(record: dict[str, Any], seq: int) -> None:
        if seq not in record["source_event_seqs"]:
            record["source_event_seqs"].append(seq)

    def apply_compaction_commit(record: dict[str, Any]) -> None:
        checkpoint = committed_compactions.get(record["record_id"])
        if checkpoint is None or checkpoint.data["turn_id"] != record.get("turn_id"):
            return
        # A complete checkpoint line is the durable commit even if the next
        # status line was torn. Later status events cannot undo that commit.
        record["status"] = "completed"
        record.pop("error", None)
        for field in (
            "estimated_tokens_before",
            "estimated_tokens_after",
            "target_tokens",
        ):
            record[field] = checkpoint.data[field]
        append_source(record, checkpoint.seq)
        record["source_event_seqs"].sort()

    def model_record(
        *,
        call_id: str,
        channel: str,
        event: SessionEvent,
        data: dict[str, Any],
        value: Any,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        header = headers_by_call.get(call_id, {})
        header_model = header.get("model") or {}
        return {
            "record_id": record_id or f"model_{call_id}_{channel}",
            "kind": "model",
            "channel": channel,
            "turn_id": data.get("turn_id"),
            "call_id": call_id,
            "purpose": data.get("purpose") or purpose_by_call.get(call_id),
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
        }

    def upsert_text_channel(
        *,
        call_id: str,
        channel: str,
        text: str,
        event: SessionEvent,
        data: dict[str, Any],
        replace: bool = False,
    ) -> dict[str, Any] | None:
        key = (call_id, channel)
        record = model_channels.get(key)
        if record is None:
            if not text or (channel == "reasoning" and not text.strip()):
                return None
            record = model_record(
                call_id=call_id,
                channel=channel,
                event=event,
                data=data,
                value=text,
            )
            model_channels[key] = record
            records.append(record)
            return record
        record["value"] = text if replace else str(record.get("value") or "") + text
        if not replace:
            record["status"] = "streaming"
            record["error"] = None
        record["duration_ms"] = max(
            int(record.get("duration_ms") or 0), int(data.get("duration_ms") or 0)
        )
        append_source(record, event.seq)
        return record

    for event in materialized:
        data = event.data
        if event.type == "turn/start":
            turn_start[str(data.get("turn_id") or "")] = event.time
            continue
        if event.type in {"user/message", "assistant/message"}:
            kind = "user" if event.type == "user/message" else "assistant"
            if data.get("branch_addressable") is False:
                continue
            message_id = str(data.get("message_id") or "")
            if not message_id:
                continue
            existing = messages.get(message_id)
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
                continue
            record = {
                **data,
                "record_id": message_id,
                "kind": kind,
                "seq": event.seq,
                "time": event.time,
                "source_event_seqs": list(event.source_event_seqs or (event.seq,)),
            }
            messages[message_id] = record
            records.append(record)
            continue
        if event.type == "compaction/status":
            record_id = str(data["message_id"])
            record = compaction_statuses.get(record_id)
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
                compaction_statuses[record_id] = record
                records.append(record)
            for field in ("estimated_tokens_after", "error"):
                record.pop(field, None)
            record.update(data)
            append_source(record, event.seq)
            apply_compaction_commit(record)
            continue
        if event.type == "compaction/checkpoint":
            compaction_id = data["compaction_id"]
            committed_compactions[compaction_id] = event
            if compaction_id in compaction_statuses:
                apply_compaction_commit(compaction_statuses[compaction_id])
            record_id = str(data.get("message_id") or f"compaction_{event.seq}")
            records.append(
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
            continue
        if event.type in {"user/message-update", "assistant/message-update"}:
            message_id = str(data.get("message_id") or "")
            patch = data.get("patch")
            if message_id in messages and isinstance(patch, dict):
                messages[message_id].update(patch)
                append_source(messages[message_id], event.seq)
            continue
        if event.type == "request/context":
            call_id = str(data.get("call_id") or "")
            context = data.get("context")
            if not call_id or not isinstance(context, dict):
                continue
            purpose = str(context.get("purpose") or purpose_by_call.get(call_id) or "")
            record_id = str(
                context.get("record_id") or f"context_{call_id}_{event.seq}"
            )
            header = headers_by_call.get(call_id, {})
            records.append(
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
            continue
        if event.type == "request/header":
            call_id = str(data.get("call_id") or "")
            header = data.get("header")
            if not call_id or not isinstance(header, dict):
                continue
            record = model_record(
                call_id=call_id,
                channel="input",
                event=event,
                data=data,
                value=header.get("provider_payload"),
            )
            model_channels[(call_id, "input")] = record
            records.append(record)
            continue
        if event.type == "assistant/chunk":
            chunk = data.get("chunk")
            call_id = str(data.get("call_id") or "")
            if not isinstance(chunk, dict) or not call_id:
                continue
            chunk_type = str(chunk.get("type") or "")
            if (
                chunk_type == "text-delta"
                and data.get("branch_addressable") is not False
            ):
                message_id = str(data.get("final_assistant_message_id") or "")
                if not message_id:
                    continue
                record = messages.get(message_id)
                if record is None:
                    record = {
                        "record_id": message_id,
                        "message_id": message_id,
                        "parent_message_id": data.get("message_id")
                        or data.get("parent_message_id"),
                        "kind": "assistant",
                        "turn_id": data.get("turn_id"),
                        "model_id": data.get("model_id"),
                        "content": "",
                        "status": "streaming",
                        "created_at": data.get("created_at"),
                        "duration_ms": 0,
                        "seq": event.seq,
                        "time": event.time,
                        "source_event_seqs": [],
                    }
                    messages[message_id] = record
                    records.append(record)
                record["content"] += str(chunk.get("delta") or "")
                record["duration_ms"] = max(
                    int(record.get("duration_ms") or 0),
                    int(data.get("duration_ms") or 0),
                )
                append_source(record, event.seq)
                continue
            if chunk_type == "channel-end":
                ended_record = model_channels.get(
                    (call_id, str(chunk.get("channel") or ""))
                )
                if ended_record is not None:
                    ended_record["status"] = "completed"
                    ended_record["duration_ms"] = int(data.get("duration_ms") or 0)
                    append_source(ended_record, event.seq)
                continue
            channel = {
                "reasoning-delta": "reasoning",
                "text-delta": "content",
                "raw-text-delta": "raw_output",
            }.get(chunk_type)
            if channel is not None:
                upsert_text_channel(
                    call_id=call_id,
                    channel=channel,
                    text=str(chunk.get("delta") or ""),
                    event=event,
                    data=data,
                )
                continue
            if chunk_type == "tool-call-delta":
                index = int(chunk.get("index") or 0)
                key = (call_id, index)
                record = model_tool_requests.get(key)
                if record is None:
                    name = str(chunk.get("name_delta") or "")
                    arguments = str(chunk.get("arguments_delta") or "")
                    record = model_record(
                        call_id=call_id,
                        channel="tool_request",
                        event=event,
                        data=data,
                        value={"name": name, "arguments": arguments},
                        record_id=f"model_{call_id}_tool_request_{index}",
                    )
                    record["provider_index"] = index
                    record["tool_call_id"] = str(chunk.get("id") or "")
                    record["name"] = name
                    record["arguments"] = arguments
                    model_tool_requests[key] = record
                    records.append(record)
                else:
                    if chunk.get("id"):
                        record["tool_call_id"] = str(chunk["id"])
                    record["name"] += str(chunk.get("name_delta") or "")
                    arguments_delta = str(chunk.get("arguments_delta") or "")
                    record["arguments"] += arguments_delta
                    record["value"] = {
                        "name": record["name"],
                        "arguments": record["arguments"],
                    }
                    record["duration_ms"] = max(
                        int(record.get("duration_ms") or 0),
                        int(data.get("duration_ms") or 0),
                    )
                    append_source(record, event.seq)
                continue
            continue
        if event.type == "model/result":
            call_id = str(data.get("call_id") or "")
            if not call_id:
                continue
            raw_result = data.get("result")
            result = (
                raw_result if isinstance(raw_result, dict) else {"content": raw_result}
            )
            raw_channel_durations = data.get("channel_durations_ms")
            channel_durations = (
                raw_channel_durations if isinstance(raw_channel_durations, dict) else {}
            )
            for channel, key in (
                ("reasoning", "reasoning"),
                ("content", "content"),
                ("raw_output", "raw_content"),
            ):
                text = str(result.get(key) or "")
                record = upsert_text_channel(
                    call_id=call_id,
                    channel=channel,
                    text=text,
                    event=event,
                    data=data,
                    replace=True,
                )
                if record is not None:
                    if channel in channel_durations:
                        record["duration_ms"] = int(channel_durations[channel] or 0)
                    record["status"] = data.get("status") or "completed"
                    record["error"] = data.get("error")
            tool_calls = result.get("tool_calls")
            if isinstance(tool_calls, list):
                for index, raw_call in enumerate(tool_calls):
                    if not isinstance(raw_call, dict):
                        continue
                    function = raw_call.get("function")
                    function = function if isinstance(function, dict) else {}
                    tool_call_id = str(raw_call.get("id") or "")
                    name = str(function.get("name") or raw_call.get("name") or "")
                    raw_arguments = function.get(
                        "arguments", raw_call.get("arguments", {})
                    )
                    arguments: Any = raw_arguments
                    if isinstance(raw_arguments, str):
                        try:
                            parsed_arguments = json.loads(raw_arguments or "{}")
                        except json.JSONDecodeError:
                            parsed_arguments = raw_arguments
                        arguments = parsed_arguments
                    record = model_tool_requests.get((call_id, index))
                    value = (
                        str(result.get("raw_content") or "")
                        if (record or {}).get("transport_mode") == "text_tool"
                        else (function or raw_call)
                    )
                    if record is None:
                        record = model_record(
                            call_id=call_id,
                            channel="tool_request",
                            event=event,
                            data=data,
                            value=value,
                            record_id=f"model_{call_id}_tool_request_{index}",
                        )
                        record["provider_index"] = index
                        model_tool_requests[(call_id, index)] = record
                        records.append(record)
                    record.update(
                        {
                            "value": value,
                            "tool_call_id": tool_call_id,
                            "name": name,
                            "arguments": arguments,
                            "status": data.get("status") or "completed",
                            "error": data.get("error"),
                            "duration_ms": int(
                                channel_durations["tool_request"]
                                if "tool_request" in channel_durations
                                else data.get("duration_ms") or 0
                            ),
                        }
                    )
                    append_source(record, event.seq)
            status = str(data.get("status") or "completed")
            duration_ms = int(data.get("duration_ms") or 0)
            result_value = {
                "status": status,
                "usage": result.get("usage")
                if isinstance(result.get("usage"), dict)
                else {},
                "stop_reason": result.get("stop_reason"),
                "error": data.get("error"),
                "duration_ms": duration_ms,
            }
            record = model_record(
                call_id=call_id,
                channel="result",
                event=event,
                data=data,
                value=result_value,
            )
            record.update(
                {
                    "status": status,
                    "error": data.get("error"),
                    "duration_ms": duration_ms,
                    "usage": result_value["usage"],
                    "stop_reason": result_value["stop_reason"],
                }
            )
            model_channels[(call_id, "result")] = record
            records.append(record)
            continue
        if event.type == "harness/observation":
            observation = data.get("observation")
            if not isinstance(observation, dict):
                continue
            records.append(
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
            continue
        if event.type == "tool/call":
            call_id = str(data.get("call_id") or "")
            if not call_id:
                continue
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
            tools[call_id] = record
            records.append(record)
            continue
        if event.type == "tool/result":
            call_id = str(data.get("call_id") or "")
            record = tools.get(call_id)
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
                append_source(record, event.seq)
            continue
        if event.type == "turn/end":
            turn_id = str(data.get("turn_id") or "")
            turn_end_time[turn_id] = event.time
            for record in compaction_statuses.values():
                if (
                    record.get("turn_id") == turn_id
                    and record.get("status") == "running"
                ):
                    record.update(
                        status="failed",
                        error={
                            "code": "CONTEXT_COMPACTION_INTERRUPTED",
                            "message": "轮次已结束，上下文压缩未完成。",
                        },
                    )
                    append_source(record, event.seq)
            reason = data.get("reason")
            if not isinstance(reason, dict):
                continue
            reason_kind = str(reason.get("kind") or "")
            if reason_kind in {"completed", "cancelled", "aborted", "steered"}:
                continue
            records.append(
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

    for record in records:
        turn_id = str(record.get("turn_id") or "")
        started_at = turn_start.get(turn_id)
        ended_at = turn_end_time.get(turn_id)
        if started_at is not None and ended_at is not None:
            record["turn_duration_ms"] = max(0, ended_at - started_at)
    records.sort(key=lambda item: int(item.get("seq") or 0))
    return records


class ConversationTimelineProjector:
    """Incrementally reproject only Turns touched by newly appended events."""

    def __init__(self, events: Iterable[SessionEvent] = ()) -> None:
        self._events_by_turn: OrderedDict[str, list[SessionEvent]] = OrderedDict()
        self._records_by_turn: dict[str, list[dict[str, Any]]] = {}
        self._turn_by_message_id: dict[str, str] = {}
        self._records: list[dict[str, Any]] = []
        self.apply_events(events)

    def _event_turn_id(self, event: SessionEvent) -> str:
        turn_id = str(event.data.get("turn_id") or "")
        if turn_id:
            return turn_id
        if event.type in {"user/message-update", "assistant/message-update"}:
            return self._turn_by_message_id.get(
                str(event.data.get("message_id") or ""), ""
            )
        return ""

    def apply_events(self, events: Iterable[SessionEvent]) -> set[str]:
        affected_turns: set[str] = set()
        unscoped_events: list[SessionEvent] = []
        for event in events:
            turn_id = self._event_turn_id(event)
            if event.type in {"user/message", "assistant/message"}:
                message_id = str(event.data.get("message_id") or "")
                if message_id and turn_id:
                    self._turn_by_message_id[message_id] = turn_id
            if not turn_id:
                unscoped_events.append(event)
                continue
            self._events_by_turn.setdefault(turn_id, []).append(event)
            affected_turns.add(turn_id)

        if unscoped_events:
            # Record-producing events are Turn-scoped by contract. Keeping an
            # explicit bucket makes an unexpected future event truthful instead
            # of silently attaching it to the active Turn.
            bucket = self._events_by_turn.setdefault("", [])
            bucket.extend(unscoped_events)
            affected_turns.add("")

        changed_record_ids: set[str] = set()
        for turn_id in affected_turns:
            previous = {
                str(record.get("record_id") or record.get("message_id") or ""): record
                for record in self._records_by_turn.get(turn_id, [])
            }
            projected = _project_records_for_events(self._events_by_turn[turn_id])
            current = {
                str(record.get("record_id") or record.get("message_id") or ""): record
                for record in projected
            }
            changed_record_ids.update(
                record_id
                for record_id in previous.keys() | current.keys()
                if previous.get(record_id) != current.get(record_id)
            )
            self._records_by_turn[turn_id] = projected

        if affected_turns:
            self._records = sorted(
                (
                    record
                    for records in self._records_by_turn.values()
                    for record in records
                ),
                key=lambda item: int(item.get("seq") or 0),
            )
        return changed_record_ids

    def records(self) -> list[dict[str, Any]]:
        return list(self._records)

    def records_for_turn(self, turn_id: str) -> list[dict[str, Any]]:
        return list(self._records_by_turn.get(turn_id, []))

    def records_for_ids(self, record_ids: Iterable[str]) -> list[dict[str, Any]]:
        selected = set(record_ids)
        return [
            record
            for record in self._records
            if str(record.get("record_id") or record.get("message_id") or "")
            in selected
        ]


def records_from_events(events: Iterable[SessionEvent]) -> list[dict[str, Any]]:
    """Project the durable log as one flat, truthful execution timeline."""

    return ConversationTimelineProjector(events).records()


def active_records(
    records: Iterable[dict[str, Any]],
    events: Iterable[SessionEvent],
) -> list[dict[str, Any]]:
    """Project the current linear UI surface while retaining old attempts durably."""

    materialized = list(records)
    event_list = list(events)
    active_turns = current_session_turn_ids(event_list)
    active_user_turn_by_id = {
        str(event.data.get("user_message_id") or ""): str(
            event.data.get("turn_id") or ""
        )
        for event in event_list
        if event.type == "turn/start"
        and str(event.data.get("turn_id") or "") in active_turns
    }
    active_user_turn_by_id.update(
        {
            str(event.data.get("message_id") or ""): str(
                event.data.get("turn_id") or ""
            )
            for event in event_list
            if event.type == "user/message"
            and str(event.data.get("turn_id") or "") in active_turns
            and event.data.get("message_id")
        }
    )
    active_user_ids = set(active_user_turn_by_id)

    selected: list[dict[str, Any]] = []
    for record in materialized:
        kind = record.get("kind")
        message_id = record.get("message_id") or record.get("record_id")
        if kind == "user":
            if str(message_id or "") in active_user_ids:
                selected.append(
                    {
                        **record,
                        "turn_id": active_user_turn_by_id[str(message_id)],
                    }
                )
            continue
        if kind == "assistant":
            if str(record.get("turn_id") or "") in active_turns:
                selected.append(record)
            continue
        if (
            kind in {"context", "error", "model", "observation", "tool"}
            and str(record.get("turn_id") or "") in active_turns
        ):
            selected.append(record)
    return selected


def _context_purpose_label(purpose: str) -> str:
    return {
        "agent_action": "Agent 行动上下文",
        "vision_parse": "医疗报告解析上下文",
    }.get(purpose, "模型请求上下文")

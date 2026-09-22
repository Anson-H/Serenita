"""模型请求、片段、重试与结果的增量投影。"""

from __future__ import annotations
import json
from typing import TYPE_CHECKING, Any
from backend.app.domain.conversations.events import SessionEvent

if TYPE_CHECKING:
    from backend.app.domain.conversations.timeline_state import TurnTimelineState


class ModelTimelineHandlers:
    def __init__(self, state: TurnTimelineState) -> None:
        self.state = state

    def on_retry(self, event: SessionEvent) -> None:
        data = event.data
        first_call_id = data["first_call_id"]
        retry = dict(data["retry"])
        record = self.state.retries.get(first_call_id)
        if record is None:
            record = self.state.model_record(
                call_id=data["call_id"],
                channel="retry",
                event=event,
                data=data,
                value="",
                record_id=f"model_{first_call_id}_retry",
            )
            self.state.retries[first_call_id] = record
            self.state.add_record(record)
        record.update(
            call_id=data["call_id"],
            step=data["step"],
            first_call_id=first_call_id,
            retry=retry,
            value=_retry_message(retry),
            error=data.get("error"),
            status={
                "waiting": "running",
                "running": "running",
                "cancelled": "interrupted",
            }.get(retry["status"], retry["status"]),
        )
        self.state.append_source(record, event.seq)
        return

    def on_request_header(self, event: SessionEvent) -> None:
        data = event.data
        call_id = str(data.get("call_id") or "")
        header = data.get("header")
        if not call_id or not isinstance(header, dict):
            return
        record = self.state.model_record(
            call_id=call_id,
            channel="input",
            event=event,
            data=data,
            value=header.get("provider_payload"),
        )
        self.state.model_channels[call_id, "input"] = record
        self.state.add_record(record)
        return

    def on_chunk(self, event: SessionEvent) -> None:
        data = event.data
        chunk = data.get("chunk")
        call_id = str(data.get("call_id") or "")
        if not isinstance(chunk, dict) or not call_id:
            return
        chunk_type = str(chunk.get("type") or "")
        if chunk_type == "text-delta" and data.get("branch_addressable") is not False:
            message_id = str(data.get("final_assistant_message_id") or "")
            if not message_id:
                return
            record = self.state.messages.get(message_id)
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
                self.state.messages[message_id] = record
                self.state.add_record(record)
            record["content"] += str(chunk.get("delta") or "")
            record["duration_ms"] = max(
                int(record.get("duration_ms") or 0), int(data.get("duration_ms") or 0)
            )
            self.state.append_source(record, event.seq)
            return
        if chunk_type == "channel-end":
            ended_record = self.state.model_channels.get(
                (call_id, str(chunk.get("channel") or ""))
            )
            if ended_record is not None:
                ended_record["status"] = "completed"
                ended_record["duration_ms"] = int(data.get("duration_ms") or 0)
                self.state.append_source(ended_record, event.seq)
            return
        channel = {
            "reasoning-delta": "reasoning",
            "text-delta": "content",
            "raw-text-delta": "raw_output",
        }.get(chunk_type)
        if channel is not None:
            self.state.upsert_text_channel(
                call_id=call_id,
                channel=channel,
                text=str(chunk.get("delta") or ""),
                event=event,
                data=data,
            )
            return
        if chunk_type == "tool-call-delta":
            index = int(chunk.get("index") or 0)
            key = (call_id, index)
            record = self.state.model_tool_requests.get(key)
            if record is None:
                name = str(chunk.get("name_delta") or "")
                arguments = str(chunk.get("arguments_delta") or "")
                record = self.state.model_record(
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
                self.state.model_tool_requests[key] = record
                self.state.add_record(record)
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
                self.state.append_source(record, event.seq)
            return
        return

    def on_result(self, event: SessionEvent) -> None:
        data = event.data
        call_id = str(data.get("call_id") or "")
        if not call_id:
            return
        raw_result = data.get("result")
        result = raw_result if isinstance(raw_result, dict) else {"content": raw_result}
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
            record = self.state.upsert_text_channel(
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
                raw_arguments = function.get("arguments", raw_call.get("arguments", {}))
                arguments: Any = raw_arguments
                if isinstance(raw_arguments, str):
                    try:
                        parsed_arguments = json.loads(raw_arguments or "{}")
                    except json.JSONDecodeError:
                        parsed_arguments = raw_arguments
                    arguments = parsed_arguments
                record = self.state.model_tool_requests.get((call_id, index))
                value = (
                    str(result.get("raw_content") or "")
                    if (record or {}).get("transport_mode") == "text_tool"
                    else function or raw_call
                )
                if record is None:
                    record = self.state.model_record(
                        call_id=call_id,
                        channel="tool_request",
                        event=event,
                        data=data,
                        value=value,
                        record_id=f"model_{call_id}_tool_request_{index}",
                    )
                    record["provider_index"] = index
                    self.state.model_tool_requests[call_id, index] = record
                    self.state.add_record(record)
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
                self.state.append_source(record, event.seq)
        status = str(data.get("status") or "completed")
        duration_ms = int(data.get("duration_ms") or 0)
        if status in {"failed", "interrupted", "cancelled"}:
            for (record_call_id, _), existing in [
                *self.state.model_channels.items(),
                *self.state.model_tool_requests.items(),
            ]:
                if record_call_id == call_id:
                    existing.update(status=status, error=data.get("error"))
                    self.state.append_source(existing, event.seq)
        result_value = {
            "status": status,
            "usage": result.get("usage")
            if isinstance(result.get("usage"), dict)
            else {},
            "stop_reason": result.get("stop_reason"),
            "error": data.get("error"),
            "duration_ms": duration_ms,
        }
        record = self.state.model_record(
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
        self.state.model_channels[call_id, "result"] = record
        self.state.add_record(record)
        return


def _retry_message(retry: dict[str, Any]) -> str:
    attempt, maximum = (retry["attempt"], retry["max_attempts"])
    if retry["status"] == "waiting":
        return f"第 {attempt}/{maximum} 次请求失败，等待 {retry['delay_seconds']} 秒后进行第 {attempt + 1}/{maximum} 次尝试。"
    if retry["status"] == "running":
        return f"正在进行第 {attempt}/{maximum} 次尝试。"
    return {
        "completed": f"第 {attempt}/{maximum} 次尝试已完成。",
        "failed": f"第 {attempt}/{maximum} 次尝试失败，已停止重试。",
        "cancelled": f"第 {attempt}/{maximum} 次尝试已取消，已停止重试。",
    }[retry["status"]]

from __future__ import annotations
from typing import Any
from backend.app.session_events import SessionEventCorruptionError


def message_response(
    message: dict[str, Any],
) -> dict[str, Any]:
    response = {
        "message_id": message["message_id"],
        "turn_id": message["turn_id"],
        "parent_message_id": message.get("parent_message_id"),
        "role": message["role"],
        "model_id": message.get("model_id"),
        "content": message.get("content", ""),
        "created_at": message.get("created_at"),
    }
    if message["role"] == "user":
        response["thinking_mode"] = message.get("thinking_mode", "default")
        response["context_resources"] = message.get("context_resources", [])
    if message["role"] == "assistant":
        response["status"] = message.get("status", "completed")
        response["duration_ms"] = message.get("duration_ms", 0)
        response["error"] = message.get("error")
        response["stop_reason"] = message.get("stop_reason", "end_turn")
        response["usage"] = message.get("usage", {})
    return response


def record_response(
    record: dict[str, Any],
) -> dict[str, Any]:
    kind = str(record.get("kind") or "")
    common = {
        "record_id": str(record.get("record_id") or ""),
        "kind": kind,
        "turn_id": record.get("turn_id"),
        "time": record.get("time"),
        "created_at": record.get("created_at"),
        "source_event_seqs": list(record.get("source_event_seqs") or []),
    }
    if kind in {"user", "assistant"}:
        message = {**record, "role": kind}
        return {
            **message_response(
                message,
            ),
            **common,
        }
    if kind == "context":
        return {
            **common,
            "call_id": record.get("call_id"),
            "context_id": record.get("context_id"),
            "context_type": record.get("context_type"),
            "label": record.get("label"),
            "purpose": record.get("purpose"),
            "step": record.get("step"),
            "transport_mode": record.get("transport_mode"),
            "parent_tool_call_id": record.get("parent_tool_call_id"),
            "content": record.get("content"),
            "provider_source": record.get("provider_source"),
            "status": record.get("status", "completed"),
            "duration_ms": record.get("duration_ms", 0),
            "estimated_tokens_before": record.get("estimated_tokens_before"),
            "estimated_tokens_after": record.get("estimated_tokens_after"),
            "target_tokens": record.get("target_tokens"),
            "error": record.get("error"),
        }
    if kind == "model":
        return {
            **common,
            "channel": record.get("channel"),
            "call_id": record.get("call_id"),
            "purpose": record.get("purpose"),
            "summary_kind": record.get("summary_kind"),
            "step": record.get("step"),
            "model_id": record.get("model_id"),
            "context_window_tokens": record.get("context_window_tokens"),
            "transport_mode": record.get("transport_mode"),
            "parent_tool_call_id": record.get("parent_tool_call_id"),
            "tool_call_id": record.get("tool_call_id"),
            "provider_index": record.get("provider_index"),
            "name": record.get("name"),
            "arguments": record.get("arguments"),
            "value": record.get("value"),
            "usage": dict(record.get("usage") or {}),
            "stop_reason": record.get("stop_reason"),
            "status": record.get("status", "completed"),
            "error": record.get("error"),
            "duration_ms": record.get("duration_ms", 0),
        }
    if kind == "observation":
        return {
            **common,
            "call_id": record.get("call_id"),
            "step": record.get("step"),
            "observation": record.get("observation"),
            "status": record.get("status", "completed"),
            "error": record.get("error"),
            "duration_ms": record.get("duration_ms", 0),
        }
    if kind == "tool":
        return {
            **common,
            "call_id": record.get("call_id"),
            "tool_call_id": record.get("tool_call_id"),
            "step": record.get("step"),
            "name": record.get("name"),
            "arguments": record.get("arguments"),
            "result": record.get("result"),
            "status": record.get("status"),
            "error": record.get("error"),
            "duration_ms": record.get("duration_ms", 0),
        }
    if kind == "error":
        return {
            **common,
            "status": record.get("status", "failed"),
            "error": record.get("error"),
            "duration_ms": record.get("duration_ms", 0),
        }
    raise SessionEventCorruptionError(f"unknown projected record kind: {kind!r}")

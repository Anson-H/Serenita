"""提供统一取消提示，并根据未完成的模型与工具活动构造中断事件。"""

from typing import Any
import json
from backend.app.domain.conversations.queries import reduce_session_activity
from backend.app.domain.conversations.timeline import records_from_events
from backend.app.domain.conversations.events import iso_to_epoch_ms
from backend.app.core.time import local_now_iso as now_iso


CANCELLED_ASSISTANT_CONTENT = "生成已取消。"


def interrupted_activity_specifications(events, turn_id: str) -> list[dict[str, Any]]:
    state = reduce_session_activity(events).for_turn(turn_id)
    open_models = {
        call_id: (int(event.data.get("step") or 0), int(event.time))
        for call_id, event in state.models.items()
    }
    open_tools = {
        call_id: (
            str(event.data.get("name") or ""),
            str(event.data.get("tool_call_id") or call_id),
            event.data.get("started_at_ms"),
        )
        for call_id, event in state.tools.items()
    }
    specifications: list[dict[str, Any]] = []
    model_records: dict[str, list[dict[str, Any]]] = {}
    for record in records_from_events(events):
        call_id = str(record.get("call_id") or "")
        if call_id in open_models and record.get("kind") == "model":
            model_records.setdefault(call_id, []).append(record)
    interrupted_at_ms = iso_to_epoch_ms(now_iso())
    for call_id, (step, started_at_ms) in open_models.items():
        records = model_records.get(call_id, [])
        channel_values = {
            str(record.get("channel") or ""): record.get("value") for record in records
        }
        tool_calls = [
            {
                "id": str(record.get("tool_call_id") or ""),
                "type": "function",
                "function": {
                    "name": str(record.get("name") or ""),
                    "arguments": (
                        record.get("arguments")
                        if isinstance(record.get("arguments"), str)
                        else json.dumps(
                            record.get("arguments") or {},
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                },
            }
            for record in sorted(
                (item for item in records if item.get("channel") == "tool_request"),
                key=lambda item: int(item.get("provider_index") or 0),
            )
        ]
        specifications.append(
            {
                "type": "model/result",
                "data": {
                    "turn_id": turn_id,
                    "step": step,
                    "call_id": call_id,
                    "status": "interrupted",
                    "duration_ms": max(0, interrupted_at_ms - started_at_ms),
                    "channel_durations_ms": {
                        str(record.get("channel")): int(record.get("duration_ms") or 0)
                        for record in records
                        if record.get("channel")
                    },
                    "created_at": now_iso(),
                    "result": {
                        "content": str(channel_values.get("content") or ""),
                        "raw_content": str(channel_values.get("raw_output") or ""),
                        "reasoning": str(channel_values.get("reasoning") or ""),
                        "tool_calls": tool_calls,
                        "usage": {},
                        "stop_reason": "cancelled",
                    },
                    "error": {
                        "type": "OperationCancelledError",
                        "code": "CANCELLED",
                        "message": "生成已取消。",
                    },
                },
            }
        )
    for call_id, (name, tool_call_id, _started_at_ms) in open_tools.items():
        specifications.append(
            {
                "type": "tool/result",
                "data": {
                    "turn_id": turn_id,
                    "call_id": call_id,
                    "tool_call_id": tool_call_id,
                    "name": name,
                    "result": None,
                    "status": "interrupted",
                    "error": {
                        "code": "TOOL_OUTCOME_UNKNOWN",
                        "message": "工具结果未知；重试前应核对外部状态。",
                    },
                },
            }
        )
    return specifications

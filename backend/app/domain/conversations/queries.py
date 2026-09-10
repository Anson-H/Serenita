"""从会话事件计算消息、等待输入、有效轮次和未结束活动；不执行读写。"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterable
from backend.app.domain.conversations.events import SessionEvent


def queued_inputs_from_events(
    events: Iterable[SessionEvent],
) -> list[dict[str, Any]]:
    """Project the current waiting-input queue from durable session events."""

    queued: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for event in events:
        data = event.data
        if event.type == "input/queued":
            input_id = str(data.get("input_id") or "")
            if input_id:
                queued.pop(input_id, None)
                queued[input_id] = {
                    **data,
                    "input_id": input_id,
                    "event_seq": event.seq,
                }
            continue
        if event.type == "input/queue-reordered":
            ordered = OrderedDict()
            for input_id in data.get("input_ids") or []:
                if input_id in queued:
                    ordered[input_id] = queued[input_id]
            for input_id, item in queued.items():
                if input_id not in ordered:
                    ordered[input_id] = item
            queued = ordered
            continue
        if event.type == "input/queue-removed":
            queued.pop(str(data.get("input_id") or ""), None)
            continue
        if event.type == "user/message":
            queued.pop(str(data.get("queued_input_id") or ""), None)

    return [
        {**item, "position": position} for position, item in enumerate(queued.values())
    ]


def messages_from_events(events: Iterable[SessionEvent]) -> list[dict[str, Any]]:
    """Project branch-addressable user and assistant surfaces from the log."""
    materialized = list(events)
    messages: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    pending_updates: dict[str, dict[str, Any]] = {}

    for event in materialized:
        data = event.data
        if event.type in {"user/message", "assistant/message"}:
            role = "user" if event.type == "user/message" else "assistant"
            message = {**data, "role": role, "event_seq": event.seq}
            if data.get("branch_addressable") is False:
                continue
            message_id = str(message.get("message_id") or "")
            if not message_id:
                continue
            if message_id in pending_updates:
                message.update(pending_updates.pop(message_id))
            messages.append(message)
            by_id[message_id] = message
            continue

        if event.type in {"user/message-update", "assistant/message-update"}:
            message_id = str(data.get("message_id") or "")
            patch = data.get("patch")
            if not message_id or not isinstance(patch, dict):
                continue
            if message_id in by_id:
                by_id[message_id].update(patch)
            else:
                pending_updates.setdefault(message_id, {}).update(patch)
            continue

    messages.sort(key=lambda item: int(item.get("event_seq") or 0))
    return messages


def current_session_turn_ids(events: Iterable[SessionEvent]) -> set[str]:
    """Return Turn ids not superseded by a later retry or edit."""

    materialized = list(events)
    started = {
        str(event.data.get("turn_id") or "")
        for event in materialized
        if event.type == "turn/start" and event.data.get("turn_id")
    }
    if not started:
        started = {
            str(event.data.get("turn_id") or "")
            for event in materialized
            if event.data.get("turn_id")
        }
    superseded = {
        str(event.data.get("supersedes_turn_id") or "")
        for event in materialized
        if event.type == "turn/start" and event.data.get("supersedes_turn_id")
    }
    return {turn_id for turn_id in started - superseded if turn_id}


@dataclass
class TurnActivity:
    steps: dict[int, SessionEvent] = field(default_factory=dict)
    models: dict[str, SessionEvent] = field(default_factory=dict)
    tools: dict[str, SessionEvent] = field(default_factory=dict)


@dataclass
class SessionActivity:
    open_turn_id: str | None = None
    turns: dict[str, TurnActivity] = field(default_factory=dict)

    def for_turn(self, turn_id: str) -> TurnActivity:
        return self.turns.get(turn_id, TurnActivity())


def reduce_session_activity(events: Iterable[SessionEvent]) -> SessionActivity:
    """归约未结束活动，供取消与存储恢复分别决定如何收尾。"""
    result = SessionActivity()
    for event in events:
        data = event.data
        turn_id = str(data.get("turn_id") or "")
        if not turn_id:
            continue
        state = result.turns.setdefault(turn_id, TurnActivity())
        call_id = str(data.get("call_id") or "")
        step = int(data.get("step") or 0)
        if event.type == "turn/start":
            result.open_turn_id = turn_id
        elif event.type == "turn/end":
            result.open_turn_id = None
        elif event.type == "step/start":
            state.steps[step] = event
        elif event.type == "step/end":
            state.steps.pop(step, None)
        elif event.type == "request/header":
            state.models[call_id] = event
        elif event.type == "model/result":
            state.models.pop(call_id, None)
        elif event.type == "tool/call":
            state.tools[call_id] = event
        elif event.type == "tool/result":
            state.tools.pop(call_id, None)
    return result

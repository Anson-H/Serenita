"""按轮次分发新事件并提供时间线查询；完整读取也使用同一增量投影器。"""

from __future__ import annotations
from typing import Any, Iterable
from backend.app.domain.conversations.events import SessionEvent
from backend.app.domain.conversations.queries import current_session_turn_ids
from backend.app.domain.conversations.timeline_state import TurnTimelineState


class ConversationTimelineProjector:
    def __init__(self, events: Iterable[SessionEvent] = ()) -> None:
        self._turns: dict[str, TurnTimelineState] = {}
        self._turn_by_message_id: dict[str, str] = {}
        self._records_by_id: dict[str, dict[str, Any]] = {}
        self.apply_events(events)

    def _event_turn_id(self, event: SessionEvent) -> str:
        turn_id = str(event.data.get("turn_id") or "")
        if turn_id:
            return turn_id
        return self._turn_by_message_id.get(str(event.data.get("message_id") or ""), "")

    def apply_events(self, events: Iterable[SessionEvent]) -> set[str]:
        routed = []
        touched = {}
        for event in events:
            turn_id = self._event_turn_id(event)
            message_id = str(event.data.get("message_id") or "")
            if (
                event.type in {"user/message", "assistant/message"}
                and message_id
                and turn_id
            ):
                self._turn_by_message_id[message_id] = turn_id
            state = (
                self._turns.setdefault(turn_id, TurnTimelineState())
                if turn_id not in self._turns
                else self._turns[turn_id]
            )
            routed.append((state, event))
            touched[turn_id] = state
            if event.type == "request/header":
                state.register_header(event)
        for state, event in routed:
            state.apply_event(event)
        changed = set()
        for state in touched.values():
            for record in state.new_records:
                self._records_by_id[record["record_id"]] = record
            state.new_records.clear()
            changed.update(state.changed)
            for record_id in state.changed:
                self._records_by_id[record_id] = state.records[record_id]
            state.changed.clear()
        return changed

    def records(self) -> list[dict[str, Any]]:
        return sorted(
            self._records_by_id.values(), key=lambda record: int(record.get("seq") or 0)
        )

    def records_for_turn(self, turn_id: str) -> list[dict[str, Any]]:
        state = self._turns.get(turn_id)
        return (
            sorted(
                state.records.values(), key=lambda record: int(record.get("seq") or 0)
            )
            if state
            else []
        )

    def records_for_ids(self, record_ids: Iterable[str]) -> list[dict[str, Any]]:
        return sorted(
            (
                self._records_by_id[key]
                for key in set(record_ids)
                if key in self._records_by_id
            ),
            key=lambda record: int(record.get("seq") or 0),
        )


def records_from_events(events: Iterable[SessionEvent]) -> list[dict[str, Any]]:
    """Project the durable log as one flat, truthful execution timeline."""
    return ConversationTimelineProjector(events).records()


def active_records(
    records: Iterable[dict[str, Any]], events: Iterable[SessionEvent]
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
                    {**record, "turn_id": active_user_turn_by_id[str(message_id)]}
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

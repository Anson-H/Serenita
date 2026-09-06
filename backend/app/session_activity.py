"""Pure reduction of unfinished activity; callers choose cancellation/recovery policy."""

from dataclasses import dataclass, field
from typing import Iterable
from backend.app.session_events import SessionEvent


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

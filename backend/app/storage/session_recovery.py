from typing import Iterable
from backend.app.domain.conversations.queries import reduce_session_activity
from backend.app.domain.conversations.events import SessionEvent, event_now_ms, make_event


def interrupted_turn_closers(events: Iterable[SessionEvent]) -> list[SessionEvent]:
    materialized = list(events)
    activity = reduce_session_activity(materialized)
    open_turn = activity.open_turn_id
    state = activity.for_turn(open_turn or "")
    last_step = next(reversed(state.steps.values()), None)
    open_step = (
        (str(last_step.data["turn_id"]), int(last_step.data["step"]))
        if last_step
        else None
    )
    open_tools = {
        call_id: (
            str(event.data["turn_id"]),
            str(event.data["name"]),
            str(event.data["tool_call_id"]),
        )
        for call_id, event in state.tools.items()
    }

    if open_turn is None:
        return []
    seq = len(materialized)
    timestamp = event_now_ms()
    closers: list[SessionEvent] = []
    for call_id, (turn_id, name, tool_call_id) in open_tools.items():
        closers.append(
            make_event(
                "tool/result",
                seq,
                {
                    "turn_id": turn_id,
                    "call_id": call_id,
                    "tool_call_id": tool_call_id,
                    "name": name,
                    "result": None,
                    "status": "interrupted",
                    "error": {
                        "code": "TOOL_OUTCOME_UNKNOWN",
                        "message": "工具调用结果未知；重试前应先核对外部状态。",
                    },
                },
                timestamp=timestamp,
            )
        )
        seq += 1
    if open_step is not None:
        closers.append(
            make_event(
                "step/end",
                seq,
                {
                    "turn_id": open_step[0],
                    "step": open_step[1],
                    "status": "interrupted",
                },
                timestamp=timestamp,
            )
        )
        seq += 1
    closers.append(
        make_event(
            "turn/end",
            seq,
            {"turn_id": open_turn, "reason": {"kind": "interrupted"}},
            timestamp=timestamp,
        )
    )
    return closers

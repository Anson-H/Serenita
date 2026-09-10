"""校验工具调用对应关系，完整且幂等地保存已执行工具的结果与影响。"""

from backend.app.core.member_lifecycle import (
    member_lifecycle_guard,
)
from typing import Any


from backend.app.core.errors import raise_error
from backend.app.core.cancellation import (
    CancellationToken,
)
from backend.app.core.time import local_now_iso


now_iso = local_now_iso


class ConversationToolResults:
    def __init__(self, repository, events, task_state, paths, guard):
        self.repository = repository
        self.events = events
        self.task_state = task_state
        self.paths = paths
        self.guard = guard

    def persist(
        self,
        account_id: str,
        turn,
        payload: dict[str, Any],
        *,
        failed: bool,
        cancellation_token: CancellationToken | None = None,
    ) -> bool:
        """Finalize an existing call once, including after cancellation."""
        session_id, turn_id = str(turn["session_id"]), str(turn["turn_id"])
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            self.guard.member_access(account_id, session_id)
            if failed:
                details = (payload.get("error") or {}).get("details") or {}
                if details.get("execution_completed") is not True:
                    self.guard.ensure_active(account_id, turn, cancellation_token)
            view = self.events.view(account_id, session_id)
            events = view.events
            users, call_events, result_events = view.tool_event_index
            identity = {
                "turn_id": turn_id,
                "call_id": str(payload.get("call_id") or ""),
                "tool_call_id": str(payload.get("tool_call_id") or ""),
                "name": str(payload.get("tool") or ""),
            }
            calls = [
                event
                for event in call_events.get(identity["call_id"], [])
                if all(event.data.get(key) == value for key, value in identity.items())
            ]
            if not all(identity.values()) or len(calls) != 1 or turn_id not in users:
                raise_error(
                    "conflict",
                    "TOOL_RESULT_CALL_MISMATCH",
                    "工具结果没有匹配的既有工具调用。",
                )
            data = {
                **identity,
                "step": calls[0].data.get("step", 0),
                "result": payload.get("output"),
                "status": "failed" if failed else "completed",
                **({"error": payload.get("error")} if failed else {}),
            }
            previous = next(
                (
                    event
                    for event in reversed(result_events.get(identity["call_id"], []))
                    if event.data.get("turn_id") == turn_id
                ),
                None,
            )
            specification: dict[str, Any] = {
                "type": "tool/result",
                "data": {**data, "created_at": now_iso()},
                "surface_op": "append",
            }
            if previous is not None:
                if all(previous.data.get(key) == value for key, value in data.items()):
                    return False
                if not (
                    all(
                        previous.data.get(key) == value
                        for key, value in identity.items()
                    )
                    and previous.data.get("status") == "interrupted"
                    and previous.data.get("result") is None
                    and (previous.data.get("error") or {}).get("code")
                    == "TOOL_OUTCOME_UNKNOWN"
                ):
                    raise_error(
                        "conflict",
                        "TOOL_RESULT_CONFLICT",
                        "该工具调用已保存不同的结果。",
                    )
                specification.update(
                    source_event_seqs=[previous.seq],
                    surface_op={
                        "op": "replace",
                        "start": previous.seq,
                        "end": previous.seq + 1,
                    },
                )
            self.repository.append_session_events(
                account_id,
                session_id,
                [specification],
                expected_seq=events[-1].seq + 1,
            )
            return True

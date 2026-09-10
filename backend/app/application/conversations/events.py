"""维护会话事件读取视图与增量索引，定位消息、技能和工具观测。"""

from collections import OrderedDict
from copy import deepcopy
from functools import cached_property
from threading import RLock

from backend.app.domain.conversations.timeline import active_records, records_from_events
from backend.app.core.tabular_json import decode_tabular_json
from backend.app.domain.conversations.queries import (
    messages_from_events,
    queued_inputs_from_events,
)


class SessionView:
    def __init__(self, stored):
        self.events = stored.events if stored else ()
        self.revision = stored.revision if stored else None

    @cached_property
    def records(self):
        return active_records(records_from_events(self.events), self.events)

    @cached_property
    def messages(self):
        return {
            message["message_id"]: message
            for message in messages_from_events(self.events)
        }

    @cached_property
    def queued(self):
        return queued_inputs_from_events(self.events)

    @cached_property
    def fork_available(self):
        return any(event.type == "turn/end" for event in self.events)

    @cached_property
    def tool_event_index(self):
        users, calls, results = {}, {}, {}
        for event in self.events:
            data = event.data
            if event.type == "turn/start":
                users[data.get("turn_id")] = data.get("user_message_id")
            elif event.type == "tool/call":
                calls.setdefault(data.get("call_id"), []).append(event)
            elif event.type == "tool/result":
                results.setdefault(data.get("call_id"), []).append(event)
        return users, calls, results

    @cached_property
    def tool_index(self):
        users, calls, results = self.tool_event_index
        return (
            users,
            {key: [event.data for event in items] for key, items in calls.items()},
            {key: [event.data for event in items] for key, items in results.items()},
        )

    @cached_property
    def model_steps(self):
        steps = {}
        for event in self.events:
            if event.type == "step/start":
                turn = str(event.data.get("turn_id") or "")
                steps[turn] = max(steps.get(turn, 0), int(event.data.get("step") or 0))
        return steps

    def observation(self, *, call_id, allowed_tools, session_id, visible_message_ids):
        users, calls, results = self.tool_index
        call = next(
            (
                data
                for data in reversed(calls.get(call_id, []))
                if data.get("name") in allowed_tools
                and users.get(data.get("turn_id")) in visible_message_ids
            ),
            None,
        )
        if call is None:
            return None
        result = next(
            (
                data
                for data in reversed(results.get(call_id, []))
                if all(
                    data.get(key) == call.get(key)
                    for key in ("turn_id", "tool_call_id", "name")
                )
                and (
                    data.get("status") == "completed"
                    or ((data.get("error") or {}).get("details") or {}).get(
                        "execution_completed"
                    )
                    is True
                )
            ),
            None,
        )
        raw = result.get("result") if result else None
        if not isinstance(raw, dict):
            return None
        output = raw.get("output")
        if raw.get("type") != "tool_result" or not isinstance(output, dict):
            output = raw
        return {
            "call_id": call_id,
            "tool_name": call["name"],
            "session_id": session_id,
            "source_message_id": users[call["turn_id"]],
            "output": decode_tabular_json(deepcopy(output)),
        }


class ConversationEvents:
    """Read on demand. Any append, branch edit or replaced file changes the revision."""

    def __init__(self, repository):
        self.repository = repository
        self.cache = OrderedDict()
        self.lock = RLock()
        self.cached_bytes = 0

    def reader(self, account_id, session_id):
        """Retain one request's snapshot even when it exceeds the shared cache limit."""
        current = None

        def read():
            nonlocal current
            revision = self.repository.session_event_revision(account_id, session_id)
            if current is None or current.revision != revision:
                current = self.view(account_id, session_id)
            return current

        return read

    def current_model_step(self, account_id, turn):
        return self.view(account_id, turn["session_id"]).model_steps.get(
            str(turn["turn_id"]), 0
        )

    def view(self, account_id, session_id):
        key = (account_id, session_id)
        with self.lock:
            revision = self.repository.session_event_revision(account_id, session_id)
            previous = self.cache.get(key)
            if previous and previous[0].revision == revision:
                self.cache.move_to_end(key)
                return previous[0]
            stored = self.repository.session_event_snapshot(account_id, session_id)
            view = SessionView(stored)
            if previous:
                self.cached_bytes -= self.cache.pop(key)[1]
            try:
                size = int(str(view.revision).split(":")[-2])
            except (ValueError, IndexError):
                size = sum(len(str(event.data)) for event in view.events)
            if size <= 8 * 1024 * 1024:
                self.cache[key] = (view, size)
                self.cached_bytes += size
                while len(self.cache) > 24 or self.cached_bytes > 8 * 1024 * 1024:
                    _, (_, removed_size) = self.cache.popitem(last=False)
                    self.cached_bytes -= removed_size
            return view

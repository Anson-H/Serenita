from types import SimpleNamespace

from backend.app.application.conversations.events import ConversationEvents
from backend.app.domain.conversations.events import make_event


def test_tool_lookup_indexes_once_and_rechecks_visibility_after_append_and_replace():
    events = [
        make_event("turn/start", 0, {"turn_id": "turn", "user_message_id": "user", "stream_id": "stream"})
    ]
    for index in range(2000):
        identity = {
            "turn_id": "turn",
            "call_id": f"call-{index}",
            "tool_call_id": f"tool-{index}",
            "name": "read_report_information",
        }
        events.append(
            make_event("tool/call", len(events), {**identity, "arguments": {}})
        )
        events.append(
            make_event(
                "tool/result",
                len(events),
                {
                    **identity,
                    "status": "completed",
                    "result": {"output": {"value": index}, "type": "tool_result"},
                },
            )
        )

    class Repository:
        reads = 0
        revision = "first"

        def session_event_revision(self, account, session):
            return self.revision

        def session_event_snapshot(self, account, session):
            self.reads += 1
            return SimpleNamespace(events=tuple(events), revision=self.revision)

    repository = Repository()
    query = ConversationEvents(repository)
    assert repository.reads == 0
    arguments = {
        "call_id": "call-1999",
        "allowed_tools": {"read_report_information"},
        "session_id": "session",
        "visible_message_ids": {"user"},
    }
    for _ in range(100):
        result = query.view("actor", "session").observation(**arguments)
        assert result["output"] == {"value": 1999}
        result["output"]["value"] = -1
    assert repository.reads == 1
    assert (
        query.view("actor", "session").observation(
            **{**arguments, "visible_message_ids": set()}
        )
        is None
    )
    assert (
        query.view("actor", "session").observation(
            **{**arguments, "allowed_tools": {"delete_report"}}
        )
        is None
    )
    identity = {
        "turn_id": "turn",
        "call_id": "call-1999",
        "tool_call_id": "tool-1999",
        "name": "read_report_information",
    }
    events.append(
        make_event(
            "tool/result",
            len(events),
            {**identity, "status": "completed", "result": {"value": "new"}},
        )
    )
    repository.revision = "appended"
    assert (
        query.view("actor", "session").observation(**arguments)["output"]["value"]
        == "new"
    )
    assert repository.reads == 2
    events.clear()
    repository.revision = "replaced"
    assert query.view("actor", "session").observation(**arguments) is None
    assert repository.reads == 3
    print({"event_count": 4001, "repeated_lookups": 100, "snapshot_reads": 1})


def test_large_session_request_reader_retains_snapshot_without_global_cache():
    class Repository:
        reads = 0
        revision = "inode:12000000:1"

        def session_event_revision(self, account, session):
            return self.revision

        def session_event_snapshot(self, account, session):
            self.reads += 1
            return SimpleNamespace(events=(), revision=self.revision)

    repository = Repository()
    events = ConversationEvents(repository)
    reader = events.reader("account", "session")
    assert repository.reads == 0
    for _ in range(100):
        reader()
    assert repository.reads == 1 and not events.cache
    repository.revision = "inode:12000000:2"
    reader()
    assert repository.reads == 2

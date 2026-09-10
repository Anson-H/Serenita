"""Automatic reads keep progress outside context and audit every complete page."""
import json
import pytest

from backend.app.agent_runtime.context import AgentContext
from backend.app.agent_runtime.model_types import AssistantModelOutput, ToolCall
from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.agent_runtime.tools.pagination import automatic_pages
from backend.app.core.cancellation import OperationCancelledError
from backend.app.core.tabular_json import decode_tabular_json
from tests.agent_support import HarnessDriver, assert_native_pairs, call, runtime


class ReadPages(Tool):
    name = "read_pages"
    model_exposure = "direct"
    input_schema = {"type": "object", "properties": {"query": {"type": "string"}}, "additionalProperties": False}

    def __init__(self, count=5, fail_at=None):
        self.count, self.fail_at = count, fail_at
        self.loaded = []
        self.calls = 0

    def run(self, arguments):
        self.calls += 1
        query = arguments.get("query")

        def load(cursor):
            page = cursor or 0
            if page == self.fail_at:
                raise ValueError("page unavailable")
            self.loaded.append((page, query))
            return ToolResult(self.name, {
                "items": [{"id": page, "fact": f"fact-{page}"}], "total": self.count,
                "next_cursor": page + 1 if page + 1 < self.count else None,
            })
        return automatic_pages(load)


def run_read(tool, **callbacks):
    driver = HarnessDriver(call("read", tool.name, query="sleep"), AssistantModelOutput(content="done"))
    harness = runtime(tools=[tool])
    harness.max_actions = 2
    result = harness.execute(
        AgentContext(account_id="alice", member_id="alice-member", task_type="conversation"),
        derive_messages=driver.derive, complete_model=driver.complete, on_event=driver.record,
        **callbacks,
    )
    return result, driver


def test_harness_reads_all_pages_without_model_cursor_or_extra_model_actions():
    tool = ReadPages(count=6)
    result, driver = run_read(tool)
    assert len(driver.requests) == 2 and tool.calls == 1
    assert tool.loaded == [(page, "sleep") for page in range(6)]
    assert [entry["output"]["items"][0]["id"] for entry in result.output["tool_results"]] == list(range(6))
    assert result.output["tool_results"][-1]["output"]["pagination"] == {"page": 6, "complete": True}
    assert all("next_cursor" not in item["output"] for item in result.output["tool_results"])
    calls = [event for event in result.events if event.type == "tool_call"]
    assert len({event.payload["call_id"] for event in calls}) == 6
    assert all(event.payload["arguments"] == {"query": "sleep"} for event in calls)
    assert all(event.payload["pagination"]["root_call_id"] == "read" for event in calls[1:])
    assert_native_pairs(driver.messages)


def test_pagination_failure_preserves_completed_pages_and_stops_following_reads():
    tool = ReadPages(count=6, fail_at=2)
    result, driver = run_read(tool)
    assert tool.loaded == [(0, "sleep"), (1, "sleep")]
    assert len(result.output["tool_results"]) == 2
    assert all(not item["output"]["pagination"]["complete"] for item in result.output["tool_results"])
    error = next(event for event in result.events if event.type == "tool_error")
    assert "page unavailable" in error.payload["error"]["message"]
    assert error.payload["error"]["details"]["pagination"] == {"root_call_id": "read", "page": 3, "complete": False}
    assert_native_pairs(driver.messages)


def test_pagination_never_interleaves_a_new_call_into_an_unfinished_parallel_group():
    tool = ReadPages(count=3)
    driver = HarnessDriver(
        AssistantModelOutput(tool_calls=(ToolCall("a", tool.name, {}), ToolCall("b", tool.name, {}))),
        AssistantModelOutput(content="done"),
    )
    result = runtime(tools=[tool]).execute(
        AgentContext(account_id="alice", member_id="alice-member", task_type="conversation"),
        derive_messages=driver.derive, complete_model=driver.complete, on_event=driver.record,
    )
    assert len(result.output["tool_results"]) == 6
    assert_native_pairs(driver.messages)


def test_cancellation_before_next_page_does_not_read_it():
    tool = ReadPages()
    driver = HarnessDriver(call("read", tool.name), AssistantModelOutput(content="done"))

    def active():
        if tool.loaded:
            raise OperationCancelledError("cancelled")

    with pytest.raises(OperationCancelledError):
        runtime(tools=[tool]).execute(
            AgentContext(account_id="alice", member_id="alice-member", task_type="conversation"),
            derive_messages=driver.derive, complete_model=driver.complete, on_event=driver.record,
            before_model_request=active,
        )
    assert tool.loaded == [(0, None)]
    assert_native_pairs(driver.messages)


def test_compaction_between_pages_preserves_query_progress():
    tool = ReadPages(count=8)
    driver = HarnessDriver(call("read", tool.name, query="sleep"), AssistantModelOutput(content="done"))
    compressed = []

    def estimate(request):
        return 20 + 20 * sum(message["role"] == "tool" for message in request.messages)

    def prepare(request, rebuild, force=False):
        if estimate(request) < 80:
            return request
        # Emulate a checkpoint consuming old complete pairs; the current page
        # and next cursor live in the Harness, not in this model history.
        old = driver.messages[1:5]
        assert_native_pairs(old)
        compressed.extend(decode_tabular_json(json.loads(item["content"])["output"])["items"][0]["id"] for item in old if item["role"] == "tool")
        driver.messages = [driver.messages[0], *driver.messages[5:]]
        return rebuild(messages=driver.derive(), skill_names=[])

    result = runtime(tools=[tool]).execute(
        AgentContext(account_id="alice", member_id="alice-member", task_type="conversation"),
        derive_messages=driver.derive, complete_model=driver.complete, on_event=driver.record,
        prepare_request=prepare, before_tool_result=lambda request, rebuild: prepare(request, rebuild),
        estimate_request_tokens=estimate, context_window_tokens=110, reserved_output_tokens=10,
    )
    assert compressed
    assert tool.loaded == [(page, "sleep") for page in range(8)]
    assert len(result.output["tool_results"]) == 8 and len(driver.requests) == 2
    assert_native_pairs(driver.messages)


@pytest.mark.parametrize("next_field,position", [("next_cursor", "same"), ("next_offset", 2)])
def test_repeated_pagination_position_is_rejected(next_field, position):
    first = automatic_pages(lambda _: ToolResult("read", {next_field: position}), next_field=next_field)
    second = first.next_page()
    assert not second.output["pagination"]["complete"]
    with pytest.raises(ValueError, match="重复"):
        second.next_page()


def test_automatic_page_limit_stops_before_fetching_extra_data():
    loads = []
    def load(cursor):
        loads.append(cursor)
        return ToolResult("read", {"next_cursor": (cursor or 0) + 1})
    first = automatic_pages(load, max_pages=1)
    with pytest.raises(ValueError, match="上限"):
        first.next_page()
    assert loads == [None]


def test_oversized_page_stops_before_reading_later_pages():
    tool = ReadPages(count=5)
    def estimate(request):
        for message in request.messages:
            if message.get("role") == "tool":
                data = json.loads(message["content"])
                output = decode_tabular_json(data.get("output"))
                if output and output.get("items", [{}])[0].get("id") == 1:
                    return 1000
        return 20
    result, driver = run_read(tool, estimate_request_tokens=estimate, context_window_tokens=100, reserved_output_tokens=10)
    assert tool.loaded == [(0, "sleep"), (1, "sleep")]
    error = next(event for event in result.events if event.type == "tool_error")
    assert error.payload["error"]["code"] == "TOOL_RESULT_TOO_LARGE"
    assert error.payload["error"]["details"]["pagination"] == {"page": 2, "complete": False}
    assert not result.output["tool_results"][-1]["output"]["pagination"]["complete"]
    assert_native_pairs(driver.messages)

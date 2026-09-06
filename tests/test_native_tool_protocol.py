import json
import pytest
from backend.app.agent_runtime.model_types import AssistantModelOutput, ModelRequest, ModelStreamChunk, ToolCall, ToolSchema
from backend.app.application.model_provider_service import ModelProviderService
from backend.app.providers.base import ModelProvider
from backend.app.providers.errors import ProviderChatCompletionError


TOOL = ToolSchema(
    name="lookup_report",
    description="Read one report.",
    parameters={
        "type": "object",
        "properties": {"report_id": {"type": "string"}},
        "required": ["report_id"],
        "additionalProperties": False,
    },
)


class Response:
    status = 200

    def __init__(self, body=None, lines=()):
        self.body = body
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.body).encode("utf-8")

    def __iter__(self):
        return iter(self.lines)


def request_with_tool():
    return ModelRequest.build(
        system="system",
        messages=[{"role": "user", "content": "read it"}],
        tools=[TOOL],
        tool_choice="auto",
        model_config={"purpose": "agent_action"},
    )


def test_native_non_stream_request_sends_schema_and_accepts_empty_tool_call_content():
    seen = {}

    def urlopen(request, timeout):
        seen["payload"] = json.loads(request.data)
        return Response(
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup_report",
                                        "arguments": '{"report_id":"r1"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            }
        )

    result = ModelProvider(urlopen=urlopen).complete_chat(
        api_url="https://example.test/v1",
        api_key="secret",
        remote_model_id="model",
        model_request=request_with_tool(),
    )
    assert seen["payload"]["tools"] == [TOOL.as_dict()]
    assert seen["payload"]["tool_choice"] == "auto"
    assert result.content == ""
    assert result.stop_reason == "tool_calls"
    assert result.tool_calls == (
        ToolCall(id="call_1", name="lookup_report", arguments={"report_id": "r1"}),
    )


def test_native_stream_preserves_fragmented_multiple_tool_calls_by_index():
    lines = [
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"lookup_","arguments":"{\\\"report"}},{"index":1,"id":"c2","function":{"name":"lookup_report","arguments":"{\\\"report_id\\\":\\\"r2\\\"}"}}]},"finish_reason":null}]}\n\n',
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"report","arguments":"_id\\\":\\\"r1\\\"}"}}]},"finish_reason":"tool_calls"}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    chunks = list(
        ModelProvider(urlopen=lambda _request, timeout: Response(lines=lines)).stream_chat(
            api_url="https://example.test/v1",
            api_key="secret",
            remote_model_id="model",
            model_request=request_with_tool(),
        )
    )
    parts = {}
    for chunk in chunks:
        for delta in chunk.tool_call_deltas:
            part = parts.setdefault(delta.index, {"id": "", "name": "", "arguments": ""})
            part["id"] = delta.id or part["id"]
            part["name"] += delta.name_delta
            part["arguments"] += delta.arguments_delta
    assert parts == {
        0: {
            "id": "c1",
            "name": "lookup_report",
            "arguments": '{"report_id":"r1"}',
        },
        1: {
            "id": "c2",
            "name": "lookup_report",
            "arguments": '{"report_id":"r2"}',
        },
    }
    assert chunks[-1].stop_reason == "tool_calls"


def test_text_fallback_maps_to_same_internal_tool_call_and_translates_history():
    logical = ModelRequest.build(
        system="system",
        messages=[
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    ToolCall(
                        id="old",
                        name="lookup_report",
                        arguments={"report_id": "r0"},
                    ).as_dict()
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "old",
                "name": "lookup_report",
                "content": '{"status":"completed"}',
            },
        ],
        tools=[TOOL],
    )
    wire = ModelProviderService.prepare_transport_request(
        {"supports_tool_calling": False}, logical, "default"
    )
    assert wire.transport_mode == "text_tool"
    assert wire.tools == ()
    assert "TEXT_TOOL_PROTOCOL" in wire.system
    assert wire.messages[1]["role"] == "user"
    assert str(wire.messages[1]["content"]).startswith(
        "TOOL_OBSERVATION"
    )

    result = ModelProviderService._transport_result(
        wire,
        logical,
        AssistantModelOutput(
            content='{"type":"tool_call","name":"lookup_report",'
            '"arguments":{"report_id":"r1"}}'
        ),
    )
    assert result.tool_calls[0].name == "lookup_report"
    assert result.tool_calls[0].arguments == {"report_id": "r1"}
    assert result.stop_reason == "tool_calls"


def test_text_fallback_stream_keeps_raw_json_separate_from_parsed_final():
    chunks = list(
        ModelProviderService._stream_text_tool_result(
            [
                ModelStreamChunk(content_delta='{"type":"final",'),
                ModelStreamChunk(content_delta='"content":"answer"}', stop_reason="stop"),
            ]
        )
    )
    assert "".join(item.raw_content_delta for item in chunks) == (
        '{"type":"final","content":"answer"}'
    )
    assert "".join(item.content_delta for item in chunks) == "answer"


@pytest.mark.parametrize(
    "value",
    [
        "not json",
        '```json\n{"type":"final","content":"answer"}\n```',
        '{"type":"final","content":""}',
        '{"type":"tool_call","name":"lookup_report","arguments":[]}',
        '{"type":"other"}',
    ],
)
def test_text_fallback_rejects_invalid_protocol_outputs(value):
    with pytest.raises(ProviderChatCompletionError, match="文本工具协议"):
        ModelProviderService._parse_text_tool_output(value)

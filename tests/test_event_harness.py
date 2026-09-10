from backend.app.application.conversations.compaction import ConversationCompaction
from backend.app.application.conversations.request_audit import ModelRequestAudit
from backend.app.application.conversations.sse import ConversationSSESubscriber
from tests.model_support import CompactCatalog
from backend.app.application.conversations.presenter import record_response
from member_support import account_id as account_id_for, member_id
import base64
import json
import pytest
from backend.app.agent_runtime.model_types import ModelRequest, PromptContextSection, ToolSchema
from backend.app.application.conversations.service import ConversationService
from backend.app.application.model_provider_service import ModelProviderService, PreparedProviderRequest
from backend.app.domain.conversations.timeline import ConversationTimelineProjector, active_records, records_from_events
from backend.app.domain.conversations.model_history import derive_model_messages, visible_loaded_skill_names
from backend.app.domain.conversations.queries import messages_from_events
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.providers.base import ModelProvider
from backend.app.domain.conversations.events import SessionEvent, SessionEventCorruptionError, SessionHeader
from backend.app.storage.session_recovery import interrupted_turn_closers
from backend.app.storage.session_persistence import JsonlSessionPersistence


def event(event_type, seq, data, surface_op=None, *, source_event_seqs=None):
    return SessionEvent(
        type=event_type,
        seq=seq,
        time=1000 + seq,
        data=data,
        surface_op=surface_op,
        source_event_seqs=source_event_seqs,
    )


def test_session_header_has_one_versioned_contract():
    immutable_id = "00000000-0000-4000-8000-000000000001"
    assert SessionHeader(id="s", account_id=immutable_id, created_at=1).to_record() == {
        "type": "session",
        "version": 2,
        "id": "s",
        "accountId": immutable_id,
        "createdAt": 1,
    }


def test_request_header_rejects_duplicate_logical_model_input_fields():
    with pytest.raises(SessionEventCorruptionError, match="duplicate logical model input"):
        SessionEvent.from_record(
            {
                "type": "request/header",
                "seq": 0,
                "time": 1,
                "data": {
                    "turn_id": "turn-1",
                    "step": 1,
                    "call_id": "call-1",
                    "purpose": "agent_action",
                    "header": {
                        "provider_payload": {
                            "model": "model",
                            "messages": [],
                            "stream": True,
                        },
                        "messages": [],
                    },
                },
            }
        )


def test_provider_native_image_binary_is_not_estimated_as_prompt_text():
    image_bytes = 3 * 1024 * 1024
    request = ModelRequest.build(
        system="system",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请阅读附件"},
                    {
                        "type": "image",
                        "mime_type": "image/jpeg",
                        "name": "report.jpg",
                        "data_base64": base64.b64encode(b"x" * image_bytes).decode(
                            "ascii"
                        ),
                    },
                ],
            }
        ],
        model_config={"purpose": "agent_action", "max_output_tokens": 65_536},
    )

    estimated = ConversationCompaction.estimate_model_request_tokens(request)

    available_input = 1_000_000 - 65_536
    assert 10_000 < estimated < available_input * 0.8


def test_turn_mode_temporarily_switches_only_when_the_other_state_fully_matches():
    service = ConversationService(repository=object(), model_catalog=object())
    model = {
        "thinking_modes": ["default", "off", "high", "max"],
        "capability_profiles": {
            "default_state": "thinking",
            "non_thinking": {
                "availability": "available",
                "supports_text": True,
                "supports_tool_calling": True,
                "file_mime_types": ["image/png"],
            },
            "thinking": {
                "availability": "available",
                "supports_text": True,
                "supports_tool_calling": False,
                "file_mime_types": ["image/png"],
            },
        },
    }

    assert service.inputs.effective_thinking_mode_for_turn(
        model,
        "max",
        has_tools=True,
        attachment_parts=[{"type": "image", "mime_type": "image/png"}],
    ) == ("off", ["tool_calling"])

    model["capability_profiles"]["non_thinking"]["file_mime_types"] = []
    assert service.inputs.effective_thinking_mode_for_turn(
        model,
        "max",
        has_tools=True,
        attachment_parts=[{"type": "image", "mime_type": "image/png"}],
    ) == ("max", [])


def test_turn_mode_switches_from_fast_to_the_models_default_thinking_state():
    service = ConversationService(repository=object(), model_catalog=object())
    model = {
        "thinking_modes": ["default", "off", "low", "max"],
        "capability_profiles": {
            "default_state": "thinking",
            "non_thinking": {
                "availability": "available",
                "supports_text": True,
                "supports_tool_calling": False,
                "file_mime_types": [],
            },
            "thinking": {
                "availability": "available",
                "supports_text": True,
                "supports_tool_calling": True,
                "file_mime_types": [],
            },
        },
    }

    assert service.inputs.effective_thinking_mode_for_turn(
        model,
        "off",
        has_tools=True,
        attachment_parts=[],
    ) == ("default", ["tool_calling"])


def test_thinking_mode_changed_event_requires_and_streams_the_real_mode_change():
    changed = event(
        "turn/thinking_mode_changed",
        1,
        {
            "turn_id": "turn-1",
            "requested_mode": "max",
            "effective_mode": "off",
            "reasons": ["tool_calling"],
        },
    )
    assert ConversationSSESubscriber.thinking_mode_events_for_turn(
        [changed], "turn-1"
    ) == [changed]
    payload = ConversationSSESubscriber.thinking_mode_changed_stream_event(
        {"session_id": "session-1", "turn_id": "turn-1"},
        changed.data,
    )
    assert "event: thinking_mode_changed" in payload
    assert '"requested_mode": "max"' in payload
    assert '"effective_mode": "off"' in payload


def test_provider_payload_redaction_removes_all_attachment_binary_shapes():
    redacted = ModelRequestAudit.redact_provider_payload(
        {
            "messages": [
                {
                    "content": [
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                        {"type": "input_audio", "input_audio": {"data": "BBBB", "format": "mp3"}},
                        {"type": "file", "file": {"file_data": "data:application/pdf;base64,CCCC"}},
                    ]
                }
            ]
        }
    )
    serialized = json.dumps(redacted)
    assert "AAAA" not in serialized
    assert "BBBB" not in serialized
    assert "CCCC" not in serialized
    assert serialized.count("attachment-binary-redacted") == 3


def test_loaded_skill_message_is_a_historical_tool_result_context_record(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "skill-context"))
    service = ConversationService(
        repository=ConversationRepository(JsonlSessionPersistence()),
        model_catalog=object(),
    )
    skill_text = "# 医疗报告导入\n\n完整 report-import 指令"
    model_request = ModelRequest.build(
        system="system\n\nSKILL_CATALOG\nreport-query",
        messages=[
            {"role": "user", "content": "导入附件"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "load-1",
                        "type": "function",
                        "function": {
                            "name": "load_skill",
                            "arguments": '{"name":"report-import"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "load-1",
                "name": "load_skill",
                "content": skill_text,
            },
        ],
        tools=[
            ToolSchema(
                name="load_skill",
                parameters={"type": "object"},
            )
        ],
        context_sections=[
            PromptContextSection(
                context_type="system_prompt",
                label="系统提示词",
                content="system",
            ),
            PromptContextSection(
                context_type="skill_catalog",
                label="1 个可用技能",
                content="SKILL_CATALOG\nreport-query",
            ),
        ],
        model_config={"purpose": "agent_action"},
    )

    model = {
        "model_id": "model-1",
        "provider_id": "test",
        "remote_model_id": "test-model",
        "model_name": "Test Model",
        "supports_tool_calling": True,
    }
    provider = ModelProvider()
    transport_request = ModelProviderService.prepare_transport_request(
        model, model_request, "default"
    )
    provider_payload = provider.build_chat_payload(
        remote_model_id="test-model",
        model_request=transport_request,
        thinking_mode="default",
        stream=True,
    )
    prepared_request = PreparedProviderRequest(
        provider=provider,
        provider_id="test",
        remote_model_id="test-model",
        transport_request=transport_request,
        provider_payload=provider_payload,
        transport_mode="native",
        thinking_mode="default",
        api_url="https://provider.example/v1",
        api_key="test-key",
    )
    durable_provider_payload = service.model_calls.audit.redact_provider_payload(provider_payload)
    assert isinstance(durable_provider_payload, dict)

    specifications = service.model_calls.audit.request_event_specifications(
        turn={"session_id": "session-1", "turn_id": "turn-1"},
        call_id="model-2",
        purpose="agent_action",
        model=model,
        model_request=model_request,
        thinking_mode="default",
        step=2,
        prepared_request=prepared_request,
        durable_provider_payload=durable_provider_payload,
    )

    contexts = [
        item["data"]["context"]
        for item in specifications
        if item["type"] == "request/context"
    ]
    assert contexts[0]["context_type"] == "system_prompt"
    tool_catalog_index = next(
        index for index, item in enumerate(contexts) if item["label"] == "1 个可用工具"
    )
    skill_catalog_index = next(
        index for index, item in enumerate(contexts) if item["label"] == "1 个可用技能"
    )
    assert tool_catalog_index < skill_catalog_index
    tool_request_history = next(
        item for item in contexts if item["context_type"] == "model_tool_request"
    )
    assert tool_request_history["label"] == "模型请求工具调用 · 历史"
    skill_result_context = next(
        item
        for item in contexts
        if item["context_type"] == "tool_observation"
        and item["label"] == "工具调用结果 · load_skill"
    )
    header = next(
        item["data"]["header"]
        for item in specifications
        if item["type"] == "request/header"
    )
    provider_skill_message = next(
        message
        for message in header["provider_payload"]["messages"]
        if message.get("role") == "tool"
        and message.get("tool_call_id") == "load-1"
    )
    assert skill_result_context["content"] == provider_skill_message
    assert skill_result_context["content"]["content"] == skill_text
    assert skill_result_context["provider_source"] == {"path": "/messages/3"}
    service.model_calls.audit.assert_provider_context_coverage(
        header["provider_payload"],
        contexts,
    )


def test_text_tool_payload_places_tools_before_skill_and_projects_only_wire_values():
    skill_text = "# 医疗报告导入\n\n完整指令"
    model_request = ModelRequest.build(
        system=(
            "# 系统提示词\n主系统"
            "\n\nSKILL_CATALOG\nreport-import"
            "\n\nRUNTIME_CONTEXT\n{\"visible_attachments\":[]}"
        ),
        messages=[
            {"role": "user", "content": "导入医疗报告"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "load-text-1",
                        "type": "function",
                        "function": {
                            "name": "load_skill",
                            "arguments": '{"name":"report-import"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "load-text-1",
                "name": "load_skill",
                "content": skill_text,
            },
        ],
        tools=[
            ToolSchema(
                name="load_skill",
                parameters={"type": "object"},
            )
        ],
    )
    model = {
        "provider_id": "test",
        "remote_model_id": "text-model",
        "supports_tool_calling": False,
    }
    transport = ModelProviderService.prepare_transport_request(
        model, model_request, "default"
    )
    payload = ModelProvider().build_chat_payload(
        remote_model_id="text-model",
        model_request=transport,
        thinking_mode="default",
        stream=True,
    )

    assert transport.transport_mode == "text_tool"
    assert "tools" not in payload
    system = payload["messages"][0]["content"]
    assert system.index("TEXT_TOOL_PROTOCOL") < system.index(
        "SKILL_CATALOG"
    ) < system.index("RUNTIME_CONTEXT")

    durable = ModelRequestAudit.redact_provider_payload(payload)
    contexts = ModelRequestAudit.provider_payload_contexts(durable)
    ModelRequestAudit.assert_provider_context_coverage(durable, contexts)
    tool_index = next(
        index
        for index, item in enumerate(contexts)
        if item["label"] == "1 个可用工具"
    )
    skill_catalog_index = next(
        index
        for index, item in enumerate(contexts)
        if item["label"] == "1 个可用技能"
    )
    skill_result_context = next(
        item
        for item in contexts
        if item["context_type"] == "tool_observation"
        and item["label"] == "工具调用结果 · load_skill"
    )
    assert tool_index < skill_catalog_index
    assert skill_result_context["provider_source"] == {"path": "/messages/3"}
    assert skill_result_context["content"] == payload["messages"][3]
    assert skill_result_context["content"]["role"] == "user"
    observation = json.loads(
        skill_result_context["content"]["content"].split("\n", 1)[1]
    )
    assert observation["content"] == skill_text


def test_provider_context_projection_covers_unknown_top_level_fields_and_messages():
    payload = {
        "model": "provider-model",
        "messages": [
            {"role": "system", "content": "plain system"},
            {"role": "developer", "content": {"opaque": True}},
        ],
        "stream": True,
        "provider_extension": {"nested": [1, {"flag": False}]},
    }

    contexts = ModelRequestAudit.provider_payload_contexts(payload)
    ModelRequestAudit.assert_provider_context_coverage(payload, contexts)

    extension = next(
        item
        for item in contexts
        if item["provider_source"] == {"path": "/provider_extension"}
    )
    unknown_message = next(
        item
        for item in contexts
        if item["provider_source"] == {"path": "/messages/1"}
    )
    assert extension["content"] is payload["provider_extension"]
    assert unknown_message["label"] == "Provider 消息 · developer"


def test_model_history_contains_tool_surface_and_excludes_log_only_events():
    events = [
        event(
            "user/message",
            0,
            {
                "session_id": "s",
                "turn_id": "t",
                "message_id": "u",
                "parent_message_id": None,
                "content": "read report",
            },
        ),
        event("step/start", 1, {"turn_id": "t", "step": 1, "purpose": "agent_action"}),
        event(
            "request/header",
            2,
            {
                "turn_id": "t",
                "step": 1,
                "call_id": "m1",
                "purpose": "agent_action",
                "header": {
                    "provider_payload": {
                        "model": "test-model",
                        "messages": [{"role": "user", "content": "read report"}],
                        "stream": True,
                    }
                },
            },
        ),
        event(
            "assistant/message",
            3,
            {
                "session_id": "s",
                "turn_id": "t",
                "message_id": "internal",
                "parent_message_id": "u",
                "content": None,
                "branch_addressable": False,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "lookup_report",
                            "arguments": '{"report_id":"r1"}',
                        },
                    }
                ],
            },
        ),
        event(
            "tool/result",
            4,
            {
                "turn_id": "t",
                "call_id": "c1",
                "tool_call_id": "c1",
                "name": "lookup_report",
                "result": {"value": 7},
                "status": "completed",
            },
        ),
        event(
            "assistant/chunk",
            5,
            {
                "turn_id": "t",
                "step": 2,
                "call_id": "m2",
                "chunk": {"type": "usage", "usage": {"input_tokens": 10}},
            },
        ),
    ]
    messages = derive_model_messages(events)
    assert [item["role"] for item in messages] == ["user", "assistant", "tool"]
    assert messages[1]["content"] is None
    assert messages[1]["tool_calls"][0]["id"] == "c1"
    assert messages[2]["tool_call_id"] == "c1"
    assert json.loads(messages[2]["content"]) == {"value": 7}
    assert "not duplicated" not in json.dumps(messages)


def test_tool_result_content_is_projected_exactly_as_persisted():
    persisted_result = {
        "type": "tool_result",
        "call_id": "c1",
        "name": "read_lab_dictionary",
        "output": {
            "corpus_version": "v1",
            "items": {
                "$keys": ["item_name_zh", "aliases", "description"],
                "$rows": [
                    ["丙氨酸氨基转移酶", ["ALT"], None],
                    ["葡萄糖", [], None],
                ],
            },
        },
        "effects": {},
        "trust": "untrusted_data_only",
    }
    events = [
        event(
            "user/message",
            0,
            {
                "session_id": "s",
                "turn_id": "t",
                "message_id": "u",
                "parent_message_id": None,
                "content": "read dictionary",
            },
        ),
        event(
            "tool/result",
            1,
            {
                "turn_id": "t",
                "call_id": "c1",
                "tool_call_id": "c1",
                "name": "read_lab_dictionary",
                "result": persisted_result,
                "status": "completed",
            },
        ),
    ]

    messages = derive_model_messages(events)
    assert json.loads(messages[-1]["content"]) == persisted_result


def test_model_projection_can_preserve_each_user_messages_attachment_context():
    events = [
        event(
            "user/message",
            0,
            {
                "session_id": "s",
                "turn_id": "first-turn",
                "message_id": "first-user",
                "parent_message_id": None,
                "content": "first image",
                "context_resources": [
                    {"resource_type": "file", "resource_id": "image-a"}
                ],
            },
        ),
        event(
            "user/message",
            1,
            {
                "session_id": "s",
                "turn_id": "second-turn",
                "message_id": "second-user",
                "parent_message_id": "assistant-a",
                "content": "second image",
                "context_resources": [
                    {"resource_type": "file", "resource_id": "image-b"}
                ],
            },
        ),
    ]

    assert derive_model_messages(events) == [
        {"role": "user", "content": "first image"},
        {"role": "user", "content": "second image"},
    ]
    assert derive_model_messages(events, include_user_context=True) == [
        {
            "role": "user",
            "content": "first image",
            "_message_id": "first-user",
            "_context_resources": [
                {"resource_type": "file", "resource_id": "image-a"}
            ],
        },
        {
            "role": "user",
            "content": "second image",
            "_message_id": "second-user",
            "_context_resources": [
                {"resource_type": "file", "resource_id": "image-b"}
            ],
        },
    ]


def test_harness_observation_is_a_durable_visible_record_and_model_observation():
    events = [
        event(
            "user/message",
            0,
            {
                "session_id": "s",
                "turn_id": "t",
                "message_id": "u",
                "parent_message_id": None,
                "content": "continue",
            },
        ),
        event(
            "harness/observation",
            1,
            {
                "turn_id": "t",
                "step": 2,
                "call_id": "model-call",
                "observation": {
                    "type": "protocol_error",
                    "error": {
                        "code": "TEXT_TOOL_PROTOCOL_INVALID",
                        "message": "invalid wire output",
                    },
                },
                "status": "failed",
            },
        ),
    ]

    records = records_from_events(events)
    assert [record["kind"] for record in records] == ["user", "observation"]
    observation = records[1]
    assert observation["call_id"] == "model-call"
    assert observation["step"] == 2
    assert observation["status"] == "failed"
    assert observation["source_event_seqs"] == [1]
    assert observation["error"]["code"] == "TEXT_TOOL_PROTOCOL_INVALID"

    messages = derive_model_messages(events)
    assert len(messages) == 2
    assert messages[1]["role"] == "user"
    assert messages[1]["content"].startswith("HARNESS_OBSERVATION\n")
    assert "TEXT_TOOL_PROTOCOL_INVALID" in messages[1]["content"]


def test_turn_failure_is_a_durable_timeline_record_with_the_original_message():
    failure_message = "模型服务调用失败，HTTP 400（上游代码 InvalidParameter）"
    events = [
        event(
            "turn/start",
            0,
            {
                "turn_id": "turn-failed",
                "user_message_id": "user-failed",
                "final_assistant_message_id": "assistant-failed",
                "stream_id": "stream-failed",
            },
        ),
        event(
            "user/message",
            1,
            {
                "turn_id": "turn-failed",
                "message_id": "user-failed",
                "parent_message_id": None,
                "content": "Hello",
            },
        ),
        event(
            "turn/end",
            2,
            {
                "turn_id": "turn-failed",
                "reason": {
                    "kind": "error",
                    "code": "MODEL_ERROR",
                    "message": failure_message,
                },
            },
        ),
    ]

    records = active_records(records_from_events(events), events)

    assert [record["kind"] for record in records] == ["user", "error"]
    assert records[1]["record_id"] == "turn_error_2"
    assert records[1]["status"] == "failed"
    assert records[1]["error"] == {
        "kind": "error",
        "code": "MODEL_ERROR",
        "message": failure_message,
    }
    assert records[1]["source_event_seqs"] == [2]
    response = record_response(records[1])
    assert response["kind"] == "error"
    assert response["error"]["message"] == failure_message


def test_regenerated_turn_tool_result_enters_the_next_model_request():
    events = [
        event(
            "turn/start",
            0,
            {"turn_id": "original-turn", "user_message_id": "u", "stream_id": "stream"},
        ),
        event(
            "user/message",
            1,
            {
                "turn_id": "original-turn",
                "message_id": "u",
                "parent_message_id": None,
                "content": "import attachment",
            },
        ),
        event(
            "turn/end",
            2,
            {"turn_id": "original-turn", "status": "completed"},
        ),
        event(
            "turn/start",
            3,
            {
                "turn_id": "regenerated-turn",
                "user_message_id": "u",
                "supersedes_turn_id": "original-turn",
             "stream_id": "stream"},
        ),
        event(
            "assistant/message",
            4,
            {
                "turn_id": "regenerated-turn",
                "message_id": "internal-tool-request",
                "parent_message_id": "u",
                "branch_addressable": False,
                "content": None,
                "tool_calls": [
                    {
                        "id": "read-skill-call",
                        "type": "function",
                        "function": {
                            "name": "load_skill",
                            "arguments": '{"name":"report-import"}',
                        },
                    }
                ],
            },
        ),
        event(
            "tool/result",
            5,
            {
                "turn_id": "regenerated-turn",
                "call_id": "read-skill-call",
                "tool_call_id": "read-skill-call",
                "name": "load_skill",
                "result": "# report-import\ncomplete ingestion instructions",
                "status": "completed",
            },
        ),
    ]

    messages = derive_model_messages(events)
    assert [item["role"] for item in messages] == ["user", "assistant", "tool"]
    assert messages[2]["content"] == "# report-import\ncomplete ingestion instructions"
    assert messages[2]["tool_call_id"] == "read-skill-call"


def test_visible_loaded_skill_names_restores_successful_linear_session_loads():
    events = [
        event(
            "user/message",
            0,
            {
                "session_id": "s",
                "turn_id": "turn-1",
                "message_id": "u1",
                "parent_message_id": None,
                "content": "import",
            },
        ),
        event(
            "assistant/message",
            1,
            {
                "session_id": "s",
                "turn_id": "turn-1",
                "message_id": "internal-1",
                "parent_message_id": "u1",
                "branch_addressable": False,
                "content": None,
                "tool_calls": [
                    {
                        "id": "load-1",
                        "type": "function",
                        "function": {
                            "name": "load_skill",
                            "arguments": '{"name":"report-import"}',
                        },
                    }
                ],
            },
        ),
        event(
            "tool/call",
            2,
            {
                "turn_id": "turn-1",
                "call_id": "load-1",
                "tool_call_id": "load-1",
                "name": "load_skill",
                "arguments": {"name": "report-import"},
            },
        ),
        event(
            "tool/result",
            3,
            {
                "turn_id": "turn-1",
                "call_id": "load-1",
                "tool_call_id": "load-1",
                "name": "load_skill",
                "result": "# report-import\ncomplete ingestion instructions",
                "status": "completed",
            },
        ),
        event(
            "user/message",
            4,
            {
                "session_id": "s",
                "turn_id": "inactive-turn",
                "message_id": "inactive-u",
                "parent_message_id": None,
                "content": "inactive branch",
            },
        ),
        event(
            "tool/call",
            5,
            {
                "turn_id": "inactive-turn",
                "call_id": "load-inactive",
                "tool_call_id": "load-inactive",
                "name": "load_skill",
                "arguments": {"name": "report-analysis"},
            },
        ),
        event(
            "tool/result",
            6,
            {
                "turn_id": "inactive-turn",
                "call_id": "load-inactive",
                "tool_call_id": "load-inactive",
                "name": "load_skill",
                "result": "# report-analysis\nanalysis instructions",
                "status": "completed",
            },
        ),
        event(
            "tool/call",
            7,
            {
                "turn_id": "turn-1",
                "call_id": "load-failed",
                "tool_call_id": "load-failed",
                "name": "load_skill",
                "arguments": {"name": "report-query"},
            },
        ),
        event(
            "tool/result",
            8,
            {
                "turn_id": "turn-1",
                "call_id": "load-failed",
                "tool_call_id": "load-failed",
                "name": "load_skill",
                "result": None,
                "status": "failed",
                "error": {"code": "SKILL_READ_FAILED"},
            },
        ),
        event(
            "user/message",
            9,
            {
                "session_id": "s",
                "turn_id": "turn-2",
                "message_id": "u2",
                "parent_message_id": "u1",
                "content": "continue import",
            },
        ),
    ]

    assert visible_loaded_skill_names(events, current_turn_ids=["turn-2"]) == [
        "report-import",
        "report-analysis",
    ]


def test_visible_loaded_skill_names_does_not_restore_compacted_skill():
    events = [
        event(
            "user/message",
            0,
            {
                "session_id": "s",
                "turn_id": "turn-1",
                "message_id": "u1",
                "parent_message_id": None,
                "content": "import",
            },
        ),
        event(
            "tool/call",
            1,
            {
                "turn_id": "turn-1",
                "call_id": "load-1",
                "tool_call_id": "load-1",
                "name": "load_skill",
                "arguments": {"name": "report-import"},
            },
        ),
        event(
            "tool/result",
            2,
            {
                "turn_id": "turn-1",
                "call_id": "load-1",
                "tool_call_id": "load-1",
                "name": "load_skill",
                "result": "# report-import\ncomplete ingestion instructions",
                "status": "completed",
            },
        ),
        event(
            "compaction/checkpoint",
            3,
            {
                "turn_id": "turn-2",
                "message_id": "compaction-1",
                "compaction_id": "compaction_1",
                "summary": "summary",
                "content": "<compacted-summary>\nsummary\n</compacted-summary>",
                "estimated_tokens_before": 1000,
                "estimated_tokens_after": 500,
                "target_tokens": 600,
                "replaced_turn_ids": ["turn-1"],
            },
            surface_op={"op": "replace", "start": 0, "end": 3},
            source_event_seqs=(0, 2),
        ),
        event(
            "user/message",
            4,
            {
                "session_id": "s",
                "turn_id": "turn-2",
                "message_id": "u2",
                "parent_message_id": "u1",
                "content": "continue import",
            },
        ),
    ]

    assert visible_loaded_skill_names(
        events, current_turn_ids=["turn-2"]
    ) == []


def test_model_channels_are_flat_and_blank_reasoning_is_omitted():
    events = [
        event(
            "user/message",
            0,
            {
                "session_id": "s",
                "turn_id": "t",
                "message_id": "u",
                "parent_message_id": None,
                "content": "question",
            },
        ),
        event(
            "assistant/chunk",
            1,
            {
                "session_id": "s",
                "turn_id": "t",
                "call_id": "blank",
                "message_id": "model_blank",
                "branch_addressable": False,
                "chunk": {"type": "reasoning-delta", "delta": "   \n"},
            },
        ),
        event(
            "model/result",
            2,
            {
                "turn_id": "t",
                "call_id": "blank",
                "status": "completed",
                "result": {
                    "reasoning": "   \n",
                    "content": "answer",
                    "tool_calls": [],
                },
            },
        ),
        event(
            "assistant/chunk",
            3,
            {
                "session_id": "s",
                "turn_id": "t",
                "call_id": "real",
                "message_id": "model_real",
                "branch_addressable": False,
                "chunk": {"type": "reasoning-delta", "delta": "  first fact"},
            },
        ),
        event(
            "model/result",
            4,
            {
                "turn_id": "t",
                "call_id": "real",
                "status": "completed",
                "result": {
                    "reasoning": "  first fact",
                    "content": "| 指标 | 结果 |\n| --- | --- |\n| ALT | 31 |",
                    "raw_content": '{"type":"final","content":"answer"}',
                    "tool_calls": [
                        {
                            "id": "tool-1",
                            "type": "function",
                            "function": {
                                "name": "read_report_information",
                                "arguments": '{ "report_ids" : ["LAB-1"] }',
                            },
                        }
                    ],
                    "usage": {"input_tokens": 12, "output_tokens": 8},
                    "stop_reason": "tool_calls",
                },
            },
        ),
    ]

    records = records_from_events(events)

    model_records = [record for record in records if record["kind"] == "model"]
    assert [record["channel"] for record in model_records] == [
        "content",
        "result",
        "reasoning",
        "content",
        "raw_output",
        "tool_request",
        "result",
    ]
    assert all(
        not (record["channel"] == "reasoning" and record["call_id"] == "blank")
        for record in model_records
    )
    assert next(
        record for record in model_records
        if record["call_id"] == "blank" and record["channel"] == "content"
    )["value"] == "answer"
    assert next(
        record for record in model_records
        if record["call_id"] == "real" and record["channel"] == "reasoning"
    )["value"] == "  first fact"
    tool_request = next(
        record for record in model_records if record["channel"] == "tool_request"
    )
    assert tool_request["arguments"] == {
        "report_ids": ["LAB-1"]
    }
    assert tool_request["value"] == {
        "name": "read_report_information",
        "arguments": '{ "report_ids" : ["LAB-1"] }',
    }
    result = model_records[-1]
    assert result["usage"] == {"input_tokens": 12, "output_tokens": 8}
    assert result["stop_reason"] == "tool_calls"
    assert [message["role"] for message in messages_from_events(events)] == ["user"]


def test_model_context_window_snapshot_projects_to_records_and_sse():
    events = [
        event(
            "request/header",
            0,
            {
                "turn_id": "turn-1",
                "call_id": "call-1",
                "purpose": "agent_action",
                "header": {
                    "model": {
                        "model_id": "model-1",
                        "context_window_tokens": 258_000,
                    },
                    "provider_payload": {"model": "remote-model", "messages": []},
                },
            },
        ),
        event(
            "model/result",
            1,
            {
                "turn_id": "turn-1",
                "call_id": "call-1",
                "status": "completed",
                "result": {
                    "content": "answer",
                    "usage": {"total_tokens": 95_000},
                },
            },
        ),
    ]

    records = [record for record in records_from_events(events) if record["kind"] == "model"]

    assert {record["context_window_tokens"] for record in records} == {258_000}
    result = next(record for record in records if record["channel"] == "result")
    service = ConversationService(repository=object(), model_catalog=object())
    turn = {"session_id": "session-1", "turn_id": "turn-1"}
    started = json.loads(
        service.streams.projected_record_started_stream_event(turn, result)
        .split("data: ", 1)[1]
    )
    completed = json.loads(
        service.streams.projected_record_completed_stream_event(turn, result)
        .split("data: ", 1)[1]
    )

    assert started["context_window_tokens"] == 258_000
    assert completed["context_window_tokens"] == 258_000


def test_incremental_timeline_projection_matches_every_full_prefix():
    events = [
        event(
            "turn/start",
            0,
            {
                "turn_id": "turn-1",
                "user_message_id": "user-1",
                "final_assistant_message_id": "assistant-1",
             "stream_id": "stream"},
        ),
        event(
            "user/message",
            1,
            {
                "turn_id": "turn-1",
                "message_id": "user-1",
                "content": "question",
            },
        ),
        event(
            "request/header",
            2,
            {
                "turn_id": "turn-1",
                "call_id": "call-1",
                "purpose": "agent_action",
                "header": {
                    "model": {"model_id": "model-1"},
                    "transport_mode": "native",
                    "provider_payload": {"messages": []},
                },
            },
        ),
        event(
            "assistant/chunk",
            3,
            {
                "turn_id": "turn-1",
                "call_id": "call-1",
                "branch_addressable": False,
                "chunk": {"type": "reasoning-delta", "delta": "check evidence"},
            },
        ),
        event(
            "tool/call",
            4,
            {
                "turn_id": "turn-1",
                "call_id": "tool-1",
                "tool_call_id": "tool-1",
                "name": "load_skill",
                "arguments": {"name": "report-query"},
            },
        ),
        event(
            "tool/result",
            5,
            {
                "turn_id": "turn-1",
                "call_id": "tool-1",
                "tool_call_id": "tool-1",
                "name": "load_skill",
                "status": "completed",
                "result": "instructions",
            },
        ),
        event(
            "model/result",
            6,
            {
                "turn_id": "turn-1",
                "call_id": "call-1",
                "status": "completed",
                "result": {
                    "reasoning": "check evidence",
                    "content": "answer",
                    "tool_calls": [],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            },
        ),
        event(
            "assistant/message",
            7,
            {
                "turn_id": "turn-1",
                "message_id": "assistant-1",
                "content": "answer",
                "status": "completed",
            },
        ),
        event(
            "assistant/message-update",
            8,
            {"message_id": "assistant-1", "patch": {"stop_reason": "end_turn"}},
        ),
        event("turn/end", 9, {"turn_id": "turn-1"}),
    ]
    projector = ConversationTimelineProjector()

    for index, item in enumerate(events):
        changed = projector.apply_events([item])
        assert projector.records() == records_from_events(events[: index + 1])
        if item.type in {"assistant/chunk", "assistant/message-update"}:
            assert changed


def test_model_result_assigns_independent_channel_durations():
    events = [
        event(
            "assistant/chunk",
            0,
            {
                "session_id": "s",
                "turn_id": "t",
                "call_id": "c",
                "message_id": "model_c",
                "branch_addressable": False,
                "duration_ms": 1,
                "chunk": {"type": "reasoning-delta", "delta": "先思考。"},
            },
        ),
        event(
            "assistant/chunk",
            1,
            {
                "session_id": "s",
                "turn_id": "t",
                "call_id": "c",
                "message_id": "model_c",
                "branch_addressable": False,
                "duration_ms": 220,
                "chunk": {"type": "reasoning-delta", "delta": "继续思考。"},
            },
        ),
        event(
            "assistant/chunk",
            2,
            {
                "session_id": "s",
                "turn_id": "t",
                "call_id": "c",
                "message_id": "model_c",
                "branch_addressable": False,
                "duration_ms": 1,
                "chunk": {"type": "text-delta", "delta": "正文。"},
            },
        ),
        event(
            "assistant/chunk",
            3,
            {
                "session_id": "s",
                "turn_id": "t",
                "call_id": "c",
                "message_id": "model_c",
                "branch_addressable": False,
                "duration_ms": 1,
                "chunk": {
                    "type": "tool-call-delta",
                    "index": 0,
                    "id": "tool-1",
                    "name_delta": "read_report_information",
                    "arguments_delta": "{\"report_ids\":",
                },
            },
        ),
        event(
            "assistant/chunk",
            4,
            {
                "session_id": "s",
                "turn_id": "t",
                "call_id": "c",
                "message_id": "model_c",
                "branch_addressable": False,
                "duration_ms": 3,
                "chunk": {
                    "type": "tool-call-delta",
                    "index": 0,
                    "id": "",
                    "name_delta": "",
                    "arguments_delta": " [\"LAB-1\"]}",
                },
            },
        ),
        event(
            "model/result",
            5,
            {
                "turn_id": "t",
                "call_id": "c",
                "status": "completed",
                "duration_ms": 240,
                "channel_durations_ms": {
                    "reasoning": 220,
                    "content": 15,
                    "tool_request": 3,
                },
                "result": {
                    "reasoning": "先思考。继续思考。",
                    "content": "正文。",
                    "tool_calls": [
                        {
                            "id": "tool-1",
                            "name": "read_report_information",
                            "arguments": {"report_ids": ["LAB-1"]},
                        }
                    ],
                    "usage": {"input_tokens": 12, "output_tokens": 8},
                    "stop_reason": "tool_calls",
                },
            },
        ),
    ]

    records = records_from_events(events)

    model_records = [record for record in records if record["kind"] == "model"]
    by_channel = {record["channel"]: record for record in model_records}
    assert by_channel["reasoning"]["duration_ms"] == 220
    assert by_channel["content"]["duration_ms"] == 15
    assert by_channel["tool_request"]["duration_ms"] == 3
    assert by_channel["result"]["duration_ms"] == 240


def _model_chunk_event(seq, call_id, chunk, duration_ms=0):
    return event(
        "assistant/chunk",
        seq,
        {
            "session_id": "s",
            "turn_id": "t",
            "call_id": call_id,
            "message_id": f"model_{call_id}",
            "branch_addressable": False,
            "duration_ms": duration_ms,
            "chunk": chunk,
        },
    )


def test_channel_end_completes_text_record_before_tool_request_finishes():
    events = [
        _model_chunk_event(0, "c", {"type": "text-delta", "delta": "正文。"}, 1),
        _model_chunk_event(1, "c", {"type": "text-delta", "delta": "继续。"}, 120),
        _model_chunk_event(2, "c", {"type": "channel-end", "channel": "content"}, 120),
        _model_chunk_event(
            3,
            "c",
            {
                "type": "tool-call-delta",
                "index": 0,
                "id": "tool-1",
                "name_delta": "load_skill",
                "arguments_delta": '{"name": ',
            },
            1,
        ),
    ]

    records = records_from_events(events)

    by_channel = {
        record["channel"]: record
        for record in records
        if record["kind"] == "model"
    }
    assert by_channel["content"]["status"] == "completed"
    assert by_channel["content"]["duration_ms"] == 120
    assert by_channel["content"]["value"] == "正文。继续。"
    assert by_channel["tool_request"]["status"] == "streaming"


def test_channel_delta_after_channel_end_reopens_record_until_model_result():
    events = [
        _model_chunk_event(0, "c", {"type": "text-delta", "delta": "正文。"}, 1),
        _model_chunk_event(1, "c", {"type": "channel-end", "channel": "content"}, 30),
        _model_chunk_event(2, "c", {"type": "text-delta", "delta": "补充。"}, 45),
        event(
            "model/result",
            3,
            {
                "turn_id": "t",
                "call_id": "c",
                "status": "completed",
                "duration_ms": 50,
                "channel_durations_ms": {"content": 45},
                "result": {
                    "content": "正文。补充。",
                    "tool_calls": [],
                    "usage": {},
                    "stop_reason": "end_turn",
                },
            },
        ),
    ]

    records = records_from_events(events)

    content = next(
        record
        for record in records
        if record["kind"] == "model" and record["channel"] == "content"
    )
    assert content["value"] == "正文。补充。"
    assert content["status"] == "completed"
    assert content["duration_ms"] == 45

    reopened = records_from_events(events[:3])
    reopened_content = next(
        record
        for record in reopened
        if record["kind"] == "model" and record["channel"] == "content"
    )
    assert reopened_content["status"] == "streaming"
    assert reopened_content["value"] == "正文。补充。"
    assert reopened_content["duration_ms"] == 45


def test_incomplete_active_path_keeps_ordered_model_reasoning_tools_and_answer():
    events = [
        event(
            "user/message",
            0,
            {
                "turn_id": "t",
                "message_id": "u",
                "parent_message_id": None,
                "content": "question",
            },
        ),
        event(
            "model/result",
            1,
            {
                "turn_id": "t",
                "call_id": "m1",
                "status": "completed",
                "result": {
                    "reasoning": "先判断需要读取什么证据。",
                    "content": "我先读取医疗报告。",
                    "tool_calls": [{"id": "c1", "name": "read_report_information"}],
                },
            },
        ),
        event(
            "tool/call",
            2,
            {
                "turn_id": "t",
                "call_id": "c1",
                "tool_call_id": "c1",
                "name": "read_report_information",
                "arguments": {"operation": "evidence"},
            },
        ),
        event(
            "tool/result",
            3,
            {
                "turn_id": "t",
                "call_id": "c1",
                "tool_call_id": "c1",
                "name": "read_report_information",
                "status": "completed",
                "result": {"reports": 1},
            },
        ),
        event(
            "model/result",
            4,
            {
                "turn_id": "t",
                "call_id": "m2",
                "status": "completed",
                "result": {
                    "reasoning": "证据已经完整，可以组织回答。",
                    "content": "这是最终回答。",
                    "tool_calls": [],
                },
            },
        ),
        event(
            "assistant/message",
            5,
            {
                "turn_id": "t",
                "message_id": "a",
                "parent_message_id": "stale-thinking-id",
                "content": "这是最终回答。",
                "status": "completed",
            },
        ),
    ]
    projected = records_from_events(events)
    visible = active_records(projected, events)

    assert [record["kind"] for record in visible] == [
        "user", "model", "model", "model", "model", "tool",
        "model", "model", "model", "assistant",
    ]
    assert [
        record["value"]
        for record in visible
        if record["kind"] == "model" and record["channel"] == "reasoning"
    ] == ["先判断需要读取什么证据。", "证据已经完整，可以组织回答。"]
    tool_request = next(
        record for record in visible
        if record["kind"] == "model" and record["channel"] == "tool_request"
    )
    tool_call = next(record for record in visible if record["kind"] == "tool")
    assert tool_request["tool_call_id"] == tool_call["tool_call_id"] == "c1"


def test_tool_only_model_result_projects_request_and_result_records():
    records = records_from_events(
        [
            event(
                "model/result",
                1,
                {
                    "turn_id": "t",
                    "call_id": "tool-only",
                    "status": "completed",
                    "result": {
                        "reasoning": "",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "name": "read_report_information",
                                "arguments": {"operation": "catalog"},
                            }
                        ],
                    },
                },
            )
        ]
    )

    assert [record["channel"] for record in records] == ["tool_request", "result"]
    assert records[0]["kind"] == "model"
    assert records[0]["name"] == "read_report_information"
    assert records[0]["arguments"] == {"operation": "catalog"}


def test_parallel_tool_requests_accumulate_by_provider_index_and_finish_exactly():
    events = [
        event(
            "assistant/chunk",
            1,
            {
                "turn_id": "t",
                "call_id": "parallel",
                "chunk": {
                    "type": "tool-call-delta",
                    "index": 0,
                    "id": "call-a",
                    "name_delta": "read_",
                    "arguments_delta": '{"report_',
                },
            },
        ),
        event(
            "assistant/chunk",
            2,
            {
                "turn_id": "t",
                "call_id": "parallel",
                "chunk": {
                    "type": "tool-call-delta",
                    "index": 1,
                    "id": "call-b",
                    "name_delta": "search_",
                    "arguments_delta": '{"query":',
                },
            },
        ),
        event(
            "assistant/chunk",
            3,
            {
                "turn_id": "t",
                "call_id": "parallel",
                "chunk": {
                    "type": "tool-call-delta",
                    "index": 0,
                    "name_delta": "report",
                    "arguments_delta": 'id":"LAB-1"}',
                },
            },
        ),
        event(
            "model/result",
            4,
            {
                "turn_id": "t",
                "call_id": "parallel",
                "status": "completed",
                "result": {
                    "tool_calls": [
                        {
                            "id": "call-a",
                            "type": "function",
                            "function": {
                                "name": "read_report",
                                "arguments": '{"report_id":"LAB-1"}',
                            },
                        },
                        {
                            "id": "call-b",
                            "type": "function",
                            "function": {
                                "name": "search_reports",
                                "arguments": '{ "query" : "血脂" }',
                            },
                        },
                    ],
                    "stop_reason": "tool_calls",
                },
            },
        ),
    ]

    records = records_from_events(events)
    requests = [record for record in records if record.get("channel") == "tool_request"]

    assert [record["provider_index"] for record in requests] == [0, 1]
    assert [record["tool_call_id"] for record in requests] == ["call-a", "call-b"]
    assert [record["name"] for record in requests] == ["read_report", "search_reports"]
    assert [record["arguments"] for record in requests] == [
        {"report_id": "LAB-1"},
        {"query": "血脂"},
    ]
    assert [record["value"] for record in requests] == [
        {"name": "read_report", "arguments": '{"report_id":"LAB-1"}'},
        {"name": "search_reports", "arguments": '{ "query" : "血脂" }'},
    ]
    assert requests[0]["source_event_seqs"] == [1, 3, 4]
    assert requests[1]["source_event_seqs"] == [2, 4]


def test_compaction_checkpoint_replaces_old_surface_at_original_position():
    events = [
        event(
            "user/message",
            0,
            {
                "session_id": "s",
                "turn_id": "old",
                "message_id": "u1",
                "parent_message_id": None,
                "content": "old user",
            },
        ),
        event(
            "assistant/message",
            1,
            {
                "session_id": "s",
                "turn_id": "old",
                "message_id": "a1",
                "parent_message_id": "u1",
                "content": "old assistant",
            },
        ),
        event(
            "user/message",
            2,
            {
                "session_id": "s",
                "turn_id": "new",
                "message_id": "u2",
                "parent_message_id": "a1",
                "content": "new user",
            },
        ),
        event(
            "compaction/checkpoint",
            3,
            {
                "session_id": "s",
                "turn_id": "new",
                "message_id": "summary",
                "compaction_id": "compaction_summary",
                "summary": "kept facts",
                "content": "<compacted-summary>\nkept facts\n</compacted-summary>",
                "estimated_tokens_before": 1000,
                "estimated_tokens_after": 500,
                "target_tokens": 600,
                "replaced_turn_ids": ["old"],
            },
            {"op": "replace", "start": 0, "end": 2},
            source_event_seqs=(0, 1),
        ),
    ]
    messages = derive_model_messages(events)
    assert messages == [
        {"role": "user", "content": "<compacted-summary>\nkept facts\n</compacted-summary>"},
        {"role": "user", "content": "new user"},
    ]
    assert events[0].data["content"] == "old user"


def test_recovery_pairs_unknown_outcome_with_original_tool_call_id():
    open_events = [
        event("turn/start", 0, {"turn_id": "t", "user_message_id": "user", "stream_id": "stream"}),
        event("step/start", 1, {"turn_id": "t", "step": 2, "purpose": "agent_action"}),
        event(
            "tool/call",
            2,
            {
                "turn_id": "t",
                "call_id": "internal-call",
                "tool_call_id": "provider-call",
                "name": "write_report",
                "arguments": {"value": 1},
            },
        ),
    ]
    closers = interrupted_turn_closers(open_events)
    result = next(item for item in closers if item.type == "tool/result")
    assert result.data["call_id"] == "internal-call"
    assert result.data["tool_call_id"] == "provider-call"
    assert result.data["error"]["code"] == "TOOL_OUTCOME_UNKNOWN"
    projected = derive_model_messages(
        [
            event(
                "user/message",
                0,
                {
                    "session_id": "s",
                    "turn_id": "t",
                    "message_id": "u",
                    "parent_message_id": None,
                    "content": "write",
                },
            ),
            event(
                "assistant/message",
                1,
                {
                    "session_id": "s",
                    "turn_id": "t",
                    "message_id": "internal",
                    "parent_message_id": "u",
                    "content": None,
                    "branch_addressable": False,
                    "tool_calls": [
                        {
                            "id": "provider-call",
                            "type": "function",
                            "function": {"name": "write_report", "arguments": "{}"},
                        }
                    ],
                },
            ),
            SessionEvent(
                type="tool/result",
                seq=2,
                time=result.time,
                data=result.data,
            ),
        ],
    )
    assert json.loads(projected[-1]["content"])["error"]["code"] == (
        "TOOL_OUTCOME_UNKNOWN"
    )


def test_compaction_retains_unresolved_collection_observations():
    pending_items = [
        {"item_index": 0, "item": {"label": "已写入"}},
        {"item_index": 1, "item": {"label": "仍待判断"}},
    ]
    # Persisted tool results store output in the columnar $keys/$rows form.
    encoded_items = {
        "$keys": ["item_index", "item"],
        "$rows": [
            [0, {"label": "已写入"}],
            [1, {"label": "仍待判断"}],
        ],
    }
    events = [
        event(
            "tool/result",
            0,
            {
                "turn_id": "read-turn",
                "call_id": "read-call",
                "name": "validate_pending_items",
                "status": "completed",
                "result": {
                    "type": "tool_result",
                    "name": "validate_pending_items",
                    "output": {
                        "sources": [
                            {
                                "source_index": 0,
                                "source_type": "attachment",
                                "resource_id": "r1",
                            }
                        ],
                        "items": encoded_items,
                    },
                    "effects": {
                        "context_retention": {
                            "collection_field": "items",
                            "index_field": "item_index",
                        }
                    },
                },
            },
        ),
        event(
            "tool/call",
            1,
            {
                "turn_id": "write-turn",
                "call_id": "write-call",
                "name": "save_item",
                "arguments": {"read_call_id": "read-call", "item_index": 0},
            },
        ),
        event(
            "tool/result",
            2,
            {
                "turn_id": "write-turn",
                "call_id": "write-call",
                "name": "save_item",
                "status": "completed",
                "result": {
                    "type": "tool_result",
                    "output": {"entity_id": "LAB-1"},
                    "effects": {
                        "resolved_context_items": [
                            {"call_id": "read-call", "index": 0}
                        ]
                    },
                },
            },
        ),
    ]

    retained = ConversationCompaction.unresolved_context_observations(
        events,
        compact_turns={"read-turn"},
        active_turns={"read-turn", "write-turn"},
    )

    assert retained == [
        {
            "call_id": "read-call",
            "tool_name": "validate_pending_items",
            "output": {
                "sources": [
                    {
                        "source_index": 0,
                        "source_type": "attachment",
                        "resource_id": "r1",
                    }
                ],
                "items": [pending_items[1]],
            },
        }
    ]

    retained_all = ConversationCompaction.unresolved_context_observations(
        events[:1],
        compact_turns={"read-turn"},
        active_turns={"read-turn"},
    )
    assert retained_all[0]["output"]["items"] == encoded_items


def _append_message(repository, session_id, *, turn_id, message_id, parent, role, content):
    repository.append_session_event(
        account_id_for("alice"),
        session_id,
        f"{role}/message",
        {
            "turn_id": turn_id,
            "message_id": message_id,
            "parent_message_id": parent,
            "content": content,
        },
        surface_op="append",
    )


def test_context_compaction_keeps_current_and_budgeted_recent_history(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    repository = ConversationRepository(JsonlSessionPersistence())
    session_id = repository.ensure_session(account_id_for("alice"), member_id=member_id("alice"))
    parent = None
    for index in range(6):
        turn_id = f"t{index}"
        user_id = f"u{index}"
        assistant_id = f"a{index}"
        repository.append_session_event(
            account_id_for("alice"), session_id, "turn/start", {"turn_id": turn_id, "user_message_id": "user", "stream_id": "stream"}
        )
        text = "非常长的早期医学证据" * 1200 if index == 0 else f"recent {index}"
        _append_message(
            repository,
            session_id,
            turn_id=turn_id,
            message_id=user_id,
            parent=parent,
            role="user",
            content=text,
        )
        _append_message(
            repository,
            session_id,
            turn_id=turn_id,
            message_id=assistant_id,
            parent=user_id,
            role="assistant",
            content=f"answer {index}",
        )
        repository.append_session_event(
            account_id_for("alice"),
            session_id,
            "turn/end",
            {"turn_id": turn_id, "reason": {"kind": "completed"}},
        )
        parent = assistant_id

    repository.append_session_event(
        account_id_for("alice"), session_id, "turn/start", {"turn_id": "current", "user_message_id": "user", "stream_id": "stream"}
    )
    _append_message(
        repository,
        session_id,
        turn_id="current",
        message_id="current-user",
        parent=parent,
        role="user",
        content="current question",
    )
    model = {
        "model_id": "m",
        "provider_id": "fake",
        "remote_model_id": "fake-model",
        "thinking_modes": ["default"],
        "supports_tool_calling": True,
        "context_window_tokens": 5000,
        "max_output_tokens": 500,
    }
    catalog = CompactCatalog(model)
    service = ConversationService(repository=repository, model_catalog=catalog)
    repository.insert_turn(account_id_for("alice"), session_id, "current", "current-user", "final", "stream", "streaming", None, None, "2026-09-09", "2026-09-09")
    turn = {"session_id": session_id, "turn_id": "current"}
    user_message = {
        "message_id": "current-user",
        "parent_message_id": parent,
        "context_resources": [],
    }
    def derive_with_recent_attachment():
        messages = derive_model_messages(
            repository.session_events(account_id_for("alice"), session_id),
        )
        for message in messages:
            if message.get("role") == "user" and message.get("content") == "recent 5":
                message["content"] = [
                    {"type": "text", "text": "recent 5"},
                    {
                        "type": "image",
                        "mime_type": "image/png",
                        "data_base64": "aW1hZ2U=",
                    },
                ]
        return messages

    original_messages = derive_with_recent_attachment()
    rebuilt = service.compaction.compact_model_request_if_needed(
        account_id=account_id_for("alice"),
        turn=turn,
        user_message=user_message,
        model=model,
        model_request=ModelRequest.build(
            system="system",
            messages=original_messages,
            tools=[
                ToolSchema(
                    name="control",
                    parameters={"type": "object", "properties": {}},
                )
            ],
            model_config={"purpose": "agent_action", "max_output_tokens": 500},
        ),
        thinking_mode="default",
    )
    events = repository.session_events(account_id_for("alice"), session_id)
    checkpoint = next(item for item in events if item.type == "compaction/checkpoint")
    assert checkpoint.data["replaced_turn_ids"] == ["t0"]
    assert checkpoint.data["estimated_tokens_after"] <= checkpoint.data["target_tokens"]
    assert checkpoint.surface_op["op"] == "replace"
    assert rebuilt.messages[0]["content"].startswith("<compacted-summary>")
    serialized = json.dumps(rebuilt.messages, ensure_ascii=False)
    assert "非常长的早期医学证据" not in serialized
    for index in range(2, 6):
        assert f"recent {index}" in serialized
    assert "current question" in serialized
    assert "aW1hZ2U=" in serialized
    assert any(
        request.model_config.get("purpose") == "context_compaction"
        for request in catalog.requests
    )

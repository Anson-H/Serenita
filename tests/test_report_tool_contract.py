from backend.app.plugins.medical_report.registry import build_tools
import json
from types import SimpleNamespace
import pytest
from backend.app.agent_runtime.runtime import AgentHarnessRuntime
from backend.app.plugins import PluginRuntimeContext, resolve_plugin_resource_states
from backend.app.plugins.medical_report.registry import build_skills
from backend.app.plugins.medical_report.tools.import_tools import CreateReportTool
from backend.app.plugins.medical_report.tools.mutation_tools import AddLabReportItemsTool, DeleteLabReportItemsTool, DeleteReportTool, UpdateReportFieldsTool
from backend.app.plugins.medical_report.tools.query_tools import ReadLabDictionaryTool, ReadReportAnalysisTool, ReadReportCatalogTool, ReadReportInformationTool
from backend.app.plugins.medical_report.tools.write_report_analysis import WriteReportAnalysisTool


REPORT_TOOLS = {
    "read_report_catalog",
    "read_report_information",
    "read_report_analysis",
    "read_lab_dictionary",
    "create_report",
    "link_duplicate_sources",
    "merge_report",
    "write_report_analysis",
    "update_report_fields",
    "add_lab_report_items",
    "delete_lab_report_items",
    "reclassify_report",
    "delete_report",
}

def context(**memory):
    return SimpleNamespace(
        account_id="demo",
        member_id="demo-member",
        model_id="chat",
        session_id="session",
        turn_id="turn",
        input_text="2026-08-01 肌酐 70 μmol/L",
        memory={
            "current_message_id": "message",
            "visible_message_ids": ["message"],
            "visible_attachments": {},
            **memory,
        },
    )


def _parameters_without_descriptions(
    schema: object,
    *,
    path: str = "$",
) -> list[str]:
    missing: list[str] = []
    if isinstance(schema, list):
        for index, item in enumerate(schema):
            missing.extend(
                _parameters_without_descriptions(item, path=f"{path}[{index}]")
            )
        return missing
    if not isinstance(schema, dict):
        return missing

    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, parameter in properties.items():
            parameter_path = f"{path}.{name}"
            if not isinstance(parameter, dict) or not str(
                parameter.get("description") or ""
            ).strip():
                missing.append(parameter_path)
            missing.extend(
                _parameters_without_descriptions(parameter, path=parameter_path)
            )

    for key, value in schema.items():
        if key == "properties":
            continue
        missing.extend(
            _parameters_without_descriptions(value, path=f"{path}.{key}")
        )
    return missing


def test_report_plugin_exposes_only_registered_model_tools():
    runtime_context = PluginRuntimeContext(
        account_id="demo",
        event_recorder=lambda _event: None,
        services={"medical_report": object()}, member_id="demo-member")
    tools = build_tools( runtime_context=runtime_context)
    assert {tool.name for tool in tools} == REPORT_TOOLS
    serialized = json.dumps([tool.input_schema for tool in tools], ensure_ascii=False)
    assert "parse_report_attachment" not in serialized
    assert "parse_report_text" not in serialized
    assert '"account"' not in serialized
    assert '"account_id"' not in serialized
    assert '"parsed_sources"' not in serialized
    assert '"trusted_import_context"' not in serialized
    assert "sql" not in serialized.lower()


def test_report_plugin_resolves_current_resource_state_once_per_report():
    class FakeStateService:
        def report_resource_state(self, account, report_id):
            assert account == "demo-member"
            return {
                "resource_type": "report",
                "resource_id": report_id,
                "availability": "available",
                "current_created_at": "2026-08-20T10:00:00+08:00",
                "current_updated_at": "2026-08-20T10:05:00+08:00",
            }

    states = resolve_plugin_resource_states(
        runtime_context=PluginRuntimeContext(
            account_id="demo",
            event_recorder=lambda _event: None,
            services={"medical_report:demo-member": FakeStateService()}, member_id="demo-member"),
        resource_refs=[
            {"resource_type": "report", "resource_id": "LAB-1", "member_id": "demo-member"},
            {"resource_type": "report", "resource_id": "LAB-1", "member_id": "demo-member"},
            {"resource_type": "file", "resource_id": "FILE-1"},
        ],
    )

    assert states == [
        {
            "resource_type": "report",
            "resource_id": "LAB-1",
            "availability": "available",
            "current_created_at": "2026-08-20T10:00:00+08:00",
            "current_updated_at": "2026-08-20T10:05:00+08:00",
        }
    ]


def test_all_model_tools_use_required_descriptions_and_describe_every_parameter():
    from backend.app.agent_runtime.prompts import assemble_serenita_prompt
    from backend.app.plugins.registry import build_available_tools

    class InMemoryService:
        def for_runtime(self, *args, **kwargs):
            return self

    runtime_context = PluginRuntimeContext(
        account_id="demo", event_recorder=lambda _event: None,
        service_factory=lambda _name: InMemoryService(), member_id="demo-member",
    )
    tools = build_available_tools(runtime_context=runtime_context)
    control = assemble_serenita_prompt(available_skills=[{"name": "report-query", "description": "医疗报告查询"}], application_tools=[]).tools
    descriptions = {tool.name: tool.description for tool in [*control, *tools]}
    # These exact sentences are the model-visible contract required by AGENTS.md.
    assert descriptions == {
        "load_skill": "读取一个技能的完整技能正文并返回实际指令文本。",
        "update_plan": "创建或调整当前轮次的非强制任务计划，并返回计划内容。",
        "web_search": "搜索公开互联网，返回搜索结果摘要和引用标识。",
        "web_read": "读取一条既有搜索结果的网页正文，并保留其引用标识。",
        "read_log": "读取当前成员中匹配的健康日记，返回日记内容。",
        "create_log": "为当前成员创建健康日记，返回创建结果。",
        "update_log": "更新当前成员的一条健康日记，返回更新后的健康日记。",
        "delete_log": "删除当前成员的一条健康日记，返回删除结果。",
        "read_history": "读取当前成员的既往史，返回已保存内容。",
        "update_history": "更新当前成员的既往史，返回保存结果。",
        "read_report_catalog": "读取当前账号中匹配的医疗报告目录，返回用于定位医疗报告的目录信息。",
        "read_report_information": "读取匹配医疗报告的医疗报告事实。",
        "read_report_analysis": "读取匹配医疗报告的既有解读结果。",
        "read_lab_dictionary": "读取当前账号的完整检验指标分类目录。",
        "create_report": "将一份医疗报告写入医疗报告档案库，返回创建结果。",
        "link_duplicate_sources": "将来源关联到一份既有医疗报告，返回关联结果。",
        "merge_report": "将补充的医疗报告事实和来源合并到一份既有医疗报告，返回合并结果。",
        "write_report_analysis": "将解读结果写入医疗报告档案库中的目标医疗报告，返回保存结果。",
        "update_report_fields": "更新一份医疗报告的基础信息或结构化内容，返回更新后的医疗报告。",
        "add_lab_report_items": "向一份检验报告添加检验指标记录，返回更新后的医疗报告。",
        "delete_lab_report_items": "从一份检验报告删除检验指标记录，返回更新后的医疗报告。",
        "reclassify_report": "使用经过校验的新结构重分类一份医疗报告，返回重分类后的医疗报告。",
        "delete_report": "删除一份医疗报告及其已保存内容，返回删除结果。",
        "read_medication_information": "读取当前成员中匹配的药品信息，返回已保存的药品资料。",
        "create_medication": "向药品目录添加一项药品，返回创建结果。",
        "add_medication_sources": "向药品目录中的一项药品补充原件，返回保存结果。",
        "read_medication_inventory": "读取当前成员的药品库存，返回库存批次、数量和有效期。",
        "read_medication_plan": "读取当前成员的用药计划，返回已保存内容。",
        "create_medication_plan": "为当前成员创建用药计划，返回创建结果。",
        "update_medication_plan": "更新当前成员的用药计划，返回更新后的内容。",
        "delete_medication_plan": "删除当前成员的用药计划，返回删除结果。",
        "read_medication_batch": "读取当前成员的药品批次，返回已保存内容。",
        "create_medication_batch": "为当前成员创建药品批次，返回创建结果。",
        "update_medication_batch": "更新当前成员的药品批次，返回更新后的内容。",
        "delete_medication_batch": "删除当前成员的药品批次，返回删除结果。",
        "read_body_metric_catalog": "读取身体指标分类目录，返回支持的指标和记录类型。",
        "read_body_record_catalog": "读取当前成员中匹配的身体指标记录目录，返回用于定位记录的目录信息。",
        "read_body_record": "读取当前成员的身体指标记录，返回记录内容和图片关联信息。",
        "read_body_statistics": "读取当前成员的身体指标统计，返回趋势、统计口径和数据覆盖信息。",
        "create_body_record": "为当前成员创建身体指标记录，返回创建结果。",
        "update_body_record": "更新当前成员的身体指标记录，返回更新后的内容。",
        "delete_body_record": "删除当前成员的一条身体指标记录及其图片关联，返回删除结果。",
        "attach_body_record_file": "将会话图片保存为饮食记录附件，返回保存结果。",
        "detach_body_record_file": "解除饮食记录的图片关联，返回解除结果。",
    }
    schemas = {tool.name: tool.input_schema for tool in tools}
    schemas.update({tool.name: tool.parameters for tool in control})
    assert not {name: missing for name, schema in schemas.items()
                if (missing := _parameters_without_descriptions(schema))}


def test_detailed_report_schema_exposes_fields_whitelist():
    schema = ReadReportInformationTool.input_schema
    assert "fields" in schema["properties"]
    field_enum = schema["properties"]["fields"]["items"]["enum"]
    assert "sources" in field_enum
    assert "lab_test_results" in field_enum


@pytest.mark.parametrize(
    ("tool_class", "arguments", "change"),
    [
        (
            UpdateReportFieldsTool,
            {
                "updates": [
                    {"field": "report_time", "value": "2026-08-23T09:00:00+08:00"},
                    {"field": "institution_name", "value": "复核医院"},
                ]
            },
            "fields_updated",
        ),
        (
            DeleteLabReportItemsTool,
            {"item_ids": ["item-remove-one", "item-remove-two"]},
            "lab_items_deleted",
        ),
        (
            AddLabReportItemsTool,
            {
                "items": [
                    {"item_id": "item-ast", "result_text": "35 U/L"},
                    {"item_id": "item-albumin", "result_text": "45 g/L"},
                ]
            },
            "lab_items_added",
        ),
    ],
)
def test_report_mutation_tools_forward_one_batch_and_describe_the_change(
    tool_class, arguments, change
):
    class FakeMutationService:
        def mutate(self, account, report_id, **received_arguments):
            self.received = (account, report_id, received_arguments)
            return {"report_id": report_id}

        update_report_fields = mutate
        delete_lab_report_items = mutate
        add_lab_report_items = mutate

        def report_exists(self, account, report_id):
            return account == "demo-member" and report_id == "LAB-1"

        def validate_report_context(self, account, report_id):
            return {"resource_type": "report", "resource_id": report_id}

    service = FakeMutationService()
    result = tool_class(
        account_id="demo", service=service, member_id="demo-member"
    ).run({"report_id": "LAB-1", **arguments})

    assert service.received == ("demo-member", "LAB-1", arguments)
    assert result.output == {"report_id": "LAB-1"}
    assert result.effects == {
        "resource_refs": [{"resource_type": "report", "resource_id": "LAB-1"}],
        "changed_entities": [
            {"entity_type": "report", "entity_id": "LAB-1", "change": change}
        ],
    }


def test_report_read_tools_emit_ordered_resource_refs_for_returned_reports():
    reports = [
        {
            "report_id": "LAB-1",
            "report_time": "2026-08-20T09:30:00+08:00",
            "report_type": "检验报告",
            "report_name": "血常规",
        },
        {
            "report_id": "EXAM-2",
            "report_time": "2026-08-18T14:00:00+08:00",
            "report_type": "检查报告",
            "report_name": "胸部 CT",
        },
    ]

    class FakeReadService:
        def read_report_catalog(self, account, **arguments):
            assert account == "demo-member"
            return {"total": 2, "reports": reports}

        def query_evidence(self, account, **arguments):
            assert account == "demo-member"
            return {"total": 2, "reports": reports}

        def read_report_analysis(self, account, **arguments):
            assert account == "demo-member"
            return {"total": 2, "analyses": reports}

        def validate_report_context(self, account, report_id):
            assert account == "demo-member"
            report = next(item for item in reports if item["report_id"] == report_id)
            return {
                "resource_type": "report",
                "resource_id": report_id,
                "report_time": report["report_time"],
                "report_type": report["report_type"],
                "report_name": report["report_name"],
                "captured_created_at": "2026-08-20T10:00:00+08:00",
                "captured_updated_at": "2026-08-20T10:00:00+08:00",
            }

    expected_refs = [
        {
            "resource_type": "report",
            "resource_id": report["report_id"],
            "report_time": report["report_time"],
            "report_type": report["report_type"],
            "report_name": report["report_name"],
            "captured_created_at": "2026-08-20T10:00:00+08:00",
            "captured_updated_at": "2026-08-20T10:00:00+08:00",
        }
        for report in reports
    ]
    service = FakeReadService()
    results = [
        ReadReportCatalogTool(account_id="demo", service=service, member_id="demo-member").run({}),
        ReadReportInformationTool(account_id="demo", service=service, member_id="demo-member").run({}),
        ReadReportAnalysisTool(account_id="demo", service=service, member_id="demo-member").run({}),
    ]
    assert [result.effects["resource_refs"] for result in results] == [
        expected_refs,
        expected_refs,
        expected_refs,
    ]


def test_report_read_tools_keep_logical_messages_and_automatic_catalog_pages():
    def reports(count):
        return [
            {
                "report_id": f"LAB-{index:03d}",
                "report_time": f"2026-08-{(index % 28) + 1:02d}T08:00:00+08:00",
            }
            for index in range(count)
        ]

    class CompleteSnapshotService:
        def read_report_catalog(self, account, **arguments):
            values = reports(25)[24:] if arguments.get("cursor") else reports(24)
            return {
                "total": 25,
                "next_cursor": None if arguments.get("cursor") else "following-page",
                "reports": values,
                "report_ids": [item["report_id"] for item in values],
            }

        def query_evidence(self, account, **arguments):
            values = reports(13)
            return {"total": len(values), "reports": values}

        def read_lab_dictionary(self, account, **arguments):
            values = [{"item_id": f"item-{index:03d}"} for index in range(101)]
            return {"total": len(values), "items": values, "categories": []}

        def read_report_analysis(self, account, **arguments):
            values = reports(25)
            return {"total": len(values), "analyses": values}

        def validate_report_context(self, account, report_id):
            return {"resource_type": "report", "resource_id": report_id}

    service = CompleteSnapshotService()
    tools = [
        (ReadReportCatalogTool(account_id="demo", service=service, member_id="demo-member"), "reports", [24]),
        (ReadReportInformationTool(account_id="demo", service=service, member_id="demo-member"), "reports", [12, 1]),
        (ReadLabDictionaryTool(account_id="demo", service=service, member_id="demo-member"), "items", [100, 1]),
        (ReadReportAnalysisTool(account_id="demo", service=service, member_id="demo-member"), "analyses", [24, 1]),
    ]

    for tool, collection_field, expected_page_lengths in tools:
        assert "cursor" not in tool.input_schema["properties"]
        assert "page_size" not in tool.input_schema["properties"]
        result = tool.run({})
        assert [
            len(page[collection_field]) for page in result.logical_pages
        ] == expected_page_lengths
        assembled = AgentHarnessRuntime._assemble_tool_output(result)
        assert len(assembled[collection_field]) == sum(expected_page_lengths)
        if tool.name == "read_report_catalog":
            assert assembled["total"] == 25
            assert assembled["pagination"] == {"page": 1, "complete": False}
            following = result.next_page()
            last = AgentHarnessRuntime._assemble_tool_output(following)
            assert last["reports"] == reports(25)[24:]
            assert last["pagination"] == {"page": 2, "complete": True}
            assert following.next_page is None
        else:
            assert assembled["total"] == sum(expected_page_lengths)
            assert "next_cursor" not in assembled


def test_delete_report_preserves_the_pre_delete_resource_snapshot():
    snapshot = {
        "resource_type": "report",
        "resource_id": "LAB-1",
        "report_time": "2026-08-20T09:30:00+08:00",
        "report_type": "检验报告",
        "report_name": "血常规",
        "captured_created_at": "2026-08-20T10:00:00+08:00",
        "captured_updated_at": "2026-08-20T10:05:00+08:00",
    }

    class FakeDeleteService:
        def validate_report_context(self, account, report_id):
            assert (account, report_id) == ("demo-member", "LAB-1")
            return snapshot

        def delete_report(self, account, report_id):
            assert (account, report_id) == ("demo-member", "LAB-1")
            return {"report_id": report_id, "deleted": True}

    result = DeleteReportTool(account_id="demo", service=FakeDeleteService(), member_id="demo-member").run(
        {"report_id": "LAB-1"}
    )

    assert result.effects["affected_resource_refs"] == [snapshot]
    assert result.effects["changed_entities"] == [
        {"entity_type": "report", "entity_id": "LAB-1", "change": "deleted"}
    ]


def test_validate_schema_enumerates_visible_attachment_ids():
    tool = CreateReportTool(account_id="demo", service=object(), member_id="demo-member")
    schema = tool.input_schema_for_context(
        context(
            visible_attachments={
                "resource-one": {"resource_id": "resource-one"},
                "resource-two": {"resource_id": "resource-two"},
            }
        )
    )
    source_union = schema["properties"]["sources"]["items"]["oneOf"]
    assert source_union[1]["properties"]["resource_id"]["enum"] == [
        "resource-one",
        "resource-two",
    ]


def test_write_binds_exact_text_and_visible_read_source_observations():
    tool = CreateReportTool(account_id="demo", service=object(), member_id="demo-member")
    bound = tool.bind_runtime_arguments(
        {"report": {}, "sources": []},
        context=context(),
        observations=[
            {
                "call_id": "read-one",
                "name": "read_report_information",
                "output": {
                    "reports": [
                        {
                            "report_id": "LAB-1",
                            "sources": [
                                {"resource_id": "FILE-1", "mime_type": "image/jpeg"}
                            ],
                        }
                    ],
                },
            }
        ],
    )
    assert bound["source_text"] == "2026-08-01 肌酐 70 μmol/L"
    assert bound["source_message_id"] == "message"
    assert bound["authorized_report_sources"] == {
        "read-one\0LAB-1\0FILE-1": {
            "resource_id": "FILE-1",
            "mime_type": "image/jpeg",
        }
    }


def test_import_write_tools_do_not_bind_corpus_context():
    class FakeWriteService:
        def __init__(self):
            self.received = None

        def create_report_from_parsed(self, account, **arguments):
            assert account == "demo-member"
            self.received = arguments
            return {"report_id": "LAB-1"}

        def validate_report_context(self, account, report_id):
            return {"report_id": report_id}

    fake = FakeWriteService()
    tool = CreateReportTool(account_id="demo", service=fake, member_id="demo-member")
    bound = tool.bind_runtime_arguments(
        {"report": {"report_name": "肝功能"}, "sources": [{"source_type": "conversation_text"}]},
        context=context(),
        observations=[],
    )
    assert "trusted_import_context" not in bound
    result = tool.run(bound)
    assert result.output == {"report_id": "LAB-1"}
    assert "trusted_import_context" not in fake.received


def test_analysis_write_uses_only_model_arguments_and_conversation_binding():
    class FakeAnalysisService:
        def __init__(self):
            self.received = None

        def write_report_analysis(self, account, **arguments):
            assert account == "demo-member"
            self.received = arguments
            return {
                "report_id": arguments["report_id"],
                "analysis_content": arguments["analysis_content"],
            }

        def validate_report_context(self, account, report_id):
            assert account == "demo-member"
            return {"resource_type": "report", "resource_id": report_id}

    fake = FakeAnalysisService()
    tool = WriteReportAnalysisTool(account_id="demo", service=fake, member_id="demo-member")
    bound = tool.bind_runtime_arguments(
        {"report_id": "LAB-1", "analysis_content": "当前解读。"},
        context=context(),
        observations=[
            {
                "name": "read_report_information",
                "output": {"reports": [{"report_id": "LAB-OTHER"}]},
            }
        ],
    )
    result = tool.run(bound)

    assert fake.received == {
        "report_id": "LAB-1",
        "analysis_content": "当前解读。",
        "session_id": "session",
        "source_message_id": "message",
    }
    assert result.output["report_id"] == "LAB-1"


def test_create_report_requires_item_id_for_each_lab_result():
    report_schema = CreateReportTool.input_schema["properties"]["report"]
    assert "lab_results" not in report_schema["properties"]
    assert "examination_result" not in report_schema["properties"]
    assert "examination_report" in report_schema["properties"]
    lab_item_schema = report_schema["properties"]["lab_test_results"]["items"]
    assert "item_id" in lab_item_schema["required"]
    assert lab_item_schema["properties"]["item_id"]["minLength"] == 1


def test_report_skills_reference_only_current_capabilities():
    contracts = {
        skill.name: skill.read(None).allowed_tools for skill in build_skills()
    }
    assert contracts["report-query"] == {
        "read_report_catalog",
        "read_report_information",
        "read_report_analysis",
        "read_lab_dictionary",
    }
    assert contracts["report-import"] == {
        "create_report",
        "link_duplicate_sources",
        "merge_report",
    }
    assert contracts["report-analysis"] == {
        "write_report_analysis",
    }
    assert contracts["report-update"] == {
        "update_report_fields",
        "add_lab_report_items",
        "delete_lab_report_items",
        "reclassify_report",
        "delete_report",
    }
    assert set().union(*contracts.values()) <= REPORT_TOOLS

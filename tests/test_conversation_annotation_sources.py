import pytest
from backend.app.application.conversation_service import _annotation_source_values, _annotation_text_belongs_to_record
from types import SimpleNamespace
from backend.app.plugins.report.tools.write_report_analysis import WriteReportAnalysisTool


@pytest.mark.parametrize(
    "source,selection",
    [
        (
            "两小段文字：**「接问我健康相关」**和**「问题，也可以」**——这两段都是我自己说的话",
            "两小段文字：「接问我健康相关」和「问题，也可以」——这两段",
        ),
        ("建议**适量运动**，并*规律作息*。", "建议适量运动，并规律作息。"),
        ("# 建议\n\n- 记录**睡眠**\n- 观察症状", "建议\n\n记录睡眠\n观察症状"),
        ("1. 记录睡眠\n2. 观察症状", "记录睡眠\n观察症状"),
        ("> 先记录\n> 再**复查**", "先记录 再复查"),
        ("阅读[复查建议](https://example.com)后记录。", "阅读复查建议后记录。"),
        ("阅读[复查建议][guide]后记录。\n\n[guide]: https://example.com", "阅读复查建议后记录。"),
        ("A &amp; B：&lt; 5，&#x2265; 3。", "A & B：< 5，≥ 3。"),
        (r"保留\*星号\*，数值为 **-2**。", "保留*星号*，数值为 -2。"),
        ("先看 `a_b * 2`，再记录。", "先看 a_b * 2，再记录。"),
        ("示例\n\n```text\n**原样** &amp; a_b\n```\n\n结束", "示例\n**原样** &amp; a_b\n结束"),
        ("| 指标 | 数值 |\n| --- | --- |\n| **体温** | 36.5 |", "指标\t数值\n体温\t36.5"),
        ("保留~~旧值~~，查看新值。", "保留旧值，查看新值。"),
        ("保留~旧值~，查看新值。", "保留旧值，查看新值。"),
        ("- [x] 已完成\n- [ ] 待处理", "已完成\n待处理"),
        ("第一行  \n第二行\\\n第三行", "第一行\n第二行\n第三行"),
    ],
)
def test_annotations_accept_rendered_markdown_selections(source, selection):
    record = {"kind": "assistant", "channel": "content", "content": source}
    assert _annotation_text_belongs_to_record(selection, record)


@pytest.mark.parametrize(
    "source,selection",
    [
        ("建议**复查**。", "建议停止治疗。"),
        ("数值为 **-2**。", "数值为 2。"),
        ("范围为 3-5。", "范围为 35。"),
        ("浓度为 3.5。", "浓度为 35。"),
        ("先看 `a_b * 2`，再记录。", "先看 ab 2，再记录。"),
        ("```text\n**原样** &amp; a_b\n```", "原样 & ab"),
        ("A B", "AB"),
        ("建议**复查**。", " \n\t "),
        ("建议**复查**。", ""),
        ("甲\n\n乙\n\n丙", "甲 丙"),
    ],
)
def test_annotations_reject_text_not_present_in_the_source(source, selection):
    assert not _annotation_text_belongs_to_record(selection, {"kind": "assistant", "content": source})


def test_annotation_sources_only_allow_user_input_and_assistant_answers():
    user = {"kind": "user", "content": "我最近头晕"}
    assistant = {"kind": "assistant", "content": "请尽快就医"}
    model_content = {
        "kind": "model",
        "channel": "content",
        "value": "核心结论\n建议复查",
    }
    model_result = {
        "kind": "model",
        "channel": "result",
        "value": {"usage": {"input_tokens": 12}},
    }

    assert _annotation_text_belongs_to_record("最近头晕", user)
    assert _annotation_text_belongs_to_record("核心结论 建议复查", model_content)
    assert _annotation_text_belongs_to_record("尽快就医", assistant)
    assert _annotation_source_values(model_result) is None


def test_non_answer_execution_records_cannot_be_annotation_sources():
    reasoning_record = {
        "kind": "model",
        "channel": "reasoning",
        "value": "需要先读取报告目录",
    }
    context_record = {
        "kind": "context",
        "label": "上下文装配",
        "content": "系统提示词",
    }
    tool_record = {
        "kind": "tool",
        "result": {"output": {"report_name": "肾功能检查"}, "effects": {"internal": True}},
        "error": None,
    }
    observation_record = {
        "kind": "observation",
        "observation": {"report_name": "肾功能检查"},
    }

    for record in (
        reasoning_record,
        context_record,
        tool_record,
        observation_record,
    ):
        assert _annotation_source_values(record) is None
        assert not _annotation_text_belongs_to_record("肾功能检查", record)


def bind(content, observations):
    tool = WriteReportAnalysisTool(account_id='account', member_id='member', service=SimpleNamespace())
    return tool.bind_runtime_arguments({'report_id': 'report', 'analysis_content': content},
        context=SimpleNamespace(account_id='account', member_id='member', session_id='session', memory={}, model_id='model'),
        observations=observations)['analysis_content']


def test_report_citations_are_portable_and_use_only_observed_sources():
    observations = [{'name': 'web_search', 'output': {'results': [{'citation_id': 'a-1', 'title': 'Evidence', 'url': 'https://example.org/evidence'}]}}]
    assert bind('正文[cite:a-1]', observations) == '正文[Evidence](<https://example.org/evidence>)'
    with pytest.raises(ValueError) as failure:
        bind('正文[cite:unknown]', observations)
    assert failure.value.code == 'REPORT_CITATION_UNRESOLVED'
    assert failure.value.details == {'citation_ids': ['unknown']}
    assert bind('`[cite:unknown]` \\[cite:unknown]', []) == '`[cite:unknown]` \\[cite:unknown]'


@pytest.mark.parametrize("content", [
    "~~~markdown\n[cite:unknown]\n~~~",
    "``code `[cite:unknown]` code``",
    "    [cite:unknown]\n",
])
def test_citation_binding_preserves_markdown_code(content):
    assert bind(content, []) == content


def test_even_backslashes_do_not_escape_a_citation():
    with pytest.raises(ValueError):
        bind(r"\\[cite:unknown]", [])


@pytest.mark.parametrize("citation", ["unknown/id", "unknown id"])
def test_unresolvable_citation_syntax_is_not_silently_saved(citation):
    with pytest.raises(ValueError) as failure:
        bind(f"正文[cite:{citation}]", [])
    assert failure.value.details == {"citation_ids": [citation]}

from backend.app.application.conversation_compaction import ConversationCompaction
"""Independent history/prefix summaries, followed by protected original messages."""
import json
import re

import pytest

from backend.app.agent_runtime.compaction import (
    CompactionError, CompactionSummary, ContextBudget, INITIAL_HISTORY_PROMPT,
    TURN_PREFIX_PROMPT, UPDATE_HISTORY_PROMPT, split_summary_records,
    summarize_compaction, summarize_history,
)
from backend.app.agent_runtime.model_types import AssistantModelOutput
from backend.app.application.conversation_service import ConversationService


ESTIMATE = ConversationCompaction.estimate_model_request_tokens
BUDGET = ContextBudget(6000, 500)


@pytest.mark.parametrize("prompt", [INITIAL_HISTORY_PROMPT, UPDATE_HISTORY_PROMPT])
def test_history_prompt_uses_pi_format_in_chinese(prompt):
    assert re.findall(r"^#{2,3} .+$", prompt, re.MULTILINE) == [
        "## 目标", "## 限制与偏好", "## 进度", "### 已完成", "### 进行中",
        "### 受阻", "## 关键决策", "## 下一步", "## 关键上下文",
    ]
    assert "### 已完成\n- [x] " in prompt
    assert "### 进行中\n- [ ] " in prompt
    assert "## 关键决策\n- **[决策]**：[简要原因]" in prompt
    assert "## 下一步\n1. " in prompt
    assert "## 关键上下文\n- " in prompt
    assert "精确保留文件路径、函数名和错误信息" in prompt


def test_prefix_prompt_uses_pi_format_in_chinese():
    assert re.findall(r"^#{2,3} .+$", TURN_PREFIX_PROMPT, re.MULTILINE) == [
        "## 原始请求", "## 早期进展", "## 后续步骤所需背景",
    ]
    assert "## 原始请求\n[" in TURN_PREFIX_PROMPT
    assert "## 早期进展\n- " in TURN_PREFIX_PROMPT
    assert "## 后续步骤所需背景\n- " in TURN_PREFIX_PROMPT


def record(seq, turn, role="assistant"):
    return {"seq": seq, "turn_id": turn, "message": {"role": role, "content": f"fact-{seq}"}}


def visible(item):
    return {**item["message"], "_source_seq": item["seq"], "_turn_id": item["turn_id"]}


@pytest.mark.parametrize("previous", ["", "old summary"])
@pytest.mark.parametrize("split", [False, True])
def test_four_combinations_choose_independent_prompts(previous, split):
    records = [record(1, "old", "user"), record(2, "old"), record(4, "current")]
    surface = [visible(r) for r in [*records[:2], record(3, "current", "user"), records[2], record(5, "current")]]
    selected = records if split else records[:2]
    history, prefix = split_summary_records(selected, surface, {r["seq"] for r in selected})
    assert history == records[:2]
    assert bool(prefix) is split
    calls = []

    def complete(request):
        calls.append(request)
        data = json.loads(request.messages[0]["content"])
        assert ESTIMATE(request) <= BUDGET.available
        return AssistantModelOutput(content=data["summary_kind"] + " result")

    result = summarize_compaction(history, prefix, previous_summary=previous,
                                 budget=BUDGET, estimate=ESTIMATE, complete=complete)
    assert len(calls) == (2 if split else 1)
    assert (UPDATE_HISTORY_PROMPT if previous else INITIAL_HISTORY_PROMPT) in calls[0].system
    assert json.loads(calls[0].messages[0]["content"])["previous_summary"] == previous
    if split:
        assert TURN_PREFIX_PROMPT in calls[1].system
        data = json.loads(calls[1].messages[0]["content"])
        assert data["previous_summary"] == ""
        supplied = json.loads(data["history_fragment"])
        assert supplied[0]["preserved_original_request"] is True
        assert supplied[0]["seq"] == 3  # Evidence, not a replacement source.
        assert supplied[1:] == [records[-1]]
    assert result.render().count("# 历史摘要") == 1
    assert result.render().count("# 轮次前半段摘要") == int(split)


def test_cut_in_older_turn_is_still_a_split():
    records = [record(1, "old", "user"), record(2, "old")]
    surface = [visible(r) for r in [*records, record(3, "old"), record(4, "current", "user")]]
    history, prefix = split_summary_records(records, surface, {1, 2})
    assert history == []
    assert prefix == records


def test_no_extra_prefix_when_only_protected_user_remains_before_selected_steps():
    records = [record(2, "current")]
    history, prefix = split_summary_records(records, [visible(record(1, "current", "user")), visible(records[0])], {2})
    assert history == records
    assert prefix == []


def test_prefix_only_skips_history_call_and_empty_input_skips_all_calls():
    calls = []

    def complete(request):
        calls.append(request)
        return AssistantModelOutput(content="ALT 45 U/L，2026-01-01，来源 source-1，尚待核对")

    result = summarize_compaction([], [record(1, "current")], previous_summary="",
                                 budget=BUDGET, estimate=ESTIMATE, complete=complete)
    assert result.history == ""
    assert "source-1" in result.turn_prefix
    assert len(calls) == 1 and TURN_PREFIX_PROMPT in calls[0].system
    empty = summarize_compaction([], [], previous_summary="", budget=BUDGET,
                                estimate=ESTIMATE, complete=complete)
    assert empty.render() == "" and len(calls) == 1


def test_first_history_chunk_then_update_chunks_and_prefix_stays_prefix():
    for kind in ("history", "turn_prefix"):
        calls = []

        def complete(request):
            assert ESTIMATE(request) <= 1548
            calls.append(request)
            return AssistantModelOutput(content="事实保留")

        summarize_history([{"content": "医学数值 ALT 45 U/L，来源source-1。" * 500}],
                          previous_summary="", kind=kind, budget=ContextBudget(2048, 500),
                          estimate=ESTIMATE, complete=complete)
        assert len(calls) > 1
        if kind == "history":
            assert INITIAL_HISTORY_PROMPT in calls[0].system
            assert all(UPDATE_HISTORY_PROMPT in call.system for call in calls[1:])
        else:
            assert all(TURN_PREFIX_PROMPT in call.system for call in calls)


def test_tightening_preserves_layer_boundaries():
    calls = []

    def complete(request):
        data = json.loads(request.messages[0]["content"])
        calls.append(data)
        assert data["history_fragment"] == "[]"
        assert "收紧" in data["instruction"]
        return AssistantModelOutput(content="short " + data["summary_kind"])

    result = summarize_compaction([], [], previous_summary="", budget=BUDGET,
                                 estimate=ESTIMATE, complete=complete,
                                 tighten=CompactionSummary("history facts", "prefix facts"))
    assert [call["previous_summary"] for call in calls] == ["history facts", "prefix facts"]
    assert result == CompactionSummary("short history", "short turn_prefix")


def test_prefix_failure_does_not_return_partial_history_summary():
    def complete(request):
        data = json.loads(request.messages[0]["content"])
        return AssistantModelOutput(content="history" if data["summary_kind"] == "history" else "")

    with pytest.raises(CompactionError, match="空摘要"):
        summarize_compaction([record(1, "old")], [record(3, "current")], previous_summary="",
                             budget=BUDGET, estimate=ESTIMATE, complete=complete)


def test_replaced_event_uses_surface_order_not_append_sequence_for_split():
    records = [record(20, "current")]
    surface = [visible(record(1, "current", "user")), visible(records[0]), visible(record(5, "current"))]
    history, prefix = split_summary_records(records, surface, {20})
    assert history == []
    assert prefix[-1] == records[0]
    assert prefix[0]["preserved_original_request"] is True


def test_only_previous_summary_is_updated_without_creating_prefix():
    calls = []

    def complete(request):
        calls.append(request)
        assert UPDATE_HISTORY_PROMPT in request.system
        data = json.loads(request.messages[0]["content"])
        assert data["previous_summary"] == "# 轮次前半段摘要\n已读取来源 source-1"
        assert data["history_fragment"] == "[]"
        return AssistantModelOutput(content="已读取来源 source-1")

    result = summarize_compaction([], [], previous_summary="# 轮次前半段摘要\n已读取来源 source-1",
                                 budget=BUDGET, estimate=ESTIMATE, complete=complete)
    assert result.render() == "# 历史摘要\n\n已读取来源 source-1"
    assert len(calls) == 1

import assert from "node:assert/strict";
import test, { describe } from "node:test";
import { loadModule } from "./helpers/load-module.mjs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

describe("assistant-response-presentation", () => {
  const loadTurnsModule = () => loadModule("features/conversations/conversationTurns.ts");
  const loadPresentationModule = () => loadModule("features/conversations/conversationTurnPresentation.ts", {},
    id => id.endsWith("/reportContext") ? { reportContextResourceFromRecord: record => record } : undefined);

  test("the terminal model content record is reserved for the final assistant surface", () => {
    const { terminalModelContentRecordId } = loadTurnsModule();
    const records = [
      { kind: "model", channel: "content", call_id: "call-1", record_id: "answer-1" },
      { kind: "model", channel: "tool_request", call_id: "call-1", record_id: "request-1" },
      { kind: "model", channel: "result", call_id: "call-1", record_id: "result-1", status: "completed" },
      { kind: "tool", call_id: "tool-1", record_id: "tool-1" },
      { kind: "model", channel: "reasoning", call_id: "call-2", record_id: "reasoning-2" },
      { kind: "model", channel: "content", call_id: "call-2", record_id: "answer-2" },
      { kind: "model", channel: "result", call_id: "call-2", record_id: "result-2", status: "completed" }
    ];

    assert.equal(terminalModelContentRecordId(records), "answer-2");
    assert.equal(terminalModelContentRecordId(records.slice(0, 3)), null);
    assert.equal(terminalModelContentRecordId([
      { kind: "model", channel: "content", call_id: "failed-call", record_id: "partial-answer" },
      {
        kind: "model",
        channel: "result",
        call_id: "failed-call",
        record_id: "failed-result",
        status: "failed",
        error: "provider failed"
      }
    ]), null);
  });

  test("related reports use the fixed create, delete, update, read order", () => {
    const { relatedReportResourcesForAssistant } = loadPresentationModule();
    const resources = [
      ["read", undefined],
      ["source-linked", "source_linked"],
      ["created", undefined],
      ["analysis-written", "analysis_written"],
      ["deleted", "deleted"],
      ["modified", "modified"],
      ["reclassified", "reclassified"]
    ].map(([resourceId, change]) => ({
      change,
      resource_id: resourceId,
      resource_type: "report"
    }));
    const changedEntities = resources
      .filter((resource) => resource.change)
      .map((resource) => ({
        change: resource.change,
        entity_id: resource.resource_id,
        entity_type: "report"
      }));

    const reports = relatedReportResourcesForAssistant(
      { message_id: "assistant-1", turn_id: "turn-1" },
      [{
        turn_id: "turn-1",
        result: {
          effects: {
            changed_entities: changedEntities,
            created_entities: [{ entity_id: "created", entity_type: "report" }],
            resource_refs: resources
          }
        }
      }]
    );

    assert.deepEqual(
      reports.map((report) => report.resource.resource_id),
      [
        "created",
        "deleted",
        "source-linked",
        "analysis-written",
        "modified",
        "reclassified",
        "read"
      ]
    );
  });
});

describe("conversation-tool-result-observation", () => {
  const { mergedTextToolRawOutputCallIds, modelReadableToolResultContent } = loadModule("features/conversations/toolTracePresentation.ts");

  test("text Tool Request suppresses the duplicate raw-output row", () => {
    const raw = {
      kind: "model",
      channel: "raw_output",
      call_id: "model-2",
      value: '{"type":"tool_call","name":"read_report","arguments":{"id":"LAB-1"}}'
    };
    const request = {
      kind: "model",
      channel: "tool_request",
      call_id: "model-2",
      transport_mode: "text_tool",
      name: "read_report",
      arguments: { id: "LAB-1" }
    };

    assert.deepEqual([...mergedTextToolRawOutputCallIds([raw, request])], ["model-2"]);
  });

  test("native Tool Result displays content but not unreadable provider routing fields", () => {
    const result = {
      kind: "tool",
      tool_call_id: "call-1",
      result: { type: "tool_result", output: { value: 7 }, trust: "untrusted_data_only" }
    };
    const readableContent = '{"type":"tool_result","output":{"value":7},"trust":"untrusted_data_only"}';
    const context = {
      kind: "context",
      context_type: "tool_observation",
      content: {
        role: "tool",
        tool_call_id: "call-1",
        name: "read_report",
        content: readableContent,
        provider_only: "not model-readable text"
      }
    };

    assert.equal(modelReadableToolResultContent(result, [result, context]), readableContent);
  });

  test("text Tool Result preserves the readable observation envelope", () => {
    const result = {
      kind: "tool",
      tool_call_id: "call-2",
      result: { output: { value: 8 } }
    };
    const readableContent = "TOOL_OBSERVATION\n" + JSON.stringify({
      tool_call_id: "call-2",
      name: "read_report",
      content: '{"output":{"value":8}}'
    });
    const context = {
      kind: "context",
      context_type: "tool_observation",
      content: { role: "user", content: readableContent }
    };

    assert.equal(modelReadableToolResultContent(result, [result, context]), readableContent);
  });
});

describe("conversation-citations", () => {
  function loadCitationModule() {
    return { ...loadModule("utils/markdownCitations.ts"), ...loadModule("features/conversations/citations.ts") };
  }

  test("citation projection numbers trusted sources and removes unresolved markers", () => {
    const {
      exportableCitationMarkdown,
      projectCitationMarkers,
      webCitationSourcesFromToolRecords
    } = loadCitationModule();
    const records = [
      {
        turn_id: "turn-1",
        status: "completed",
        name: "web_search",
        result: {
          output: {
            results: {
              $keys: ["citation_id", "title", "url", "domain", "snippet"],
              $rows: [
                ["abc-1", "WHO guidance", "https://www.who.int/guidance", "who.int", "Evidence"],
                ["abc-2", "FDA update", "https://www.fda.gov/update", "fda.gov", "Update"]
              ]
            }
          }
        }
      },
      {
        turn_id: "another-turn",
        status: "completed",
        name: "web_search",
        result: {
          results: [{ citation_id: "foreign-1", title: "Foreign", url: "https://example.test" }]
        }
      }
    ];
    const sources = webCitationSourcesFromToolRecords(records, "turn-1");
    const raw = "结论。[cite:abc-1][cite:abc-1] 未知。[cite:missing] `代码 [cite:abc-2]`";

    assert.deepEqual(Array.from(sources, (source) => source.citationId), ["abc-1", "abc-2"]);
    assert.equal(
      projectCitationMarkers(raw, sources).content,
      "结论。[1](#serenita-citation-abc-1)[1](#serenita-citation-abc-1) 未知。 `代码 [cite:abc-2]`"
    );
    assert.equal(
      exportableCitationMarkdown(raw, sources),
      "结论。[WHO guidance](<https://www.who.int/guidance>)[WHO guidance](<https://www.who.int/guidance>) 未知。 `代码 [cite:abc-2]`"
    );
  });
});

describe("context-compaction-display", () => {
  const load = path => loadModule(path.replace(/^src\//, ""), {}, id => {
    if (id.endsWith("/api/client")) return { isConversationMessage: record => record.kind === "user" || record.kind === "assistant" };
    if (id.endsWith("/conversationPreferences")) return {};
    if (id.endsWith("/MarkdownContent")) return { MarkdownContent: ({ content }) => React.createElement("p", null, content) };
  });

  const conversations = "src/features/conversations/";
  const display = load(`${conversations}contextCompactionDisplay`);
  const { ConversationTurnExecution } = load(`${conversations}ConversationTurnExecution`);
  const { buildConversationTurnViewModels } = load(`${conversations}conversationTurnViewModel`);
  const { contextWindowUsageFromRecords } = load(`${conversations}modelTokenUsage`);
  const { terminalModelContentRecordId } = load(`${conversations}conversationTurns`);
  const { ConversationTurnTokenUsage } = load(`${conversations}ConversationTokenUsage`);
  const streaming = load(`${conversations}streamingMessages`);

  function status(overrides = {}) {
    return {
      record_id: "compaction_1", kind: "context", turn_id: "turn-1", call_id: "compaction_1",
      context_id: "compaction_1", context_type: "compaction_status", purpose: "context_compaction",
      label: "上下文压缩", status: "running", estimated_tokens_before: 80000, target_tokens: 60000,
      time: 1000, source_event_seqs: [1], ...overrides
    };
  }
  function model(callId, channel, overrides = {}) {
    return {
      record_id: `${callId}_${channel}`, kind: "model", turn_id: "turn-1", call_id: callId,
      channel, purpose: "context_compaction", status: "completed", value: "分块摘要内容",
      source_event_seqs: [2], ...overrides
    };
  }
  function render(records) {
    return renderToStaticMarkup(React.createElement(ConversationTurnExecution, {
      active: true, activeTurnId: "turn-1", highlightedMessageId: null,
      onRegisterMessageElement() {}, records, turnRecords: records,
      visibleBaseContextRecordIds: new Set(), visibleContextTypes: new Set(), visibleToolTypes: new Set()
    }));
  }

  test("one persistent operation is visible with all input traces disabled, without chunk cards or summary leakage", () => {
    const html = render([status(), model("chunk-1", "content"), model("chunk-1", "result"),
      model("chunk-2", "reasoning"), model("chunk-2", "result"),
      status({ record_id: "checkpoint", context_type: "compacted_summary", content: "已提交摘要" })]);
    assert.equal((html.match(/上下文压缩/g) ?? []).length, 1);
    assert.match(html, /role="status">运行中/);
    assert.match(html, /80,000 → —，目标 60,000/);
    assert.doesNotMatch(html, /分块摘要内容|已提交摘要|请求工具调用|思考过程/);
    assert.match(render([status({ status: "completed", estimated_tokens_after: 52000 })]), /已完成/);
    assert.match(render([status({ status: "failed", error: { code: "INVALID_SUMMARY", message: "摘要为空" } })]), /压缩失败/);
  });

  test("expanded model records stay within their operation and never include complete model input", () => {
    const first = status();
    const second = status({ record_id: "compaction_2" });
    const records = [first, model("one", "input"), model("one", "content"), model("one", "result"),
      model("action", "result", { purpose: "agent_action" }), second, model("two", "result")];
    assert.deepEqual(display.compactionModelRecords(first, records).map((r) => r.record_id), ["one_content", "one_result"]);
    assert.deepEqual(display.compactionModelRecords(second, records).map((r) => r.record_id), ["two_result"]);
    assert.deepEqual(display.compactionModelRecords(status({ record_id: "missing" }), records), []);
    assert.equal(display.compactionTokenLabel(status({ estimated_tokens_before: NaN, target_tokens: -1 })), "估算词元 — → —，目标 —");
  });

  test("status SSE updates and replay preserve one row and all supplied estimates and errors", () => {
    const started = { session_id: "session-1", ...status() };
    let detail = streaming.startStreamingRecordInDetail({ records: [] }, started);
    assert.equal(detail.records[0].estimated_tokens_before, 80000);
    const completed = { ...started, status: "completed", estimated_tokens_after: 52000 };
    detail = streaming.completeStreamingRecordInDetail(detail, completed);
    detail = streaming.completeStreamingRecordInDetail(detail, completed);
    assert.equal(detail.records.length, 1);
    assert.equal(detail.records[0].estimated_tokens_after, 52000);
    assert.equal(render(detail.records), render([status({ status: "completed", estimated_tokens_after: 52000 })]));
    const failed = { ...started, record_id: "compaction_2", status: "running" };
    detail = streaming.startStreamingRecordInDetail(detail, failed);
    const error = { code: "INVALID_SUMMARY", message: "摘要为空" };
    detail = streaming.completeStreamingRecordInDetail(detail, { ...failed, status: "failed", error });
    assert.deepEqual(detail.records[1].error, error);
    assert.equal(detail.records.length, 2);
  });

  test("chunk usage is included once while context occupancy and final answer remain action-only", () => {
    const records = [status(),
      model("action", "content", { purpose: "agent_action", value: "最终回答" }),
      model("action", "result", { purpose: "agent_action", context_window_tokens: 100000,
        usage: { prompt_tokens: 1000, completion_tokens: 100 } }),
      model("one", "content"), model("one", "result", { usage: { prompt_tokens: 200, completion_tokens: 20 } }),
      model("two", "content"), model("two", "result", { usage: { prompt_tokens: 300, completion_tokens: 30 } })];
    const results = buildConversationTurnViewModels(records, null)[0].modelResultRecords;
    assert.equal(results.length, 3);
    const html = renderToStaticMarkup(React.createElement(ConversationTurnTokenUsage, { records: results }));
    assert.match(html, />1,500</);
    assert.match(html, />150</);
    assert.equal(contextWindowUsageFromRecords(records).usedTokens, 1100);
    assert.equal(terminalModelContentRecordId(records), "action_content");
    assert.equal(terminalModelContentRecordId(records.slice(3)), null);
  });
});

describe("context-window-usage", () => {
  const loadTypescriptModule = (path, requireModule = {}) => loadModule(path.replace(/^src\//, ""), {}, requireModule);

  function modelResult({
    callId,
    contextWindowTokens = 258_000,
    purpose = "agent_action",
    usage
  }) {
    return {
      record_id: `model_${callId}_result`,
      kind: "model",
      channel: "result",
      turn_id: "turn-1",
      call_id: callId,
      purpose,
      context_window_tokens: contextWindowTokens,
      value: { usage },
      status: "completed",
      source_event_seqs: []
    };
  }

  test("Codex-style context usage uses the latest valid real Agent call", () => {
    const { contextWindowUsageFromRecords } = loadTypescriptModule(
      "src/features/conversations/modelTokenUsage.ts"
    );
    const usage = contextWindowUsageFromRecords([
      modelResult({ callId: "first", usage: { total_tokens: 120_000 } }),
      modelResult({
        callId: "compact",
        purpose: "context_compaction",
        usage: { total_tokens: 220_000 }
      }),
      modelResult({ callId: "latest", usage: { total_tokens: 95_000 } }),
      modelResult({ callId: "missing", usage: { input_tokens: 12_000 } })
    ]);

    assert.equal(usage.usedTokens, 95_000);
    assert.equal(usage.contextWindowTokens, 258_000);
    assert.equal(Math.round(usage.percent), 37);
    assert.equal(100 - Math.round(usage.percent), 63);
  });

  test("real total tokens take priority and aliases require both input and output", () => {
    const { contextWindowUsageFromRecords } = loadTypescriptModule(
      "src/features/conversations/modelTokenUsage.ts"
    );
    const total = contextWindowUsageFromRecords([
      modelResult({
        callId: "total",
        usage: {
          total_tokens: 95_000,
          input_tokens: 80_000,
          output_tokens: 30_000,
          cached_tokens: 70_000,
          reasoning_tokens: 25_000
        }
      })
    ]);
    const aliases = contextWindowUsageFromRecords([
      modelResult({
        callId: "aliases",
        usage: { prompt_tokens: 80_000, completion_tokens: 15_000 }
      })
    ]);
    const incomplete = contextWindowUsageFromRecords([
      modelResult({ callId: "incomplete", usage: { prompt_tokens: 80_000 } })
    ]);

    assert.equal(total.usedTokens, 95_000);
    assert.equal(aliases.usedTokens, 95_000);
    assert.equal(incomplete, null);
    assert.equal(contextWindowUsageFromRecords([
      modelResult({
        callId: "invalid-total",
        usage: { total_tokens: -1, input_tokens: 80_000, output_tokens: 15_000 }
      })
    ]), null);
  });

  test("context usage rejects invalid windows and clamps billed usage to the window", () => {
    const { contextWindowUsageFromRecords } = loadTypescriptModule(
      "src/features/conversations/modelTokenUsage.ts"
    );

    assert.equal(contextWindowUsageFromRecords([
      modelResult({ callId: "zero", contextWindowTokens: 0, usage: { total_tokens: 1 } })
    ]), null);
    assert.equal(contextWindowUsageFromRecords([
      modelResult({ callId: "negative", contextWindowTokens: -1, usage: { total_tokens: 1 } })
    ]), null);
    assert.deepEqual(contextWindowUsageFromRecords([
      modelResult({ callId: "clamped", contextWindowTokens: 10_000, usage: { total_tokens: 12_000 } })
    ]), {
      contextWindowTokens: 10_000,
      percent: 100,
      usedTokens: 10_000
    });
  });

  test("conversation display preferences read and update the shared account store", () => {
    const preferences = new Map();
    const defaults = () => ({
      composer_submit_shortcut: "enter",
      base_context_display_modes: {
        system_prompt: "conversation_start",
        tool_catalog: "conversation_start",
        skill_catalog: "conversation_start",
        runtime_context: "conversation_start"
      },
      is_context_window_usage_visible: false,
      is_related_content_visible: true,
      is_token_usage_visible: false,
      visible_context_types: [],
      tool_display_types: ["model_tool_request", "tool_call"]
    });
    const preferenceModule = {
      readConversationPreferences(accountId) {
        return preferences.get(accountId) ?? defaults();
      },
      useConversationPreferences(accountId) {
        return preferences.get(accountId) ?? defaults();
      },
      writeConversationPreferences(accountId, value) {
        preferences.set(accountId, value);
      }
    };
    const settingsModule = loadTypescriptModule(
      "src/features/accountPreferences/contextAssemblyDisplay.ts",
      (specifier) => {
        if (specifier === "./conversationPreferences") return preferenceModule;
        throw new Error(`Unexpected module: ${specifier}`);
      }
    );
    const readSettings = (accountId) => settingsModule.useContextAssemblyDisplaySettings(accountId);
    const aliceDefaults = readSettings("alice");
    assert.equal(aliceDefaults.showContextWindowUsage, false);
    assert.equal(aliceDefaults.showRelatedContent, true);
    assert.equal(aliceDefaults.showTokenUsage, false);

    settingsModule.writeContextAssemblyDisplaySettings("alice", {
      ...aliceDefaults,
      showContextWindowUsage: true,
      showRelatedContent: false,
      showTokenUsage: true
    });

    assert.equal(readSettings("alice").showContextWindowUsage, true);
    assert.equal(readSettings("alice").showRelatedContent, false);
    assert.equal(readSettings("alice").showTokenUsage, true);
    assert.equal(readSettings("bob").showContextWindowUsage, false);
  });
});

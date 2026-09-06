import assert from "node:assert/strict";
import test, { describe } from "node:test";
import { loadModule } from "./helpers/load-module.mjs";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";

describe("conversation-concurrency-behavior", () => {
  const load = (name, mocks = {}) => loadModule("features/conversations/" + name, { window: globalThis }, {
    "../../utils/useActiveScope": { useActiveScope: () => () => true }, ...mocks
  });

  const streaming = load("streamingMessages.ts", {
    "../../api/client": { isConversationMessage: (r) => r.kind === "user" || r.kind === "assistant" },
    "../../utils/localTime": { localIsoString: () => "now" }
  });
  const deferred = () => {
    let resolve;
    const promise = new Promise((r) => { resolve = r; });
    return { promise, resolve };
  };
  const response = (id) => ({
    session_id: "session", stream_id: id, turn_id: id, final_assistant_message_id: "a-" + id,
    message_status: "streaming"
  });
  function harness(api, overrides = {}) {
    const activeStreamRef = { current: null };
    let detail = { session_id: "session", records: [], pending_turns: [], queued_inputs: [] };
    const options = {
      activeStreamRef, openConversation: async () => true,
      onThinkingModeChanged() {}, onTurnSettled() {}, refreshConversations: async () => {},
      setActiveStreamTurnId() {}, setCancellingTurnId() {}, setComposerError() {},
      setConversationDetail: (next) => { detail = typeof next === "function" ? next(detail) : next; },
      setConversations() {}, ...overrides
    };
    const controller = load("useConversationStreamController.ts", {
      "../../api/client": { apiClient: api },
      "../../components/StatusNotificationCenter": { showStatusNotification() {} },
      "./streamingMessages": streaming,
      "./thinking": { isAbortError: (e) => e.name === "AbortError", thinkingModeLabel: (m) => m }
    }).useConversationStreamController(options);
    return { ...controller, activeStreamRef, detail: () => detail };
  }

  test("terminal events clear the sidebar before detail refresh finishes", async () => {
    const refresh = deferred();
    let conversations = [{ session_id: "session", pending_turn_status: null },
      { session_id: "other", pending_turn_status: "streaming" }];
    const h = harness({ streamConversation: async (_session, _id, { onEvent }) => {
      onEvent({ event: "turn_completed", data: {} });
      assert.equal(conversations[0].pending_turn_status, null);
      assert.equal(conversations[1].pending_turn_status, "streaming");
    } }, {
      setConversations: (next) => { conversations = next(conversations); },
      openConversation: () => refresh.promise
    });
    const run = h.startResponseStream(response("one"));
    assert.equal(conversations[0].pending_turn_status, null);
    refresh.resolve(true);
    assert.equal(await run, "completed");
  });

  test("replay is idempotent over a newer snapshot, including emoji UTF-16 offsets", () => {
    let detail = { records: [{ record_id: "a", kind: "assistant", content: "甲🙂乙丙", status: "streaming" }] };
    detail = streaming.startStreamingRecordInDetail(detail, { record_id: "a", kind: "assistant" });
    assert.equal(detail.records[0].content, "甲🙂乙丙");
    for (const [offset, delta] of [[0, "甲🙂"], [3, "乙"], [3, "乙"], [4, "丙丁"]]) {
      detail = streaming.appendRecordDeltaToDetail(detail, "a", delta, offset);
    }
    assert.equal(detail.records[0].content, "甲🙂乙丙丁");
  });

  test("only one subscriber exists for a stream and old subscribers cannot write into replacements", async () => {
    const pending = [];
    const h = harness({ streamConversation: async (_session, id, options) => {
      const wait = deferred(); pending.push({ id, options, wait }); await wait.promise;
    } });
    const first = h.startResponseStream(response("one"));
    assert.equal(await h.startResponseStream(response("one")), "detached");
    assert.equal(pending.length, 1);
    const second = h.startResponseStream(response("two"));
    assert.equal(pending[0].options.signal.aborted, true);
    pending[0].options.onEvent({ event: "record_started", data: { kind: "assistant", record_id: "stale" } });
    assert.equal(h.detail().records.length, 0);
    pending[0].wait.resolve();
    await first;
    assert.equal(h.activeStreamRef.current.streamId, "two");
    pending[1].options.onEvent({ event: "turn_completed", data: {} });
    pending[1].wait.resolve();
    await second;
  });

  test("final answer materialization never rewinds already visible model text", () => {
    const records = [
      { record_id: "model", kind: "model", channel: "content", turn_id: "t", purpose: "agent_action", status: "completed", value: "完整正文🙂" },
      { record_id: "a", kind: "assistant", turn_id: "t", content: "", status: "streaming" }
    ];
    let detail = streaming.startStreamingRecordInDetail({ records }, { kind: "assistant", record_id: "a", turn_id: "t" });
    assert.equal(detail.records[1].content, "完整正文🙂");
    detail = streaming.appendRecordDeltaToDetail(detail, "a", "完整", 0);
    assert.equal(detail.records[1].content, "完整正文🙂");
  });

  test("terminal refresh can attach the promoted turn before the old finalizer finishes", async () => {
    const wait = deferred();
    let nextPromise;
    let h;
    h = harness({
      streamConversation: async (_session, id, { onEvent }) => {
        if (id === "one") onEvent({ event: "turn_completed", data: {} });
        else { await wait.promise; onEvent({ event: "turn_completed", data: {} }); }
      }
    }, { openConversation: async () => {
      assert.equal(h.activeStreamRef.current, null);
      if (!nextPromise) nextPromise = h.startResponseStream(response("two"));
      return true;
    } });
    await h.startResponseStream(response("one"));
    assert.equal(h.activeStreamRef.current.streamId, "two");
    wait.resolve(); await nextPromise;
    assert.equal(h.activeStreamRef.current, null);
  });

  test("a stop response arriving after navigation never reopens the old conversation", async () => {
    const wait = deferred();
    let opened = 0;
    const h = harness({ cancelTurn: () => wait.promise }, {
      openConversation: async () => { opened += 1; return true; }
    });
    h.activeStreamRef.current = { sessionId: "session", turnId: "one", streamId: "one", abortController: new AbortController() };
    const stopping = h.cancelActiveGeneration({ preservePartial: true });
    h.activeStreamRef.current = null;
    wait.resolve(); await stopping;
    assert.equal(opened, 0);
  });

  test("network loss reconnects using the same session and stream until terminal", async () => {
    const calls = [];
    const h = harness({ streamConversation: async (session, stream, { onEvent }) => {
      calls.push([session, stream]);
      if (calls.length === 1) throw new TypeError("network offline");
      onEvent({ event: "turn_completed", data: {} });
    } });
    assert.equal(await h.startResponseStream(response("one")), "completed");
    assert.deepEqual(calls, [["session", "one"], ["session", "one"]]);
  });

  const composerModule = load("ConversationComposer.tsx", {
    "../../components/icons": { ArrowUpIcon: () => null, PaperclipIcon: () => null, StopIcon: () => null },
    "../../utils/inputMethod": { isImeComposing: event => Boolean(event.nativeEvent?.isComposing) },
    "./composerSubmitShortcut": {},
    "./ContextWindowUsageIndicator": { ContextWindowUsageIndicator: () => null }
  });
  const Composer = composerModule.ConversationComposer;
  const shouldSubmitComposerFromKeyDown = composerModule.shouldSubmitComposerFromKeyDown;

  const QueuePanel = load("QueuedInputPanel.tsx", {
    "../../components/icons": Object.fromEntries(
      ["DocumentFormatIcon", "EditIcon", "GripIcon", "TrashIcon", "TurnRightIcon"]
        .map((name) => [name, () => null])
    )
  }).QueuedInputPanel;

  test("queue shows only the first attachment before exact text, with steer/edit/delete actions", () => {
    const item = {
      input_id: "q1", content: "  原文🙂\n下一行  ", context_resources: [
        { resource_type: "annotation", resource_id: "quote" },
        { resource_type: "file", resource_id: "first", original_filename: "first.png", mime_type: "image/png" },
        { resource_type: "file", resource_id: "second", original_filename: "second.png", mime_type: "image/png" }
      ]
    };
    const urls = [];
    const html = renderToStaticMarkup(createElement(QueuePanel, {
      items: [item], resourceUrl: (id) => { urls.push(id); return `/files/${id}`; }
    }));
    assert.deepEqual(urls, ["first"]);
    assert.equal((html.match(/<img /g) ?? []).length, 1);
    assert.match(html, /aria-label="附件：first\.png"/);
    assert.doesNotMatch(html, /second\.png|等候发送/);
    assert.match(html, /<img [\s\S]*<p title="  原文🙂\n下一行  ">  原文🙂\n下一行  <\/p>/);
    const actions = [...html.matchAll(/<button aria-label="([^"]+)"/g)].map((match) => match[1]);
    assert.deepEqual(actions.slice(1), ["调整方向", "编辑", "删除"]);
    assert.equal(item.context_resources.length, 3);
  });

  test("non-image attachments use one file placeholder and plain text needs no thumbnail", () => {
    for (const [resources, expectedThumbnail] of [
      [[], false],
      [[{ resource_type: "file", resource_id: "pdf", original_filename: "report.pdf", mime_type: "application/pdf" },
        { resource_type: "file", resource_id: "image", original_filename: "image.png", mime_type: "image/png" }], true]
    ]) {
      const html = renderToStaticMarkup(createElement(QueuePanel, {
        items: [{ input_id: "q", content: "", context_resources: resources }],
        resourceUrl: () => { assert.fail("only the first file is eligible for a thumbnail URL"); }
      }));
      assert.equal(html.includes('class="queued-input-thumbnail"'), expectedThumbnail);
      assert.doesNotMatch(html, /<img /);
      assert.match(html, /仅附件输入/);
    }
  });

  test("running composer has exactly one action: stop empty, send text or attachment drafts", () => {
    const props = {
      activeStreamTurnId: "one", composerText: "", conversationEnabled: true,
      composerSubmitShortcut: "enter",
      uploadedResources: [], uploadingResources: [], annotatedContexts: [],
      selectedModelFileMimeTypes: [], renderComposerModelControl: () => null,
      renderUploadedResourceChip: () => null, renderUploadingResourceChip: () => null,
      renderAnnotationContextChip: () => null
    };
    for (const [draft, expected] of [
      [{}, "停止生成"], [{ composerText: "问题" }, "发送"],
      [{ uploadedResources: [{}] }, "发送"], [{ uploadingResources: [{}] }, "发送"],
      [{ annotatedContexts: [{}] }, "发送"], [{ activeStreamTurnId: null }, "发送"]
    ]) {
      const html = renderToStaticMarkup(createElement(Composer, { ...props, ...draft }));
      assert.equal((html.match(/<button/g) ?? []).length, 1);
      assert.match(html, new RegExp(`aria-label="${expected}"`));
    }
  });

  test("composer Enter behavior follows the selected shortcut without intercepting IME or repeats", () => {
    const event = (overrides = {}) => ({
      ctrlKey: false,
      key: "Enter",
      keyCode: 13,
      metaKey: false,
      nativeEvent: { isComposing: false },
      repeat: false,
      ...overrides
    });

    assert.equal(shouldSubmitComposerFromKeyDown(event(), "enter"), true);
    assert.equal(shouldSubmitComposerFromKeyDown(event({ metaKey: true }), "enter"), false);
    assert.equal(shouldSubmitComposerFromKeyDown(event({ ctrlKey: true }), "enter"), false);
    assert.equal(shouldSubmitComposerFromKeyDown(event(), "modifier_enter"), false);
    assert.equal(shouldSubmitComposerFromKeyDown(event({ metaKey: true }), "modifier_enter"), true);
    assert.equal(shouldSubmitComposerFromKeyDown(event({ ctrlKey: true }), "modifier_enter"), true);
    assert.equal(shouldSubmitComposerFromKeyDown(event({ nativeEvent: { isComposing: true } }), "enter"), false);
    assert.equal(shouldSubmitComposerFromKeyDown(event({ repeat: true }), "enter"), false);
    assert.equal(shouldSubmitComposerFromKeyDown(event({ key: "a" }), "enter"), false);
  });
});

describe("conversation-stream-terminal", () => {
  for (const terminal of ["turn_completed", "turn_cancelled", "turn_failed"]) {
    test(`${terminal} settles without waiting for the server to close the connection`, async () => {
      let cancelled = false;
      const bytes = new TextEncoder().encode(
        'event: record_completed\ndata: {"record_id":"a"}\n\n'
        + `event: ${terminal}\ndata: {}\n\n`
      );
      const body = new ReadableStream({
        start(controller) {
          // Split the terminal frame across network chunks; leave the stream open.
          controller.enqueue(bytes.slice(0, bytes.length - 1));
          controller.enqueue(bytes.slice(bytes.length - 1));
        },
        cancel() { cancelled = true; }
      });
      const exports = loadModule("api/conversationApi.ts", {
        fetch: async () => ({ ok: true, body })
      });
      const events = [];
      await exports.streamConversation("session", "stream", {
        onEvent: (event) => events.push(event.event)
      });
      assert.deepEqual(events, ["record_completed", terminal]);
      assert.equal(cancelled, true);
      assert.equal(body.locked, false);
    });
  }
});

describe("conversation-resource-url", () => {
  test("conversation resource URLs encode Unicode spaces and reserved characters", () => {
    const { conversationContextResourceUrl } = loadModule("api/conversationApi.ts");
    const resourceId = "检查 报告-002#1%?.pdf";
    assert.equal(conversationContextResourceUrl("会话 1", resourceId),
      `/api/conversations/${encodeURIComponent("会话 1")}/context-resources/${encodeURIComponent(resourceId)}`);
  });
});

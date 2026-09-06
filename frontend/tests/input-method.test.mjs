import assert from "node:assert/strict";
import test, { describe } from "node:test";
import { loadModule } from "./helpers/load-module.mjs";

describe("input-method", () => {
  const { captureScrollPosition, focusWithoutScroll, formTextValue, formTextValues, isImeComposing,
    keepTextControlFocused, restoreScrollPosition, syncCommittedText } = loadModule("utils/inputMethod.ts", { window: undefined });

  test("text input preserves composition, committed values and scroll position", () => {
  let focusOptions = null;
  focusWithoutScroll({ focus: (options) => { focusOptions = options; } });
  assert.deepEqual(focusOptions, { preventScroll: true });

  let restoredScrollOptions = null;
  const scrollElement = {
    scrollLeft: 18,
    scrollTop: 240,
    scrollTo: (options) => { restoredScrollOptions = options; }
  };
  restoreScrollPosition(captureScrollPosition(scrollElement));
  assert.deepEqual(restoredScrollOptions, { behavior: "auto", left: 18, top: 240 });

  assert.equal(isImeComposing({ nativeEvent: { isComposing: true } }), true);
  assert.equal(isImeComposing({ isComposing: true }), true);
  assert.equal(isImeComposing({ keyCode: 229 }), true);
  assert.equal(isImeComposing({ keyCode: 13, nativeEvent: { isComposing: false } }), false);

  let prevented = false;
  keepTextControlFocused({ preventDefault: () => { prevented = true; } });
  assert.equal(prevented, true);

  let committed = "";
  syncCommittedText({ currentTarget: { value: "最终输入" } }, (value) => { committed = value; });
  assert.equal(committed, "最终输入");

  const originalInput = globalThis.HTMLInputElement;
  const originalTextarea = globalThis.HTMLTextAreaElement;
  class TestInput {
    constructor(value) { this.value = value; }
  }
  class TestTextarea {
    constructor(value) { this.value = value; }
  }
  globalThis.HTMLInputElement = TestInput;
  globalThis.HTMLTextAreaElement = TestTextarea;
  try {
    const controls = new Map([
      ["message", new TestTextarea("刚刚提交的中文")],
      ["title", new TestInput("当前标题")]
    ]);
    const form = { elements: { namedItem: (name) => controls.get(name) ?? null } };
    assert.equal(formTextValue(form, "message", "旧内容"), "刚刚提交的中文");
    assert.equal(formTextValue(form, "missing", "回退内容"), "回退内容");
    assert.deepEqual(
      formTextValues(form, { message: "旧内容", title: "旧标题", other: "保留" }),
      { message: "刚刚提交的中文", title: "当前标题", other: "保留" }
    );
  } finally {
    globalThis.HTMLInputElement = originalInput;
    globalThis.HTMLTextAreaElement = originalTextarea;
  }

  });
});

describe("clipboard", () => {
  const { copyTextToClipboard } = loadModule("utils/clipboard.ts");

  test("copyTextToClipboard uses the asynchronous Clipboard API", async () => {
    const writes = [];
    await copyTextToClipboard("带引用的正文", {
      navigatorObject: { clipboard: { writeText: async (text) => writes.push(text) } }
    });
    assert.deepEqual(writes, ["带引用的正文"]);
  });

  test("copyTextToClipboard falls back to the document copy command", async () => {
    let copiedValue = "";
    const textarea = {
      value: "",
      style: {},
      focus() {},
      select() { copiedValue = this.value; },
      setSelectionRange() {},
      setAttribute() {},
      remove() {}
    };
    const documentObject = {
      activeElement: null,
      body: { append() {} },
      createElement: () => textarea,
      execCommand: (command) => command === "copy",
      getSelection: () => ({ rangeCount: 0 })
    };

    await copyTextToClipboard("降级复制内容", {
      documentObject,
      navigatorObject: { clipboard: { writeText: async () => { throw new Error("denied"); } } }
    });
    assert.equal(copiedValue, "降级复制内容");
  });

  test("copyTextToClipboard reports an unavailable clipboard", async () => {
    await assert.rejects(
      copyTextToClipboard("无法复制", { navigatorObject: {} }),
      /无法访问剪贴板/
    );
  });
});

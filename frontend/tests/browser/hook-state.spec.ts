import { expect, test } from "@playwright/test";

test("report upload retry retains successful resources and does not submit a batch from a departed page", async ({ page }) => {
  await page.goto("/tests/fixtures/hook-state.html");
  const results = await page.evaluate(async () => {
    const { mountHook, act } = await import("../fixtures/hook-state");
    const { useReportUpload } = await import("../../src/features/reports/useReportUpload");
    type Options = Parameters<typeof useReportUpload>[0];
    const files = [new File(["a"], "a.png", { type: "image/png" }), new File(["b"], "b.png", { type: "image/png" })];
    const uploads: string[][] = [], submissions: unknown[] = [], errors: string[][] = [];
    let release: (() => void) | undefined;
    const options: Options = {
      accountId: "account", route: "/reports", memberId: "member-a", currentSessionId: null,
      canEdit: true, unavailableReason: "", mimeTypes: ["image/png"], setUploadErrors: value => errors.push(value),
      uploadFiles: async (batch, _session, callbacks) => {
        uploads.push(batch.map(file => file.name));
        if (uploads.length === 3) await new Promise<void>(resolve => { release = resolve; });
        for (const file of batch) {
          if (uploads.length === 1 && file.name === "b.png") throw new Error("second upload failed");
          const resource = { resource_id: file.name, original_filename: file.name } as Parameters<NonNullable<NonNullable<typeof callbacks>["onUploaded"]>>[1];
          callbacks?.onUploaded?.("upload-session", resource);
        }
        return { sessionId: "upload-session", resources: [] };
      },
      submitMessage: async input => {
        submissions.push({ memberId: input.memberId, sessionId: input.sessionId, resources: input.contextResources });
        input.onSubmitted?.();
        return undefined;
      }
    };
    const h = mountHook(useReportUpload, options);
    await act(async () => h.current.startReportUpload(files));
    const partial = { uploaded: h.current.uploadedReportNames, remaining: h.current.remainingReportFiles.map(file => file.name), submissions: submissions.length };
    await act(async () => h.current.startReportUpload(h.current.remainingReportFiles));
    const afterRetry = { uploaded: h.current.uploadedReportNames, remaining: h.current.remainingReportFiles.length };
    let pending!: Promise<void>;
    act(() => { pending = h.current.startReportUpload(files); });
    h.render({ ...options, memberId: "member-b" });
    h.render(options);
    await act(async () => { release!(); await pending; });
    h.unmount();
    return { uploads, submissions, partial, afterRetry, errors: errors.flat() };
  });
  expect(results.uploads).toEqual([["a.png", "b.png"], ["b.png"], ["a.png", "b.png"]]);
  expect(results.partial).toEqual({ uploaded: ["a.png"], remaining: ["b.png"], submissions: 0 });
  expect(results.afterRetry).toEqual({ uploaded: [], remaining: 0 });
  expect(results.errors).toContain("second upload failed");
  expect(results.submissions).toEqual([{ memberId: "member-a", sessionId: "upload-session", resources: [
    { resource_type: "file", resource_id: "a.png", original_filename: "a.png" },
    { resource_type: "file", resource_id: "b.png", original_filename: "b.png" }
  ] }]);
});

test("member selection and request ownership survive A-B-A renders and unmount", async ({ page }) => {
  await page.goto("/tests/fixtures/hook-state.html");
  const results = await page.evaluate(async () => {
    const { mountHook, act } = await import("../fixtures/hook-state");
    const { useReportSelection } = await import("../../src/features/reports/useReportSelection");
    const { useActiveScope } = await import("../../src/utils/useActiveScope");
    const h = mountHook((member: string) => ({ selection: useReportSelection(member), current: useActiveScope(member) }), "a");
    const a = h.current;
    act(() => a.selection[1](new Set(["same-report"])));
    const results = [[...h.current.selection[0]], a.current()];
    h.render("b");
    act(() => a.selection[1](new Set(["late-report"])));
    results.push([...h.current.selection[0]], a.current());
    act(() => h.current.selection[1](new Set(["same-report"])));
    results.push([...h.current.selection[0]]);
    h.render("a");
    results.push([...h.current.selection[0]], a.current(), h.current.current());
    const latest = h.current.current;
    h.unmount(); results.push(latest());
    return results;
  });
  expect(results).toEqual([["same-report"], true, [], false, ["same-report"], [], false, true, false]);
});

test("attachment capabilities reject stale models, retry failures and invalidate vision changes", async ({ page }) => {
  await page.goto("/tests/fixtures/hook-state.html");
  const results = await page.evaluate(async () => {
    const { mountHook, act } = await import("../fixtures/hook-state");
    const { useAttachmentCapabilities } = await import("../../src/features/conversations/useAttachmentCapabilities");
    const { apiClient } = await import("../fixtures/hook-state");
    const pending: { resolve: (value: Awaited<ReturnType<typeof apiClient.fetchAttachmentCapabilities>>) => void; reject: (error: Error) => void }[] = [];
    apiClient.fetchAttachmentCapabilities = () => new Promise((resolve, reject) => pending.push({ resolve, reject }));
    type Model = NonNullable<Parameters<typeof useAttachmentCapabilities>[0]>;
    const a = { model_id: "a" } as Model, b = { model_id: "b" } as Model;
    const h = mountHook(([model, vision]: Parameters<typeof useAttachmentCapabilities>) => useAttachmentCapabilities(model, vision), [a, null]);
    const results: unknown[] = [h.current.attachmentCapabilitiesReady];
    h.render([b, null]);
    await act(async () => pending[1].resolve({ model_id: "b", file_mime_types: ["audio/wav"] }));
    await act(async () => pending[0].resolve({ model_id: "a", file_mime_types: ["image/png"] }));
    results.push(h.current.selectedModelFileMimeTypes);
    h.render([a, null]);
    await act(async () => pending[2].reject(new Error("offline")));
    results.push(h.current.attachmentCapabilitiesReady, h.current.attachmentCapabilitiesError);
    act(() => h.current.retryAttachmentCapabilities());
    results.push(h.current.attachmentCapabilitiesReady);
    await act(async () => pending[3].resolve({ model_id: "a", file_mime_types: [] }));
    results.push(h.current.attachmentCapabilitiesReady);
    h.render([a, b]); results.push(h.current.attachmentCapabilitiesReady);
    await act(async () => pending[4].resolve({ model_id: "a", file_mime_types: ["application/pdf"] }));
    results.push(h.current.selectedModelFileMimeTypes);
    h.unmount(); return results;
  });
  expect(results).toEqual([false, ["audio/wav"], false, "offline", false, true, false, ["application/pdf"]]);
});

test("context menus support keyboard focus, viewport boundaries, catalog changes and removed entries", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 700 });
  await page.goto("/tests/fixtures/hook-state.html#menu");
  const row = page.locator("#row"), trigger = page.getByRole("button", { name: "打开报告", exact: true });
  const menu = page.getByRole("menu");
  for (const key of ["Shift+F10", "ContextMenu"]) {
    await trigger.focus(); await trigger.press(key);
    await expect(menu).toBeVisible();
    await expect(page.getByRole("menuitem")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(menu).toHaveCount(0); await expect(trigger).toBeFocused();
  }
  await row.evaluate(node => node.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 389, clientY: 699, button: 2 })));
  await expect(menu).toBeVisible();
  const bounds = (await menu.boundingBox())!;
  expect(bounds.x).toBeGreaterThanOrEqual(0); expect(bounds.x + bounds.width).toBeLessThanOrEqual(390);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(700);
  await page.getByRole("button", { name: "切换目录" }).click(); await expect(menu).toHaveCount(0);
  await page.getByRole("button", { name: "切换启用" }).click();
  await row.evaluate(node => node.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true }))); await expect(menu).toHaveCount(0);
  await page.getByRole("button", { name: "切换启用" }).click();
  await page.getByRole("button", { name: "移除入口" }).click();
  await row.evaluate(node => node.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true }))); await expect(menu).toHaveCount(0);
});

test("touch long press respects its threshold, cancellation and one suppressed release click", async ({ page }) => {
  await page.clock.install();
  await page.goto("/tests/fixtures/hook-state.html#menu");
  const row = page.locator("#row"), menu = page.getByRole("menu");
  await expect(page.getByRole("button", { name: "打开报告", exact: true })).toBeVisible();
  const pointer = { pointerType: "touch", isPrimary: true, button: 0, pointerId: 1, clientX: 40, clientY: 80 };
  for (const action of ["move", "up", "cancel", "ancestor", "mouse", "disabled"]) {
    if (action === "disabled") await page.getByRole("button", { name: "切换启用" }).click();
    await row.dispatchEvent("pointerdown", { ...pointer, pointerType: action === "mouse" ? "mouse" : "touch" });
    await page.clock.runFor(200);
    if (action === "move") await row.dispatchEvent("pointermove", { ...pointer, clientX: 49 });
    if (action === "up" || action === "cancel") await row.dispatchEvent(action === "up" ? "pointerup" : "pointercancel", pointer);
    if (action === "ancestor") await page.locator("#ancestor").dispatchEvent("scroll");
    await page.clock.runFor(500); await expect(menu).toHaveCount(0);
    if (action === "disabled") await page.getByRole("button", { name: "切换启用" }).click();
  }
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 10000));
  await row.dispatchEvent("pointerdown", pointer);
  await page.locator("#unrelated").dispatchEvent("scroll");
  await page.clock.runFor(499); await expect(menu).toHaveCount(0);
  await page.clock.runFor(1); await expect(menu).toBeVisible();
  await page.clock.runFor(2000);
  await row.dispatchEvent("pointerup", pointer);
  const trigger = page.getByRole("button", { name: "打开报告", exact: true });
  await trigger.dispatchEvent("click"); await expect(page.getByLabel("打开次数")).toHaveText("0");
  await trigger.dispatchEvent("click"); await expect(page.getByLabel("打开次数")).toHaveText("1");
});

test("conversation lifecycle loads models during a slow list request and preserves drafts on same-session refresh", async ({ page }) => {
  await page.goto("/tests/fixtures/hook-state.html");
  const results = await page.evaluate(async () => {
    const { mountHook, act } = await import("../fixtures/hook-state");
    const { useConversationLifecycle } = await import("../../src/features/conversations/useConversationLifecycle");
    const { apiClient } = await import("../fixtures/hook-state");
    type Options = Parameters<typeof useConversationLifecycle>[0];
    let finish!: (value: Awaited<ReturnType<typeof apiClient.fetchConversations>>) => void;
    apiClient.fetchConversations = () => new Promise(resolve => { finish = resolve; });
    apiClient.fetchFavorites = async () => ({ favorites: [], has_more: false, next_cursor: null });
    apiClient.fetchModels = async () => ({ models: [] });
    apiClient.fetchModelDefaults = async () => ({ defaults: { chat: null, compact: null, title: null, vision_parse: null } });
    const detail: Awaited<ReturnType<typeof apiClient.getConversation>> = {
      session_id: "session", records: [], pending_turns: [], queued_inputs: [], member_id: null,
      member_name: null, access_state: "available", title: "会话", parent_session_id: null,
      seed_event_count: 0, fork_available: true, resource_states: []
    };
    apiClient.getConversation = async () => detail;
    let modelReady = false, cleared = 0;
    const base: Partial<Options> = {
      route: "/", activeStreamRef: { current: null }, conversationRequestSeqRef: { current: 0 },
      currentSessionId: null, conversationDetail: null,
      setModelCatalog: catalog => { if (typeof catalog !== "function") modelReady = catalog.status === "ready"; },
      setComposerText: () => { cleared++; },
      refreshConversations: async () => { await apiClient.fetchConversations(); }
    };
    const options = new Proxy(base, { get: (target, key) => key in target ? target[key as keyof Options] : () => {} }) as Options;
    const h = mountHook(useConversationLifecycle, options);
    await act(async () => {});
    const readyBeforeList = modelReady;
    const staleCallback = h.current.openConversation;
    base.currentSessionId = "session"; base.conversationDetail = detail;
    h.render(options);
    let opened = false;
    await act(async () => { opened = await staleCallback("session"); });
    await act(async () => finish({ sessions: [], has_more: false, next_cursor: null }));
    h.unmount(); return { readyBeforeList, opened, cleared };
  });
  expect(results).toEqual({ readyBeforeList: true, opened: true, cleared: 0 });
});

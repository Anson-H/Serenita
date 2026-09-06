import { expect, test, type Page } from "@playwright/test";

const profile = {
  availability: "available" as const,
  supports_text: true,
  file_mime_types: ["image/png"],
  supports_tool_calling: true
};

const model = {
  model_id: "test:model",
  provider_id: "test",
  remote_model_id: "model",
  model_name: "测试模型",
  supports_text: true,
  file_mime_types: ["image/png"],
  thinking_modes: ["default"],
  supports_tool_calling: true,
  capability_profiles: {
    default_state: "non_thinking" as const,
    non_thinking: profile,
    thinking: { ...profile, availability: "unavailable" as const }
  },
  context_window_tokens: 128_000,
  max_output_tokens: 8_192
};

async function mockWorkspace(page: Page, withMessage = false) {
  let uploadAttempts = 0;
  const uploadBodies: string[] = [];
  await page.route(url => url.pathname.startsWith("/api/"), async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.slice(4);
    const json = (value: unknown, status = 200) => route.fulfill({ json: value, status });
    if (path === "/conversations/attachment-capabilities") return json({ model_id: new URL(route.request().url()).searchParams.get("model_id"), file_mime_types: ["image/jpeg", "image/png", "application/pdf"] });
    if (path === "/auth/session") {
      return json({
        authenticated: true,
        account_id: "upload-test-account",
        account: "upload-test",
        account_name: "上传测试",
        expires_at: "2099-01-01T00:00:00+08:00"
      });
    }
    if (path === "/members/access-events") {
      return route.fulfill({ body: "retry: 60000\n\n", contentType: "text/event-stream" });
    }
    if (path === "/members") {
      return json({
        access_revision: 1,
        default_member_id: null,
        initial_member_id: null,
        last_member_id: null,
        members: [],
        startup_mode: "last_used"
      });
    }
    if (path === "/conversations") {
      return json({ sessions: [], has_more: false, next_cursor: null });
    }
    if (path === "/conversations/session-1") {
      return json({
        member_id: null,
        member_name: null,
        access_state: "available",
        session_id: "session-1",
        title: "新聊天",
        parent_session_id: null,
        seed_event_count: 0,
        fork_available: false,
        pending_turns: [],
        queued_inputs: [],
        resource_states: [],
        records: withMessage ? [{
          kind: "assistant", role: "assistant", record_id: "answer", message_id: "answer",
          turn_id: "turn-1", parent_message_id: null, content: "用于检查注释条栏的文字。",
          status: "completed", created_at: "2026-09-06T00:00:00+08:00"
        }] : []
      });
    }
    if (path === "/favorites") {
      return json({ favorites: [], has_more: false, next_cursor: null });
    }
    if (path === "/models") return json({ models: [model] });
    if (path === "/model-providers") return json({ providers: [] });
    if (path === "/model-access-settings") {
      return json({
        defaults: { chat: model, compact: null, title: null, vision_parse: null }
      });
    }
    if (path === "/account-settings/conversation-preferences") {
      return json({
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
    }
    if (path === "/account-settings/web-access") {
      return json({ is_enabled: false, active_provider_id: "exa", providers: [] });
    }
    if (path === "/conversations/context-resources") {
      uploadAttempts += 1;
      uploadBodies.push(request.postDataBuffer()?.toString("utf8") ?? "");
      const baseResource = {
        resource_id: "报告.png",
        original_filename: "报告.png",
        mime_type: "image/png",
        size_bytes: 4,
        relative_path: "conversations/attachments/session-1/报告.png",
        sha256: "upload-sha",
        expires_at: "2099-01-02T00:00:00+08:00"
      };
      if (uploadAttempts === 1) {
        return json({
          session_id: "session-1",
          resource: { ...baseResource, status: "uploaded", usage_status: "pending" }
        });
      }
      return json({
        session_id: "session-1",
        resource: {
          ...baseResource,
          storage_status: "ready",
          lifecycle_status: "pending"
        }
      });
    }
    return json({ detail: { message: `未模拟 ${path}` } }, 404);
  });
  return {
    uploadAttempts: () => uploadAttempts,
    uploadBodies
  };
}

test("invalid upload response clears progress and the same file can be selected again", async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.goto("/");
  const fileInput = page.locator('input[type="file"][aria-label="附加文件"]');
  await expect(fileInput).toHaveCount(1);
  const file = {
    name: "报告.png",
    mimeType: "image/png",
    buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47])
  };

  await fileInput.setInputFiles(file);

  await expect(page.getByRole("alert")).toContainText("上传响应无效。");
  await expect(page.getByLabel("正在上传：报告.png")).toHaveCount(0);

  await fileInput.setInputFiles(file);

  await expect(page.getByRole("link", { name: "打开附件：报告.png" })).toBeVisible();
  await expect(page.getByLabel("正在上传：报告.png")).toHaveCount(0);
  expect(state.uploadAttempts()).toBe(2);
  expect(state.uploadBodies).toHaveLength(2);
  for (const body of state.uploadBodies) {
    expect(body).not.toContain('name="upload_id"');
  }
});

test("annotation bar preserves expanded state while accessory hover owns only its button", async ({ page }) => {
  await mockWorkspace(page, true);
  await page.goto("/chat/session-1");
  const message = page.getByText("用于检查注释条栏的文字。", { exact: true });
  await expect(message).toBeVisible();
  await message.evaluate(element => {
    const range = document.createRange();
    range.selectNodeContents(element);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    element.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
  });
  await page.getByRole("button", { name: "添加到聊天" }).click();
  const primary = page.getByRole("button", { name: "预览发送给模型的 1 条注释" });
  const remove = page.getByRole("button", { name: "移除全部注释" });
  const bar = primary.locator("..");
  await page.mouse.move(0, 0);
  const base = await bar.evaluate(el => getComputedStyle(el).backgroundColor);
  await primary.hover();
  await expect.poll(() => bar.evaluate(el => getComputedStyle(el).backgroundColor)).not.toBe(base);
  await remove.hover();
  await expect(bar).toHaveCSS("background-color", base);
  await primary.click();
  await expect(primary).toHaveAttribute("aria-expanded", "true");
  await bar.evaluate(async el => {
    await Promise.all(el.getAnimations().map(animation => animation.finished));
  });
  const expanded = await bar.evaluate(el => getComputedStyle(el).backgroundColor);
  expect(expanded).not.toBe(base);
  await remove.hover();
  await expect(bar).toHaveCSS("background-color", expanded);
  await page.keyboard.press("Escape");
  await expect(primary).toHaveAttribute("aria-expanded", "false");
  await expect(bar).toHaveCSS("background-color", base);
  await remove.click();
  await expect(primary).toHaveCount(0);
});

test("attachment bar transfers hover and focus between its primary and accessory action", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/");
  const fileInput = page.locator('input[type="file"][aria-label="附加文件"]');
  const file = { name: "报告.png", mimeType: "image/png", buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47]) };
  await fileInput.setInputFiles(file);
  await expect(page.getByRole("alert")).toContainText("上传响应无效。");
  await fileInput.setInputFiles(file);
  const primary = page.getByRole("link", { name: "打开附件：报告.png" });
  const remove = page.getByRole("button", { name: "移除附件：报告.png" });
  const bar = primary.locator("..");
  await expect(primary).toBeVisible();
  await page.mouse.move(0, 0);
  const base = await bar.evaluate(el => getComputedStyle(el).backgroundColor);
  const removeBase = await remove.evaluate(el => getComputedStyle(el).backgroundColor);
  await primary.hover();
  await expect.poll(() => bar.evaluate(el => getComputedStyle(el).backgroundColor)).not.toBe(base);
  await remove.hover();
  await expect(bar).toHaveCSS("background-color", base);
  await expect.poll(() => remove.evaluate(el => getComputedStyle(el).backgroundColor)).not.toBe(removeBase);
  await primary.hover();
  await expect.poll(() => bar.evaluate(el => getComputedStyle(el).backgroundColor)).not.toBe(base);
  await primary.focus();
  await page.keyboard.press("Tab");
  await expect(remove).toBeFocused();
  await expect(remove).toHaveAttribute("data-keyboard-focus", "outset");
  await expect(bar).not.toHaveAttribute("data-keyboard-focus");
  await page.keyboard.press("Shift+Tab");
  await expect(primary).toBeFocused();
  await expect(bar).toHaveAttribute("data-keyboard-focus", "inset");
  await expect(primary).not.toHaveAttribute("data-keyboard-focus");
  await remove.click();
  await expect(primary).toHaveCount(0);
});

test("attachment capability failures keep text and uploaded drafts while retry restores the input", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/");
  const fileInput = page.locator('input[type="file"][aria-label="附加文件"]');
  const file = { name: "报告.png", mimeType: "image/png", buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47]) };
  await fileInput.setInputFiles(file);
  await expect(page.getByRole("alert")).toContainText("上传响应无效。");
  await fileInput.setInputFiles(file);
  await expect(page.getByRole("link", { name: "打开附件：报告.png" })).toBeVisible();
  const composer = page.locator(".conversation-composer textarea");
  await composer.fill("保留我的草稿");
  let failed = true;
  await page.route("**/api/conversations/attachment-capabilities?*", route => route.fulfill({
    status: failed ? 503 : 200,
    json: failed ? { detail: { code: "TEMPORARY_ERROR", message: "能力查询暂不可用" } }
      : { model_id: "test:model", file_mime_types: ["image/png"] }
  }));
  await page.locator(".composer-model-trigger").click();
  await expect(page.getByRole("button", { name: "重试附件能力" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(composer).toHaveValue("保留我的草稿");
  await expect(page.getByRole("link", { name: "打开附件：报告.png" })).toBeVisible();
  failed = false;
  await page.getByRole("button", { name: "重试附件能力" }).click();
  await expect(fileInput).toHaveAttribute("accept", "image/png");
  await expect(page.getByRole("link", { name: "打开附件：报告.png" })).toBeVisible();
});
